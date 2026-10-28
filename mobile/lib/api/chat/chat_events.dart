/// SSE event models for Karmi chat streaming.
library;

import 'chat_models.dart';

sealed class ChatStreamEvent {
  const ChatStreamEvent();

  factory ChatStreamEvent.fromEvent(
    String eventName,
    Map<String, dynamic> data, {
    int? id,
  }) {
    switch (eventName) {
      case 'run.started':
        return RunStartedEvent.fromJson(data);
      case 'message.delta':
        return MessageDeltaEvent.fromJson(data, seq: id);
      case 'heartbeat':
        return HeartbeatEvent.fromJson(data);
      case 'run.finished':
        return RunFinishedEvent.fromJson(data);
      case 'run.error':
        return RunErrorEvent.fromJson(data);
      default:
        throw FormatException('Unknown chat stream event: $eventName');
    }
  }
}

class RunStartedEvent extends ChatStreamEvent {
  const RunStartedEvent({
    required this.runId,
    required this.conversationId,
    required this.userMessageId,
    required this.assistantMessageId,
    this.seq = 0,
  });

  factory RunStartedEvent.fromJson(
    Map<String, dynamic> json,
  ) => RunStartedEvent(
    runId: (json['run_id'] ?? json['runId']) as String,
    conversationId:
        (json['conversation_id'] ?? json['conversationId']) as String,
    userMessageId: (json['user_message_id'] ?? json['userMessageId']) as String,
    assistantMessageId:
        (json['assistant_message_id'] ?? json['assistantMessageId']) as String,
    seq: (json['seq'] as int?) ?? 0,
  );

  final String runId;
  final String conversationId;
  final String userMessageId;
  final String assistantMessageId;
  final int seq;
}

class MessageDeltaEvent extends ChatStreamEvent {
  const MessageDeltaEvent({required this.text, this.seq});

  factory MessageDeltaEvent.fromJson(Map<String, dynamic> json, {int? seq}) =>
      MessageDeltaEvent(
        text: (json['text'] as String?) ?? '',
        seq: seq ?? (json['seq'] as int?),
      );

  final String text;
  final int? seq;
}

class HeartbeatEvent extends ChatStreamEvent {
  const HeartbeatEvent({required this.at});

  factory HeartbeatEvent.fromJson(Map<String, dynamic> json) => HeartbeatEvent(
    at: json['at'] != null
        ? DateTime.parse(json['at'] as String)
        : DateTime.now(),
  );

  final DateTime at;
}

class RunFinishedEvent extends ChatStreamEvent {
  const RunFinishedEvent({
    required this.finishReason,
    this.outcome,
    this.inputTokens,
    this.outputTokens,
    this.assistantMessageId,
  });

  factory RunFinishedEvent.fromJson(
    Map<String, dynamic> json,
  ) => RunFinishedEvent(
    finishReason:
        FinishReason.fromWire(json['finish_reason'] ?? json['finishReason']) ??
        FinishReason.stop,
    outcome: json['outcome'] as String?,
    inputTokens: (json['input_tokens'] ?? json['inputTokens']) as int?,
    outputTokens: (json['output_tokens'] ?? json['outputTokens']) as int?,
    assistantMessageId:
        (json['assistant_message_id'] ?? json['assistantMessageId']) as String?,
  );

  final FinishReason finishReason;
  final String? outcome;
  final int? inputTokens;
  final int? outputTokens;
  final String? assistantMessageId;
}

class RunErrorEvent extends ChatStreamEvent {
  const RunErrorEvent({
    required this.category,
    required this.retryable,
    this.retryAfterSeconds,
    this.assistantMessageId,
  });

  factory RunErrorEvent.fromJson(Map<String, dynamic> json) => RunErrorEvent(
    category:
        ErrorCategory.fromWire(json['category']) ?? ErrorCategory.internal,
    retryable: (json['retryable'] as bool?) ?? false,
    retryAfterSeconds:
        (json['retry_after_s'] ?? json['retryAfterSeconds']) as int?,
    assistantMessageId:
        (json['assistant_message_id'] ?? json['assistantMessageId']) as String?,
  );

  final ErrorCategory category;
  final bool retryable;
  final int? retryAfterSeconds;
  final String? assistantMessageId;
}
