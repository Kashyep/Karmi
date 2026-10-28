import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/auth/session.dart';
import 'package:karmi_app/features/chat/composer/draft_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Dev token shape issued by the backend: `<userId>|<role>|<exp>|<tv>|<sig>`.
String _devToken(String userId) => '$userId|customer|9999999999|1|sig';

/// Session construction purges legacy drafts without awaiting (constructors
/// cannot be async); give the platform-backed removals time to finish.
Future<void> _settle() => Future<void>.delayed(const Duration(milliseconds: 5));

Future<KarmiSession> _signIn(SharedPreferences prefs, String userId) async {
  await prefs.setString('dev_session_token', _devToken(userId));
  final session = KarmiSession(
    api: KarmiApi(baseUrl: 'http://fake.test'),
    prefs: prefs,
  );
  await _settle();
  return session;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('draft scoping per user id', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('two users on one device never see each other drafts', () async {
      final prefs = await SharedPreferences.getInstance();

      final sessionA = await _signIn(prefs, 'user_a');
      final storeA = sessionA.draftStore!;
      expect(sessionA.userId, 'user_a');
      await storeA.save('new', 'a secret plan');
      await storeA.save('conv-1', 'a conversation draft');

      final sessionB = await _signIn(prefs, 'user_b');
      final storeB = sessionB.draftStore!;
      expect(sessionB.userId, 'user_b');
      expect(await storeB.load('new'), isNull);
      expect(await storeB.load('conv-1'), isNull);

      await storeB.save('new', 'b draft');
      expect(await storeB.load('new'), 'b draft');

      // User A's drafts are untouched by user B's writes.
      final storeAAgain = (await _signIn(prefs, 'user_a')).draftStore!;
      expect(await storeAAgain.load('new'), 'a secret plan');
      expect(await storeAAgain.load('conv-1'), 'a conversation draft');
    });

    test('keys are stored as draft.v1.<userId>.<id>', () async {
      final prefs = await SharedPreferences.getInstance();
      final store = SharedPrefsDraftStore(userId: 'user_a', prefs: prefs);
      await store.save('new', 'x');
      expect(prefs.getString('draft.v1.user_a.new'), 'x');
    });

    test('legacy unscoped drafts are discarded, not shown to anyone', () async {
      SharedPreferences.setMockInitialValues({
        'draft.v1.new': 'legacy draft',
        'draft.v1.conv-9': 'legacy conversation draft',
        'draft.v1.user_a.new': 'scoped draft',
      });
      final prefs = await SharedPreferences.getInstance();

      final session = await _signIn(prefs, 'user_b');
      expect(prefs.getString('draft.v1.new'), isNull);
      expect(prefs.getString('draft.v1.conv-9'), isNull);
      expect(await session.draftStore!.load('new'), isNull);

      // Scoped drafts of other users are preserved until sign-out.
      expect(prefs.getString('draft.v1.user_a.new'), 'scoped draft');
    });

    test('sign-out clears drafts for every user', () async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('unrelated', 'keep');

      final sessionA = await _signIn(prefs, 'user_a');
      await sessionA.draftStore!.save('new', 'a');
      await (await _signIn(prefs, 'user_b')).draftStore!.save('new', 'b');

      await sessionA.signOut();

      expect(prefs.getKeys().where((k) => k.startsWith('draft.v1.')), isEmpty);
      expect(prefs.getString('unrelated'), 'keep');
    });

    test('draftStore is null when no user id is known', () async {
      final prefs = await SharedPreferences.getInstance();
      final session = KarmiSession(
        api: KarmiApi(baseUrl: 'http://fake.test'),
        prefs: prefs,
      );
      expect(session.userId, isNull);
      expect(session.draftStore, isNull);
    });
  });
}
