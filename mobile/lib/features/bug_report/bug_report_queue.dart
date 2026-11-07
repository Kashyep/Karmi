import 'dart:async';
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
  BugReportCreateRequest toRequest([BugReportScreenshot? screenshot]) {
    final map = Map<String, dynamic>.from(payload);
    if (screenshot != null) {
      map['screenshot'] = screenshot.toJson();
    }
    return BugReportCreateRequest.fromJson(map);
  }
}

/// Single-lane async lock to serialize read-modify-write queue operations.
class _AsyncLock {
  Future<void> _last = Future.value();

  Future<T> synchronized<T>(Future<T> Function() callback) {
    final completer = Completer<T>();
    _last = _last.then((_) async {
      try {
        final result = await callback();
        completer.complete(result);
      } catch (e, st) {
        completer.completeError(e, st);
      }
    });
    return completer.future;
  }
}

/// Persistent offline queue backed by [SharedPreferences].
class BugReportQueue {
  BugReportQueue({SharedPreferences? prefs}) : _prefs = prefs;

  static const String prefKey = 'karmi_bug_report_offline_queue';
  static const String screenshotPrefix = 'karmi_bug_report_screenshot_';
  static final _AsyncLock _globalLock = _AsyncLock();

  SharedPreferences? _prefs;

  static String screenshotPrefKey(String clientReportId) =>
      '$screenshotPrefix$clientReportId';

  Future<SharedPreferences> _getPrefs() async {
    _prefs ??= await SharedPreferences.getInstance();
    return _prefs!;
  }

