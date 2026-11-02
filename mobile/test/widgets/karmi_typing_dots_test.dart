import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/chat/chat_models.dart';
import 'package:karmi_app/features/chat/message_bubble.dart';
import 'package:karmi_app/theme/karmi_colors.dart';
import 'package:karmi_app/theme/karmi_motion.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:karmi_app/widgets/karmi_typing_dots.dart';

Widget _wrap(
  Widget child, {
  KarmiTier tier = KarmiTier.ananta,
  Brightness brightness = Brightness.light,
  bool reduceMotion = false,
}) {
  return MaterialApp(
    theme: KarmiTheme.of(tier, brightness),
    home: MediaQuery(
      data: MediaQueryData(disableAnimations: reduceMotion),
      child: KarmiAccessibility(
        reduceTransparency: false,
        reduceMotion: reduceMotion,
        child: Scaffold(body: Center(child: child)),
      ),
    ),
  );
}

void main() {
  group('KarmiTypingDots', () {
    testWidgets('shows each phase label beside dots', (tester) async {
      const labels = [
        'Working…',
        'Preparing…',
        'Writing…',
        'Still working, free models can be slow',
        'Still working, Karmi can be slow',
        'Connection slow, still trying…',
      ];

      for (final label in labels) {
        await tester.pumpWidget(_wrap(KarmiTypingDots(label: label)));
        expect(find.text(label), findsOneWidget);
        expect(find.byType(KarmiTypingDots), findsOneWidget);
      }
    });

    testWidgets('provides one live-region semantics label, not per-dot', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      const label = 'Still working, free models can be slow';

      await tester.pumpWidget(_wrap(const KarmiTypingDots(label: label)));

      expect(find.bySemanticsLabel(label), findsOneWidget);

      final semanticsNode = tester.getSemantics(find.byType(KarmiTypingDots));
      expect(semanticsNode.label, label);
      expect(
        semanticsNode.getSemanticsData().flagsCollection.isLiveRegion,
        isTrue,
      );

      handle.dispose();
    });

    testWidgets('pulses in active tier accent colour', (tester) async {
      for (final tier in KarmiTier.values) {
        await tester.pumpWidget(
          _wrap(const KarmiTypingDots(label: 'Working…'), tier: tier),
        );
        final element = tester.element(find.byType(KarmiTypingDots));
        final tierColors = KarmiColors.of(element);
        expect(tierColors.primary, isNotNull);
      }
    });

    testWidgets(
      'reduce motion renders static with no transient callbacks or running animations',
      (tester) async {
        await tester.pumpWidget(
          _wrap(
            const KarmiTypingDots(label: 'Static dots'),
            reduceMotion: true,
          ),
        );
        await tester.pump();

        expect(find.text('Static dots'), findsOneWidget);
        expect(tester.hasRunningAnimations, isFalse);
        expect(tester.binding.transientCallbackCount, 0);

        // Advance simulated time to ensure no tickers wake up
        await tester.pump(const Duration(milliseconds: 500));
        expect(tester.hasRunningAnimations, isFalse);
        expect(tester.binding.transientCallbackCount, 0);
      },
    );

    testWidgets('controller is disposed on unmount with no ticker error', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(const KarmiTypingDots(label: 'To be unmounted')),
      );
      await tester.pump();
      expect(tester.hasRunningAnimations, isTrue);

      // Unmount the widget by replacing it
      await tester.pumpWidget(_wrap(const SizedBox.shrink()));
      await tester.pump();

      expect(find.byType(KarmiTypingDots), findsNothing);
      expect(tester.hasRunningAnimations, isFalse);
      expect(tester.binding.transientCallbackCount, 0);
    });

    testWidgets(
      'frame-count test: parent list item / builder rebuild count == 0 during 30 animation frames',
      (tester) async {
        var parentBuildCount = 0;

        Widget buildListItem() {
          return Builder(
            builder: (context) {
              parentBuildCount++;
              return MessageBubble.chatMessage(
                chatMessage: ChatMessageView(
                  conversationId: 'conv-1',
                  id: 'msg-1',
                  role: 'assistant',
                  content: '',
                  status: MessageStatus.streaming,
                  createdAt: DateTime(2026, 11, 2),
                  updatedAt: DateTime(2026, 11, 2),
                ),
                pendingNotice: 'Writing…',
              );
            },
          );
        }

        await tester.pumpWidget(_wrap(buildListItem()));
        expect(parentBuildCount, 1);
        expect(find.byType(KarmiTypingDots), findsOneWidget);
        expect(find.text('Writing…'), findsOneWidget);

        // Record build count before running animation frames
        final baselineBuildCount = parentBuildCount;

        // Pump 30 frames at 60 FPS (~500 ms)
        for (var i = 0; i < 30; i++) {
          await tester.pump(const Duration(milliseconds: 16));
        }

        // Parent message bubble and list builder must NOT rebuild on animation frames!
        final rebuildsDuringAnimation = parentBuildCount - baselineBuildCount;
        expect(
          rebuildsDuringAnimation,
          0,
          reason: 'List item rebuilds during animation frames must be zero',
        );
      },
    );
  });
}
