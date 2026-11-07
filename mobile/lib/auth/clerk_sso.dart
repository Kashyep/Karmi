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
