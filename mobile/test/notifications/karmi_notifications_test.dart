import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/stream/run_stream_client.dart';
import 'package:karmi_app/features/chat/state/chat_controller.dart';
import 'package:karmi_app/notifications/karmi_notifications.dart';

class FakeNotificationPlatformAdapter implements NotificationPlatformAdapter {
  bool shouldThrowOnInit = false;
  bool shouldThrowOnPermission = false;
  bool permissionGranted = true;

  int initCallCount = 0;
  int permissionCallCount = 0;
  final List<Map<String, dynamic>> showCalls = [];

  @override
  Future<bool?> initialize({required InitializationSettings settings}) async {
    initCallCount++;
    if (shouldThrowOnInit) {
      throw Exception('Simulated initialization failure');
    }
    return true;
  }

  @override
  Future<bool> requestPermission() async {
    permissionCallCount++;
    if (shouldThrowOnPermission) {
      throw Exception('Simulated permission request failure');
    }
    return permissionGranted;
  }

  @override
  Future<void> show({
    required int id,
    String? title,
    String? body,
    NotificationDetails? notificationDetails,
  }) async {
    showCalls.add({
      'id': id,
      'title': title,
      'body': body,
      'notificationDetails': notificationDetails,
    });
  }
}

class FakeChatRunStreamClient extends RunStreamClient {
  FakeChatRunStreamClient() : super(baseUrl: 'http://fake.test');

  StreamController<RunEvent>? activeStream;
  int startRunCallCount = 0;
  int resumeRunCallCount = 0;
  int stopRunCallCount = 0;

  @override
  Stream<RunEvent> startRun({
    required String text,
    String? conversationId,
    required String clientMessageId,
  }) {
    startRunCallCount++;
    activeStream = StreamController<RunEvent>();
    return activeStream!.stream;
  }

  @override
  Stream<RunEvent> resumeRun({required String runId, required int afterSeq}) {
    resumeRunCallCount++;
    activeStream = StreamController<RunEvent>();
    return activeStream!.stream;
  }

  @override
  Future<void> stopRun(String runId) async {
    stopRunCallCount++;
  }
}

class TestKarmiNotifications extends KarmiNotifications {
  final List<Map<String, dynamic>> readyCalls = [];
  final List<String> failedCalls = [];

  @override
  Future<void> notifyReplyReady({
    required String conversationId,
    required String body,
  }) async {
    readyCalls.add({'conversationId': conversationId, 'body': body});
  }

  @override
  Future<void> notifyReplyFailed({required String conversationId}) async {
    failedCalls.add(conversationId);
  }
}

