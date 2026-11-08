import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/conversations/conversations_api.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/api/stream/run_stream_client.dart';
import 'package:karmi_app/features/chat/chat_screen.dart';
import 'package:karmi_app/features/chat/state/chat_controller.dart';
import 'package:karmi_app/features/history/conversation_list_controller.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

class FakeRunStreamClient extends RunStreamClient {
  FakeRunStreamClient() : super(baseUrl: 'http://fake.test');

  StreamController<RunEvent>? activeRunController;
  final List<Map<String, dynamic>> startRunCalls = [];

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
    activeRunController = StreamController<RunEvent>.broadcast();
    return activeRunController!.stream;
  }

  void emitStarted() {
    activeRunController?.add(
      const RunStartedEvent(
        runId: 'run-1',
        conversationId: 'conv-1',
        userMessageId: 'user-1',
        assistantMessageId: 'asst-1',
      ),
    );
  }

  void emitDelta(String text) {
    activeRunController?.add(MessageDeltaEvent(text: text));
  }

  void emitFinished({FinishReason finishReason = FinishReason.stop}) {
    activeRunController?.add(RunFinishedEvent(finishReason: finishReason));
    activeRunController?.close();
  }
}

class FakeConversationsApi implements ConversationsApi {
  FakeConversationsApi({
    this.conversations = const [],
    this.messageItems = const [],
  });

  final List<ConversationView> conversations;
  final List<ChatMessageView> messageItems;
  final List<String> callLog = [];

  @override
  String baseUrl = 'http://fake.test';

  @override
  Duration timeout = const Duration(seconds: 1);

  @override
  Future<String?> Function()? tokenProvider;

  @override
  void close() {}

  @override
  Future<ConversationPage> list({
    bool archived = false,
    String? cursor,
    int limit = 20,
  }) async {
    callLog.add('list');
    return ConversationPage(items: conversations, nextCursor: null);
  }

  @override
  Future<MessagePage> messages(
    String id, {
    String? before,
    int limit = 50,
  }) async {
    callLog.add('messages:$id');
    return MessagePage(items: messageItems, hasMoreBefore: false);
  }

  @override
  Future<ConversationView> get(String id) async => throw UnimplementedError();

  @override
  Future<ConversationView> update(
    String id, {
    String? title,
    bool? pinned,
    bool? archived,
  }) async => throw UnimplementedError();

  @override
  Future<void> delete(String id) async => throw UnimplementedError();

  @override
  Future<ConversationView> restore(String id) async =>
      throw UnimplementedError();

  @override
  Future<List<ConversationSearchResult>> search(
    String q, {
    int limit = 20,
  }) async => [];
}

class _FakeHttpHeaders implements HttpHeaders {
  final Map<String, List<String>> _headers = {};

  @override
  void add(String name, Object value, {bool preserveHeaderCase = false}) {
    _headers.putIfAbsent(name.toLowerCase(), () => []).add(value.toString());
  }

  @override
  void set(String name, Object value, {bool preserveHeaderCase = false}) {
    _headers[name.toLowerCase()] = [value.toString()];
  }

  @override
  List<String>? operator [](String name) => _headers[name.toLowerCase()];

  @override
  String? value(String name) => _headers[name.toLowerCase()]?.firstOrNull;

  @override
  void remove(String name, Object value) {}

  @override
  void removeAll(String name) {}

  @override
  void forEach(void Function(String name, List<String> values) action) =>
      _headers.forEach(action);

  @override
  void noFolding(String name) {}

  @override
  bool persistentConnection = false;

  @override
  bool chunkedTransferEncoding = false;

  @override
  int contentLength = 0;

  @override
  ContentType? contentType;

  @override
  DateTime? date;

  @override
  DateTime? expires;

  @override
  String? host;

  @override
  DateTime? ifModifiedSince;

  @override
  int? port;

  @override
  void clear() => _headers.clear();
}

class _FakeHttpClientResponse extends Stream<List<int>>
    implements HttpClientResponse {
  final List<int> body;
  @override
  final int statusCode = 200;

  _FakeHttpClientResponse(this.body);

  @override
  Future<HttpClientResponse> redirect([
    String? method,
    Uri? url,
    bool? followLoops,
  ]) => throw UnimplementedError();

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int> event)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream.value(body).listen(
      onData,
      onError: onError,
      onDone: onDone,
      cancelOnError: cancelOnError,
    );
  }

  @override
  final HttpHeaders headers = _FakeHttpHeaders();

  @override
  int get contentLength => body.length;

  @override
  HttpClientResponseCompressionState get compressionState =>
      HttpClientResponseCompressionState.notCompressed;

  @override
  List<Cookie> get cookies => [];

  @override
  Future<Socket> detachSocket() => throw UnimplementedError();

  @override
  bool get isRedirect => false;

  @override
  bool get persistentConnection => false;

  @override
  String get reasonPhrase => 'OK';

  @override
  List<RedirectInfo> get redirects => [];

  @override
  X509Certificate? get certificate => null;

  @override
  HttpConnectionInfo? get connectionInfo => null;
}

