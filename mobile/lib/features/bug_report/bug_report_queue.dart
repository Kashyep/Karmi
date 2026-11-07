import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

import '../../api/bug_reports/bug_report_models.dart';

/// Single item stored in the persistent offline bug report queue.
class BugReportQueueItem {
  BugReportQueueItem({
    required this.clientReportId,
    required this.payload,
    required this.createdAt,
    this.retryCount = 0,
    this.retryAfterUntil,
    this.isRejected = false,
    this.rejectionReason,
  });

  final String clientReportId;
  final Map<String, dynamic> payload;
  final DateTime createdAt;
  final int retryCount;
  final DateTime? retryAfterUntil;
  final bool isRejected;
  final String? rejectionReason;

  bool get isRateLimited {
    if (retryAfterUntil == null) return false;
    return retryAfterUntil!.isAfter(DateTime.now().toUtc());
  }

  int get retryAfterRemainingSeconds {
    if (retryAfterUntil == null) return 0;
    final diff = retryAfterUntil!.difference(DateTime.now().toUtc()).inSeconds;
    return diff > 0 ? diff : 0;
  }

  BugReportQueueItem copyWith({
    int? retryCount,
    DateTime? retryAfterUntil,
    bool? isRejected,
    String? rejectionReason,
  }) {
    return BugReportQueueItem(
      clientReportId: clientReportId,
      payload: payload,
      createdAt: createdAt,
      retryCount: retryCount ?? this.retryCount,
      retryAfterUntil: retryAfterUntil ?? this.retryAfterUntil,
      isRejected: isRejected ?? this.isRejected,
      rejectionReason: rejectionReason ?? this.rejectionReason,
    );
  }

  Map<String, dynamic> toJson() => {
    'client_report_id': clientReportId,
    'payload': payload,
    'created_at': createdAt.toIso8601String(),
    'retry_count': retryCount,
    if (retryAfterUntil != null)
      'retry_after_until': retryAfterUntil!.toIso8601String(),
    'is_rejected': isRejected,
    if (rejectionReason != null) 'rejection_reason': rejectionReason,
  };

  factory BugReportQueueItem.fromJson(Map<String, dynamic> json) {
    return BugReportQueueItem(
      clientReportId: json['client_report_id'] as String,
      payload: Map<String, dynamic>.from(json['payload'] as Map),
      createdAt: DateTime.parse(json['created_at'] as String),
      retryCount: json['retry_count'] as int? ?? 0,
      retryAfterUntil: json['retry_after_until'] != null
          ? DateTime.parse(json['retry_after_until'] as String)
          : null,
      isRejected: json['is_rejected'] as bool? ?? false,
      rejectionReason: json['rejection_reason'] as String?,
    );
  }

  /// Converts the stored payload back into a [BugReportCreateRequest].
  BugReportCreateRequest toRequest() {
    return BugReportCreateRequest.fromJson(payload);
  }
}

/// Persistent offline queue backed by [SharedPreferences].
class BugReportQueue {
  BugReportQueue({SharedPreferences? prefs}) : _prefs = prefs;

  static const String prefKey = 'karmi_bug_report_offline_queue';
  SharedPreferences? _prefs;

  Future<SharedPreferences> _getPrefs() async {
    _prefs ??= await SharedPreferences.getInstance();
    return _prefs!;
  }

  /// Loads all items in the queue from storage.
  Future<List<BugReportQueueItem>> loadAll() async {
    final prefs = await _getPrefs();
    final rawList = prefs.getStringList(prefKey) ?? [];
    final items = <BugReportQueueItem>[];
    for (final raw in rawList) {
      try {
        final decoded = jsonDecode(raw) as Map<String, dynamic>;
        items.add(BugReportQueueItem.fromJson(decoded));
      } catch (_) {}
    }
    return items;
  }

  /// Saves the complete list back to [SharedPreferences].
  Future<void> _saveAll(List<BugReportQueueItem> items) async {
    final prefs = await _getPrefs();
    final serialized = items.map((item) => jsonEncode(item.toJson())).toList();
    await prefs.setStringList(prefKey, serialized);
  }

  /// Enqueues a report payload.
  ///
  /// Guarantees that each queued entry stores the exact payload and client_report_id
  /// without re-generating or altering them.
  Future<void> enqueue(BugReportCreateRequest request) async {
    final items = await loadAll();
    final index = items.indexWhere(
      (i) => i.clientReportId == request.clientReportId,
    );
    if (index >= 0) {
      // Already queued with this client_report_id; preserve the exact existing payload
      return;
    }
    items.add(
      BugReportQueueItem(
        clientReportId: request.clientReportId,
        payload: request.toJson(),
        createdAt: DateTime.now().toUtc(),
      ),
    );
    await _saveAll(items);
  }

  /// Returns items eligible for automatic retrying (not rejected).
  Future<List<BugReportQueueItem>> getEligibleItems() async {
    final items = await loadAll();
    final now = DateTime.now().toUtc();
    return items.where((item) {
      if (item.isRejected) return false;
      if (item.retryAfterUntil != null && item.retryAfterUntil!.isAfter(now)) {
        return false;
      }
      return true;
    }).toList();
  }

  /// Alias for [loadAll].
  Future<List<BugReportQueueItem>> getAll() => loadAll();

  /// Returns all active pending items (not marked as rejected).
  Future<List<BugReportQueueItem>> getPending() async {
    final items = await loadAll();
    return items.where((i) => !i.isRejected).toList();
  }

  /// Removes an item once successfully submitted or manually cleared.
  Future<void> remove(String clientReportId) async {
    final items = await loadAll();
    items.removeWhere((i) => i.clientReportId == clientReportId);
    await _saveAll(items);
  }

  /// Marks an item rejected so it is dropped from automatic retries (e.g. 413, 415, 422).
  Future<void> markRejected(String clientReportId, String reason) async {
    final items = await loadAll();
    final index = items.indexWhere((i) => i.clientReportId == clientReportId);
    if (index >= 0) {
      items[index] = items[index].copyWith(
        isRejected: true,
        rejectionReason: reason,
      );
      await _saveAll(items);
    }
  }

  /// Records a 429 rate limit reset timestamp.
  Future<void> recordRetryAfter(String clientReportId, int seconds) async {
    final items = await loadAll();
    final index = items.indexWhere((i) => i.clientReportId == clientReportId);
    if (index >= 0) {
      final resetTime = DateTime.now().toUtc().add(Duration(seconds: seconds));
      items[index] = items[index].copyWith(retryAfterUntil: resetTime);
      await _saveAll(items);
    }
  }

  /// Alias for [recordRetryAfter].
  Future<void> setRateLimit(String clientReportId, int seconds) =>
      recordRetryAfter(clientReportId, seconds);

  /// Increments the retry count for backoff.
  Future<void> incrementRetry(String clientReportId) async {
    final items = await loadAll();
    final index = items.indexWhere((i) => i.clientReportId == clientReportId);
    if (index >= 0) {
      items[index] = items[index].copyWith(
        retryCount: items[index].retryCount + 1,
      );
      await _saveAll(items);
    }
  }

  /// Clears the entire queue.
  Future<void> clear() async {
    final prefs = await _getPrefs();
    await prefs.remove(prefKey);
  }
}
