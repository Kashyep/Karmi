import 'dart:async';

import 'package:clerk_auth/clerk_auth.dart' as clerk;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/auth/clerk_sso.dart';

void main() {
  group('SSO redirection constants', () {
    test('canonical redirect URL matches ai.karmi.app://sso-callback', () {
      expect(kClerkOAuthRedirectUrl, 'ai.karmi.app://sso-callback');
      expect(kClerkOAuthRedirectUri, Uri.parse('ai.karmi.app://sso-callback'));
      expect(kClerkOAuthRedirectUri.scheme, 'ai.karmi.app');
      expect(kClerkOAuthRedirectUri.host, 'sso-callback');
    });
  });

  group('isSsoCallbackLink', () {
    test('accepts exact canonical redirect URI', () {
      expect(
        isSsoCallbackLink(Uri.parse('ai.karmi.app://sso-callback')),
        isTrue,
      );
      expect(isSsoCallbackLink(kClerkOAuthRedirectUri), isTrue);
    });

    test('accepts callback link with query parameters', () {
      final uri = Uri.parse(
        'ai.karmi.app://sso-callback?created_session_id=sess_123&status=complete',
      );
      expect(isSsoCallbackLink(uri), isTrue);
    });

    test('accepts callback link with query parameters and fragment', () {
      final uri = Uri.parse(
        'ai.karmi.app://sso-callback?rotating_token_nonce=nonce_abc#step2',
      );
      expect(isSsoCallbackLink(uri), isTrue);
    });

    test('is case-insensitive for scheme and host', () {
      expect(
        isSsoCallbackLink(Uri.parse('AI.KARMI.APP://SSO-CALLBACK')),
        isTrue,
      );
      expect(
        isSsoCallbackLink(Uri.parse('Ai.Karmi.App://Sso-Callback?code=123')),
        isTrue,
      );
    });

    test('rejects other schemes with sso-callback host', () {
      expect(isSsoCallbackLink(Uri.parse('https://sso-callback')), isFalse);
      expect(isSsoCallbackLink(Uri.parse('http://sso-callback')), isFalse);
      expect(isSsoCallbackLink(Uri.parse('custom://sso-callback')), isFalse);
      expect(isSsoCallbackLink(Uri.parse('karmi://sso-callback')), isFalse);
    });

    test('rejects other hosts under ai.karmi.app scheme', () {
      expect(
        isSsoCallbackLink(Uri.parse('ai.karmi.app://other-callback')),
        isFalse,
      );
      expect(
        isSsoCallbackLink(Uri.parse('ai.karmi.app://sso-callback-phish')),
        isFalse,
      );
      expect(isSsoCallbackLink(Uri.parse('ai.karmi.app://oauth')), isFalse);
      expect(isSsoCallbackLink(Uri.parse('ai.karmi.app://')), isFalse);
    });

    test('rejects web URLs where sso-callback is only in path', () {
      expect(
        isSsoCallbackLink(Uri.parse('https://ai.karmi.app/sso-callback')),
        isFalse,
      );
      expect(
        isSsoCallbackLink(Uri.parse('https://clerk.com/sso-callback')),
        isFalse,
      );
    });

    test('rejects arbitrary external URLs and empty URIs', () {
      expect(isSsoCallbackLink(Uri.parse('https://google.com')), isFalse);
      expect(isSsoCallbackLink(Uri.parse('mailto:support@karmi.ai')), isFalse);
      expect(isSsoCallbackLink(Uri.parse('tel:123456789')), isFalse);
      expect(isSsoCallbackLink(Uri()), isFalse);
    });
  });

  group('clerkRedirectionGenerator', () {
    testWidgets('returns canonical redirect URI for OAuth strategies', (
      tester,
    ) async {
      await tester.pumpWidget(const SizedBox());
      final context = tester.element(find.byType(SizedBox));

      final googleRedirect = clerkRedirectionGenerator(
        context,
        clerk.Strategy.oauthGoogle,
      );
      expect(googleRedirect, equals(kClerkOAuthRedirectUri));

      final githubRedirect = clerkRedirectionGenerator(
        context,
        clerk.Strategy.oauthGithub,
      );
      expect(githubRedirect, equals(kClerkOAuthRedirectUri));
    });

    testWidgets('returns null for non-OAuth strategies', (tester) async {
      await tester.pumpWidget(const SizedBox());
      final context = tester.element(find.byType(SizedBox));

      expect(
        clerkRedirectionGenerator(context, clerk.Strategy.emailCode),
        isNull,
      );
      expect(
        clerkRedirectionGenerator(context, clerk.Strategy.emailLink),
        isNull,
      );
      expect(
        clerkRedirectionGenerator(context, clerk.Strategy.password),
        isNull,
      );
      expect(clerkRedirectionGenerator(context, clerk.Strategy.ticket), isNull);
    });
  });

  group('createSsoDeepLinkStream', () {
    test('emits initial link when it is a valid SSO callback', () async {
      final emitted = <Uri?>[];
      final stream = createSsoDeepLinkStream(
        getInitialLink: () async => 'ai.karmi.app://sso-callback?token=tok_123',
        eventStream: const Stream<dynamic>.empty(),
      );

      final sub = stream.listen(emitted.add);
      await Future<void>.delayed(Duration.zero);
      await sub.cancel();

      expect(emitted.length, 1);
      expect(
        emitted.first,
        Uri.parse('ai.karmi.app://sso-callback?token=tok_123'),
      );
    });

    test('ignores initial link when it is not a valid SSO callback', () async {
      final emitted = <Uri?>[];
      final stream = createSsoDeepLinkStream(
        getInitialLink: () async => 'https://malicious.example.com/oauth',
        eventStream: const Stream<dynamic>.empty(),
      );

      final sub = stream.listen(emitted.add);
      await Future<void>.delayed(Duration.zero);
      await sub.cancel();

      expect(emitted, isEmpty);
    });

    test('ignores null or empty initial link and does not throw', () async {
      final emitted = <Uri?>[];
      final stream = createSsoDeepLinkStream(
        getInitialLink: () async => null,
        eventStream: const Stream<dynamic>.empty(),
      );

      final sub = stream.listen(emitted.add);
      await Future<void>.delayed(Duration.zero);
      await sub.cancel();

      expect(emitted, isEmpty);
    });

    test('filters eventStream to emit only valid SSO callback URIs', () async {
      final eventController = StreamController<dynamic>();
      final emitted = <Uri?>[];

      final stream = createSsoDeepLinkStream(
        getInitialLink: () async => null,
        eventStream: eventController.stream,
      );

      final sub = stream.listen(emitted.add);

      // Invalid schemes / hosts
      eventController.add('https://google.com');
      eventController.add('ai.karmi.app://other-target');
      eventController.add(123); // Non-string
      eventController.add('');

      // Valid SSO link
      eventController.add('ai.karmi.app://sso-callback?state=xyz');

      await Future<void>.delayed(Duration.zero);

      expect(emitted.length, 1);
      expect(emitted.first, Uri.parse('ai.karmi.app://sso-callback?state=xyz'));

      await sub.cancel();
      await eventController.close();
    });
  });
}
