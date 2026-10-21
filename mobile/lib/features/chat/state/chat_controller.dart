import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';

import '../../../api/stream/run_stream_client.dart';

/// Phase of a chat run in the controller state machine.
enum ChatRunPhase {
  idle,
  sending,
  streaming,
  stalled,
  finished,
  error,
}

/// State controller managing chat message streams, delta batching, stall recovery,
/// and continuation/regeneration per Karmi execution contract §7.
class ChatController extends ChangeNotifier {
  ChatController({
    required RunStreamClient client,
    String? conversationId,
    List<ChatMessageView>? initialMessages,
    Duration stallTimeout = const Duration(seconds: 25),
    Duration deltaFlushInterval = const Duration(milliseconds: 50),
    int maxResumeRetries = 3,
    Duration retryDelay = const Duration(milliseconds: 500),
    String Function()? idGenerator,
  })  : _client = client,
        _conversationId = conversationId,
        _messages = initialMessages != null
            ? List<ChatMessageView>.of(initialMessages)
            : <ChatMessageView>[],
        _stallTimeout = stallTimeout,
        _deltaFlushInterval = deltaFlushInterval,
        _maxResumeRetries = maxResumeRetries,
        _retryDelay = retryDelay,
        _idGenerator = idGenerator;

  final RunStreamClient _client;
  final Duration _stallTimeout;
  final Duration _deltaFlushInterval;
  final int _maxResumeRetries;
  final Duration _retryDelay;
  final String Function()? _idGenerator;

  String? _conversationId;
  final List<ChatMessageView> _messages;

  ChatRunPhase _phase = ChatRunPhase.idle;
  ErrorCategory? _error;
  FinishReason? _finishReason;

  String? _currentRunId;
  String? _currentClientMessageId;
  String? _currentSendText;
  String? _currentAssistantMessageId;
  int _lastSeq = 0;
  int _resumeAttempts = 0;
  bool _terminalReceived = false;
  bool _stopping = false;
  bool _disposed = false;

  final StringBuffer _deltaBuffer = StringBuffer();
  Timer? _deltaFlushTimer;
  Timer? _stallTimer;
  StreamSubscription<RunEvent>? _streamSubscription;

  /// Unmodifiable view of chat messages in this conversation.
  List<ChatMessageView> get messages => List.unmodifiable(_messages);

  /// Current run phase.
  ChatRunPhase get phase => _phase;

  /// Error category if the last run failed.
  ErrorCategory? get error => _error;

  /// Terminal finish reason if the run finished or halted.
  FinishReason? get finishReason => _finishReason;

  /// Active conversation ID, if established.
  String? get conversationId => _conversationId;

  /// Active run ID, if known.
  String? get currentRunId => _currentRunId;

  /// Last event sequence number observed.
  int get lastSeq => _lastSeq;

  /// Client message ID used for the current/most recent send.
  String? get currentClientMessageId => _currentClientMessageId;

