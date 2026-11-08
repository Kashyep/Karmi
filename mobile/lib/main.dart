import 'dart:async';

import 'package:flutter/material.dart';
import 'package:clerk_flutter/clerk_flutter.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api/karmi_api.dart';
import 'app.dart';
import 'armory/armory_controller.dart';
import 'features/admin/admin_controller.dart';
import 'features/admin/admin_http_api.dart';
import 'auth/session.dart';
import 'auth/clerk_sso.dart';
import 'fonts.dart';
import 'settings/karmi_settings.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  configureBundledFonts();
  // Startup (R1 §6 G): these three inits are independent and run in parallel.
  // Clerk is NOT deferred: KarmiSession takes ClerkAuthState at construction
  // (session.dart owns the token provider wiring), so it must be ready before
  // KarmiApp is built. No deferred (`deferred as`) imports: every first-frame
  // screen (Welcome, Shell, TesterNotice) is imported eagerly by app.dart, so
  // there is no startup-path screen to defer.
  // The SDK is deliberately NOT given a deepLinkStream: signInWithGoogle
  // exchanges the callback itself so failures surface (see SsoCallbackHandler).
  startSsoCallbackBridge();
  final initialSsoLinkFuture = readInitialSsoCallback();
  const publishableKey = String.fromEnvironment('CLERK_PUBLISHABLE_KEY');
  final glassInitFuture = LiquidGlassWidgets.initialize();
  final prefsFuture = SharedPreferences.getInstance();
  final clerkAuthFuture = publishableKey.isEmpty
      ? Future<ClerkAuthState?>.value(null)
      : ClerkAuthState.create(
          config: ClerkAuthConfig(
            publishableKey: publishableKey,
            redirectionGenerator: clerkRedirectionGenerator,
          ),
        );

  await Future.wait<dynamic>([glassInitFuture, prefsFuture, clerkAuthFuture]);

  final prefs = await prefsFuture;
  final clerkAuth = await clerkAuthFuture;
  if (clerkAuth case final auth?) {
    unawaited(
      initialSsoLinkFuture.then(
        (link) => exchangeColdStartSsoCallback(
          link,
          auth.parseDeepLink,
          report: debugPrint,
        ),
      ),
    );
  }
  final settings = KarmiSettings(prefs);
  final api = KarmiApi(baseUrl: settings.apiBaseUrl ?? KarmiApi.defaultBaseUrl);
  final session = KarmiSession(api: api, prefs: prefs, clerkAuth: clerkAuth);

  Widget app = KarmiApp(
    settings: settings,
    session: session,
    armory: ArmoryController(api: api, prefs: prefs),
    admin: AdminController(
      api: HttpAdminApi(
        baseUrl: api.baseUrl,
        client: api.client,
        tokenProvider: api.tokenProvider ?? () async => api.token,
      ),
    ),
  );
  if (clerkAuth case final auth?) {
    app = ClerkAuth(authState: auth, child: app);
  }
  runApp(app);
}
