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
}
