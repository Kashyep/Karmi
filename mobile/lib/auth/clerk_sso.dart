import 'dart:async';

import 'package:clerk_auth/clerk_auth.dart' as clerk;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

/// Single constant for the Karmi OAuth redirection URL.
const String kClerkOAuthRedirectUrl = 'ai.karmi.app://sso-callback';

/// Parsed URI for the Karmi OAuth redirection URL.
final Uri kClerkOAuthRedirectUri = Uri.parse(kClerkOAuthRedirectUrl);

/// Pure function to test whether [uri] is the Karmi SSO redirect callback.
bool isSsoCallbackLink(Uri uri) {
  return uri.scheme.toLowerCase() == 'ai.karmi.app' &&
      uri.host.toLowerCase() == 'sso-callback';
}

/// Generates the redirect URI for Clerk OAuth strategies.
/// Returns `ai.karmi.app://sso-callback` for OAuth, null otherwise (e.g. email link).
Uri? clerkRedirectionGenerator(BuildContext context, clerk.Strategy strategy) {
  if (strategy.isOauth) {
    return kClerkOAuthRedirectUri;
  }
  return null;
}

const MethodChannel _deepLinkMethodChannel = MethodChannel(
  'ai.karmi.app/deep_links/messages',
);
const EventChannel _deepLinkEventChannel = EventChannel(
  'ai.karmi.app/deep_links/events',
);

final StreamController<Uri> _ssoCallbackController =
    StreamController<Uri>.broadcast();

/// Broadcast stream of valid SSO callback links received by the application.
Stream<Uri> get ssoCallbackStream => _ssoCallbackController.stream;

/// Returns a single-subscription stream of deep links received by the application,
/// buffering events until listened, emitting only valid SSO callback URLs (`isSsoCallbackLink`).
Stream<Uri> createSsoDeepLinkStream({
  Future<String?> Function()? getInitialLink,
  Stream<dynamic>? eventStream,
}) {
  late final StreamController<Uri> controller;
  StreamSubscription<dynamic>? eventSub;

  void handleRawLink(dynamic raw) {
    if (raw is String && raw.isNotEmpty) {
      final uri = Uri.tryParse(raw);
      if (uri != null && isSsoCallbackLink(uri)) {
        if (!controller.isClosed) {
          controller.add(uri);
        }
        if (!_ssoCallbackController.isClosed) {
          _ssoCallbackController.add(uri);
        }
      }
    }
  }

  controller = StreamController<Uri>(
    onCancel: () {
      return eventSub?.cancel();
    },
  );

  final fetchInitial =
      getInitialLink ??
      () async {
        try {
          return await _deepLinkMethodChannel.invokeMethod<String>(
            'getInitialLink',
          );
        } catch (_) {
          return null;
        }
      };

  fetchInitial().then((initial) => handleRawLink(initial), onError: (_) {});

  final events =
      eventStream ??
      _deepLinkEventChannel.receiveBroadcastStream().handleError((_) => null);

  eventSub = events.listen(handleRawLink);

  return controller.stream;
}

/// Starts the native deep-link bridge that feeds [ssoCallbackStream].
/// Call once at startup; links received while no Google sign-in is listening
/// are dropped. The cold-start link is NOT replayed here: it is claimed
/// separately via [readInitialSsoCallback] so it is never processed twice.
void startSsoCallbackBridge() {
  unawaited(
    createSsoDeepLinkStream(getInitialLink: () async => null).drain<void>(),
  );
}

/// Returns the SSO callback that launched the process (cold start after the
/// OS killed Karmi during the browser trip), or null when there is none.
Future<Uri?> readInitialSsoCallback({
  Future<String?> Function()? getInitialLink,
}) async {
  try {
    final raw =
        await (getInitialLink ??
            () => _deepLinkMethodChannel.invokeMethod<String>(
              'getInitialLink',
            ))();
    final uri = raw == null || raw.isEmpty ? null : Uri.tryParse(raw);
    return uri != null && isSsoCallbackLink(uri) ? uri : null;
  } catch (_) {
    return null;
  }
}

/// Exchanges a cold-start SSO callback exactly once. Never throws; a failed
/// exchange is reported via [report] (without token or nonce) and the user
/// stays on the sign-in screen to retry. Returns true if the exchange ran
/// and succeeded.
Future<bool> exchangeColdStartSsoCallback(
  Uri? link,
  Future<Object?> Function(Uri uri) parse, {
  void Function(String message)? report,
}) async {
  if (link == null || !isSsoCallbackLink(link)) return false;
  try {
    await parse(link);
    return true;
  } catch (e) {
    report?.call(
      'Cold-start Google sign-in exchange failed (${e.runtimeType}).',
    );
    return false;
  }
}
