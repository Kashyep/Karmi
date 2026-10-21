import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/composer/draft_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DraftStore per-conversation and persistence', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('drafts are keyed independently per conversation id and "new"', () async {
      final store = SharedPrefsDraftStore(userId: 'user_a');

      await store.save('conv_1', 'draft for conversation 1');
      await store.save('conv_2', 'draft for conversation 2');
      await store.save('new', 'draft for new conversation');

      expect(await store.load('conv_1'), 'draft for conversation 1');
      expect(await store.load('conv_2'), 'draft for conversation 2');
      expect(await store.load('new'), 'draft for new conversation');

      // Modifying one key does not alter others
      await store.save('conv_1', 'updated conversation 1');
      expect(await store.load('conv_1'), 'updated conversation 1');
      expect(await store.load('conv_2'), 'draft for conversation 2');
      expect(await store.load('new'), 'draft for new conversation');

      // Clearing 'new' does not affect conversation keys
      await store.clear('new');
      expect(await store.load('new'), isNull);
      expect(await store.load('conv_1'), 'updated conversation 1');
      expect(await store.load('conv_2'), 'draft for conversation 2');
    });

    test('drafts survive re-creating the DraftStore instance', () async {
      final store1 = SharedPrefsDraftStore(userId: 'user_a');
      await store1.save('new', 'draft persisted from store 1');
      await store1.save('conv_persist', 'conversation draft from store 1');

      // Re-create the store
      final store2 = SharedPrefsDraftStore(userId: 'user_a');
      expect(await store2.load('new'), 'draft persisted from store 1');
      expect(await store2.load('conv_persist'), 'conversation draft from store 1');

      // Mutate via store2 and read via store3
      await store2.save('new', 'mutated draft in store 2');
      final store3 = SharedPrefsDraftStore(userId: 'user_a');
      expect(await store3.load('new'), 'mutated draft in store 2');
      expect(await store3.load('conv_persist'), 'conversation draft from store 1');
    });

    test('recovers drafts from pre-populated SharedPreferences (app restart scenario)', () async {
      SharedPreferences.setMockInitialValues({
        'draft.v1.user_a.new': 'restored new draft',
        'draft.v1.user_a.conv_saved': 'restored saved conversation',
      });

      final store = SharedPrefsDraftStore(userId: 'user_a');
      expect(await store.load('new'), 'restored new draft');
      expect(await store.load('conv_saved'), 'restored saved conversation');
      expect(await store.load('conv_missing'), isNull);

      await store.clear('conv_saved');
      expect(await store.load('conv_saved'), isNull);
      expect(await store.load('new'), 'restored new draft');
    });
  });
}
