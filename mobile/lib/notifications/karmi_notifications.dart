import 'dart:async';
import 'dart:ui' show Color;

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

/// Testable adapter wrapping the underlying notification plugin/platform calls.
abstract interface class NotificationPlatformAdapter {
  Future<bool?> initialize({required InitializationSettings settings});

  Future<bool> requestPermission();

  Future<void> show({
    required int id,
    String? title,
    String? body,
    NotificationDetails? notificationDetails,
  });
}

/// Production implementation of [NotificationPlatformAdapter] delegating to
/// [FlutterLocalNotificationsPlugin].
class DefaultNotificationPlatformAdapter
    implements NotificationPlatformAdapter {
  DefaultNotificationPlatformAdapter([FlutterLocalNotificationsPlugin? plugin])
    : _plugin = plugin ?? FlutterLocalNotificationsPlugin();

  final FlutterLocalNotificationsPlugin _plugin;

  @override
  Future<bool?> initialize({required InitializationSettings settings}) async {
    final result = await _plugin.initialize(settings: settings);
    final androidPlugin = _plugin
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();
    if (androidPlugin != null) {
      const channel = AndroidNotificationChannel(
        KarmiNotifications.channelId,
        KarmiNotifications.channelName,
        description: KarmiNotifications.channelDescription,
        importance: Importance.high,
      );
      await androidPlugin.createNotificationChannel(channel);
    }
    return result;
  }

  @override
  Future<bool> requestPermission() async {
    final androidPlugin = _plugin
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();
    if (androidPlugin != null) {
      final granted = await androidPlugin.requestNotificationsPermission();
      return granted ?? false;
    }

    final iosPlugin = _plugin
        .resolvePlatformSpecificImplementation<
          IOSFlutterLocalNotificationsPlugin
        >();
    if (iosPlugin != null) {
      final granted = await iosPlugin.requestPermissions(
        alert: true,
        badge: true,
        sound: true,
      );
      return granted ?? false;
    }

    final macosPlugin = _plugin
        .resolvePlatformSpecificImplementation<
          MacOSFlutterLocalNotificationsPlugin
        >();
    if (macosPlugin != null) {
      final granted = await macosPlugin.requestPermissions(
        alert: true,
        badge: true,
        sound: true,
      );
      return granted ?? false;
    }

    return false;
  }

  @override
  Future<void> show({
    required int id,
    String? title,
    String? body,
    NotificationDetails? notificationDetails,
  }) {
    return _plugin.show(
      id: id,
      title: title,
      body: body,
      notificationDetails: notificationDetails,
    );
  }
}

/// Manages local notifications for Karmi chat replies and permissions.
class KarmiNotifications {
  KarmiNotifications({NotificationPlatformAdapter? adapter})
    : _adapter = adapter ?? DefaultNotificationPlatformAdapter();

  static const String channelId = 'karmi_chat_replies';
  static const String channelName = 'Chat Replies';
  static const String channelDescription =
      'Notifications for Karmi assistant replies';

  static const _androidDetails = AndroidNotificationDetails(
    channelId,
    channelName,
    channelDescription: channelDescription,
    importance: Importance.high,
    priority: Priority.high,
    icon: 'ic_stat_karmi',
    color: Color(0xFF2BB39A),
  );

  static const _darwinDetails = DarwinNotificationDetails(
    presentAlert: true,
    presentBadge: true,
    presentSound: true,
  );

  static const _notificationDetails = NotificationDetails(
    android: _androidDetails,
    iOS: _darwinDetails,
    macOS: _darwinDetails,
  );

  /// Global singleton instance.
  static final KarmiNotifications instance = KarmiNotifications();

  final NotificationPlatformAdapter _adapter;
  bool _initialized = false;

