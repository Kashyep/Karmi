import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/rendering/citation_chip.dart';
import 'package:karmi_app/features/chat/rendering/file_chip.dart';
import 'package:karmi_app/features/chat/rendering/markdown_message.dart';
import 'package:karmi_app/features/chat/rendering/safe_link.dart';

Widget _host(Widget child) => MaterialApp(
  theme: ThemeData(),
  home: Scaffold(body: SingleChildScrollView(child: child)),
);

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
}
