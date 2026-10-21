import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/chat/chat_models.dart';
import 'package:karmi_app/widgets/usage_warning_pill.dart';
import 'package:karmi_app/features/chat/error_card.dart';
import '../support/harness.dart';

void main() {
  testWidgets('ErrorCard and UsageWarningPill pass contrast in light and dark', (tester) async {
    for (final brightness in [Brightness.light, Brightness.dark]) {
      // Test ErrorCard
      for (final cat in ErrorCategory.values) {
        final handle = tester.ensureSemantics();
        await pumpHost(
          tester,
          Center(
            child: ErrorCard(
              category: cat,
              onRetry: () {},
              onContinue: () {},
              onUpgrade: () {},
            ),
          ),
          env: Env(brightness: brightness),
        );
        await expectLater(tester, meetsGuideline(textContrastGuideline));
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
        await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
        handle.dispose();
      }

      // Test UsageWarningPill
      for (final fraction in [0.85, 1.0]) {
        final handle = tester.ensureSemantics();
        await pumpHost(
          tester,
          Center(child: UsageWarningPill(fraction: fraction)),
          env: Env(brightness: brightness),
        );
        await expectLater(tester, meetsGuideline(textContrastGuideline));
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
        await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
        handle.dispose();
      }
    }
  });
}
