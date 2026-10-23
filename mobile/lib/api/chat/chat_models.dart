/// Wire types for Karmi chat and conversations.
library;

import '../debug_meta.dart';
import '../models.dart';

enum FinishReason {
  stop('stop'),
  length('length'),
  contentFilter('content_filter'),
  cancelled('cancelled'),
  interrupted('interrupted'),
  error('error');

  const FinishReason(this.wireName);

  final String wireName;

  static FinishReason? fromWire(Object? value) {
    if (value == null) return null;
    for (final reason in values) {
      if (reason.wireName == value) return reason;
    }
    return null;
  }
}

enum MessageStatus {
  complete('complete'),
  streaming('streaming'),
  stopped('stopped'),
  interrupted('interrupted'),
  failed('failed');

  const MessageStatus(this.wireName);

  final String wireName;

  static MessageStatus fromWire(Object? value) {
    for (final status in values) {
      if (status.wireName == value) return status;
    }
    return MessageStatus.failed;
  }
}

enum ErrorCategory {
  quotaExhausted('quota_exhausted'),
  capacityFull('capacity_full'),
  providerUnavailable('provider_unavailable'),
  validationFailed('validation_failed'),
  unauthorized('unauthorized'),
  resumeUnavailable('resume_unavailable'),
  internal('internal'),
  network('network');

  const ErrorCategory(this.wireName);

  final String wireName;

  static ErrorCategory? fromWire(Object? value) {
    if (value == null) return null;
    for (final category in values) {
      if (category.wireName == value) return category;
    }
    return null;
  }
}

class ConversationView {
  const ConversationView({
    required this.id,
    this.title,
    this.titleSource = 'auto',
    this.pinned = false,
    this.archivedAt,
    required this.updatedAt,
    this.lastMessageAt,
    this.messageCount = 0,
  });

  factory ConversationView.fromJson(
    Map<String, dynamic> json,
  ) => ConversationView(
    id: json['id'] as String,
    title: json['title'] as String?,
    titleSource:
        (json['titleSource'] ?? json['title_source'] as String?) ?? 'auto',
    pinned: (json['pinned'] as bool?) ?? false,
    archivedAt: (json['archivedAt'] ?? json['archived_at']) != null
        ? DateTime.parse((json['archivedAt'] ?? json['archived_at']) as String)
        : null,
    updatedAt: DateTime.parse(
      (json['updatedAt'] ?? json['updated_at']) as String,
    ),
    lastMessageAt: (json['lastMessageAt'] ?? json['last_message_at']) != null
        ? DateTime.parse(
            (json['lastMessageAt'] ?? json['last_message_at']) as String,
          )
        : null,
    messageCount: (json['messageCount'] ?? json['message_count'] as int?) ?? 0,
  );

  final String id;
  final String? title;
  final String titleSource;
  final bool pinned;
  final DateTime? archivedAt;
  final DateTime updatedAt;
  final DateTime? lastMessageAt;
  final int messageCount;

  Map<String, dynamic> toJson() => {
    'id': id,
    if (title != null) 'title': title,
    'titleSource': titleSource,
    'pinned': pinned,
    if (archivedAt != null) 'archivedAt': archivedAt!.toIso8601String(),
    'updatedAt': updatedAt.toIso8601String(),
    if (lastMessageAt != null)
      'lastMessageAt': lastMessageAt!.toIso8601String(),
    'messageCount': messageCount,
  };

  ConversationView copyWith({
    String? id,
    String? title,
    String? titleSource,
    bool? pinned,
    DateTime? archivedAt,
    DateTime? updatedAt,
    DateTime? lastMessageAt,
    int? messageCount,
  }) => ConversationView(
    id: id ?? this.id,
    title: title ?? this.title,
    titleSource: titleSource ?? this.titleSource,
    pinned: pinned ?? this.pinned,
    archivedAt: archivedAt ?? this.archivedAt,
    updatedAt: updatedAt ?? this.updatedAt,
    lastMessageAt: lastMessageAt ?? this.lastMessageAt,
    messageCount: messageCount ?? this.messageCount,
  );
}

class ChatMessageView {
  const ChatMessageView({
    required this.id,
    required this.conversationId,
    required this.role,
    required this.status,
    required this.content,
    this.finishReason,
    this.outcome,
    this.runId,
    this.parentMessageId,
    this.variantIndex = 0,
    required this.createdAt,
    required this.updatedAt,
    this.clientMessageId,
    this.debug,
  });

