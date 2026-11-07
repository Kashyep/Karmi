import 'package:clerk_auth/clerk_auth.dart' as clerk;
import 'package:clerk_flutter/clerk_flutter.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/bug_reports/bug_reports_api_models.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/features/bug_report/bug_report_queue.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeClerkUser implements clerk.User {
  _FakeClerkUser(this.id);

  @override
  final String id;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeClerkAuthState extends ChangeNotifier implements ClerkAuthState {
  _FakeClerkAuthState({required bool signedIn, String? userId})
      : _isSignedIn = signedIn,
        _user = userId != null ? _FakeClerkUser(userId) : null;

  bool _isSignedIn;
  clerk.User? _user;

  @override
  bool get isSignedIn => _isSignedIn;

  @override
  clerk.User? get user => _user;

  @override
  Future<void> signOut() async {
    _isSignedIn = false;
    _user = null;
    notifyListeners();
  }

  void remoteSignOut() {
    _isSignedIn = false;
    _user = null;
    notifyListeners();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('KarmiSession bug report queue cleanup rules', () {
    test('expiry does not clear the queue', () async {
      SharedPreferences.setMockInitialValues({
        'dev_session_token': 'user_abc|admin|9999999999|1|sig',
      });
      final prefs = await SharedPreferences.getInstance();
      final api = KarmiApi(baseUrl: 'http://test');
      final session = KarmiSession(api: api, prefs: prefs);

      expect(session.userId, 'user_abc');

      // Enqueue an item for user_abc
      final queue = BugReportQueue(prefs: prefs);
      const req = BugReportCreateRequest(
        clientReportId: '550e8400-e29b-41d4-a716-446655440001',
        category: BugReportCategory.chat,
        description: 'Offline bug report',
        diagnostics: BugReportDiagnostics(screen: 'chat'),
      );
      await queue.enqueue(req, userId: 'user_abc');

      expect((await queue.getAll()).length, 1);

      // Session expires (HTTP 401)
      session.expire();

      expect(session.lastEnd, SessionEnd.expired);
      expect(session.isSignedIn, isFalse);

      // Items for user_abc are NOT cleared on expiry
      final remaining = await queue.getAll();
      expect(remaining.length, 1);
      expect(remaining.first.userId, 'user_abc');
    });

    test(
      'sign-out clears owner items even after user became null (out-of-band sign-out)',
      () async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        final api = KarmiApi(baseUrl: 'http://test');
        final fakeClerk = _FakeClerkAuthState(
          signedIn: true,
          userId: 'user_clerk_123',
        );
        final session = KarmiSession(
          api: api,
          prefs: prefs,
          clerkAuth: fakeClerk,
        );

        expect(session.userId, 'user_clerk_123');

        // Enqueue an item for user_clerk_123
        final queue = BugReportQueue(prefs: prefs);
        const req = BugReportCreateRequest(
          clientReportId: '550e8400-e29b-41d4-a716-446655440002',
          category: BugReportCategory.settings,
          description: 'Clerk user bug report',
          diagnostics: BugReportDiagnostics(screen: 'settings'),
        );
        await queue.enqueue(req, userId: 'user_clerk_123');
        expect((await queue.getAll()).length, 1);

        // Remote out-of-band sign-out makes user null before listener fires
        fakeClerk.remoteSignOut();

        expect(session.lastEnd, SessionEnd.signedOut);
        expect(session.isSignedIn, isFalse);
        expect(session.userId, isNull);

        // Queue items for the signed-out user are cleared
        final remaining = await queue.getAll();
        expect(remaining.isEmpty, isTrue);
      },
    );
  });
}
