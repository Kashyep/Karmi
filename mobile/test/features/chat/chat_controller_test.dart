import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/stream/run_stream_client.dart';
import 'package:karmi_app/features/chat/state/chat_controller.dart';

class FakeRunStreamClient extends RunStreamClient {
  FakeRunStreamClient() : super(baseUrl: 'http://fake.test');

  StreamController<RunEvent>? startRunController;
  StreamController<RunEvent>? resumeRunController;
  StreamController<RunEvent>? continueController;
  StreamController<RunEvent>? regenerateController;

  final List<String> stoppedRuns = [];
  final List<Map<String, dynamic>> startRunCalls = [];
  final List<Map<String, dynamic>> resumeRunCalls = [];
  final List<String> continueCalls = [];
  final List<String> regenerateCalls = [];

  Stream<RunEvent> Function({
    required String text,
    String? conversationId,
    required String clientMessageId,
  })? onStartRun;

  Stream<RunEvent> Function({
    required String runId,
    required int afterSeq,
  })? onResumeRun;

  Stream<RunEvent> Function(String assistantMessageId)? onContinueMessage;
  Stream<RunEvent> Function(String assistantMessageId)? onRegenerateMessage;
  Future<void> Function(String runId)? onStopRun;

  @override
  Stream<RunEvent> startRun({
    required String text,
    String? conversationId,
    required String clientMessageId,
  }) {
    startRunCalls.add({
      'text': text,
      'conversationId': conversationId,
      'clientMessageId': clientMessageId,
    });
    if (onStartRun != null) {
      return onStartRun!(
        text: text,
        conversationId: conversationId,
        clientMessageId: clientMessageId,
      );
    }
    startRunController = StreamController<RunEvent>.broadcast();
    return startRunController!.stream;
  }

  @override
  Stream<RunEvent> resumeRun({
    required String runId,
    required int afterSeq,
  }) {
    resumeRunCalls.add({
      'runId': runId,
      'afterSeq': afterSeq,
    });
    if (onResumeRun != null) {
      return onResumeRun!(runId: runId, afterSeq: afterSeq);
    }
    resumeRunController = StreamController<RunEvent>.broadcast();
    return resumeRunController!.stream;
  }

  @override
  Stream<RunEvent> continueMessage(String assistantMessageId) {
    continueCalls.add(assistantMessageId);
    if (onContinueMessage != null) {
      return onContinueMessage!(assistantMessageId);
    }
    continueController = StreamController<RunEvent>.broadcast();
    return continueController!.stream;
  }

  @override
  Stream<RunEvent> regenerateMessage(String assistantMessageId) {
    regenerateCalls.add(assistantMessageId);
    if (onRegenerateMessage != null) {
      return onRegenerateMessage!(assistantMessageId);
    }
    regenerateController = StreamController<RunEvent>.broadcast();
    return regenerateController!.stream;
  }

  @override
  Future<void> stopRun(String runId) async {
    stoppedRuns.add(runId);
    if (onStopRun != null) {
      await onStopRun!(runId);
    }
  }
}