class _FakeHttpClientRequest implements HttpClientRequest {
  final _FakeHttpClientResponse response;
  _FakeHttpClientRequest(this.response);

  @override
  void abort([Object? exception, StackTrace? stackTrace]) {}

  @override
  final HttpHeaders headers = _FakeHttpHeaders();

  @override
  Future<HttpClientResponse> close() async => response;

  @override
  void add(List<int> data) {}

  @override
  void addError(Object error, [StackTrace? stackTrace]) {}

  @override
  Future addStream(Stream<List<int>> stream) async {}

  @override
  Future<HttpClientResponse> get done async => response;

  @override
  Future flush() async {}

  @override
  void write(Object? object) {}

  @override
  void writeAll(Iterable objects, [String separator = '']) {}

  @override
  void writeCharCode(int charCode) {}

  @override
  void writeln([Object? object = '']) {}

  @override
  bool bufferOutput = false;

  @override
  int contentLength = 0;

  @override
  Encoding encoding = utf8;

  @override
  bool followRedirects = true;

  @override
  int maxRedirects = 5;

  @override
  String method = 'GET';

  @override
  bool persistentConnection = false;

  @override
  Uri get uri => Uri.parse('http://fake.test');

  @override
  HttpConnectionInfo? get connectionInfo => null;

  @override
  List<Cookie> get cookies => [];
}

class _FakeHttpClient implements HttpClient {
  final Map<String, dynamic> responseJson;
  _FakeHttpClient(this.responseJson);

  @override
  void addProxyCredentials(
    String host,
    int port,
    String realm,
    HttpClientCredentials credentials,
  ) {}

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async {
    final bytes = utf8.encode(jsonEncode(responseJson));
    return _FakeHttpClientRequest(_FakeHttpClientResponse(bytes));
  }

  @override
  Future<HttpClientRequest> getUrl(Uri url) => openUrl('GET', url);
  @override
  Future<HttpClientRequest> postUrl(Uri url) => openUrl('POST', url);
  @override
  Future<HttpClientRequest> putUrl(Uri url) => openUrl('PUT', url);
  @override
  Future<HttpClientRequest> deleteUrl(Uri url) => openUrl('DELETE', url);
  @override
  Future<HttpClientRequest> patchUrl(Uri url) => openUrl('PATCH', url);
  @override
  Future<HttpClientRequest> headUrl(Uri url) => openUrl('HEAD', url);
  @override
  Future<HttpClientRequest> open(
    String method,
    String host,
    int port,
    String path,
  ) => openUrl(method, Uri.parse('http://$host:$port$path'));
  @override
  Future<HttpClientRequest> get(String host, int port, String path) =>
      open('GET', host, port, path);
  @override
  Future<HttpClientRequest> post(String host, int port, String path) =>
      open('POST', host, port, path);
  @override
  Future<HttpClientRequest> put(String host, int port, String path) =>
      open('PUT', host, port, path);
  @override
  Future<HttpClientRequest> delete(String host, int port, String path) =>
      open('DELETE', host, port, path);
  @override
  Future<HttpClientRequest> patch(String host, int port, String path) =>
      open('PATCH', host, port, path);
  @override
  Future<HttpClientRequest> head(String host, int port, String path) =>
      open('HEAD', host, port, path);

  @override
  bool autoUncompress = true;
  @override
  Duration? connectionTimeout;
  @override
  Duration idleTimeout = const Duration(seconds: 15);
  @override
  int? maxConnectionsPerHost;
  @override
  String? userAgent;
  @override
  void addCredentials(
    Uri url,
    String realm,
    HttpClientCredentials credentials,
  ) {}
  @override
  void close({bool force = false}) {}
  @override
  set authenticate(
    Future<bool> Function(Uri url, String scheme, String? realm)? f,
  ) {}
  @override
  set authenticateProxy(
    Future<bool> Function(String host, int port, String scheme, String? realm)?
    f,
  ) {}
  @override
  set badCertificateCallback(
    bool Function(X509Certificate cert, String host, int port)? callback,
  ) {}
  @override
  set findProxy(String Function(Uri url)? f) {}
  @override
  set connectionFactory(
    Future<ConnectionTask<Socket>> Function(
      Uri url,
      String? proxyHost,
      int? proxyPort,
    )?
    f,
  ) {}
  @override
  set keyLog(Function(String line)? callback) {}
}

class _GlobalHttpOverrides extends HttpOverrides {
  final Map<String, dynamic> responseJson;
  _GlobalHttpOverrides(this.responseJson);

  @override
  HttpClient createHttpClient(SecurityContext? context) =>
      _FakeHttpClient(responseJson);
}

Widget wrapChatScreen(Widget child) {
  return LiquidGlassWidgets.wrap(
    child: MaterialApp(
      theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
      home: Scaffold(body: child),
    ),
  );
}