void main() {
  group('KarmiNotifications unit & platform adapter tests', () {
    late FakeNotificationPlatformAdapter fakeAdapter;
    late KarmiNotifications notifications;

    setUp(() {
      fakeAdapter = FakeNotificationPlatformAdapter();
      notifications = KarmiNotifications(adapter: fakeAdapter);
    });

    test('init failure does not throw and is idempotent', () async {
      fakeAdapter.shouldThrowOnInit = true;

      // 1. Init failure doesn't throw
      await expectLater(notifications.init(), completes);
      expect(fakeAdapter.initCallCount, 1);

      // 2. Calling init again after recovery or retry
      fakeAdapter.shouldThrowOnInit = false;
      await expectLater(notifications.init(), completes);
      expect(fakeAdapter.initCallCount, 2);

      // Once succeeded, subsequent init calls are no-ops
      await notifications.init();
      expect(fakeAdapter.initCallCount, 2);
    });

    test(
      'requestPermission returns granted status or false on error',
      () async {
        fakeAdapter.permissionGranted = true;
        expect(await notifications.requestPermission(), isTrue);

        fakeAdapter.permissionGranted = false;
        expect(await notifications.requestPermission(), isFalse);

        fakeAdapter.shouldThrowOnPermission = true;
        expect(await notifications.requestPermission(), isFalse);
      },
    );

    test(
      'notifyReplyReady calls adapter show with stripped snippet and details',
      () async {
        await notifications.notifyReplyReady(
          conversationId: 'conv_123',
          body: '### Header\nHere is **bold** text and `inline code`.',
        );

        expect(fakeAdapter.showCalls, hasLength(1));
        final call = fakeAdapter.showCalls.first;
        expect(call['title'], 'Karmi replied');
        expect(call['body'], 'Header Here is bold text and inline code.');
      },
    );

    test(
      'notifyReplyFailed calls adapter show with failed title and null body',
      () async {
        await notifications.notifyReplyFailed(conversationId: 'conv_failed');

        expect(fakeAdapter.showCalls, hasLength(1));
        final call = fakeAdapter.showCalls.first;
        expect(call['title'], "Karmi couldn't finish a reply");
        expect(call['body'], isNull);
      },
    );

    test(
      'formatSnippet strips markdown formatting and truncates to ~120 chars',
      () {
        const markdown =
            '## Update\nThis is a **critical** message with a [link](https://karmi.ai) and ```dart\nvoid main() {}\n``` plus *italic*.';
        final snippet = KarmiNotifications.formatSnippet(markdown);
        expect(
          snippet,
          'Update This is a critical message with a link and void main() {} plus italic.',
        );

        final veryLongText = 'A' * 200;
        final truncated = KarmiNotifications.formatSnippet(veryLongText);
        expect(truncated.length, 120);
        expect(truncated.endsWith('…'), isTrue);
        expect(truncated.startsWith('A' * 119), isTrue);
      },
    );
  });

  group('ChatController notification lifecycle integration tests', () {
    late FakeChatRunStreamClient client;
    late TestKarmiNotifications testNotifications;

    setUp(() {
      client = FakeChatRunStreamClient();
      testNotifications = TestKarmiNotifications();
    });

    test('foreground completion -> no notify', () {
      fakeAsync((async) {
        final controller = ChatController(
          client: client,
          conversationId: 'conv_fg',
          notifications: testNotifications,
          lifecycleProvider: () => AppLifecycleState.resumed,
        );

        controller.send('Hello foreground');
        async.flushMicrotasks();

        final stream = client.activeStream!;
        stream.add(
          const RunStartedEvent(
            runId: 'r1',
            conversationId: 'conv_fg',
            userMessageId: 'u1',
            assistantMessageId: 'a1',
          ),
        );
        stream.add(
          const MessageDeltaEvent(text: 'Foreground reply text', seq: 2),
        );
        stream.add(
          const RunFinishedEvent(
            finishReason: FinishReason.stop,
            assistantMessageId: 'a1',
          ),
        );
        async.flushMicrotasks();

        expect(testNotifications.readyCalls, isEmpty);
        expect(testNotifications.failedCalls, isEmpty);
      });
    });

    test('inactive lifecycle (e.g. notification shade) -> no notify', () {
      fakeAsync((async) {
        final controller = ChatController(
          client: client,
          conversationId: 'conv_inactive',
          notifications: testNotifications,
          lifecycleProvider: () => AppLifecycleState.inactive,
        );

        controller.send('Hello inactive');
        async.flushMicrotasks();

        final stream = client.activeStream!;
        stream.add(
          const RunStartedEvent(
            runId: 'r_inact',
            conversationId: 'conv_inactive',
            userMessageId: 'u_inact',
            assistantMessageId: 'a_inact',
          ),
        );
        stream.add(
          const MessageDeltaEvent(text: 'Inactive reply text', seq: 2),
        );
        stream.add(
          const RunFinishedEvent(
            finishReason: FinishReason.stop,
            assistantMessageId: 'a_inact',
          ),
        );
        async.flushMicrotasks();

        expect(testNotifications.readyCalls, isEmpty);
        expect(testNotifications.failedCalls, isEmpty);
      });
    });

    test('background completion -> notifyReplyReady once with raw body', () {
      fakeAsync((async) {
        final controller = ChatController(
          client: client,
          conversationId: 'conv_bg',
          notifications: testNotifications,
          lifecycleProvider: () => AppLifecycleState.paused,
        );

        controller.send('Hello background');
        async.flushMicrotasks();

        final stream = client.activeStream!;
        stream.add(
          const RunStartedEvent(
            runId: 'r2',
            conversationId: 'conv_bg',
            userMessageId: 'u2',
            assistantMessageId: 'a2',
          ),
        );
        stream.add(
          const MessageDeltaEvent(
            text: 'Here is **Karmi** speaking! ```dart\ncode\n```',
            seq: 2,
          ),
        );
        stream.add(
          const RunFinishedEvent(
            finishReason: FinishReason.stop,
            assistantMessageId: 'a2',
          ),
        );
        async.flushMicrotasks();

        expect(testNotifications.readyCalls, hasLength(1));
        expect(testNotifications.readyCalls.first['conversationId'], 'conv_bg');
        expect(
          testNotifications.readyCalls.first['body'],
          'Here is **Karmi** speaking! ```dart\ncode\n```',
        );
        expect(testNotifications.failedCalls, isEmpty);

        // Additional events do not cause duplicate notifications
        stream.add(
          const RunFinishedEvent(
            finishReason: FinishReason.stop,
            assistantMessageId: 'a2',
          ),
        );
        async.flushMicrotasks();
        expect(testNotifications.readyCalls, hasLength(1));
      });
    });

    test(
      'end-to-end background completion formats snippet in adapter show',
      () {
        fakeAsync((async) {
          final fakeAdapter = FakeNotificationPlatformAdapter();
          final realNotifications = KarmiNotifications(adapter: fakeAdapter);

          final controller = ChatController(
            client: client,
            conversationId: 'conv_bg_e2e',
            notifications: realNotifications,
            lifecycleProvider: () => AppLifecycleState.paused,
          );

          controller.send('Hello e2e');
          async.flushMicrotasks();

          final stream = client.activeStream!;
          stream.add(
            const RunStartedEvent(
              runId: 'r_e2e',
              conversationId: 'conv_bg_e2e',
              userMessageId: 'u_e2e',
              assistantMessageId: 'a_e2e',
            ),
          );
          stream.add(
            const MessageDeltaEvent(
              text: 'Here is **Karmi** speaking! ```dart\ncode\n```',
              seq: 2,
            ),
          );
          stream.add(
            const RunFinishedEvent(
              finishReason: FinishReason.stop,
              assistantMessageId: 'a_e2e',
            ),
          );
          async.flushMicrotasks();

          expect(fakeAdapter.showCalls, hasLength(1));
          expect(fakeAdapter.showCalls.first['title'], 'Karmi replied');
          expect(
            fakeAdapter.showCalls.first['body'],
            'Here is Karmi speaking! code',
          );
        });
      },
    );

    test('background failure -> notifyReplyFailed', () {
      fakeAsync((async) {
        final controller = ChatController(
          client: client,
          conversationId: 'conv_fail',
          notifications: testNotifications,
          lifecycleProvider: () => AppLifecycleState.paused,
        );

        controller.send('Trigger failure');
        async.flushMicrotasks();

        final stream = client.activeStream!;
        stream.add(
          const RunStartedEvent(
            runId: 'r3',
            conversationId: 'conv_fail',
            userMessageId: 'u3',
            assistantMessageId: 'a3',
          ),
        );
        stream.add(
          const RunErrorEvent(
            category: ErrorCategory.internal,
            retryable: false,
            assistantMessageId: 'a3',
          ),
        );
        async.flushMicrotasks();

        expect(testNotifications.failedCalls, hasLength(1));
        expect(testNotifications.failedCalls.first, 'conv_fail');
        expect(testNotifications.readyCalls, isEmpty);
      });
    });

    test('foreground failure -> no notify', () {
      fakeAsync((async) {
        final controller = ChatController(
          client: client,
          conversationId: 'conv_fg_fail',
          notifications: testNotifications,
          lifecycleProvider: () => AppLifecycleState.resumed,
        );

        controller.send('Trigger fg failure');
        async.flushMicrotasks();

        final stream = client.activeStream!;
        stream.add(
          const RunStartedEvent(
            runId: 'r_fg_fail',
            conversationId: 'conv_fg_fail',
            userMessageId: 'u_fg_fail',
            assistantMessageId: 'a_fg_fail',
          ),
        );
        stream.add(
          const RunErrorEvent(
            category: ErrorCategory.internal,
            retryable: false,
            assistantMessageId: 'a_fg_fail',
          ),
        );
        async.flushMicrotasks();

        expect(testNotifications.failedCalls, isEmpty);
        expect(testNotifications.readyCalls, isEmpty);
      });
    });

    test('background deferred outcome -> notifyReplyFailed', () {
      fakeAsync((async) {
        final controller = ChatController(
          client: client,
          conversationId: 'conv_deferred',
          notifications: testNotifications,
          lifecycleProvider: () => AppLifecycleState.paused,
        );

        controller.send('Trigger deferred');
        async.flushMicrotasks();

        final stream = client.activeStream!;
        stream.add(
          const RunStartedEvent(
            runId: 'r4',
            conversationId: 'conv_deferred',
            userMessageId: 'u4',
            assistantMessageId: 'a4',
          ),
        );
        stream.add(
          const RunFinishedEvent(
            finishReason: FinishReason.stop,
            outcome: 'DEFERRED',
            assistantMessageId: 'a4',
          ),
        );
        async.flushMicrotasks();

        expect(testNotifications.failedCalls, hasLength(1));
        expect(testNotifications.failedCalls.first, 'conv_deferred');
        expect(testNotifications.readyCalls, isEmpty);
      });
    });

    test('background interrupted finishReason -> notifyReplyFailed', () {
      fakeAsync((async) {
        final controller = ChatController(
          client: client,
          conversationId: 'conv_interrupted',
          notifications: testNotifications,
          lifecycleProvider: () => AppLifecycleState.paused,
        );

        controller.send('Trigger interrupted');
        async.flushMicrotasks();

        final stream = client.activeStream!;
        stream.add(
          const RunStartedEvent(
            runId: 'r_int',
            conversationId: 'conv_interrupted',
            userMessageId: 'u_int',
            assistantMessageId: 'a_int',
          ),
        );
        stream.add(
          const MessageDeltaEvent(
            text: 'Partial text before interruption',
            seq: 2,
          ),
        );
        stream.add(
          const RunFinishedEvent(
            finishReason: FinishReason.interrupted,
            assistantMessageId: 'a_int',
          ),
        );
        async.flushMicrotasks();

        expect(testNotifications.failedCalls, ['conv_interrupted']);
        expect(testNotifications.readyCalls, isEmpty);
      });
    });

    test('background stop/cancellation does not trigger notification', () {
      fakeAsync((async) {
        final controller = ChatController(
          client: client,
          conversationId: 'conv_cancel',
          notifications: testNotifications,
          lifecycleProvider: () => AppLifecycleState.paused,
        );

        controller.send('Stop me');
        async.flushMicrotasks();

        final stream = client.activeStream!;
        stream.add(
          const RunStartedEvent(
            runId: 'r_stop',
            conversationId: 'conv_cancel',
            userMessageId: 'u_stop',
            assistantMessageId: 'a_stop',
          ),
        );
        async.flushMicrotasks();

        controller.stop();
        async.flushMicrotasks();

        // 1. RunFinishedEvent with cancelled reason
        stream.add(
          const RunFinishedEvent(
            finishReason: FinishReason.cancelled,
            assistantMessageId: 'a_stop',
          ),
        );
        async.flushMicrotasks();

        expect(testNotifications.readyCalls, isEmpty);
        expect(testNotifications.failedCalls, isEmpty);

        // 2. Stream onDone
        stream.close();
        async.flushMicrotasks();

        expect(testNotifications.readyCalls, isEmpty);
        expect(testNotifications.failedCalls, isEmpty);
      });
    });

    test('background stop then finish with stop reason does not notify', () {
      fakeAsync((async) {
        final controller = ChatController(
          client: client,
          conversationId: 'conv_stop_finish',
          notifications: testNotifications,
          lifecycleProvider: () => AppLifecycleState.paused,
        );

        controller.send('Stop before finish');
        async.flushMicrotasks();

        final stream = client.activeStream!;
        stream.add(
          const RunStartedEvent(
            runId: 'r_stop_finish',
            conversationId: 'conv_stop_finish',
            userMessageId: 'u_stop_finish',
            assistantMessageId: 'a_stop_finish',
          ),
        );
        async.flushMicrotasks();

        controller.stop();
        async.flushMicrotasks();

        stream.add(
          const RunFinishedEvent(
            finishReason: FinishReason.stop,
            assistantMessageId: 'a_stop_finish',
          ),
        );
        async.flushMicrotasks();

        expect(testNotifications.readyCalls, isEmpty);
        expect(testNotifications.failedCalls, isEmpty);
      });
    });

    test(
      'background retries exhausted triggers exactly one failure notification',
      () {
        fakeAsync((async) {
          final controller = ChatController(
            client: client,
            conversationId: 'conv_retry_exhaust',
            notifications: testNotifications,
            lifecycleProvider: () => AppLifecycleState.paused,
            maxResumeRetries: 0,
          );

          controller.send('Exhaust retries');
          async.flushMicrotasks();

          final stream = client.activeStream!;
          stream.add(
            const RunStartedEvent(
              runId: 'r_retry',
              conversationId: 'conv_retry_exhaust',
              userMessageId: 'u_retry',
              assistantMessageId: 'a_retry',
            ),
          );
          stream.addError(
            const RunStreamException(
              category: ErrorCategory.network,
              message: 'network drop',
            ),
          );
          async.flushMicrotasks();

          expect(testNotifications.failedCalls, ['conv_retry_exhaust']);
          expect(testNotifications.readyCalls, isEmpty);
        });
      },
    );

    test(
      'background retry succeeds -> zero failed, one ready notification',
      () {
        fakeAsync((async) {
          final controller = ChatController(
            client: client,
            conversationId: 'conv_retry_ok',
            notifications: testNotifications,
            lifecycleProvider: () => AppLifecycleState.paused,
            maxResumeRetries: 1,
            retryDelay: Duration.zero,
          );

          controller.send('Retry then succeed');
          async.flushMicrotasks();

          final stream1 = client.activeStream!;
          stream1.add(
            const RunStartedEvent(
              runId: 'r_initial',
              conversationId: 'conv_retry_ok',
              userMessageId: 'u_initial',
              assistantMessageId: 'a_initial',
            ),
          );
          // Stream drop triggers auto-resume
          stream1.addError(
            const RunStreamException(
              category: ErrorCategory.network,
              message: 'connection drop',
            ),
          );
          async.flushMicrotasks();

          // While retrying, failure notification is NOT fired yet
          expect(testNotifications.failedCalls, isEmpty);

          // Resume stream succeeds
          final stream2 = client.activeStream!;
          stream2.add(const MessageDeltaEvent(text: 'Recovered reply', seq: 3));
          stream2.add(
            const RunFinishedEvent(
              finishReason: FinishReason.stop,
              assistantMessageId: 'a_initial',
            ),
          );
          async.flushMicrotasks();

          expect(testNotifications.failedCalls, isEmpty);
          expect(testNotifications.readyCalls, hasLength(1));
          expect(
            testNotifications.readyCalls.first['conversationId'],
            'conv_retry_ok',
          );
        });
      },
    );

    test(
      'background unauthorized error in stream triggers failure notification',
      () {
        fakeAsync((async) {
          final controller = ChatController(
            client: client,
            conversationId: 'conv_unauth',
            notifications: testNotifications,
            lifecycleProvider: () => AppLifecycleState.paused,
          );

          controller.send('Trigger unauth');
          async.flushMicrotasks();

          final stream = client.activeStream!;
          stream.addError(
            const RunStreamException(
              category: ErrorCategory.unauthorized,
              message: '401 Unauthorized',
            ),
          );
          async.flushMicrotasks();

          expect(testNotifications.failedCalls, ['conv_unauth']);
          expect(testNotifications.readyCalls, isEmpty);
        });
      },
    );
  });
}
