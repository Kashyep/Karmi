import 'dart:async';

import '../../api/bug_reports/bug_report_errors.dart';
import '../../api/bug_reports/bug_report_models.dart';
import '../../api/bug_reports/bug_reports_api.dart';
import 'bug_report_queue.dart';
import 'error_mapping.dart';

enum BugReportSubmissionStatus {
  success,
  queuedOffline,
  rateLimited,
  rejected,
  conflict;

  static const BugReportSubmissionStatus submitted = success;
  static const BugReportSubmissionStatus queued = queuedOffline;
}

/// Result of submitting a bug report.
class BugReportSubmissionResult {
  const BugReportSubmissionResult._({
    required this.status,
    required this.userMessage,
    this.ticket,
    this.reportStatus,
    this.retryAfterSeconds,
  });

  factory BugReportSubmissionResult.success({
    required String ticket,
    required String status,
  }) {
    return BugReportSubmissionResult._(
      status: BugReportSubmissionStatus.success,
      ticket: ticket,
      reportStatus: status,
      userMessage: 'Bug report submitted successfully.',
    );
  }

  const BugReportSubmissionResult.submitted({
    String ticket = 'KARMI-0001',
    String? status,
    String? reportStatus,
  }) : this._(
         status: BugReportSubmissionStatus.success,
         ticket: ticket,
         reportStatus: reportStatus ?? status ?? 'new',
         userMessage: 'Bug report submitted successfully.',
       );

  factory BugReportSubmissionResult.queued({required String userMessage}) {
    return BugReportSubmissionResult._(
      status: BugReportSubmissionStatus.queuedOffline,
      userMessage: userMessage,
    );
  }

  factory BugReportSubmissionResult.rateLimited({
    required String userMessage,
    required int retryAfterSeconds,
  }) {
    return BugReportSubmissionResult._(
      status: BugReportSubmissionStatus.rateLimited,
      userMessage: userMessage,
      retryAfterSeconds: retryAfterSeconds,
    );
  }

  factory BugReportSubmissionResult.rejected({required String userMessage}) {
    return BugReportSubmissionResult._(
      status: BugReportSubmissionStatus.rejected,
      userMessage: userMessage,
    );
  }

  factory BugReportSubmissionResult.conflict({required String userMessage}) {
    return BugReportSubmissionResult._(
      status: BugReportSubmissionStatus.conflict,
      userMessage: userMessage,
    );
  }

  final BugReportSubmissionStatus status;
  final String userMessage;
  final String? ticket;
  final String? reportStatus;
  final int? retryAfterSeconds;

  bool get isSuccess => status == BugReportSubmissionStatus.success;
  bool get isQueued => status == BugReportSubmissionStatus.queuedOffline;
}

/// Service that coordinates bug report submissions, offline persistence, and retries.
class BugReportService {
  BugReportService({required this.api, required this.queue, this.userId});

  final BugReportsApi api;
  final BugReportQueue queue;
  final String? userId;

