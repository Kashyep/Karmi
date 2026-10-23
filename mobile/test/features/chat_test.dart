import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:karmi_app/api/models.dart';
import 'package:karmi_app/features/chat/error_card.dart';
import 'package:karmi_app/features/chat/message_bubble.dart';
import 'package:karmi_app/features/plans/plan_selection_screen.dart';
import 'package:karmi_app/features/tasks/task_confirmation_sheet.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:karmi_app/widgets/feedback.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

Future<void> send(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.tap(find.byTooltip('Send message'));
  await tester.pump();
}

http.Response sseResponse(
  String text, {
  String runId = 'run-1',
  String finishReason = 'stop',
  String outcome = 'success',
}) {
  final sse =
      'event: run.started\n'
      'data: {"run_id":"$runId","conversation_id":"conv-1","user_message_id":"msg-u","assistant_message_id":"msg-a","seq":0}\n\n'
      'id: 1\n'
      'event: message.delta\n'
      'data: {"text":"$text"}\n\n'
      'event: run.finished\n'
      'data: {"finish_reason":"$finishReason","outcome":"$outcome"}\n\n';
  return http.Response(
    sse,
    200,
    headers: {'content-type': 'text/event-stream'},
  );
}

FakeBackend backendWith(Handler streamHandler) =>
    FakeBackend.healthy()..on('POST', '/v1/chat/stream', streamHandler);

class _FakeHttpHeaders implements HttpHeaders {
  final Map<String, List<String>> _headers = {};

  @override
  List<String>? operator [](String name) => _headers[name.toLowerCase()];

  @override
  void add(String name, Object value, {bool? preserveHeaderCase}) {
    _headers.putIfAbsent(name.toLowerCase(), () => []).add(value.toString());
  }

  @override
  void set(String name, Object value, {bool? preserveHeaderCase}) {
    _headers[name.toLowerCase()] = [value.toString()];
  }

  @override
  void remove(String name, Object value) =>
      _headers[name.toLowerCase()]?.remove(value.toString());

  @override
  void removeAll(String name) => _headers.remove(name.toLowerCase());

  @override
  void forEach(void Function(String name, List<String> values) action) =>
      _headers.forEach(action);

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
  bool persistentConnection = false;

  @override
  void clear() => _headers.clear();

  @override
  String? value(String name) => _headers[name.toLowerCase()]?.firstOrNull;

  @override
  void noFolding(String name) {}
}

class _BackendHttpClientResponse extends Stream<List<int>>
    implements HttpClientResponse {
  _BackendHttpClientResponse(
    this.statusCode,
    Map<String, String> rawHeaders,
    this.body,
  ) {
    rawHeaders.forEach((k, v) => headers.set(k, v));
  }

  @override
  final int statusCode;
  final List<int> body;
  @override
  final HttpHeaders headers = _FakeHttpHeaders();

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
  @override
  Future<HttpClientResponse> redirect([
    String? method,
    Uri? url,
    bool? followLoops,
  ]) => throw UnimplementedError();
}

class _BackendHttpClientRequest implements HttpClientRequest {
  _BackendHttpClientRequest(this.backend, this.method, this.uri);

  final FakeBackend backend;
  @override
  final String method;
  @override
  final Uri uri;

  final BytesBuilder _bodyBytes = BytesBuilder();
  @override
  final HttpHeaders headers = _FakeHttpHeaders();

  @override
  void abort([Object? exception, StackTrace? stackTrace]) {}

  @override
  void add(List<int> data) => _bodyBytes.add(data);

  @override
  void addError(Object error, [StackTrace? stackTrace]) {}

  @override
  Future addStream(Stream<List<int>> stream) async {
    await for (final chunk in stream) {
      _bodyBytes.add(chunk);
    }
  }

