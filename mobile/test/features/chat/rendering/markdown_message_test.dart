import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:markdown/markdown.dart' as md;
import 'package:karmi_app/features/chat/rendering/citation_chip.dart';
import 'package:karmi_app/features/chat/rendering/file_chip.dart';
import 'package:karmi_app/features/chat/rendering/markdown_message.dart';
import 'package:karmi_app/features/chat/rendering/safe_link.dart';

Widget _host(Widget child) => MaterialApp(
  theme: ThemeData(),
  home: Scaffold(body: SingleChildScrollView(child: child)),
);

RichText richTextContaining(WidgetTester tester, String needle) => tester
    .widgetList<RichText>(find.byType(RichText))
    .firstWhere((w) => w.text.toPlainText().contains(needle));

bool spansUseFallback(InlineSpan span, String family) {
  if (span.style?.fontFamilyFallback?.contains(family) ?? false) return true;
  var found = false;
  span.visitChildren((child) {
    found = spansUseFallback(child, family) || found;
    return !found;
  });
  return found;
}

void main() {
  group('isSafeLinkUri', () {
    test('accepts http, https and mailto', () {
      expect(isSafeLinkUri(Uri.parse('https://example.com/a')), isTrue);
      expect(isSafeLinkUri(Uri.parse('http://example.com')), isTrue);
      expect(isSafeLinkUri(Uri.parse('mailto:a@example.com')), isTrue);
    });

    test('rejects javascript, file and data schemes', () {
      expect(isSafeLinkUri(Uri.parse('javascript:alert(1)')), isFalse);
      expect(isSafeLinkUri(Uri.parse('file:///etc/passwd')), isFalse);
      expect(isSafeLinkUri(Uri.parse('data:text/html,hi')), isFalse);
    });
  });
  testWidgets('renders soft line break after bold text', (tester) async {
    await tester.pumpWidget(
      _host(const MarkdownMessage(text: '**Bold**\nText', streaming: false)),
    );
    final richText = tester.widget<RichText>(
      find.byWidgetPredicate(
        (w) => w is RichText && w.text.toPlainText().contains('Bold'),
      ),
    );
    expect(richText.text.toPlainText(), 'Bold\nText');
  });

  testWidgets('renders soft line break after quoted text', (tester) async {
    await tester.pumpWidget(
      _host(const MarkdownMessage(text: '"quoted"\nText', streaming: false)),
    );
    final richText = tester.widget<RichText>(
      find.byWidgetPredicate(
        (w) => w is RichText && w.text.toPlainText().contains('"quoted"'),
      ),
    );
    expect(richText.text.toPlainText(), '"quoted"\nText');
  });

  testWidgets(
    'fenced code block unescapes entities and copies unescaped payload',
    (tester) async {
      const code = '" < & 2³² → x';
      String? clipboardText;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (MethodCall methodCall) async {
          if (methodCall.method == 'Clipboard.setData') {
            clipboardText =
                (methodCall.arguments as Map<dynamic, dynamic>)['text']
                    as String?;
            return null;
          } else if (methodCall.method == 'Clipboard.getData') {
            return <String, dynamic>{'text': clipboardText};
          }
          return null;
        },
      );

      await tester.pumpWidget(
        _host(const MarkdownMessage(text: '```\n$code\n```', streaming: false)),
      );

      // Assert visible text
      expect(find.text(code), findsOneWidget);
      expect(find.textContaining('&quot;'), findsNothing);
      expect(find.textContaining('&lt;'), findsNothing);
      expect(find.textContaining('&amp;'), findsNothing);

      // Assert Copy payload
      final copyButton = find.byTooltip('Copy code');
      expect(copyButton, findsOneWidget);
      await tester.tap(copyButton);
      await tester.pump(const Duration(seconds: 3));

      expect(clipboardText, code);
      final clipboardData = await Clipboard.getData(Clipboard.kTextPlain);
      expect(clipboardData?.text, code);
    },
  );

  testWidgets('fenced code with entity literals is unchanged', (tester) async {
    const literal = '&lt;b&gt; &amp;amp; "q"';
    String? clipboardText;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (MethodCall methodCall) async {
        if (methodCall.method == 'Clipboard.setData') {
          clipboardText =
              (methodCall.arguments as Map<dynamic, dynamic>)['text']
                  as String?;
        }
        return null;
      },
    );

    await tester.pumpWidget(
      _host(
        const MarkdownMessage(text: '```\n$literal\n```', streaming: false),
      ),
    );

    expect(find.text(literal), findsOneWidget);
    await tester.tap(find.byTooltip('Copy code'));
    await tester.pump(const Duration(seconds: 2));
    expect(clipboardText, literal);
  });

  testWidgets('fenced code decodes parser escaping for display and copy', (
    tester,
  ) async {
    const source = '" < & \' \' 2³ → x';
    const shown = '" < & \' \' 2³ → x';
    String? clipboardText;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (MethodCall methodCall) async {
        if (methodCall.method == 'Clipboard.setData') {
          clipboardText =
              (methodCall.arguments as Map<dynamic, dynamic>)['text']
                  as String?;
        }
        return null;
      },
    );

    await tester.pumpWidget(
      _host(const MarkdownMessage(text: '```\n$source\n```', streaming: false)),
    );

    expect(find.text(shown), findsOneWidget);

    await tester.tap(find.byTooltip('Copy code'));
    await tester.pump(const Duration(seconds: 3));
    expect(clipboardText, shown);
  });

  testWidgets(
    'superscripts and arrows in prose and inline code use the glyph fallback',
    (tester) async {
      await tester.pumpWidget(
        _host(
          const MarkdownMessage(
            text: '2³² → x in prose and `2³² → x` in code',
            streaming: false,
          ),
        ),
      );

      final prose = richTextContaining(tester, '2³² → x in prose');
      expect(prose.text.toPlainText(), contains('2³² → x in prose'));
      expect(spansUseFallback(prose.text, 'Noto Sans Math'), isTrue);

      final code = richTextContaining(tester, '2³² → x');
      expect(spansUseFallback(code.text, 'Noto Sans Math'), isTrue);
    },
  );

  testWidgets('raw HTML is shown as literal text', (tester) async {
    await tester.pumpWidget(
      _host(
        const MarkdownMessage(
          text: 'Hello <script>alert(1)</script> world',
          streaming: false,
        ),
      ),
    );
    expect(find.textContaining('<script>', findRichText: true), findsWidgets);
  });

  testWidgets('citation marker renders a CitationChip', (tester) async {
    await tester.pumpWidget(
      _host(const MarkdownMessage(text: 'Fact [1] here.', streaming: false)),
    );
    expect(find.byType(CitationChip), findsOneWidget);
  });

  testWidgets('unclosed fence while streaming does not throw', (tester) async {
    await tester.pumpWidget(
      _host(
        const MarkdownMessage(
          text: 'Start\n```dart\nvoid main() {',
          streaming: true,
        ),
      ),
    );
    expect(tester.takeException(), isNull);
    expect(
      find.textContaining('void main()', findRichText: true),
      findsWidgets,
    );
  });

  testWidgets('file fence renders a FileCard with its name', (tester) async {
    await tester.pumpWidget(
      _host(
        const MarkdownMessage(
          text: '```file:notes.txt\nhello\n```',
          streaming: false,
        ),
      ),
    );
    expect(find.byType(FileCard), findsOneWidget);
    expect(find.text('notes.txt'), findsOneWidget);
  });

  testWidgets('long output shows Show more when not streaming', (tester) async {
    final long = List.generate(80, (i) => 'line $i').join('\n');
    await tester.pumpWidget(
      _host(MarkdownMessage(text: long, streaming: false)),
    );
    expect(find.text('Show more'), findsOneWidget);
    await tester.tap(find.text('Show more'));
    await tester.pump();
    expect(find.text('Show more'), findsNothing);
  });

  testWidgets('streaming never offers collapse', (tester) async {
    final long = List.generate(80, (i) => 'line $i').join('\n');
    await tester.pumpWidget(
      _host(MarkdownMessage(text: long, streaming: true)),
    );
    expect(find.text('Show more'), findsNothing);
  });

  group('ParsedMarkdownCache', () {
    test('caches parsed AST and reports hit on identical key', () {
      final cache = ParsedMarkdownCache(capacity: 5);
      var parseCount = 0;
      List<md.Node> parse(String t) {
        parseCount++;
        return [md.Text(t)];
      }

      final first = cache.getOrParse('msg-1:hello', () => parse('hello'));
      expect(parseCount, 1);
      expect(cache.hits, 0);
      expect(cache.misses, 1);

      final second = cache.getOrParse('msg-1:hello', () => parse('hello'));
      expect(parseCount, 1);
      expect(cache.hits, 1);
      expect(cache.misses, 1);
      expect(identical(first, second), isTrue);
    });

    test('invalidates on content change (streaming updates)', () {
      final cache = ParsedMarkdownCache(capacity: 5);
      var parseCount = 0;

      cache.getOrParse('msg-1:tok1', () {
        parseCount++;
        return [md.Text('tok1')];
      });
      expect(parseCount, 1);

      // Content changes -> new key, parses new revision
      cache.getOrParse('msg-1:tok1 tok2', () {
        parseCount++;
        return [md.Text('tok1 tok2')];
      });
      expect(parseCount, 2);
      expect(cache.hits, 0);
      expect(cache.misses, 2);
    });

    test('bounds cache size and evicts least recently used', () {
      final cache = ParsedMarkdownCache(capacity: 2);
      cache.getOrParse('a', () => [md.Text('a')]);
      cache.getOrParse('b', () => [md.Text('b')]);
      expect(cache.size, 2);
      expect(cache.containsKey('a'), isTrue);

      // Adding 'c' evicts 'a'
      cache.getOrParse('c', () => [md.Text('c')]);
      expect(cache.size, 2);
      expect(cache.containsKey('a'), isFalse);
      expect(cache.containsKey('b'), isTrue);
      expect(cache.containsKey('c'), isTrue);
    });
  });

  testWidgets('MarkdownMessage uses cache and updates on streaming change', (tester) async {
    final cache = ParsedMarkdownCache(capacity: 10);
    await tester.pumpWidget(
      _host(
        MarkdownMessage(
          messageId: 'm1',
          text: 'Initial text',
          streaming: true,
          cache: cache,
        ),
      ),
    );
    expect(cache.misses, 1);
    expect(cache.hits, 0);

    // Rebuilding with identical messageId and text hits cache
    await tester.pumpWidget(
      _host(
        MarkdownMessage(
          messageId: 'm1',
          text: 'Initial text',
          streaming: true,
          cache: cache,
        ),
      ),
    );
    expect(cache.misses, 1);
    expect(cache.hits, 1);

    // Streaming content update invalidates and parses new text
    await tester.pumpWidget(
      _host(
        MarkdownMessage(
          messageId: 'm1',
          text: 'Initial text with delta',
          streaming: true,
          cache: cache,
        ),
      ),
    );
    expect(cache.misses, 2);
    expect(cache.hits, 1);
  });
}