Future<void> pumpChat(
  WidgetTester tester, {
  ChatController? chatController,
  ConversationListController? convController,
  String? conversationId,
}) async {
  await tester.pumpWidget(
    wrapChatScreen(
      ChatScreen(
        api: KarmiApi(baseUrl: 'http://fake.test'),
        chatController: chatController,
        conversationListController: convController,
        conversationId: conversationId,
      ),
    ),
  );
  await tester.pump();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('(a) send -> stream -> finish renders the assistant text', () {
    testWidgets('streaming completion displays assistant message', (
      tester,
    ) async {
      final fakeStream = FakeRunStreamClient();
      final controller = ChatController(
        client: fakeStream,
        deltaFlushInterval: Duration.zero,
      );
      await pumpChat(tester, chatController: controller);

      await tester.enterText(find.byType(TextField), 'Explain gravity');
      await tester.pump();
      await tester.tap(find.byTooltip('Send message'));
      await tester.pump();

      fakeStream.emitStarted();
      fakeStream.emitDelta('Gravity is a force of attraction.');
      fakeStream.emitFinished();
      await tester.pumpAndSettle();

      expect(
        find.textContaining('Gravity is a force of attraction.'),
        findsOneWidget,
      );
    });
  });

  group('(b) a run that finishes with interrupted shows a Resume action', () {
    testWidgets('interrupted run displays Resume action button', (
      tester,
    ) async {
      final fakeStream = FakeRunStreamClient();
      final controller = ChatController(
        client: fakeStream,
        deltaFlushInterval: Duration.zero,
      );
      await pumpChat(tester, chatController: controller);

      await tester.enterText(find.byType(TextField), 'Summarize history');
      await tester.pump();
      await tester.tap(find.byTooltip('Send message'));
      await tester.pump();

      fakeStream.emitStarted();
      fakeStream.emitDelta('Once upon a time');
      fakeStream.emitFinished(finishReason: FinishReason.interrupted);
      await tester.pumpAndSettle();

      expect(find.widgetWithText(TextButton, 'Resume'), findsOneWidget);
    });
  });

  group('(c) finishReason length shows a Continue action', () {
    testWidgets('length finish reason displays Continue action button', (
      tester,
    ) async {
      final fakeStream = FakeRunStreamClient();
      final controller = ChatController(
        client: fakeStream,
        deltaFlushInterval: Duration.zero,
      );
      await pumpChat(tester, chatController: controller);

      await tester.enterText(find.byType(TextField), 'Write long story');
      await tester.pump();
      await tester.tap(find.byTooltip('Send message'));
      await tester.pump();

      fakeStream.emitStarted();
      fakeStream.emitDelta('Part 1 of the story');
      fakeStream.emitFinished(finishReason: FinishReason.length);
      await tester.pumpAndSettle();

      expect(find.widgetWithText(TextButton, 'Continue'), findsOneWidget);
    });
  });

  group('(d) New Chat creates no record before first message', () {
    testWidgets('tapping new chat does not make create API calls', (
      tester,
    ) async {
      final fakeApi = FakeConversationsApi();
      final convController = ConversationListController(api: fakeApi);
      final fakeStream = FakeRunStreamClient();
      final controller = ChatController(client: fakeStream);

      await pumpChat(
        tester,
        chatController: controller,
        convController: convController,
      );
      await tester.tap(find.byTooltip('New chat'));
      await tester.pumpAndSettle();

      final createCalls = fakeApi.callLog.where((c) => c.startsWith('create'));
      expect(createCalls, isEmpty);
      expect(fakeStream.startRunCalls, isEmpty);
    });
  });

  group(
    '(e) opening a history item loads its messages into the transcript',
    () {
      testWidgets('history modal item selection loads transcript messages', (
        tester,
      ) async {
        final fakeApi = FakeConversationsApi(
          conversations: [
            ConversationView(
              id: 'conv-42',
              title: 'Plan vacation',
              updatedAt: DateTime.utc(2026, 10, 20),
            ),
          ],
        );
        final convController = ConversationListController(api: fakeApi);
        await convController.refresh();

        HttpOverrides.global = _GlobalHttpOverrides({
          'items': [
            {
              'id': 'msg-1',
              'conversation_id': 'conv-42',
              'role': 'assistant',
              'status': 'complete',
              'content': 'Here is your vacation itinerary',
              'created_at': '2026-10-20T12:00:00Z',
              'updated_at': '2026-10-20T12:00:00Z',
            },
          ],
          'has_more_before': false,
        });
        addTearDown(() => HttpOverrides.global = null);

        await pumpChat(tester, convController: convController);

        await tester.tap(find.byTooltip('Conversation history'));
        await tester.pumpAndSettle();

        expect(find.text('Plan vacation'), findsOneWidget);
        await tester.tap(find.text('Plan vacation'));
        await tester.pumpAndSettle();

        expect(
          find.textContaining('Here is your vacation itinerary'),
          findsOneWidget,
        );
      });
    },
  );
}
