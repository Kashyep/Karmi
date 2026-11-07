import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/bug_reports/bug_report_models.dart';
import 'package:karmi_app/features/bug_report/diagnostics_collector.dart';

void main() {
  group('Diagnostics allowlist and boundaries', () {
    const allowedKeys = {
      'app_version',
      'build_number',
      'git_sha',
      'os',
      'os_version',
      'device_model',
      'locale',
      'text_scale',
      'theme',
      'reduce_transparency',
      'plan',
      'screen',
      'recent_request_ids',
      'recent_error_codes',
      'run_id',
      'error_code',
    };

    test('allowlist contains exactly the 16 contract keys', () {
      expect(allowedKeys.length, 16);
      expect(BugReportDiagnostics.allowedKeys, unorderedEquals(allowedKeys));
    });

    test('serialized JSON contains ONLY keys from the allowlist', () {
      final diag = BugReportDiagnostics(
        appVersion: '0.1.0',
        buildNumber: '5',
        gitSha: 'abc1234',
        os: 'android',
        osVersion: '16',
        deviceModel: 'Pixel 9a',
        locale: 'en-IN',
        textScale: 1.0,
        theme: 'dark',
        reduceTransparency: false,
        plan: 'ananta',
        screen: 'chat',
        recentRequestIds: ['req-1', 'req-2'],
        recentErrorCodes: ['timeout'],
        runId: 'run-99',
        errorCode: 'ERR_TIMEOUT',
      );

      final json = diag.toJson();
      for (final key in json.keys) {
        expect(
          allowedKeys.contains(key),
          isTrue,
          reason: 'Key $key not allowlisted',
        );
      }
      expect(json.keys.length, 16);
    });

    test('unknown keys cannot be added to diagnostics serialization', () {
      final diag = BugReportDiagnostics();
      final json = diag.toJson();
      // No extra user info, messages, prompts, tokens, emails
      expect(json.containsKey('user_id'), isFalse);
      expect(json.containsKey('email'), isFalse);
      expect(json.containsKey('message_text'), isFalse);
      expect(json.containsKey('prompt'), isFalse);
      expect(json.containsKey('token'), isFalse);
    });

    test('string fields are capped to 128 characters', () {
      final longString = 'a' * 200;
      final diag = BugReportDiagnostics(
        appVersion: longString,
        deviceModel: longString,
        screen: longString,
      );

      expect(diag.appVersion!.length, 128);
      expect(diag.deviceModel!.length, 128);
      expect(diag.screen!.length, 128);
    });

    test('string fields truncate on code-point boundaries without splitting surrogates', () {
      // 127 ASCII chars + 2 emoji (each emoji is 2 UTF-16 code units / 1 code point)
      // Total: 129 code points, 131 UTF-16 code units.
      final str = '${'a' * 127}🎉🔥';
      final diag = BugReportDiagnostics(screen: str);
      // Should retain 128 code points: 127 'a's + '🎉'
      expect(diag.screen!.runes.length, 128);
      expect(diag.screen!.endsWith('🎉'), isTrue);
      // And neither surrogate half is left isolated
      expect(diag.screen!.contains('\uD83C'), isTrue); // high surrogate
      expect(diag.screen!.contains('\uDF89'), isTrue); // low surrogate
    });

    test(
      'list fields are capped to 10 items and each item capped to 128 chars',
      () {
        final longLists = List.generate(20, (i) => 'item-$i-${'x' * 150}');
        final diag = BugReportDiagnostics(
          recentRequestIds: longLists,
          recentErrorCodes: longLists,
        );

        expect(diag.recentRequestIds!.length, 10);
        expect(diag.recentErrorCodes!.length, 10);
        for (final item in diag.recentRequestIds!) {
          expect(item.length, lessThanOrEqualTo(128));
        }
      },
    );

    test('toDisplayEntries matches the exact serialized values', () {
      final diag = BugReportDiagnostics(
        appVersion: '0.1.0',
        buildNumber: '5',
        os: 'android',
        textScale: 1.25,
        reduceTransparency: true,
        recentRequestIds: ['req-abc', 'req-def'],
      );

      final entries = diag.toDisplayEntries();
      final entryMap = {for (final e in entries) e.key: e.value};
      final json = diag.toJson();

      for (final entry in json.entries) {
        expect(entryMap.containsKey(entry.key), isTrue);
        expect(entryMap[entry.key], entry.value.toString());
      }
    });

    test('collector captures platform and context info cleanly', () {
      final collector = const DiagnosticsCollector(
        appVersion: '1.0.0',
        buildNumber: '42',
      );
      final diag = collector.collect(screen: 'settings', errorCode: 'ERR_TEST');

      expect(diag.appVersion, '1.0.0');
      expect(diag.buildNumber, '42');
      expect(diag.screen, 'settings');
      expect(diag.errorCode, 'ERR_TEST');
    });
  });
}