  /// Submits a bug report, enqueuing it first to ensure offline durability and idempotency.
  Future<BugReportSubmissionResult> submit(
    BugReportCreateRequest request, {
    String? userId,
  }) async {
    final effectiveUserId = userId ?? this.userId;
    if (effectiveUserId == null || effectiveUserId.isEmpty) {
      return BugReportSubmissionResult.rejected(
        userMessage: 'Sign in again to send reports',
      );
    }
    // 1. Enqueue exact payload first (with same client_report_id)
    await queue.enqueue(request, userId: effectiveUserId);
    // 2. Attempt API submission
    try {
      final created = await api.submitBugReport(request);
      // Success (201 or 200 replay): remove from queue
      await queue.remove(request.clientReportId);
      return BugReportSubmissionResult.success(
        ticket: created.ticket,
        status: created.status,
      );
    } on BugReportConflictException catch (e) {
      // 409 conflict: drop from retry and surface plain words
      await queue.markRejected(request.clientReportId, e.toString());
      return BugReportSubmissionResult.conflict(
        userMessage: mapBugReportErrorToPlainWords(e),
      );
    } on BugReportRateLimitException catch (e) {
      // 429: keep queued with Retry-After window
      await queue.recordRetryAfter(request.clientReportId, e.retryAfterSeconds);
      return BugReportSubmissionResult.rateLimited(
        userMessage: mapBugReportErrorToPlainWords(e),
        retryAfterSeconds: e.retryAfterSeconds,
      );
    } on BugReportPayloadTooLargeException catch (e) {
      // 413: drop from automatic retry and show plain message
      await queue.markRejected(request.clientReportId, e.toString());
      return BugReportSubmissionResult.rejected(
        userMessage: mapBugReportErrorToPlainWords(e),
      );
    } on BugReportUnsupportedMediaTypeException catch (e) {
      // 415: drop from automatic retry
      await queue.markRejected(request.clientReportId, e.toString());
      return BugReportSubmissionResult.rejected(
        userMessage: mapBugReportErrorToPlainWords(e),
      );
    } on BugReportValidationException catch (e) {
      // 422: drop from automatic retry
      await queue.markRejected(request.clientReportId, e.toString());
      return BugReportSubmissionResult.rejected(
        userMessage: mapBugReportErrorToPlainWords(e),
      );
    } on NetworkException catch (e) {
      // Network offline: keeps entry queued
      return BugReportSubmissionResult.queued(
        userMessage: mapBugReportErrorToPlainWords(e),
      );
    } on ApiTimeoutException catch (e) {
      await queue.incrementRetry(request.clientReportId);
      return BugReportSubmissionResult.queued(
        userMessage: mapBugReportErrorToPlainWords(e),
      );
    } on ServerException catch (e) {
      if (e.statusCode == 413 ||
          e.statusCode == 415 ||
          e.statusCode == 422 ||
          e.statusCode == 409) {
        await queue.markRejected(request.clientReportId, e.toString());
        return BugReportSubmissionResult.rejected(
          userMessage: mapBugReportErrorToPlainWords(e),
        );
      }
      await queue.incrementRetry(request.clientReportId);
      return BugReportSubmissionResult.queued(
        userMessage: mapBugReportErrorToPlainWords(e),
      );
    } catch (e) {
      await queue.incrementRetry(request.clientReportId);
      return BugReportSubmissionResult.rejected(
        userMessage: mapBugReportErrorToPlainWords(e),
      );
    }
  }

  /// Flushes eligible pending reports in the offline queue for the active user session.
  /// Returns the number of successfully submitted reports.
  Future<int> flushQueue({String? userId}) async {
    final effectiveUserId = userId ?? this.userId;
    if (effectiveUserId == null || effectiveUserId.isEmpty) return 0;
    int sentCount = 0;
    final eligible = await queue.getEligibleItems(userId: effectiveUserId);
    for (final item in eligible) {
      try {
        final request = await queue.resolveRequest(item);
        final created = await api.submitBugReport(request);
        if (created.ticket.isNotEmpty) {
          await queue.remove(item.clientReportId);
          sentCount++;
        }
        await queue.recordRetryAfter(item.clientReportId, e.retryAfterSeconds);
        // Break early since we are rate limited
        break;
      } on BugReportConflictException catch (e) {
        await queue.markRejected(item.clientReportId, e.toString());
      } on BugReportPayloadTooLargeException catch (e) {
        await queue.markRejected(item.clientReportId, e.toString());
      } on BugReportUnsupportedMediaTypeException catch (e) {
        await queue.markRejected(item.clientReportId, e.toString());
      } on BugReportValidationException catch (e) {
        await queue.markRejected(item.clientReportId, e.toString());
      } on NetworkException {
        // Still offline, stop flushing
        break;
      } on ApiTimeoutException {
        await queue.incrementRetry(item.clientReportId);
      } on ServerException catch (e) {
        if (e.statusCode == 413 ||
            e.statusCode == 415 ||
            e.statusCode == 422 ||
            e.statusCode == 409) {
          await queue.markRejected(item.clientReportId, e.toString());
        } else {
          await queue.incrementRetry(item.clientReportId);
        }
      } on FormatException catch (e) {
        await queue.markRejected(item.clientReportId, e.toString());
      } on TypeError catch (e) {
        await queue.markRejected(item.clientReportId, e.toString());
      } on ArgumentError catch (e) {
        await queue.markRejected(item.clientReportId, e.toString());
      } catch (_) {
        await queue.incrementRetry(item.clientReportId);
      }
    }
    return sentCount;
  }
}
