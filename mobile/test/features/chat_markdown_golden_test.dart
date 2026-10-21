@Tags(['golden'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:karmi_app/api/models.dart';
import 'package:karmi_app/features/chat/chat_entry.dart';
import 'package:karmi_app/features/chat/message_bubble.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

void main() {
  Future<void> fontsReady(WidgetTester tester) async {
    tester.takeException();
    await tester.runAsync(GoogleFonts.pendingFonts);
    await settle(tester);
  }

  testWidgets(
    'Markdown reply renders bold, list, and code block without overflow at 360px',
    (tester) async {
      final reply = ReplyEntry(
        id: 'reply_markdown_test',
        message: MessageView.fromJson(
          messageJson(
            'ACCEPT',
            response:
                'Here is the **recommended approach**:\n\n'
                '* Step 1: Initialize the configuration\n'
                '* Step 2: **Execute** the pipeline\n'
                '* Step 3: Verify the output\n\n'
                '```python\n'
                'def bubble_sort(items):\n'
                '    for i in range(len(items)):\n'
                '        for j in range(len(items) - i - 1):\n'
                '            if items[j] > items[j + 1]: items[j], items[j + 1] = items[j + 1], items[j]\n'
                '```\n\n'
                'For details see [documentation](https://karmi.app/docs).',
          ),
        ),
      );

      await pumpHost(
        tester,
        Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: MessageBubble.reply(reply: reply),
          ),
        ),
        size: const Size(360, 640),
      );
      await fontsReady(tester);

      expectNoOverflow(tester);
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('../${goldenPath('chat_markdown_reply')}'),
      );
    },
  );
}