  /// Sends a new user message, optionally with fenced attachment texts.
  ///
  /// Generates a 32-hex client_message_id, appends optimistic user and
  /// assistant messages, and streams provider events.
  Future<void> send(
    String text, [
    List<String> attachmentTexts = const [],
  ]) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty && attachmentTexts.isEmpty) return;

    _cancelStallTimer();
    _stopDeltaFlushTimer();
    await _streamSubscription?.cancel();
    _streamSubscription = null;

    final clientMsgId = _generateClientMessageId();
    _currentClientMessageId = clientMsgId;
    _currentRunId = null;
    _lastSeq = 0;
    _error = null;
    _finishReason = null;
    _terminalReceived = false;
    _stopping = false;
    _resumeAttempts = 0;

    final prompt = attachmentTexts.isEmpty
        ? text
        : (text.isEmpty
            ? attachmentTexts.join('\n\n')
            : '$text\n\n${attachmentTexts.join('\n\n')}');
    _currentSendText = prompt;

    final now = DateTime.now();
    final userMsgId = 'temp_user_$clientMsgId';
    final asstMsgId = 'temp_asst_$clientMsgId';

    final userMessage = ChatMessageView(
      id: userMsgId,
      conversationId: _conversationId ?? '',
      role: 'user',
      status: MessageStatus.complete,
      content: prompt,
      clientMessageId: clientMsgId,
      createdAt: now,
      updatedAt: now,
    );

    final assistantMessage = ChatMessageView(
      id: asstMsgId,
      conversationId: _conversationId ?? '',
      role: 'assistant',
      status: MessageStatus.streaming,
      content: '',
      clientMessageId: clientMsgId,
      createdAt: now,
      updatedAt: now,
    );

    _messages.add(userMessage);
    _messages.add(assistantMessage);
    _currentAssistantMessageId = asstMsgId;

    _setPhase(ChatRunPhase.sending);

    try {
      final stream = _client.startRun(
        text: prompt,
        conversationId: _conversationId,
        clientMessageId: clientMsgId,
      );
      _subscribeToStream(stream);
    } on RunStreamException catch (e) {
      _handleStreamException(e);
    } catch (e) {
      _handleGenericException(e);
    }
  }

  /// Cancels in-flight run via provider stop endpoint.
  Future<void> stop() async {
    if (_phase != ChatRunPhase.sending &&
        _phase != ChatRunPhase.streaming &&
        _phase != ChatRunPhase.stalled) {
      return;
    }

    _stopping = true;
    _cancelStallTimer();

    final runId = _currentRunId;
    if (runId != null) {
      try {
        await _client.stopRun(runId);
      } catch (_) {
        // Fall back to local cancellation if stopRun call throws
      }
    } else {
      await _streamSubscription?.cancel();
      _streamSubscription = null;
      _stopDeltaFlushTimer();
      _finishReason = FinishReason.cancelled;
      _finalizeAssistantMessage(
        status: MessageStatus.stopped,
        finishReason: FinishReason.cancelled,
      );
      _setPhase(ChatRunPhase.finished);
    }
  }

  /// Appends continuation content to an assistant message that previously stopped
  /// due to length, cancellation, interruption, or error.
  Future<void> continueMessage(String id) async {
    final index = _messages.indexWhere((m) => m.id == id);
    if (index == -1) return;
    final target = _messages[index];
    if (target.status == MessageStatus.streaming) return;

    final validReasons = [
      FinishReason.length,
      FinishReason.cancelled,
      FinishReason.interrupted,
      FinishReason.error,
    ];
    if (target.finishReason != null &&
        !validReasons.contains(target.finishReason)) {
      return;
    }

    _cancelStallTimer();
    _stopDeltaFlushTimer();
    await _streamSubscription?.cancel();
    _streamSubscription = null;

    _currentAssistantMessageId = id;
    _currentRunId = target.runId;
    _currentClientMessageId = null;
    _currentSendText = null;
    _error = null;
    _finishReason = null;
    _terminalReceived = false;
    _stopping = false;
    _resumeAttempts = 0;

    _messages[index] = target.copyWith(
      status: MessageStatus.streaming,
      finishReason: null,
      updatedAt: DateTime.now(),
    );

    _setPhase(ChatRunPhase.sending);

    try {
      final stream = _client.continueMessage(id);
      _subscribeToStream(stream);
    } on RunStreamException catch (e) {
      _handleStreamException(e);
    } catch (e) {
      _handleGenericException(e);
    }
  }

  /// Regenerates an assistant message by spawning a sibling message with
  /// variantIndex + 1 while preserving the previous variant.
  Future<void> regenerate(String id) async {
    final index = _messages.indexWhere((m) => m.id == id);
    if (index == -1) return;
    final target = _messages[index];

    _cancelStallTimer();
    _stopDeltaFlushTimer();
    await _streamSubscription?.cancel();
    _streamSubscription = null;

    final nextVariantIndex = target.variantIndex + 1;
    final parentMsgId =
        target.parentMessageId ?? _findPreviousUserMessageId(index);
    final tempAsstId = 'temp_asst_regen_${_generateClientMessageId()}';

    final now = DateTime.now();
    final siblingMsg = ChatMessageView(
      id: tempAsstId,
      conversationId: target.conversationId,
      role: 'assistant',
      status: MessageStatus.streaming,
      content: '',
      parentMessageId: parentMsgId,
      variantIndex: nextVariantIndex,
      createdAt: now,
      updatedAt: now,
    );

    _messages.add(siblingMsg);
    _currentAssistantMessageId = tempAsstId;
    _currentRunId = null;
    _currentClientMessageId = null;
    _currentSendText = null;
    _error = null;
    _finishReason = null;
    _terminalReceived = false;
    _stopping = false;
    _resumeAttempts = 0;

    _setPhase(ChatRunPhase.sending);

    try {
      final stream = _client.regenerateMessage(id);
      _subscribeToStream(stream);
    } on RunStreamException catch (e) {
      _handleStreamException(e);
    } catch (e) {
      _handleGenericException(e);
    }
  }

  /// Resumes the active run from `lastSeq` via `GET /v1/runs/{id}/events?after_seq=N`.
  Future<void> resume() async {
    if (_disposed) return;
    final runId = _currentRunId;

    if (runId != null) {
      _cancelStallTimer();
      _stopDeltaFlushTimer();
      await _streamSubscription?.cancel();
      _streamSubscription = null;

      _terminalReceived = false;
      _setPhase(ChatRunPhase.streaming);
      _resetStallTimer();

      try {
        final stream = _client.resumeRun(runId: runId, afterSeq: _lastSeq);
        _subscribeToStream(stream);
      } on RunStreamException catch (e) {
        _handleStreamException(e);
      } catch (e) {
        _handleGenericException(e);
      }
    } else if (_currentSendText != null && _currentClientMessageId != null) {
      _cancelStallTimer();
      _stopDeltaFlushTimer();
      await _streamSubscription?.cancel();
      _streamSubscription = null;

      _terminalReceived = false;
      _setPhase(ChatRunPhase.sending);

      try {
        final stream = _client.startRun(
          text: _currentSendText!,
          conversationId: _conversationId,
          clientMessageId: _currentClientMessageId!,
        );
        _subscribeToStream(stream);
      } on RunStreamException catch (e) {
        _handleStreamException(e);
      } catch (e) {
        _handleGenericException(e);
      }
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _cancelStallTimer();
    _deltaFlushTimer?.cancel();
    _deltaFlushTimer = null;
    _streamSubscription?.cancel();
    _streamSubscription = null;
    super.dispose();
  }

  // --- Private Helpers ---

  void _subscribeToStream(Stream<RunEvent> stream) {
    _streamSubscription?.cancel();
    _streamSubscription = stream.listen(
      _onEvent,
      onError: (Object err, StackTrace st) {
        if (_disposed) return;
        if (err is RunStreamException) {
          _handleStreamException(err);
        } else {
          _handleGenericException(err);
        }
      },
      onDone: () {
        if (_disposed) return;
        if (!_terminalReceived &&
            (_phase == ChatRunPhase.streaming ||
                _phase == ChatRunPhase.sending ||
                _phase == ChatRunPhase.stalled)) {
          if (_stopping) {
            _stopDeltaFlushTimer();
            _cancelStallTimer();
            _finishReason = FinishReason.cancelled;
            _finalizeAssistantMessage(
              status: MessageStatus.stopped,
              finishReason: FinishReason.cancelled,
            );
            _setPhase(ChatRunPhase.finished);
          } else {
            _triggerAutoResume();
          }
        }
      },
      cancelOnError: true,
    );
  }

  void _onEvent(RunEvent event) {
    if (_disposed) return;

    switch (event) {
      case RunStartedEvent():
        _resetStallTimer();
        _currentRunId = event.runId;
        _conversationId = event.conversationId;
        if (event.seq > _lastSeq) {
          _lastSeq = event.seq;
        }
        _updateMessageIdsOnStarted(
          event.userMessageId,
          event.assistantMessageId,
          event.conversationId,
          event.runId,
        );
        _currentAssistantMessageId = event.assistantMessageId;
        if (_phase != ChatRunPhase.streaming) {
          _setPhase(ChatRunPhase.streaming);
        }
        break;

      case MessageDeltaEvent():
        _resetStallTimer();
        if (_phase != ChatRunPhase.streaming) {
          _setPhase(ChatRunPhase.streaming);
        }
        if (event.seq != null && event.seq! > _lastSeq) {
          _lastSeq = event.seq!;
        }
        _deltaBuffer.write(event.text);
        _ensureDeltaFlushTimer();
        break;

      case HeartbeatEvent():
        _resetStallTimer();
        break;

      case RunFinishedEvent():
        _terminalReceived = true;
        _cancelStallTimer();
        _stopDeltaFlushTimer();

        _finishReason = event.finishReason;
        final MessageStatus msgStatus;
        switch (event.finishReason) {
          case FinishReason.cancelled:
            msgStatus = MessageStatus.stopped;
            break;
          case FinishReason.interrupted:
            msgStatus = MessageStatus.interrupted;
            break;
          case FinishReason.error:
            msgStatus = MessageStatus.failed;
            break;
          case FinishReason.stop:
          case FinishReason.length:
          case FinishReason.contentFilter:
            msgStatus = MessageStatus.complete;
            break;
        }

        _finalizeAssistantMessage(
          assistantMessageId: event.assistantMessageId,
          status: msgStatus,
          finishReason: event.finishReason,
        );
        _setPhase(ChatRunPhase.finished);
        break;

      case RunErrorEvent():
        _terminalReceived = true;
        _cancelStallTimer();
        _stopDeltaFlushTimer();

        _error = event.category;
        _finishReason = FinishReason.error;

        _finalizeAssistantMessage(
          assistantMessageId: event.assistantMessageId,
          status: MessageStatus.failed,
          finishReason: FinishReason.error,
        );
        _setPhase(ChatRunPhase.error);
        break;
    }
  }

  void _ensureDeltaFlushTimer() {
    _deltaFlushTimer ??= Timer.periodic(_deltaFlushInterval, (_) {
      _flushDeltaBuffer();
    });
  }

  void _flushDeltaBuffer() {
    if (_disposed || _deltaBuffer.isEmpty) return;
    final chunk = _deltaBuffer.toString();
    _deltaBuffer.clear();
    _appendAssistantText(chunk);
    _notifySafe();
  }

  void _stopDeltaFlushTimer() {
    _deltaFlushTimer?.cancel();
    _deltaFlushTimer = null;
    if (_deltaBuffer.isNotEmpty) {
      final chunk = _deltaBuffer.toString();
      _deltaBuffer.clear();
      _appendAssistantText(chunk);
    }
  }

  void _appendAssistantText(String chunk) {
    if (chunk.isEmpty) return;
    final index =
        _messages.indexWhere((m) => m.id == _currentAssistantMessageId);
    if (index != -1) {
      final current = _messages[index];
      _messages[index] = current.copyWith(
        content: current.content + chunk,
        updatedAt: DateTime.now(),
      );
    }
  }

  void _updateMessageIdsOnStarted(
    String userMessageId,
    String assistantMessageId,
    String conversationId,
    String runId,
  ) {
    for (var i = 0; i < _messages.length; i++) {
      final msg = _messages[i];
      if (msg.clientMessageId != null &&
          msg.clientMessageId == _currentClientMessageId) {
        if (msg.role == 'user') {
          _messages[i] = msg.copyWith(
            id: userMessageId,
            conversationId: conversationId,
          );
        } else if (msg.role == 'assistant' &&
            msg.id == _currentAssistantMessageId) {
          _messages[i] = msg.copyWith(
            id: assistantMessageId,
            conversationId: conversationId,
            runId: runId,
          );
        }
      } else if (msg.id == _currentAssistantMessageId) {
        _messages[i] = msg.copyWith(
          id: assistantMessageId,
          conversationId: conversationId,
          runId: runId,
        );
      }
    }
  }

  void _finalizeAssistantMessage({
    String? assistantMessageId,
    required MessageStatus status,
    required FinishReason finishReason,
  }) {
    final targetId = assistantMessageId ?? _currentAssistantMessageId;
    final index = _messages.indexWhere((m) => m.id == targetId);
    if (index != -1) {
      final current = _messages[index];
      _messages[index] = current.copyWith(
        status: status,
        finishReason: finishReason,
        updatedAt: DateTime.now(),
      );
    }
  }

  void _resetStallTimer() {
    _stallTimer?.cancel();
    _stallTimer = Timer(_stallTimeout, _onStallTimeout);
  }

  void _cancelStallTimer() {
    _stallTimer?.cancel();
    _stallTimer = null;
  }

  void _onStallTimeout() {
    if (_disposed || _phase != ChatRunPhase.streaming) return;
    _setPhase(ChatRunPhase.stalled);
    _streamSubscription?.cancel();
    _streamSubscription = null;
    resume();
  }

  Future<void> _triggerAutoResume([RunStreamException? exception]) async {
    if (_disposed || _terminalReceived) return;

    if (_resumeAttempts < _maxResumeRetries) {
      _resumeAttempts++;
      final backoff = _retryDelay * _resumeAttempts;
      if (backoff > Duration.zero) {
        await Future<void>.delayed(backoff);
      }
      if (_disposed || _terminalReceived) return;

      if (_currentRunId != null) {
        _setPhase(ChatRunPhase.streaming);
        _resetStallTimer();
        try {
          final stream = _client.resumeRun(
            runId: _currentRunId!,
            afterSeq: _lastSeq,
          );
          _subscribeToStream(stream);
        } on RunStreamException catch (e) {
          _handleStreamException(e);
        } catch (e) {
          _handleGenericException(e);
        }
        return;
      } else if (_currentSendText != null && _currentClientMessageId != null) {
        _setPhase(ChatRunPhase.sending);
        try {
          final stream = _client.startRun(
            text: _currentSendText!,
            conversationId: _conversationId,
            clientMessageId: _currentClientMessageId!,
          );
          _subscribeToStream(stream);
        } on RunStreamException catch (e) {
          _handleStreamException(e);
        } catch (e) {
          _handleGenericException(e);
        }
        return;
      }
    }

    _cancelStallTimer();
    _stopDeltaFlushTimer();
    _error = exception?.category ?? ErrorCategory.network;
    _finishReason = FinishReason.error;
    _finalizeAssistantMessage(
      status: MessageStatus.failed,
      finishReason: FinishReason.error,
    );
    _setPhase(ChatRunPhase.error);
  }

  void _handleStreamException(RunStreamException e) {
    if (_disposed || _terminalReceived) return;

    if (e.category == ErrorCategory.unauthorized ||
        e.category == ErrorCategory.quotaExhausted ||
        e.category == ErrorCategory.resumeUnavailable) {
      _cancelStallTimer();
      _stopDeltaFlushTimer();
      _error = e.category;
      _finishReason = FinishReason.error;
      _finalizeAssistantMessage(
        status: MessageStatus.failed,
        finishReason: FinishReason.error,
      );
      _setPhase(ChatRunPhase.error);
      return;
    }

    _triggerAutoResume(e);
  }

  void _handleGenericException(Object e) {
    if (_disposed || _terminalReceived) return;
    _triggerAutoResume();
  }

  String? _findPreviousUserMessageId(int assistantIndex) {
    for (var i = assistantIndex - 1; i >= 0; i--) {
      if (_messages[i].role == 'user') {
        return _messages[i].id;
      }
    }
    return null;
  }

  String _generateClientMessageId() {
    if (_idGenerator != null) return _idGenerator();
    final rnd = Random.secure();
    final bytes = List<int>.generate(16, (_) => rnd.nextInt(256));
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  }

  void _setPhase(ChatRunPhase newPhase) {
    if (_phase == newPhase) return;
    _phase = newPhase;
    _notifySafe();
  }

  void _notifySafe() {
    if (!_disposed) {
      notifyListeners();
    }
  }
}
