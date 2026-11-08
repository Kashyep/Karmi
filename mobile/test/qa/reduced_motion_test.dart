import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/theme/karmi_motion.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:karmi_app/theme/karmi_tokens.dart';
import 'package:karmi_app/widgets/feedback.dart';

Widget _buildMotionHost({
  required bool disableAnimations,
  required Widget child,
}) {
  return MaterialApp(
    theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
    home: MediaQuery(
      data: MediaQueryData(disableAnimations: disableAnimations),
      child: Scaffold(body: Center(child: child)),
    ),
  );
}

void main() {
  group('Reduced motion via MediaQuery(disableAnimations: true)', () {
    testWidgets(
      'under normal motion (disableAnimations: false), loader has running animations',
      (tester) async {
        await tester.pumpWidget(
          _buildMotionHost(
            disableAnimations: false,
            child: const KarmiLoader(label: 'Loading normally'),
          ),
        );
        // CircularProgressIndicator starts its animation
        await tester.pump();

        expect(tester.hasRunningAnimations, isTrue);
        expect(
          find.byKey(const ValueKey('karmi-loader-spinner')),
          findsOneWidget,
        );
        expect(find.byKey(const ValueKey('karmi-loader-static')), findsNothing);
      },
    );

    testWidgets(
      'under reduced motion (disableAnimations: true), no running animations and duration is 0',
      (tester) async {
        late BuildContext capturedContext;
        await tester.pumpWidget(
          _buildMotionHost(
            disableAnimations: true,
            child: Builder(
              builder: (context) {
                capturedContext = context;
                return const KarmiLoader(label: 'Loading with reduced motion');
              },
            ),
          ),
        );
        await tester.pump();

        // 1. tester.hasRunningAnimations is strictly false
        expect(tester.hasRunningAnimations, isFalse);

        // 2. Renders static icon rather than infinite spinner
        expect(
          find.byKey(const ValueKey('karmi-loader-static')),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey('karmi-loader-spinner')),
          findsNothing,
        );

        // 3. KarmiMotion and KarmiTokens durations evaluate to Duration.zero
        expect(KarmiMotion.duration(capturedContext), Duration.zero);
        expect(
          KarmiMotion.duration(capturedContext, KarmiMotion.fast),
          Duration.zero,
        );
        expect(KarmiTokens.motion(capturedContext), Duration.zero);
        expect(
          KarmiTokens.motion(capturedContext, KarmiTokens.slow),
          Duration.zero,
        );
      },
    );

    testWidgets(
      'KarmiMotion.route transitionDuration is Duration.zero when disableAnimations is true',
      (tester) async {
        late BuildContext capturedContext;
        await tester.pumpWidget(
          _buildMotionHost(
            disableAnimations: true,
            child: Builder(
              builder: (context) {
                capturedContext = context;
                return const SizedBox();
              },
            ),
          ),
        );
        await tester.pump();

        final route = KarmiMotion.route<void>(
          capturedContext,
          (_) => const Text('Route Target'),
        );

        final pageRoute = route as PageRouteBuilder<void>;
        expect(pageRoute.transitionDuration, Duration.zero);
        expect(pageRoute.reverseTransitionDuration, Duration.zero);
      },
    );
  });
}
