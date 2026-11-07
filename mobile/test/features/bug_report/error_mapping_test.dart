import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/bug_reports/bug_report_errors.dart';
import 'package:karmi_app/features/bug_report/error_mapping.dart';

void main() {
  group('Plain-words error mapping', () {
    test('429 rate limit formats Retry-After into human friendly time', () {
      expect(formatRetryAfterDuration(45), '1 minute');
      expect(formatRetryAfterDuration(60), '1 minute');
      expect(formatRetryAfterDuration(180), '3 minutes');
      expect(formatRetryAfterDuration(3600), '1 hour');
      expect(formatRetryAfterDuration(7200), '2 hours');

      final msg = formatRetryAfterMessage(3600);
      expect(msg, 'You have sent 3 reports today. Try again in 1 hour.');
      expect(msg.contains('429'), isFalse);
    });

    test('413 payload too large produces plain words without raw codes', () {
      final msg = mapBugReportErrorToMessage(
        const BugReportPayloadTooLargeException(),
      );
      expect(
        msg,
        'That screenshot is too big. Turn off the screenshot or try again.',
      );
      expect(msg.contains('413'), isFalse);
    });

    test(
      '415 unsupported media type produces plain words without raw codes',
      () {
        final msg = mapBugReportErrorToMessage(
          const BugReportUnsupportedMediaTypeException(),
        );
        expect(
          msg,
          'That screenshot type is not supported. Turn off the screenshot.',
        );
        expect(msg.contains('415'), isFalse);
      },
    );

    test('422 validation error produces plain words without raw codes', () {
      final msg = mapBugReportErrorToMessage(
        const BugReportValidationException('Unprocessable Entity'),
      );
      expect(
        msg,
        'Some details were not accepted. Please try again from the app update.',
      );
      expect(msg.contains('422'), isFalse);
      expect(msg.contains('Unprocessable'), isFalse);
    });

    test('409 conflict produces friendly message', () {
      final msg = mapBugReportErrorToMessage(
        const BugReportConflictException(),
      );
      expect(msg.contains('conflict'), isTrue);
      expect(msg.contains('409'), isFalse);
    });

    test('Network and timeout exceptions produce helpful messages', () {
      final netMsg = mapBugReportErrorToMessage(const NetworkException());
      expect(netMsg.contains('offline'), isTrue);

      final timeoutMsg = mapBugReportErrorToMessage(
        const ApiTimeoutException(),
      );
      expect(timeoutMsg.contains('too long'), isTrue);
    });
  });
}