  @override
  Future<HttpClientResponse> close() async {
    final req = http.Request(method, uri);
    headers.forEach((name, values) {
      req.headers[name] = values.join(', ');
    });
    req.bodyBytes = _bodyBytes.toBytes();
    final streamed = await backend.client.send(req);
    final responseBytes = await streamed.stream.toBytes();
    return _BackendHttpClientResponse(
      streamed.statusCode,
      streamed.headers,
      responseBytes,
    );
  }

  @override
  Future<HttpClientResponse> get done => close();

  @override
  Future flush() async {}

  @override
  void write(Object? object) {
    if (object != null) _bodyBytes.add(utf8.encode(object.toString()));
  }

  @override
  void writeAll(Iterable objects, [String separator = '']) {
    write(objects.join(separator));
  }

  @override
  void writeCharCode(int charCode) => _bodyBytes.add([charCode]);

  @override
  void writeln([Object? object = '']) {
    write(object);
    _bodyBytes.add(utf8.encode('\n'));
  }

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
  bool persistentConnection = false;
  @override
  HttpConnectionInfo? get connectionInfo => null;
  @override
  List<Cookie> get cookies => [];
}

class _BackendHttpClient implements HttpClient {
  _BackendHttpClient(this.backendProvider);
  final FakeBackend Function() backendProvider;

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async {
    return _BackendHttpClientRequest(backendProvider(), method, url);
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
  void addProxyCredentials(
    String host,
    int port,
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

class _BackendHttpOverrides extends HttpOverrides {
  _BackendHttpOverrides(this.backendProvider);
  final FakeBackend Function() backendProvider;

  @override
  HttpClient createHttpClient(SecurityContext? context) =>
      _BackendHttpClient(backendProvider);
}

FakeBackend? _currentBackend;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  HttpOverrides.global = _BackendHttpOverrides(
    () => _currentBackend ?? FakeBackend.healthy(),
  );

  setUp(() {
    _currentBackend = null;
  });

  tearDown(() {
    _currentBackend = null;
  });

  testWidgets('empty: Trykker empty state, send disabled until text', (
    tester,
  ) async {
    final app = await pumpApp(tester);
    _currentBackend = app.backend;
    final quote = find.text(
      'Ask a study question, or get help with maths or code.',
    );
    expect(quote, findsOneWidget);
    final send = tester.widget<IconButton>(
      find.ancestor(
        of: find.byIcon(Icons.arrow_upward),
        matching: find.byType(IconButton),
      ),
    );
    expect(send.onPressed, isNull);
    expect(find.byType(KarmiLoader), findsNothing);
    await expectA11yGuidelines(tester);
  });

  testWidgets('pending: loader only while the request is in flight', (
    tester,
  ) async {
    final reply = Completer<http.Response>();
    final backend = backendWith((_) => reply.future);
    _currentBackend = backend;
    await pumpApp(tester, backend: backend);
    await send(tester, 'Plan my week');
    expect(find.text('Working…'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.byIcon(Icons.stop), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'second');
    await tester.pump();
    final button = tester.widget<IconButton>(
      find.ancestor(
        of: find.byIcon(Icons.stop),
        matching: find.byType(IconButton),
      ),
    );
    expect(button.onPressed, isNotNull);
    reply.complete(sseResponse('Completed'));
    await settle(tester);
    expect(find.byType(KarmiLoader), findsNothing);
    expect(find.text('Completed'), findsOneWidget);
  });

  testWidgets('pending under reduced motion: static icon plus text', (
    tester,
  ) async {
    final reply = Completer<http.Response>();
    final backend = backendWith((_) => reply.future);
    _currentBackend = backend;
    await pumpApp(tester, backend: backend, env: const Env(reduceMotion: true));
    await send(tester, 'Plan my week');
    expect(find.text('Working…'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.byIcon(Icons.more_horiz), findsOneWidget);
    reply.complete(sseResponse('Completed'));
    await settle(tester);
  });

  const outcomeCopy = {
    'ACCEPT': 'Completed',
    'REPAIR': 'Corrected',
    'ESCALATE': 'Needs review',
    'ASK_USER': 'Awaiting confirmation',
    'SAFE_STOP': 'Could not confirm completion',
    'DEFERRED': 'Deferred',
    'BRAND_NEW_OUTCOME': 'Status unknown',
  };
  for (final MapEntry(key: wire, value: _) in outcomeCopy.entries) {
    testWidgets('outcome $wire streams "Reply for $wire"', (tester) async {
      final backend = backendWith(
        (_) => sseResponse('Reply for $wire', outcome: wire),
      );
      _currentBackend = backend;
      await pumpApp(tester, backend: backend);
      await send(tester, 'hello');
      await settle(tester);
      expect(find.text('Reply for $wire'), findsOneWidget);
      await expectA11yGuidelines(tester);
    });
  }

  testWidgets('new replies are live regions for screen readers', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    final app = await pumpApp(tester);
    _currentBackend = app.backend;
    await send(tester, 'first');
    await settle(tester);
    await send(tester, 'second');
    await settle(tester);
    final replies = tester
        .widgetList<MessageBubble>(find.byType(MessageBubble))
        .where((b) => b.chatMessage?.role == 'assistant' || b.reply != null)
        .toList();
    expect(replies, hasLength(2));
    expect(replies.first.announce, isFalse);
    expect(replies.last.announce, isTrue);
    final replyNodes = find.bySemanticsLabel(RegExp('^Karmi replied'));
    expect(replyNodes, findsNWidgets(2));
    bool live(Finder f) =>
        tester.getSemantics(f).getSemanticsData().flagsCollection.isLiveRegion;
    expect(live(replyNodes.first), isFalse);
    expect(live(replyNodes.last), isTrue);
    handle.dispose();
  });

  testWidgets('failed (500): ErrorCard, no raw exception text', (tester) async {
    final backend = backendWith((_) => http.Response('Traceback: boom', 500));
    _currentBackend = backend;
    await pumpApp(tester, backend: backend);
    await send(tester, 'hello');
    await settle(tester);
    await settle(tester);
    expect(find.byType(ErrorCard), findsOneWidget);
    expect(find.text('The model service had a problem.'), findsOneWidget);
    expect(find.textContaining('Exception'), findsNothing);
    expect(find.textContaining('500'), findsNothing);
    expect(find.textContaining('Traceback'), findsNothing);
    await expectA11yGuidelines(tester);
  });

  testWidgets('offline: banner and retry reuses the idempotency key', (
    tester,
  ) async {
    var calls = 0;
    final backend = FakeBackend.healthy();
    _currentBackend = backend;
    backend.on('POST', '/v1/chat/stream', (request) {
      calls++;
      if (calls <= 4) return FakeBackend.network()(request);
      return sseResponse('Completed');
    });
    final app = await pumpApp(tester, backend: backend);
    await send(tester, 'hello');
    await settle(tester);
    await settle(tester);
    expect(find.text('You appear to be offline.'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await settle(tester);
    expect(find.text('You appear to be offline.'), findsNothing);
    expect(find.text('Completed'), findsOneWidget);

    final keys = app.backend.requests
        .where((r) => r.url.path == '/v1/chat/stream')
        .map((r) => (jsonDecode(r.body) as Map)['client_message_id'])
        .toList();
    expect(keys.length, greaterThanOrEqualTo(2));
    expect(keys.first, keys.last);
  });

  testWidgets('409 in flight: explains and re-checks with the same key', (
    tester,
  ) async {
    var calls = 0;
    final backend = FakeBackend.healthy();
    _currentBackend = backend;
    backend.on('POST', '/v1/chat/stream', (_) {
      calls++;
      return calls == 1
          ? jsonResponse({
              'detail':
                  'request already in flight; retry to observe its result',
            }, 409)
          : sseResponse('Completed');
    });
    final app = await pumpApp(tester, backend: backend);
    await send(tester, 'hello');
    await settle(tester);
    expect(find.text('Completed'), findsOneWidget);
    final keys = app.backend.requests
        .where((r) => r.url.path == '/v1/chat/stream')
        .map((r) => (jsonDecode(r.body) as Map)['client_message_id'])
        .toSet();
    expect(keys, hasLength(1));
  });

  testWidgets('limit reached (429): allowance banner opens plans', (
    tester,
  ) async {
    final backend = backendWith(
      (_) => jsonResponse({
        'detail': {
          'code': 'ALLOWANCE_EXHAUSTED',
          'message': 'everyday allowance exhausted',
          'reset_at': '2026-09-27T00:00:00+00:00',
        },
      }, 429),
    );
    _currentBackend = backend;
    await pumpApp(tester, backend: backend);
    await send(tester, 'hello');
    await settle(tester);
    expect(
      find.text("You've reached your plan limit for now."),
      findsOneWidget,
    );
    // Tap View plans
    await tester.tap(find.text('View plans'));
    await settle(tester);
    expect(find.byType(PlanSelectionScreen), findsOneWidget);
  });

  testWidgets('beta capacity full (429): banner says try again later', (
    tester,
  ) async {
    final backend = backendWith((_) {
      return jsonResponse({
        'detail': {
          'code': 'BETA_CAPACITY_FULL',
          'message': "Karmi's beta has reached today's limit.",
          'reset_at': '2026-10-22T00:00:00+00:00',
        },
      }, 429);
    });
    _currentBackend = backend;
    await pumpApp(tester, backend: backend);
    await send(tester, 'hello');
    await settle(tester);
    await settle(tester);
    expect(find.text('Karmi is busy right now.'), findsOneWidget);
    expect(find.text('View plans'), findsNothing);
    await expectA11yGuidelines(tester);
  });

  testWidgets('401 ends the session and returns to Welcome', (tester) async {
    final backend = backendWith(
      (_) => jsonResponse({'detail': 'invalid session'}, 401),
    );
    _currentBackend = backend;
    final app = await pumpApp(tester, backend: backend);
    await send(tester, 'hello');
    await settle(tester);
    expect(app.session.isSignedIn, isFalse);
    expect(find.text('Session ended'), findsOneWidget);
    await tester.pumpWidget(
      MaterialApp(
        theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => showTaskConfirmationSheet(
                context,
                const MessageView(
                  runId: 'r',
                  status: 'completed',
                  outcome: Outcome.askUser,
                  response: 'Which day should I remind you?',
                  route: 'fake',
                ),
              ),
              child: const Text('Review details'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Review details'));
    await settle(tester);
    expect(find.byType(TaskConfirmationSheet), findsOneWidget);
    expect(find.text('Confirm task'), findsOneWidget);
    expect(find.text('Not provided'), findsNWidgets(4));
    final confirm = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Confirm'),
    );
    expect(confirm.onPressed, isNull);
    final body = tester.widget<ColoredBox>(
      find
          .descendant(
            of: find.byType(TaskConfirmationSheet),
            matching: find.byType(ColoredBox),
          )
          .first,
    );
    expect(body.color.a, 1.0);
    await expectA11yGuidelines(tester);
  });

  for (final rt in [false, true]) {
    testWidgets(
      'text scale 2.0 does not overflow (${rt ? 'opaque' : 'glass'})',
      (tester) async {
        var calls = 0;
        final backend = backendWith((request) {
          calls++;
          if (calls >= 2) return FakeBackend.network()(request);
          return sseResponse(
            'I could not confirm whether the reminder was saved. '
            "I'm checking its status.",
          );
        });
        _currentBackend = backend;
        await pumpApp(
          tester,
          env: Env(textScale: 2.0, reduceTransparency: rt),
          backend: backend,
        );
        expectNoOverflow(tester);
        await send(tester, 'Remind me to call the bank tomorrow at 9');
        await settle(tester);
        await send(tester, 'And again');
        await settle(tester);
        await settle(tester);
        expectNoOverflow(tester);
        await expectA11yGuidelines(tester);
      },
    );
  }
}
