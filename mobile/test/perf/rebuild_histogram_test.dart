// R1 perf attribution: per-widget-type rebuild histogram inside the ChatScreen
// subtree, per send and per 200-delta burst. Host-VM proxy. Uses the
// framework's debugOnRebuildDirtyWidget hook (no log parsing).
// Run: cd mobile && flutter test test/perf/rebuild_histogram_test.dart --reporter expanded
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import '../support/fake_backend.dart';
import '../support/harness.dart';

const int _deltaCount = 200;

// ignore: avoid_print
void _perf(String line) => print('PERF $line');

bool _inChatScreen(Element element) {
  if (element.widget.runtimeType.toString() == 'ChatScreen') return true;
  var found = false;
  element.visitAncestorElements((ancestor) {
    if (ancestor.widget.runtimeType.toString() == 'ChatScreen') {
      found = true;
      return false;
    }
    return true;
  });
  return found;
}

FakeBackend _numberedReplies() {
  var n = 0;
  return FakeBackend.healthy()
    ..on('POST', '/v1/chat/stream', (_) {
      n += 1;
      final sse = 'event: run.started\n'
          'data: {"run_id":"run-$n","conversation_id":"conv-1","user_message_id":"msg-u-$n","assistant_message_id":"msg-a-$n","seq":0}\n\n'
          'id: 1\n'
          'event: message.delta\n'
          'data: {"text":"Reply $n: a short streamed-style answer about the plan."}\n\n'
          'event: run.finished\n'
          'data: {"finish_reason":"stop","outcome":"success"}\n\n';
      return http.Response(
        sse,
        200,
        headers: {'content-type': 'text/event-stream'},
      );
    });
}

FakeBackend _streamingBackend() {
  final tokens = [for (var i = 1; i <= _deltaCount; i++) 'tok$i '];
  final sse = StringBuffer()
    ..write('event: run.started\n')
    ..write(
      'data: {"run_id":"run-1","conversation_id":"conv-1",'
      '"user_message_id":"msg-u-1","assistant_message_id":"msg-a-1","seq":0}\n\n',
    );
  for (var i = 0; i < tokens.length; i++) {
    sse
      ..write('id: ${i + 1}\n')
      ..write('event: message.delta\n')
      ..write('data: {"text":"${tokens[i]}"}\n\n');
  }
  sse
    ..write('event: run.finished\n')
    ..write('data: {"finish_reason":"stop","outcome":"success"}\n\n');
  final body = sse.toString();
  return FakeBackend.healthy()
    ..on(
      'POST',
      '/v1/chat/stream',
      (_) => http.Response(
        body,
        200,
        headers: {'content-type': 'text/event-stream'},
      ),
    );
}

const _gateNames = ['ChatScreen', 'MessageBubble', '_UserRow', 'Composer'];

// Gate metric, computed exactly as the log-based filter in chat_perf_test and
// stream_perf_test does: a 'Rebuilding <element>' line (not first build) whose
// element description names one of the gate widgets. Whole tree, no subtree filter.
int _gateCount = 0;
final Set<Element> _seen = <Element>{};
final Map<String, int> _gateDesc = {};

void _dump(String label, Map<String, int> hist) {
  _perf('$label gate_filtered=$_gateCount');
  for (final e in _gateDesc.entries) {
    _perf('$label gate_desc ${e.value} ${e.key}');
  }
  _gateDesc.clear();
  _gateCount = 0;
  final total = hist.values.fold<int>(0, (a, b) => a + b);
  final entries = hist.entries.toList()
    ..sort((a, b) => b.value.compareTo(a.value));
  _perf('$label total=$total');
  for (final e in entries) {
    _perf('$label   ${e.value.toString().padLeft(5)} ${e.key}');
  }
}

Future<void> _send(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.tap(find.byTooltip('Send message'));
  await tester.pump();
  await settle(tester);
}

void main() {
  testWidgets('PERF histogram per send (ChatScreen subtree, host VM)', (
    tester,
  ) async {
    final hist = <String, int>{};
    final saved = debugOnRebuildDirtyWidget;
    debugOnRebuildDirtyWidget = (element, builtOnce) {
      // The framework's builtOnce flag is only maintained while debugPrintRebuildDirtyWidgets
      // is on, so track first builds ourselves: first rebuild() per element = 'Building'.
      if (!_seen.add(element)) {
        if (_gateNames.any(element.toString().contains)) {
          _gateCount += 1;
          final key = '${element.widget.runtimeType} inChat=${_inChatScreen(element)} desc=${element.toString()}';
          _gateDesc[key] = (_gateDesc[key] ?? 0) + 1;
        }
      } else {
        return;
      }
      if (!_inChatScreen(element)) return;
      final name = element.widget.runtimeType.toString();
      hist[name] = (hist[name] ?? 0) + 1;
    };
    try {
      await pumpApp(tester, backend: _numberedReplies());
      // Warm-up send so the transcript-independent first-send cost is excluded.
      await _send(tester, 'Warm up');
      for (var i = 0; i < 5; i++) {
        hist.clear();
        _gateCount = 0;
        await _send(tester, 'Delta $i');
        _dump('send_$i', hist);
      }
    } finally {
      debugOnRebuildDirtyWidget = saved;
    }
  });

  testWidgets('PERF histogram per 200-delta burst (ChatScreen subtree, host VM)', (
    tester,
  ) async {
    final hist = <String, int>{};
    final saved = debugOnRebuildDirtyWidget;
    debugOnRebuildDirtyWidget = (element, builtOnce) {
      // The framework's builtOnce flag is only maintained while debugPrintRebuildDirtyWidgets
      // is on, so track first builds ourselves: first rebuild() per element = 'Building'.
      if (!_seen.add(element)) {
        if (_gateNames.any(element.toString().contains)) {
          _gateCount += 1;
          final key = '${element.widget.runtimeType} inChat=${_inChatScreen(element)} desc=${element.toString()}';
          _gateDesc[key] = (_gateDesc[key] ?? 0) + 1;
        }
      } else {
        return;
      }
      if (!_inChatScreen(element)) return;
      final name = element.widget.runtimeType.toString();
      hist[name] = (hist[name] ?? 0) + 1;
    };
    try {
      await pumpApp(tester, backend: _streamingBackend());
      hist.clear();
      _gateCount = 0;
      _seen.clear();
      await tester.enterText(find.byType(TextField), 'Stream the plan');
      await tester.pump();
      await tester.tap(find.byTooltip('Send message'));
      for (var i = 0; i < 200; i++) {
        await tester.pump(const Duration(milliseconds: 16));
        await tester.runAsync(() => Future<void>.delayed(Duration.zero));
      }
      _dump('burst', hist);
    } finally {
      debugOnRebuildDirtyWidget = saved;
    }
  });
}
