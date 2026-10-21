@Tags(['golden'])
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import 'package:karmi_app/api/chat/chat_models.dart';
import 'package:karmi_app/features/chat/error_card.dart';
import 'package:karmi_app/features/chat/processing_panel.dart';
import 'package:karmi_app/features/chat/state/chat_controller.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

String a11yGoldenPath(String name) =>
    'goldens/${Platform.operatingSystem}/$name.png';

void main() {
  Future<void> fontsReady(WidgetTester tester) async {
    await tester.runAsync(GoogleFonts.pendingFonts);
    await settle(tester);
  }

  final a11yEnvs = [
    for (final brightness in Brightness.values)
      for (final textScale in [1.0, 2.0])
        Env(brightness: brightness, textScale: textScale),
  ];

  for (final env in a11yEnvs) {
    final suffix =
        '${env.brightness.name}_x${env.textScale.toStringAsFixed(1)}';

    group(suffix, () {
      testWidgets('chat screen with short conversation', (tester) async {
        await pumpApp(
          tester,
          env: env,
          backend: FakeBackend.healthy()
            ..on(
              'POST',
              '/v1/chat/stream',
              (_) => http.Response(
                'event: run.started\n'
                'data: {"run_id":"run-1","conversation_id":"conv-1","user_message_id":"msg-u","assistant_message_id":"msg-a","seq":0}\n\n'
                'id: 1\n'
                'event: message.delta\n'
                'data: {"text":"Which day should I remind you to call the bank?"}\n\n'
                'event: run.finished\n'
                'data: {"finish_reason":"stop","outcome":"success"}\n\n',
                200,
                headers: {'content-type': 'text/event-stream'},
              ),
            ),
        );
        await tester.enterText(find.byType(TextField), 'Remind me to call');
        await tester.pump();
        await tester.tap(find.byTooltip('Send message'));
        await fontsReady(tester);
        await tester.enterText(find.byType(TextField), '');
        await fontsReady(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(a11yGoldenPath('a11y_chat_$suffix')),
        );
      });

      testWidgets('error card quotaExhausted', (tester) async {
        await pumpHost(
          tester,
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
              child: ErrorCard(
                category: ErrorCategory.quotaExhausted,
                onUpgrade: () {},
              ),
            ),
          ),
          env: env,
        );
        await fontsReady(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(
            a11yGoldenPath('a11y_error_card_quota_exhausted_$suffix'),
          ),
        );
      });

      testWidgets('error card network', (tester) async {
        await pumpHost(
          tester,
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
              child: ErrorCard(category: ErrorCategory.network, onRetry: () {}),
            ),
          ),
          env: env,
        );
        await fontsReady(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(a11yGoldenPath('a11y_error_card_network_$suffix')),
        );
      });

      testWidgets('processing panel streaming', (tester) async {
        await pumpHost(
          tester,
          const SafeArea(
            child: Padding(
              padding: EdgeInsets.all(16),
              child: Align(
                alignment: Alignment.topLeft,
                child: ProcessingPanel(phase: ChatRunPhase.streaming),
              ),
            ),
          ),
          env: env,
        );
        await fontsReady(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(
            a11yGoldenPath('a11y_processing_panel_streaming_$suffix'),
          ),
        );
      });
    });
  }

  group('text scale 2.0 no overflow', () {
    testWidgets('error card quotaExhausted does not overflow at 2.0 scale', (
      tester,
    ) async {
      await pumpHost(
        tester,
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: ErrorCard(
              category: ErrorCategory.quotaExhausted,
              onUpgrade: () {},
            ),
          ),
        ),
        env: const Env(textScale: 2.0),
      );
      await fontsReady(tester);
      expect(tester.takeException(), isNull);
    });

    testWidgets('error card network does not overflow at 2.0 scale', (
      tester,
    ) async {
      await pumpHost(
        tester,
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: ErrorCard(category: ErrorCategory.network, onRetry: () {}),
          ),
        ),
        env: const Env(textScale: 2.0),
      );
      await fontsReady(tester);
      expect(tester.takeException(), isNull);
    });

    testWidgets('processing panel streaming does not overflow at 2.0 scale', (
      tester,
    ) async {
      await pumpHost(
        tester,
        const SafeArea(
          child: Padding(
            padding: EdgeInsets.all(16),
            child: Align(
              alignment: Alignment.topLeft,
              child: ProcessingPanel(phase: ChatRunPhase.streaming),
            ),
          ),
        ),
        env: const Env(textScale: 2.0),
      );
      await fontsReady(tester);
      expect(tester.takeException(), isNull);
    });
  });
}