  Future<List<BugReportQueueItem>> _loadAllUnlocked() async {
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

  Future<void> _saveAllUnlocked(List<BugReportQueueItem> items) async {
    final prefs = await _getPrefs();
    final serialized = items.map((item) => jsonEncode(item.toJson())).toList();
    await prefs.setStringList(prefKey, serialized);
  }

  /// Resolves the full [BugReportCreateRequest] including any separately stored screenshot.
  Future<BugReportCreateRequest> resolveRequest(BugReportQueueItem item) async {
    final prefs = await _getPrefs();
    final rawScreenshot = prefs.getString(screenshotPrefKey(item.clientReportId));
    final payload = Map<String, dynamic>.from(item.payload);
    if (rawScreenshot != null && !payload.containsKey('screenshot')) {
      try {
        payload['screenshot'] =
            jsonDecode(rawScreenshot) as Map<String, dynamic>;
      } catch (_) {}
    }
    return BugReportCreateRequest.fromJson(payload);
  }

  /// Loads all items in the queue from storage.
  Future<List<BugReportQueueItem>> loadAll() =>
      _globalLock.synchronized(_loadAllUnlocked);

  /// Enqueues a report payload.
  ///
  /// Guarantees that each queued entry stores the exact payload and client_report_id
  /// without re-generating or altering them. Screenshots are stored under a separate
  /// key to avoid rewriting large base64 blobs on routine queue mutations.
  Future<void> enqueue(BugReportCreateRequest request) async {
    return _globalLock.synchronized(() async {
      final prefs = await _getPrefs();
      final items = await _loadAllUnlocked();

      // Separate screenshot storage to keep queue list mutations fast and small
      final scKey = screenshotPrefKey(request.clientReportId);
      if (request.screenshot != null) {
        await prefs.setString(scKey, jsonEncode(request.screenshot!.toJson()));
      } else {
        await prefs.remove(scKey);
      }

      final payloadWithoutScreenshot =
          Map<String, dynamic>.from(request.toJson());
      payloadWithoutScreenshot.remove('screenshot');

      final index = items.indexWhere(
        (i) => i.clientReportId == request.clientReportId,
      );
      if (index >= 0) {
        final existingItem = items[index];
        final existingRawScreenshot = prefs.getString(scKey);
        final newScreenshotJson = request.screenshot != null
            ? jsonEncode(request.screenshot!.toJson())
            : null;
        final payloadChanged = jsonEncode(existingItem.payload) !=
            jsonEncode(payloadWithoutScreenshot);
        final screenshotChanged = existingRawScreenshot != newScreenshotJson;

        if (payloadChanged || screenshotChanged) {
          items[index] = BugReportQueueItem(
            clientReportId: request.clientReportId,
            payload: payloadWithoutScreenshot,
            createdAt: DateTime.now().toUtc(),
          );
          await _saveAllUnlocked(items);
        }
        return;
      }
      items.add(
        BugReportQueueItem(
          clientReportId: request.clientReportId,
          payload: payloadWithoutScreenshot,
          createdAt: DateTime.now().toUtc(),
        ),
      );
      await _saveAllUnlocked(items);
    });
  }

  /// Returns items eligible for automatic retrying (not rejected).
  Future<List<BugReportQueueItem>> getEligibleItems() async {
    return _globalLock.synchronized(() async {
      final items = await _loadAllUnlocked();
      final now = DateTime.now().toUtc();
      return items.where((item) {
        if (item.isRejected) return false;
        if (item.retryAfterUntil != null && item.retryAfterUntil!.isAfter(now)) {
          return false;
        }
        return true;
      }).toList();
    });
  }

  /// Alias for [loadAll].
  Future<List<BugReportQueueItem>> getAll() => loadAll();

  /// Returns all active pending items (not marked as rejected).
  Future<List<BugReportQueueItem>> getPending() async {
    return _globalLock.synchronized(() async {
      final items = await _loadAllUnlocked();
      return items.where((i) => !i.isRejected).toList();
    });
  }

  /// Removes an item once successfully submitted or manually cleared.
  Future<void> remove(String clientReportId) async {
    return _globalLock.synchronized(() async {
      final prefs = await _getPrefs();
      final items = await _loadAllUnlocked();
      items.removeWhere((i) => i.clientReportId == clientReportId);
      await prefs.remove(screenshotPrefKey(clientReportId));
      await _saveAllUnlocked(items);
    });
  }

  /// Drops a rejected item so it is not retained indefinitely in storage (e.g. 413, 415, 422, 409).
  Future<void> markRejected(String clientReportId, String reason) async {
    return _globalLock.synchronized(() async {
      final prefs = await _getPrefs();
      final items = await _loadAllUnlocked();
      items.removeWhere((i) => i.clientReportId == clientReportId);
      await prefs.remove(screenshotPrefKey(clientReportId));
      await _saveAllUnlocked(items);
    });
  }

  /// Records a 429 rate limit reset timestamp.
  Future<void> recordRetryAfter(String clientReportId, int seconds) async {
    return _globalLock.synchronized(() async {
      final items = await _loadAllUnlocked();
      final index = items.indexWhere((i) => i.clientReportId == clientReportId);
      if (index >= 0) {
        final resetTime =
            DateTime.now().toUtc().add(Duration(seconds: seconds));
        items[index] = items[index].copyWith(retryAfterUntil: resetTime);
        await _saveAllUnlocked(items);
      }
    });
  }

  /// Alias for [recordRetryAfter].
  Future<void> setRateLimit(String clientReportId, int seconds) =>
      recordRetryAfter(clientReportId, seconds);

  /// Increments the retry count for backoff.
  Future<void> incrementRetry(String clientReportId) async {
    return _globalLock.synchronized(() async {
      final items = await _loadAllUnlocked();
      final index = items.indexWhere((i) => i.clientReportId == clientReportId);
      if (index >= 0) {
        items[index] = items[index].copyWith(
          retryCount: items[index].retryCount + 1,
        );
        await _saveAllUnlocked(items);
      }
    });
  }

  /// Clears the entire queue including separate screenshot entries.
  Future<void> clear() async {
    return _globalLock.synchronized(() async {
      final prefs = await _getPrefs();
      final items = await _loadAllUnlocked();
      for (final item in items) {
        await prefs.remove(screenshotPrefKey(item.clientReportId));
      }
      await prefs.remove(prefKey);
    });
  }
}
