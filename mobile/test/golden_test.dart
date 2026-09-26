@Tags(['golden'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:karmi_app/api/models.dart';
import 'package:karmi_app/features/plans/plan_selection_screen.dart';
import 'package:karmi_app/features/tasks/task_confirmation_sheet.dart';
import 'package:karmi_app/theme/karmi_colors.dart';
import 'package:karmi_app/theme/karmi_glass.dart';

import 'support/fake_backend.dart';
import 'support/harness.dart';

/// §8 golden gate: every screen × light/dark × text scale 1.0/2.0 × reduce
/// transparency off/on. Baselines live in `goldens/<host os>/`.
///
/// Note: under `flutter test` liquid_glass_widgets cannot load its fragment
/// shaders (it looks them up at the package-test path), so glass surfaces
/// render their non-shader fallback here. On-device glass is checked manually.
void main() {
  Future<void> fontsReady(WidgetTester tester) async {
    await tester.runAsync(GoogleFonts.pendingFonts);
    await settle(tester);
  }

  for (final env in goldenEnvs) {
    group(env.name, () {
      testWidgets('chat', (tester) async {
        await pumpApp(
          tester,
          env: env,
          backend: FakeBackend.healthy()
            ..on(
              'POST',
              '/v1/messages',
              (_) => jsonResponse(
                messageJson(
                  'ASK_USER',
                  response: 'Which day should I remind you to call the bank?',
                ),
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
          matchesGoldenFile(goldenPath('chat_${env.name}')),
        );
      });

      testWidgets('chat_empty', (tester) async {
        await pumpApp(tester, env: env);
        await fontsReady(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(goldenPath('chat_empty_${env.name}')),
        );
      });

      for (final tab in ['Tasks', 'Usage', 'Memory', 'Settings']) {
        testWidgets(tab.toLowerCase(), (tester) async {
          await pumpApp(tester, env: env);
          await openTab(tester, tab);
          await fontsReady(tester);
          await expectLater(
            find.byType(MaterialApp),
            matchesGoldenFile(goldenPath('${tab.toLowerCase()}_${env.name}')),
          );
        });
      }

      testWidgets('welcome', (tester) async {
        await pumpApp(tester, env: env, signedIn: false);
        await fontsReady(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(goldenPath('welcome_${env.name}')),
        );
      });

      testWidgets('plans', (tester) async {
        await pumpHost(
          tester,
          const PlanSelectionScreen(currentPlanId: 'ananta'),
          env: env,
        );
        await fontsReady(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(goldenPath('plans_${env.name}')),
        );
      });

      testWidgets('confirmation_sheet', (tester) async {
        await pumpHost(
          tester,
          Builder(
            builder: (context) => Center(
              child: TextButton(
                onPressed: () => showTaskConfirmationSheet(
                  context,
                  const MessageView(
                    runId: 'r',
                    status: 'completed',
                    outcome: Outcome.askUser,
                    response: 'Which day should I remind you?',
                  ),
                ),
                child: const Text('Open'),
              ),
            ),
          ),
          env: env,
        );
        await tester.tap(find.text('Open'));
        await fontsReady(tester);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(goldenPath('confirmation_sheet_${env.name}')),
        );
      });
    });
  }

  // §5.1 legibility floor: label text on glass over the worst-case backdrop
  // (pure white behind light glass, #08160a behind dark glass).
  for (final brightness in Brightness.values) {
    testWidgets(
      'glass legibility over worst-case backdrop (${brightness.name})',
      (tester) async {
        final backdrop = brightness == Brightness.light
            ? const Color(0xFFFFFFFF)
            : KarmiColors.dark.background;
        await pumpHost(
          tester,
          ColoredBox(
            color: backdrop,
            child: Center(
              child: KarmiGlassSurface(
                padding: const EdgeInsets.all(16),
                child: Builder(
                  builder: (context) => Text(
                    'Label on glass',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
              ),
            ),
          ),
          env: Env(brightness: brightness),
          size: const Size(320, 160),
        );
        await fontsReady(tester);
        await expectLater(tester, meetsGuideline(textContrastGuideline));
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(goldenPath('glass_legibility_${brightness.name}')),
        );
      },
    );
  }
}
