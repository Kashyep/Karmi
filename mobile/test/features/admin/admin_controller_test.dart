import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/admin/admin_api.dart';
import 'package:karmi_app/features/admin/admin_controller.dart';

import '../../support/fake_admin_api.dart';

void main() {
  test('probe 403 marks not eligible and hides the entry', () async {
    final api = FakeAdminApi(forbidden: true);
    final c = AdminController(api: api);
    await c.probe();
    expect(c.eligibility, AdminEligibility.notAdmin);
    expect(c.canEnter, isFalse);
  });

  test('probe success marks eligible', () async {
    final c = AdminController(api: FakeAdminApi());
    await c.probe();
    expect(c.eligibility, AdminEligibility.eligible);
    expect(c.canEnter, isTrue);
  });

  test('probe network failure stays unknown and hidden', () async {
    final api = FakeAdminApi()..failNext = const AdminFailure(500);
    final c = AdminController(api: api);
    await c.probe();
    expect(c.eligibility, AdminEligibility.unknown);
    expect(c.canEnter, isFalse);
  });

  test('verifyCode sets token and active state, notifies listeners', () async {
    final c = AdminController(api: FakeAdminApi());
    var notified = 0;
    c.addListener(() => notified++);
    await c.verifyCode('123456');
    expect(c.isActive, isTrue);
    expect(c.token, isNotNull);
    expect(c.expiresAt, isNotNull);
    expect(notified, greaterThan(0));
    c.reset();
  });

  test('wrong code throws AdminUnauthorized and stays inactive', () async {
    final c = AdminController(api: FakeAdminApi());
    await expectLater(
      c.verifyCode('000000'),
      throwsA(isA<AdminUnauthorized>()),
    );
    expect(c.isActive, isFalse);
    expect(c.token, isNull);
  });

  test('lockout throws AdminLockedOut with the retry duration', () async {
    final api = FakeAdminApi()..lockedOut = const Duration(minutes: 5);
    final c = AdminController(api: api);
    await expectLater(
      c.verifyCode('123456'),
      throwsA(
        isA<AdminLockedOut>().having(
          (e) => e.retryAfter,
          'retryAfter',
          const Duration(minutes: 5),
        ),
      ),
    );
    expect(c.isActive, isFalse);
  });

  test('forbidden on verifyCode marks not eligible and rethrows', () async {
    final api = FakeAdminApi(forbidden: true);
    final c = AdminController(api: api);
    await expectLater(c.verifyCode('123456'), throwsA(isA<AdminForbidden>()));
    expect(c.eligibility, AdminEligibility.notAdmin);
  });

  test('logout clears token and calls closeSession on the api', () async {
    final api = FakeAdminApi();
    final c = AdminController(api: api);
    await c.verifyCode('123456');
    await c.logout();
    expect(c.isActive, isFalse);
    expect(c.token, isNull);
    expect(api.calls.any((call) => call.startsWith('close:')), isTrue);
  });

  test('sessionLost clears token without a server call', () async {
    final api = FakeAdminApi();
    final c = AdminController(api: api);
    await c.verifyCode('123456');
    var notified = 0;
    c.addListener(() => notified++);
    c.sessionLost();
    expect(c.isActive, isFalse);
    expect(c.token, isNull);
    expect(notified, 1);
    expect(api.calls.any((call) => call.startsWith('close:')), isFalse);
  });

  test('reset clears session and eligibility', () async {
    final c = AdminController(api: FakeAdminApi());
    await c.probe();
    await c.verifyCode('123456');
    c.reset();
    expect(c.isActive, isFalse);
    expect(c.token, isNull);
    expect(c.eligibility, AdminEligibility.unknown);
    expect(c.canEnter, isFalse);
  });

  test('expiry ends the session and notifies listeners', () {
    fakeAsync((async) {
      final api = FakeAdminApi(sessionTtl: const Duration(minutes: 1));
      final c = AdminController(api: api);
      var notified = 0;
      c.addListener(() => notified++);

      c.verifyCode('123456');
      async.flushMicrotasks();
      expect(c.isActive, isTrue);

      async.elapse(const Duration(minutes: 2));
      expect(c.isActive, isFalse);
      expect(c.token, isNull);
      expect(notified, greaterThanOrEqualTo(2));
      c.dispose();
    });
  });
}
