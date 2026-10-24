import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/admin/admin_api.dart';
import 'package:karmi_app/features/admin/admin_support.dart';

void main() {
  test('network failure shows connection copy', () {
    expect(
      adminErrorMessage(const AdminFailure.network()),
      'No connection to Karmi. Check your network and try again.',
    );
  });

  test('timeout failure shows slow-server copy', () {
    expect(
      adminErrorMessage(const AdminFailure.timeout()),
      'The server took too long to respond.',
    );
  });

  test('server failure shows the HTTP status', () {
    expect(
      adminErrorMessage(const AdminFailure(503)),
      'Karmi server error (HTTP 503).',
    );
  });

  test('bad body shows unexpected-response copy', () {
    expect(
      adminErrorMessage(const AdminFailure.badResponse(200)),
      'Karmi returned an unexpected response.',
    );
  });

  test('failure without a category keeps the generic copy', () {
    expect(
      adminErrorMessage(const AdminFailure()),
      "Karmi couldn't complete that. Try again.",
    );
  });

  test('unknown errors keep the generic copy and never leak raw text', () {
    expect(
      adminErrorMessage(StateError('secret internals')),
      "Karmi couldn't complete that. Try again.",
    );
  });

  test('existing typed failures keep their copy', () {
    expect(
      adminErrorMessage(const AdminForbidden()),
      'Admin access is no longer available.',
    );
    expect(
      adminErrorMessage(const AdminUnauthorized()),
      'The admin session ended. Sign in again to continue.',
    );
    expect(
      adminErrorMessage(const AdminLockedOut(Duration(seconds: 60))),
      'Admin is locked after too many attempts.',
    );
  });
}
