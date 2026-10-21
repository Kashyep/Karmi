// R1 perf baseline. Host-VM widget-test measurements (NOT device frame timings).
// Run: cd mobile && flutter test test/perf/chat_perf_test.dart --reporter expanded
// Emits lines prefixed `PERF ` for capture into docs/release1/perf/BASELINE.md.
import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import '../support/fake_backend.dart';
import '../support/harness.dart';

double _median(List<double> xs) {
  final s = [...xs]..sort();
  return s[s.length ~/ 2];
}

double _p95(List<double> xs) {
  final s = [...xs]..sort();
  return s[math.min(s.length - 1, (s.length * 0.95).ceil() - 1)];
}

void _perf(String line) => print('PERF $line');

FakeBackend _numberedReplies() {
  var n = 0;
  return FakeBackend.healthy()
    ..on('POST', '/v1/messages', (_) {
      n += 1;
      return jsonResponse({
        ...messageJson('ACCEPT', response: 'Reply $n: a short streamed-style answer about the plan.'),
        'run_id': 'run-$n',
      });
    });
}

Future<void> _send(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.tap(find.byTooltip('Send message'));
  await tester.pump();
  await settle(tester);
}

void main() {
  testWidgets('PERF cold start proxy: pumpApp to settled first frame (host VM)', (
    tester,
  ) async {
    final samples = <double>[];
    for (var i = 0; i < 7; i++) {
      final sw = Stopwatch()..start();
      await pumpApp(tester);
      sw.stop();
      samples.add(sw.elapsedMicroseconds / 1000);
      await tester.pumpWidget(const SizedBox.shrink());
    }
    _perf('cold_start_pumpApp_ms median=${_median(samples).toStringAsFixed(1)} '
        'p95=${_p95(samples).toStringAsFixed(1)} n=${samples.length}');
  });

  testWidgets('PERF chat list scroll frame build time, 40-entry transcript (host VM)', (
    tester,
  ) async {
    await pumpApp(tester, backend: _numberedReplies());
    for (var i = 0; i < 20; i++) {
      await _send(tester, 'Question $i about my study plan');
    }
    final list = find.byType(ListView).last;
    final frames = <double>[];
    final gesture = await tester.startGesture(tester.getCenter(list));
    for (var i = 0; i < 90; i++) {
      await gesture.moveBy(const Offset(0, -35));
      final sw = Stopwatch()..start();
      await tester.pump(const Duration(milliseconds: 16));
      sw.stop();
      frames.add(sw.elapsedMicroseconds / 1000);
    }
    await gesture.up();
    await settle(tester);
    _perf('chat_scroll_frame_pump_ms median=${_median(frames).toStringAsFixed(2)} '
        'p95=${_p95(frames).toStringAsFixed(2)} frames=${frames.length} '
        'note=build+layout+paint on host VM, no raster/GPU');
  });

  testWidgets('PERF chat rebuild count per delta (debugPrintRebuildDirtyWidgets, host VM)', (
    tester,
  ) async {
    final lines = <String>[];
    final original = debugPrint;
    final saved = debugPrintRebuildDirtyWidgets;
    debugPrint = (String? message, {int? wrapWidth}) {
      if (message != null) lines.add(message);
    };
    debugPrintRebuildDirtyWidgets = true;
    try {
      await pumpApp(tester, backend: _numberedReplies());
      final counts = <int>[];
      for (var i = 0; i < 5; i++) {
        lines.clear();
        await _send(tester, 'Delta $i');
        counts.add(lines.where((l) => l.startsWith('Rebuilding') && (l.contains('ChatScreen') || l.contains('MessageBubble') || l.contains('_UserRow') || l.contains('Composer'))).length);
      }
      _perf('chat_screen_subtree_rebuilds_per_send median=${_median([for (final c in counts) c.toDouble()]).toStringAsFixed(0)} '
          'samples=${counts.join(',')} note=filtered debugPrintRebuildDirtyWidgets lines naming ChatScreen/MessageBubble/_UserRow/Composer; all-widget total was 398-836 per send (grew with transcript)');
    } finally {
      debugPrint = original;
      debugPrintRebuildDirtyWidgets = saved;
    }
  });
}
