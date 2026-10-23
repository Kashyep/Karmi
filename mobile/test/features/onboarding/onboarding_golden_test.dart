import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/features/onboarding/onboarding.dart';
import 'package:karmi_app/settings/karmi_settings.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/fake_backend.dart';
import '../../support/harness.dart';

void main() {
  group('Onboarding Goldens', () {
    for (final brightness in [Brightness.light, Brightness.dark]) {
      testWidgets('onboarding welcome screen ${brightness.name}', (tester) async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        final settings = KarmiSettings(prefs);
        final backend = FakeBackend.healthy();
        final session = KarmiSession(
          api: KarmiApi(baseUrl: 'http://karmi.test', client: backend.client),
          prefs: prefs,
        );

        final env = Env(brightness: brightness);
        await pumpHost(
          tester,
          OnboardingFlow(
            session: session,
            settings: settings,
            devAuthEnabled: true,
          ),
          env: env,
          size: const Size(390, 844),
        );

        expect(find.text('Meet Karmi'), findsOneWidget);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile(
            goldenPath('onboarding_welcome_${brightness.name}_x1.0_glass'),
          ),
        );
      });
    }
  });
}
