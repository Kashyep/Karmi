import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:karmi_app/api/models.dart';
import 'package:karmi_app/features/chat/chat_entry.dart';
import 'package:karmi_app/features/chat/message_bubble.dart';
import 'package:karmi_app/theme/karmi_theme.dart';

import '../support/harness.dart';

const _prose =
    'Your analysis allowance resets at 09:30 tomorrow, Asia/Kolkata. You can '
    'continue with a shorter task or view plans. I could not confirm whether '
    'the reminder was saved, so I am checking its status and will tell you '
    'as soon as the server answers. Short answers come first; details follow '
    'when you ask for them, and every reply shows its current state.';

void main() {
  for (final scale in [1.0, 2.0]) {
    testWidgets('wide screens cap bubbles at <= 720px (x$scale)', (
      tester,
    ) async {
      await pumpHost(
        tester,
        ListView(
          children: const [
            MessageBubble.reply(
              reply: ReplyEntry(
                id: 'r',
                message: MessageView(
                  runId: 'r',
                  status: 'completed',
                  outcome: Outcome.accept,
                  response: _prose,
                ),
              ),
            ),
          ],
        ),
        env: Env(textScale: scale),
        size: const Size(1600, 1200),
      );
      await tester.runAsync(GoogleFonts.pendingFonts);
      await tester.pump();
      final textWidth = tester.getSize(find.text(_prose)).width;
      expect(
        textWidth,
        lessThanOrEqualTo(KarmiShape.readableColumnMaxWidth),
      );
    });
  }
}
