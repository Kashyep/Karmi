import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/rendering/code_block.dart';

void main() {
  group('unescapeHtmlEntities', () {
    test('decodes named entities', () {
      expect(
        unescapeHtmlEntities('&quot;a&quot; &lt;b&gt; &amp; &apos;c&apos;'),
        '"a" <b> & \'c\'',
      );
      expect(unescapeHtmlEntities('x&nbsp;y'), 'x\u00A0y');
      expect(unescapeHtmlEntities('2&sup3; &rarr; &hellip;'), '2³ → …');
    });

    test('decodes decimal and hex numeric references', () {
      expect(unescapeHtmlEntities('&#39;&#x27;&#X27;'), "'''");
      expect(unescapeHtmlEntities('&#8594; &#x2192;'), '→ →');
      expect(unescapeHtmlEntities('&#128512;'), '😀');
    });

    test('leaves unknown and malformed references untouched', () {
      expect(unescapeHtmlEntities('&notAnEntity;'), '&notAnEntity;');
      expect(
        unescapeHtmlEntities('&#0; &#xD800; &#x110000;'),
        '&#0; &#xD800; &#x110000;',
      );
      expect(unescapeHtmlEntities('&#;'), '&#;');
    });

    test('requires the semicolon so URLs are not rewritten', () {
      expect(
        unescapeHtmlEntities('https://x.test/?a=1&copy=2&notify=3'),
        'https://x.test/?a=1&copy=2&notify=3',
      );
    });

    test('decodes a single level per call', () {
      expect(unescapeHtmlEntities('&amp;quot;'), '&quot;');
    });
  });

  group('decodeCodeText', () {
    test('reverses markdown escaping and model escaping', () {
      expect(decodeCodeText('&amp;quot; &amp;lt;'), '" <');
      expect(decodeCodeText('&quot; &lt; &amp;'), '" < &');
    });
  });
}
