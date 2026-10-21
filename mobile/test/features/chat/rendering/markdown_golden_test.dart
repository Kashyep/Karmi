@Tags(['golden'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/rendering/markdown_message.dart';

void main() {
  testWidgets('markdown message basic layout', (tester) async {
    tester.view
      ..physicalSize = const Size(360, 640)
      ..devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData(useMaterial3: true),
        home: const Scaffold(
          body: Padding(
            padding: EdgeInsets.all(16),
            child: SingleChildScrollView(
              child: MarkdownMessage(
                text:
                    '# Heading\n\nSome **bold** text and a [link](https://example.com).\n\n- first item\n- second item\n\n```dart\nvoid main() {\n  print(1);\n}\n```',
                streaming: false,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/markdown_message_basic.png'),
    );
  });
}
