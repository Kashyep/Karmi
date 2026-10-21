import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/models.dart';
import 'package:karmi_app/features/chat/chat_entry.dart';
import 'package:karmi_app/features/chat/message_bubble.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

void main() {
  testWidgets(
    'reply image markdown renders alt text and does not render Image widget',
    (tester) async {
      final reply = ReplyEntry(
        id: 'reply_markdown_image_test',
        message: MessageView.fromJson(
          messageJson(
            'ACCEPT',
            response: '![a chart](https://example.invalid/x.png)',
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
      );

      expect(find.text('a chart'), findsOneWidget);
      expect(find.byType(Image), findsNothing);
    },
  );

  testWidgets(
    'reply with long fenced code block has horizontal scroll and no overflow at 360x640',
    (tester) async {
      final reply = ReplyEntry(
        id: 'reply_markdown_code_test',
        message: MessageView.fromJson(
          messageJson('ACCEPT', response: '```\n${'x = 1; ' * 40}\n```'),
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

      expectNoOverflow(tester);
      final horizontalScrollView = find.byWidgetPredicate(
        (widget) =>
            widget is SingleChildScrollView &&
            widget.scrollDirection == Axis.horizontal,
      );
      expect(horizontalScrollView, findsWidgets);
    },
  );
}
