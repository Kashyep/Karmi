@Tags(['golden'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:karmi_app/features/chat/rendering/markdown_message.dart';

import '../../../support/harness.dart';

void main() {
  Future<void> fontsReady(WidgetTester tester) async {
    await tester.runAsync(GoogleFonts.pendingFonts);
    await settle(tester);
  }

  testWidgets('markdown message basic layout', (tester) async {
    await pumpHost(
      tester,
      const Padding(
        padding: EdgeInsets.all(16),
        child: SingleChildScrollView(
          child: MarkdownMessage(
            text:
                '# Heading\n\nSome **bold** text and a [link](https://example.com).\n\n- first item\n- second item\n\n```dart\nvoid main() {\n  print(1);\n}\n```',
            streaming: false,
          ),
        ),
      ),
      size: const Size(360, 640),
    );
    await fontsReady(tester);
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/markdown_message_basic.png'),
    );
  });

  const renderedReplyText = '''
# Reply Overview

**What is hashing?**
It maps input data into fixed-size values.

"Quoted insight"
Following line after quote.

Math & symbols: 2³² → address space.

```python
def solve():
    return "result" < 10 & 2³²
```
''';

  testWidgets('rendered reply in light mode', (tester) async {
    await pumpHost(
      tester,
      const Padding(
        padding: EdgeInsets.all(16),
        child: SingleChildScrollView(
          child: MarkdownMessage(text: renderedReplyText, streaming: false),
        ),
      ),
      env: const Env(brightness: Brightness.light),
      size: const Size(360, 640),
    );
    await fontsReady(tester);
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/markdown_reply_light.png'),
    );
  });

  testWidgets('rendered reply in dark mode', (tester) async {
    await pumpHost(
      tester,
      const Padding(
        padding: EdgeInsets.all(16),
        child: SingleChildScrollView(
          child: MarkdownMessage(text: renderedReplyText, streaming: false),
        ),
      ),
      env: const Env(brightness: Brightness.dark),
      size: const Size(360, 640),
    );
    await fontsReady(tester);
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/markdown_reply_dark.png'),
    );
  });
}