  factory ChatMessageView.fromJson(Map<String, dynamic> json) =>
      ChatMessageView(
        id: json['id'] as String,
        conversationId:
            (json['conversationId'] ?? json['conversation_id']) as String,
        role: json['role'] as String,
        status: MessageStatus.fromWire(json['status']),
        content: (json['content'] as String?) ?? '',
        finishReason: FinishReason.fromWire(
          json['finishReason'] ?? json['finish_reason'],
        ),
        runId: (json['runId'] ?? json['run_id']) as String?,
        parentMessageId:
            (json['parentMessageId'] ?? json['parent_message_id']) as String?,
        variantIndex:
            (json['variantIndex'] ?? json['variant_index'] as int?) ?? 0,
        clientMessageId:
            (json['clientMessageId'] ?? json['client_message_id']) as String?,
        createdAt: DateTime.parse(
          (json['createdAt'] ?? json['created_at']) as String,
        ),
        updatedAt: DateTime.parse(
          (json['updatedAt'] ?? json['updated_at']) as String,
        ),
      );

  final String id;
  final String conversationId;
  final String role;
  final MessageStatus status;
  final String content;
  final FinishReason? finishReason;
  final String? runId;
  final String? parentMessageId;
  final int variantIndex;
  final String? clientMessageId;
  final DateTime createdAt;
  final DateTime updatedAt;

  /// Task outcome from the run-finished event (`ASK_USER` etc.). Client-side
  /// only: not part of the message JSON, so it is absent after a reload.
  final Outcome? outcome;

  /// Tester-only serving metadata from the run-finished event. Client-side
  /// only: not part of the message JSON.
  final DebugMeta? debug;

  Map<String, dynamic> toJson() => {
    'id': id,
    'conversationId': conversationId,
    'role': role,
    'status': status.wireName,
    'content': content,
    if (finishReason != null) 'finishReason': finishReason!.wireName,
    if (runId != null) 'runId': runId,
    if (parentMessageId != null) 'parentMessageId': parentMessageId,
    'variantIndex': variantIndex,
    if (clientMessageId != null) 'clientMessageId': clientMessageId,
    'createdAt': createdAt.toIso8601String(),
    'updatedAt': updatedAt.toIso8601String(),
  };

  ChatMessageView copyWith({
    String? id,
    String? conversationId,
    String? role,
    MessageStatus? status,
    String? content,
    FinishReason? finishReason,
    Outcome? outcome,
    DebugMeta? debug,
    String? runId,
    String? parentMessageId,
    int? variantIndex,
    String? clientMessageId,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) => ChatMessageView(
    id: id ?? this.id,
    conversationId: conversationId ?? this.conversationId,
    role: role ?? this.role,
    status: status ?? this.status,
    content: content ?? this.content,
    finishReason: finishReason ?? this.finishReason,
    outcome: outcome ?? this.outcome,
    debug: debug ?? this.debug,
    runId: runId ?? this.runId,
    parentMessageId: parentMessageId ?? this.parentMessageId,
    variantIndex: variantIndex ?? this.variantIndex,
    clientMessageId: clientMessageId ?? this.clientMessageId,
    createdAt: createdAt ?? this.createdAt,
    updatedAt: updatedAt ?? this.updatedAt,
  );
}

class ConversationPage {
  const ConversationPage({required this.items, this.nextCursor});

  factory ConversationPage.fromJson(Map<String, dynamic> json) =>
      ConversationPage(
        items: ((json['items'] as List<dynamic>?) ?? [])
            .map((e) => ConversationView.fromJson(e as Map<String, dynamic>))
            .toList(),
        nextCursor: (json['nextCursor'] ?? json['next_cursor']) as String?,
      );

  final List<ConversationView> items;
  final String? nextCursor;
}

class MessagePage {
  const MessagePage({required this.items, this.hasMoreBefore = false});

  factory MessagePage.fromJson(Map<String, dynamic> json) => MessagePage(
    items: ((json['items'] as List<dynamic>?) ?? [])
        .map((e) => ChatMessageView.fromJson(e as Map<String, dynamic>))
        .toList(),
    hasMoreBefore:
        (json['hasMoreBefore'] ?? json['has_more_before'] as bool?) ?? false,
  );

  final List<ChatMessageView> items;
  final bool hasMoreBefore;
}

class ConversationSearchResult {
  const ConversationSearchResult({
    required this.conversation,
    required this.snippet,
    required this.matched,
  });

  factory ConversationSearchResult.fromJson(Map<String, dynamic> json) =>
      ConversationSearchResult(
        conversation: ConversationView.fromJson(
          json['conversation'] as Map<String, dynamic>,
        ),
        snippet: (json['snippet'] as String?) ?? '',
        matched: (json['matched'] as String?) ?? 'content',
      );

  final ConversationView conversation;
  final String snippet;
  final String matched;
}