void main() {
  group('ChatController', () {
    late FakeRunStreamClient client;

    setUp(() {
      client = FakeRunStreamClient();
    });

    test('generates valid 32-hex clientMessageId per send and stores initial messages', () {
      fakeAsync((async) {
        final controller = ChatController(client: client);
        expect(controller.phase, ChatRunPhase.idle);
        expect(controller.messages, isEmpty);

        controller.send('Hello world');
        async.flushMicrotasks();

        expect(controller.phase, ChatRunPhase.sending);
        expect(controller.messages.length, 2);
        expect(controller.messages[0].role, 'user');
        expect(controller.messages[0].content, 'Hello world');
        expect(controller.messages[1].role, 'assistant');
        expect(controller.messages[1].status, MessageStatus.streaming);

        final cmid = controller.currentClientMessageId;
        expect(cmid, isNotNull);
        expect(cmid!.length, 32);
        expect(RegExp(r'^[0-9a-f]{32}$').hasMatch(cmid), isTrue);

        expect(client.startRunCalls.length, 1);
        expect(client.startRunCalls.first['clientMessageId'], cmid);
        expect(client.startRunCalls.first['text'], 'Hello world');

        controller.dispose();
      });
    });

    test('send inlines attachment texts into user message prompt', () {
      fakeAsync((async) {
        final controller = ChatController(client: client);
        controller.send('Explain this', ['```dart\nvoid main() {}\n```']);
        async.flushMicrotasks();

        expect(
          controller.messages.first.content,
          'Explain this\n\n```dart\nvoid main() {}\n```',
        );
        expect(
          client.startRunCalls.first['text'],
          'Explain this\n\n```dart\nvoid main() {}\n```',
        );

        controller.dispose();
      });
    });

    test('batching: many deltas accumulate and notifyListeners once per 50 ms tick', () {
      fakeAsync((async) {
        final controller = ChatController(
          client: client,
          deltaFlushInterval: const Duration(milliseconds: 50),
        );
        controller.send('Hi');
        async.flushMicrotasks();

        var notifyCount = 0;
        controller.addListener(() => notifyCount++);

        client.startRunController!.add(
          const RunStartedEvent(
            runId: 'run_1',
            conversationId: 'conv_1',
            userMessageId: 'msg_u1',
            assistantMessageId: 'msg_a1',
            seq: 0,
          ),
        );
        async.flushMicrotasks();
        expect(controller.phase, ChatRunPhase.streaming);
        expect(notifyCount, 1); // 1 notify for phase change to streaming
        notifyCount = 0;

        // Emit deltas in rapid succession
        client.startRunController!.add(const MessageDeltaEvent(text: 'Ka', seq: 1));
        client.startRunController!.add(const MessageDeltaEvent(text: 'r', seq: 2));
        client.startRunController!.add(const MessageDeltaEvent(text: 'mi', seq: 3));
        async.flushMicrotasks();

        // Before 50 ms timer tick: no notify called, text not yet flushed to message
        expect(notifyCount, 0);
        expect(controller.messages[1].content, '');

        async.elapse(const Duration(milliseconds: 25));
        expect(notifyCount, 0);

        // At 50 ms tick: notifyListeners called exactly once
        async.elapse(const Duration(milliseconds: 25));
        expect(notifyCount, 1);
        expect(controller.messages[1].content, 'Karmi');

        // More deltas
        client.startRunController!.add(const MessageDeltaEvent(text: ' is', seq: 4));
        client.startRunController!.add(const MessageDeltaEvent(text: ' fast', seq: 5));
        async.flushMicrotasks();
        expect(notifyCount, 1); // Still 1 from previous tick

        async.elapse(const Duration(milliseconds: 50));
        expect(notifyCount, 2);
        expect(controller.messages[1].content, 'Karmi is fast');

        controller.dispose();
      });
    });

    test('stall: no event for 25 s while streaming triggers stalled phase and resumeRun', () {
      fakeAsync((async) {
        final controller = ChatController(
          client: client,
          stallTimeout: const Duration(seconds: 25),
        );
        controller.send('Wait for me');
        async.flushMicrotasks();

        client.startRunController!.add(
          const RunStartedEvent(
            runId: 'run_stall_1',
            conversationId: 'conv_stall',
            userMessageId: 'msg_u',
            assistantMessageId: 'msg_a',
            seq: 0,
          ),
        );
        client.startRunController!.add(const MessageDeltaEvent(text: 'Thinking', seq: 10));
        async.flushMicrotasks();

        expect(controller.phase, ChatRunPhase.streaming);
        expect(controller.lastSeq, 10);

        // Heartbeat at 15 s resets the stall timer
        async.elapse(const Duration(seconds: 15));
        client.startRunController!.add(HeartbeatEvent(at: DateTime.now()));
        async.flushMicrotasks();
        expect(controller.phase, ChatRunPhase.streaming);
        expect(client.resumeRunCalls, isEmpty);

        // 24 s after heartbeat: still not stalled
        async.elapse(const Duration(seconds: 24));
        expect(controller.phase, ChatRunPhase.streaming);
        expect(client.resumeRunCalls, isEmpty);

        // 25 s total silence reached: stall fires!
        async.elapse(const Duration(seconds: 1));
        async.flushMicrotasks();

        expect(client.resumeRunCalls.length, 1);
        expect(client.resumeRunCalls.first['runId'], 'run_stall_1');
        expect(client.resumeRunCalls.first['afterSeq'], 10);

        controller.dispose();
      });
    });

    test('run.finished with finish_reason=length sets finishReason=length and keeps message', () {
      fakeAsync((async) {
        final controller = ChatController(client: client);
        controller.send('Write an essay');
        async.flushMicrotasks();

        client.startRunController!.add(
          const RunStartedEvent(
            runId: 'run_len',
            conversationId: 'conv_len',
            userMessageId: 'msg_u',
            assistantMessageId: 'msg_a',
            seq: 0,
          ),
        );
        client.startRunController!.add(const MessageDeltaEvent(text: 'Long output...', seq: 1));
        client.startRunController!.add(
          const RunFinishedEvent(
            finishReason: FinishReason.length,
            outcome: 'truncated',
            assistantMessageId: 'msg_a',
          ),
        );
        async.flushMicrotasks();

        expect(controller.phase, ChatRunPhase.finished);
        expect(controller.finishReason, FinishReason.length);
        expect(controller.messages.length, 2);
        expect(controller.messages[1].status, MessageStatus.complete);
        expect(controller.messages[1].finishReason, FinishReason.length);
        expect(controller.messages[1].content, 'Long output...');

        controller.dispose();
      });
    });

    test('error mapping: run.error maps all categories and preserves partial text', () {
      final categories = [
        ErrorCategory.quotaExhausted,
        ErrorCategory.capacityFull,
        ErrorCategory.providerUnavailable,
        ErrorCategory.validationFailed,
        ErrorCategory.unauthorized,
        ErrorCategory.resumeUnavailable,
        ErrorCategory.internal,
        ErrorCategory.network,
      ];

      for (final cat in categories) {
        fakeAsync((async) {
          final testClient = FakeRunStreamClient();
          final controller = ChatController(client: testClient);
          controller.send('Test error');
          async.flushMicrotasks();

          testClient.startRunController!.add(
            const RunStartedEvent(
              runId: 'run_err',
              conversationId: 'conv_err',
              userMessageId: 'msg_u',
              assistantMessageId: 'msg_a',
              seq: 0,
            ),
          );
          testClient.startRunController!.add(
            const MessageDeltaEvent(text: 'Partial text before error', seq: 1),
          );
          testClient.startRunController!.add(
            RunErrorEvent(
              category: cat,
              retryable: false,
              assistantMessageId: 'msg_a',
            ),
          );
          async.flushMicrotasks();

          expect(controller.phase, ChatRunPhase.error);
          expect(controller.error, cat);
          expect(controller.finishReason, FinishReason.error);
          expect(controller.messages[1].status, MessageStatus.failed);
          expect(controller.messages[1].finishReason, FinishReason.error);
          expect(controller.messages[1].content, 'Partial text before error');

          controller.dispose();
        });
      }
    });

    test('single terminal event handling: subsequent events or onDone ignored', () {
      fakeAsync((async) {
        final controller = ChatController(client: client);
        controller.send('Hello');
        async.flushMicrotasks();

        client.startRunController!.add(
          const RunStartedEvent(
            runId: 'run_term',
            conversationId: 'conv_term',
            userMessageId: 'msg_u',
            assistantMessageId: 'msg_a',
            seq: 0,
          ),
        );
        client.startRunController!.add(const MessageDeltaEvent(text: 'Done', seq: 1));
        client.startRunController!.add(
          const RunFinishedEvent(
            finishReason: FinishReason.stop,
            assistantMessageId: 'msg_a',
          ),
        );
        async.flushMicrotasks();

        expect(controller.phase, ChatRunPhase.finished);
        expect(controller.finishReason, FinishReason.stop);

        // Stream closes normally
        client.startRunController!.close();
        async.flushMicrotasks();

        expect(controller.phase, ChatRunPhase.finished);
        expect(controller.finishReason, FinishReason.stop);
        expect(client.resumeRunCalls, isEmpty);

        controller.dispose();
      });
    });

    test('stop path: invokes stopRun and updates message to stopped with cancelled reason', () {
      fakeAsync((async) {
        final controller = ChatController(client: client);
        controller.send('Long generation');
        async.flushMicrotasks();

        client.startRunController!.add(
          const RunStartedEvent(
            runId: 'run_to_stop',
            conversationId: 'conv_stop',
            userMessageId: 'msg_u',
            assistantMessageId: 'msg_a',
            seq: 0,
          ),
        );
        client.startRunController!.add(const MessageDeltaEvent(text: 'Halfway there', seq: 1));
        async.flushMicrotasks();

        controller.stop();
        async.flushMicrotasks();

        expect(client.stoppedRuns, ['run_to_stop']);

        // Provider emits terminal cancelled event
        client.startRunController!.add(
          const RunFinishedEvent(
            finishReason: FinishReason.cancelled,
            assistantMessageId: 'msg_a',
          ),
        );
        async.flushMicrotasks();

        expect(controller.phase, ChatRunPhase.finished);
        expect(controller.finishReason, FinishReason.cancelled);
        expect(controller.messages[1].status, MessageStatus.stopped);
        expect(controller.messages[1].finishReason, FinishReason.cancelled);
        expect(controller.messages[1].content, 'Halfway there');

        controller.dispose();
      });
    });

    test('continueMessage appends to the same assistant message', () {
      fakeAsync((async) {
        final initialMessages = [
          ChatMessageView(
            id: 'msg_u1',
            conversationId: 'conv_c',
            role: 'user',
            status: MessageStatus.complete,
            content: 'Write chapter 1',
            createdAt: DateTime.now(),
            updatedAt: DateTime.now(),
          ),
          ChatMessageView(
            id: 'msg_a1',
            conversationId: 'conv_c',
            role: 'assistant',
            status: MessageStatus.complete,
            content: 'Chapter 1: The Beginning.',
            finishReason: FinishReason.length,
            runId: 'run_c1',
            createdAt: DateTime.now(),
            updatedAt: DateTime.now(),
          ),
        ];

        final controller = ChatController(
          client: client,
          conversationId: 'conv_c',
          initialMessages: initialMessages,
        );

        controller.continueMessage('msg_a1');
        async.flushMicrotasks();

        expect(client.continueCalls, ['msg_a1']);
        expect(controller.phase, ChatRunPhase.sending);
        expect(controller.messages.length, 2); // No new message added
        expect(controller.messages[1].status, MessageStatus.streaming);

        client.continueController!.add(
          const RunStartedEvent(
            runId: 'run_c2',
            conversationId: 'conv_c',
            userMessageId: 'msg_u1',
            assistantMessageId: 'msg_a1',
            seq: 0,
          ),
        );
        client.continueController!.add(
          const MessageDeltaEvent(text: ' And then it continued.', seq: 1),
        );
        client.continueController!.add(
          const RunFinishedEvent(
            finishReason: FinishReason.stop,
            assistantMessageId: 'msg_a1',
          ),
        );
        async.flushMicrotasks();

        expect(controller.phase, ChatRunPhase.finished);
        expect(controller.finishReason, FinishReason.stop);
        expect(controller.messages.length, 2);
        expect(
          controller.messages[1].content,
          'Chapter 1: The Beginning. And then it continued.',
        );
        expect(controller.messages[1].status, MessageStatus.complete);

        controller.dispose();
      });
    });

    test('regenerate creates sibling message with variantIndex + 1 while keeping original', () {
      fakeAsync((async) {
        final initialMessages = [
          ChatMessageView(
            id: 'msg_u1',
            conversationId: 'conv_r',
            role: 'user',
            status: MessageStatus.complete,
            content: 'Recommend a movie',
            createdAt: DateTime.now(),
            updatedAt: DateTime.now(),
          ),
          ChatMessageView(
            id: 'msg_a1',
            conversationId: 'conv_r',
            role: 'assistant',
            status: MessageStatus.complete,
            content: 'Inception',
            finishReason: FinishReason.stop,
            variantIndex: 0,
            runId: 'run_r1',
            createdAt: DateTime.now(),
            updatedAt: DateTime.now(),
          ),
        ];

        final controller = ChatController(
          client: client,
          conversationId: 'conv_r',
          initialMessages: initialMessages,
        );

        controller.regenerate('msg_a1');
        async.flushMicrotasks();

        expect(client.regenerateCalls, ['msg_a1']);
        expect(controller.phase, ChatRunPhase.sending);
        expect(controller.messages.length, 3); // Original user + original asst + new asst

        // Original assistant message intact
        expect(controller.messages[1].id, 'msg_a1');
        expect(controller.messages[1].content, 'Inception');
        expect(controller.messages[1].variantIndex, 0);

        // New sibling assistant message
        final sibling = controller.messages[2];
        expect(sibling.role, 'assistant');
        expect(sibling.variantIndex, 1);
        expect(sibling.parentMessageId, 'msg_u1');
        expect(sibling.status, MessageStatus.streaming);

        client.regenerateController!.add(
          const RunStartedEvent(
            runId: 'run_r2',
            conversationId: 'conv_r',
            userMessageId: 'msg_u1',
            assistantMessageId: 'msg_a2',
            seq: 0,
          ),
        );
        client.regenerateController!.add(
          const MessageDeltaEvent(text: 'Interstellar', seq: 1),
        );
        client.regenerateController!.add(
          const RunFinishedEvent(
            finishReason: FinishReason.stop,
            assistantMessageId: 'msg_a2',
          ),
        );
        async.flushMicrotasks();

        expect(controller.phase, ChatRunPhase.finished);
        expect(controller.messages.length, 3);
        expect(controller.messages[1].content, 'Inception');
        expect(controller.messages[2].id, 'msg_a2');
        expect(controller.messages[2].content, 'Interstellar');
        expect(controller.messages[2].variantIndex, 1);

        controller.dispose();
      });
    });

    test('network drop before terminal triggers automatic resume up to max retries then network error', () {
      fakeAsync((async) {
        var resumeCallCount = 0;
        client.onResumeRun = ({required runId, required afterSeq}) {
          resumeCallCount++;
          final sc = StreamController<RunEvent>.broadcast();
          // Simulate immediate network failure on resume
          Timer.run(() {
            sc.addError(
              const RunStreamException(category: ErrorCategory.network),
            );
          });
          return sc.stream;
        };

        final controller = ChatController(
          client: client,
          maxResumeRetries: 3,
          retryDelay: const Duration(milliseconds: 100),
        );

        controller.send('Network test');
        async.flushMicrotasks();

        client.startRunController!.add(
          const RunStartedEvent(
            runId: 'run_net',
            conversationId: 'conv_net',
            userMessageId: 'msg_u',
            assistantMessageId: 'msg_a',
            seq: 0,
          ),
        );
        client.startRunController!.add(const MessageDeltaEvent(text: 'Hello', seq: 5));
        async.flushMicrotasks();

        // Simulate premature stream error
        client.startRunController!.addError(
          const RunStreamException(category: ErrorCategory.network),
        );
        async.flushMicrotasks();

        // Retry 1 (after 100 ms)
        async.elapse(const Duration(milliseconds: 100));
        async.flushMicrotasks();
        expect(resumeCallCount, 1);

        // Retry 2 (after 200 ms)
        async.elapse(const Duration(milliseconds: 200));
        async.flushMicrotasks();
        expect(resumeCallCount, 2);

        // Retry 3 (after 300 ms)
        async.elapse(const Duration(milliseconds: 300));
        async.flushMicrotasks();
        expect(resumeCallCount, 3);

        // Retries exhausted!
        expect(controller.phase, ChatRunPhase.error);
        expect(controller.error, ErrorCategory.network);
        expect(controller.finishReason, FinishReason.error);
        expect(controller.messages[1].status, MessageStatus.failed);
        expect(controller.messages[1].content, 'Hello');

        controller.dispose();
      });
    });
  });
}
