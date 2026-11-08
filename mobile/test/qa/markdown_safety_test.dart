import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/rendering/markdown_message.dart';
import 'package:karmi_app/features/chat/rendering/safe_link.dart';

Widget _host(Widget child) => MaterialApp(
  home: Scaffold(body: SingleChildScrollView(child: child)),
);

void main() {
  group('SafeLink scheme validation', () {
    test('safe schemes allowed: http, https, mailto', () {
      expect(isSafeLinkUri(Uri.parse('https://karmi.ai/docs')), isTrue);
      expect(isSafeLinkUri(Uri.parse('http://example.com')), isTrue);
      expect(isSafeLinkUri(Uri.parse('mailto:support@karmi.ai')), isTrue);
    });

    test('dangerous schemes rejected: javascript, file, data', () {
      expect(isSafeLinkUri(Uri.parse('javascript:alert(1)')), isFalse);
      expect(isSafeLinkUri(Uri.parse('file:///etc/passwd')), isFalse);
      expect(isSafeLinkUri(Uri.parse('data:text/html,<script>')), isFalse);
    });
  });

  group('MarkdownMessage safety', () {
    testWidgets(
      'raw HTML <script> and <img onerror> render as literal text, not widgets/HTML',
      (tester) async {
        const payload =
            'Safe text <script>alert("xss")</script> middle '
            '<img src="invalid.png" onerror="alert(1)"> trailing';

        await tester.pumpWidget(
          _host(const MarkdownMessage(text: payload, streaming: false)),
        );
        await tester.pumpAndSettle();

        // No HTML image widget or native elements rendered
        expect(find.byType(Image), findsNothing);

        // Verbatim text should appear as text strings
        expect(
          find.textContaining('<script>', findRichText: true),
          findsWidgets,
        );
        expect(find.textContaining('<img', findRichText: true), findsWidgets);
        expect(
          find.textContaining('onerror=', findRichText: true),
          findsWidgets,
        );
      },
    );

    testWidgets(
      'javascript: and file: links are not tappable; https: link is tappable',
      (tester) async {
        const payload =
            '[Dangerous JS](javascript:alert(1))\n\n'
            '[Dangerous File](file:///etc/shadow)\n\n'
            '[Safe Web](https://karmi.ai)\n';

        await tester.pumpWidget(
          _host(const MarkdownMessage(text: payload, streaming: false)),
        );
        await tester.pumpAndSettle();

        // Inspect RichText spans
        final richTexts = tester.widgetList<RichText>(find.byType(RichText));
        TapGestureRecognizer? safeRecognizer;
        TapGestureRecognizer? jsRecognizer;
        TapGestureRecognizer? fileRecognizer;

        void walk(InlineSpan span) {
          if (span is TextSpan) {
            final text = span.toPlainText();
            if (text.contains('Safe Web') && span.recognizer != null) {
              safeRecognizer = span.recognizer as TapGestureRecognizer?;
            }
            if (text.contains('Dangerous JS') && span.recognizer != null) {
              jsRecognizer = span.recognizer as TapGestureRecognizer?;
            }
            if (text.contains('Dangerous File') && span.recognizer != null) {
              fileRecognizer = span.recognizer as TapGestureRecognizer?;
            }
            span.children?.forEach(walk);
          }
        }

        for (final rt in richTexts) {
          walk(rt.text);
        }

        // Safe https link has an active TapGestureRecognizer
        expect(safeRecognizer, isNotNull);

        // Malicious or file links have no TapGestureRecognizer attached
        expect(jsRecognizer, isNull);
        expect(fileRecognizer, isNull);
      },
    );
  });
}