  /// Idempotent; safe to call before runApp completes; never throws.
  Future<void> init() async {
    if (_initialized) return;
    try {
      const androidSettings = AndroidInitializationSettings('ic_stat_karmi');
      const darwinSettings = DarwinInitializationSettings(
        requestAlertPermission: false,
        requestBadgePermission: false,
        requestSoundPermission: false,
      );
      const initSettings = InitializationSettings(
        android: androidSettings,
        iOS: darwinSettings,
        macOS: darwinSettings,
      );
      await _adapter
          .initialize(settings: initSettings)
          .timeout(const Duration(seconds: 3));
      _initialized = true;
    } catch (e, st) {
      debugPrint('KarmiNotifications.init failed: $e\n$st');
    }
  }

  /// Shows Android 13+ POST_NOTIFICATIONS / iOS prompt; true if granted
  /// (pre-13 Android: true if enabled).
  Future<bool> requestPermission() async {
    try {
      return await _adapter.requestPermission();
    } catch (e, st) {
      debugPrint('KarmiNotifications.requestPermission failed: $e\n$st');
      return false;
    }
  }

  /// Shows a notification when a reply is ready.
  Future<void> notifyReplyReady({
    required String conversationId,
    required String body,
  }) async {
    try {
      final snippet = formatSnippet(body);
      final id = _notificationIdFor(conversationId);
      await _adapter.show(
        id: id,
        title: 'Karmi replied',
        body: snippet,
        notificationDetails: _notificationDetails,
      );
    } catch (e, st) {
      debugPrint('KarmiNotifications.notifyReplyReady failed: $e\n$st');
    }
  }

  /// Shows a notification when a reply fails.
  Future<void> notifyReplyFailed({required String conversationId}) async {
    try {
      final id = _notificationIdFor(conversationId);
      await _adapter.show(
        id: id,
        title: "Karmi couldn't finish a reply",
        body: null,
        notificationDetails: _notificationDetails,
      );
    } catch (e, st) {
      debugPrint('KarmiNotifications.notifyReplyFailed failed: $e\n$st');
    }
  }

  /// Converts markdown text into a plain-text snippet truncated to ~120 chars.
  static String formatSnippet(String markdownText) {
    var text = markdownText;
    // Fenced code blocks
    text = text.replaceAllMapped(
      RegExp(r'```[^\n]*\n([\s\S]*?)```'),
      (m) => m[1] ?? '',
    );
    // Inline code ticks
    text = text.replaceAllMapped(RegExp(r'`([^`]+)`'), (m) => m[1] ?? '');
    // Image markup
    text = text.replaceAllMapped(
      RegExp(r'!\[([^\]]*)\]\([^\)]*\)'),
      (m) => m[1] ?? '',
    );
    // Links
    text = text.replaceAllMapped(
      RegExp(r'\[([^\]]+)\]\([^\)]*\)'),
      (m) => m[1] ?? '',
    );
    // Markdown headings
    text = text.replaceAll(RegExp(r'^\s*#{1,6}\s+', multiLine: true), '');
    // Bold / italic
    text = text.replaceAllMapped(
      RegExp(r'(\*\*|__)(.*?)\1'),
      (m) => m[2] ?? '',
    );
    text = text.replaceAllMapped(RegExp(r'(\*|_)(.*?)\1'), (m) => m[2] ?? '');
    // Blockquotes & list items
    text = text.replaceAll(RegExp(r'^\s*>\s+', multiLine: true), '');
    text = text.replaceAll(RegExp(r'^\s*[-*+]\s+', multiLine: true), '');
    text = text.replaceAll(RegExp(r'^\s*\d+\.\s+', multiLine: true), '');
    // Collapse multi-whitespace & newlines
    text = text.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (text.length > 120) {
      return '${text.substring(0, 119)}…';
    }
    return text;
  }

  static int _notificationIdFor(String conversationId) {
    if (conversationId.isEmpty) return 1;
    final hash = conversationId.hashCode & 0x7FFFFFFF;
    return hash == 0 ? 1 : hash;
  }
}
