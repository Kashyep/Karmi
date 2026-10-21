import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/composer/draft_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('SharedPrefsDraftStore', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('storageKey prefixes with draft.v1.', () {
      expect(SharedPrefsDraftStore.storageKey('user_a', '123'), 'draft.v1.user_a.123');
      expect(SharedPrefsDraftStore.storageKey('user_a', 'new'), 'draft.v1.user_a.new');
    });

    test('load returns null when no draft exists', () async {
      final store = SharedPrefsDraftStore(userId: 'user_a');
      expect(await store.load('conv1'), isNull);
    });

    test('save stores text and load retrieves it', () async {
      final store = SharedPrefsDraftStore(userId: 'user_a');
      await store.save('conv1', 'hello world');
      expect(await store.load('conv1'), 'hello world');

      // Check SharedPreferences raw key directly
      final sp = await SharedPreferences.getInstance();
      expect(sp.getString('draft.v1.user_a.conv1'), 'hello world');
    });

    test('clear removes saved draft', () async {
      final store = SharedPrefsDraftStore(userId: 'user_a');
      await store.save('conv1', 'draft to clear');
      expect(await store.load('conv1'), 'draft to clear');

      await store.clear('conv1');
      expect(await store.load('conv1'), isNull);
    });
  });
}
