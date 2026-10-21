import 'package:flutter/material.dart';

import '../../api/chat/chat_models.dart';
import 'conversation_list_controller.dart';

/// Displays a modal bottom sheet with management actions for [conversation].
///
/// Available actions:
/// - **Rename**: opens an [AlertDialog] to edit the title (1..200 characters).
/// - **Pin / Unpin**: toggles the conversation's pinned state.
/// - **Archive / Unarchive**: toggles the conversation's archived status.
/// - **Delete**: deletes the conversation with an undo grace period.
Future<void> showConversationActions(
  BuildContext context, {
  required ConversationView conversation,
  required ConversationListController controller,
}) async {
  final isArchived = conversation.archivedAt != null;
  final isPinned = conversation.pinned;

  await showModalBottomSheet<void>(
    context: context,
    useSafeArea: true,
    builder: (sheetContext) {
      final theme = Theme.of(sheetContext);
      return SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.edit_outlined),
              title: const Text('Rename'),
              onTap: () {
                Navigator.of(sheetContext).pop();
                showRenameDialog(
                  context,
                  conversation: conversation,
                  controller: controller,
                );
              },
            ),
            ListTile(
              leading: Icon(
                isPinned ? Icons.push_pin_outlined : Icons.push_pin,
              ),
              title: Text(isPinned ? 'Unpin' : 'Pin'),
              onTap: () {
                Navigator.of(sheetContext).pop();
                controller.togglePin(conversation.id);
              },
            ),
            ListTile(
              leading: Icon(
                isArchived ? Icons.unarchive_outlined : Icons.archive_outlined,
              ),
              title: Text(isArchived ? 'Unarchive' : 'Archive'),
              onTap: () {
                Navigator.of(sheetContext).pop();
                controller.setArchived(conversation.id, !isArchived);
              },
            ),
            ListTile(
              leading: Icon(
                Icons.delete_outline,
                color: theme.colorScheme.error,
              ),
              title: Text(
                'Delete',
                style: TextStyle(color: theme.colorScheme.error),
              ),
              onTap: () {
                Navigator.of(sheetContext).pop();
                controller.delete(conversation.id);
              },
            ),
          ],
        ),
      );
    },
  );
}

/// Displays an [AlertDialog] allowing the user to rename [conversation].
Future<void> showRenameDialog(
  BuildContext context, {
  required ConversationView conversation,
  required ConversationListController controller,
}) async {
  final textController = TextEditingController(text: conversation.title ?? '');

  try {
    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (context, setState) {
            final trimmed = textController.text.trim();
            final isValid = trimmed.isNotEmpty && trimmed.length <= 200;

            return AlertDialog(
              title: const Text('Rename conversation'),
              content: TextField(
                controller: textController,
                autofocus: true,
                maxLength: 200,
                decoration: const InputDecoration(
                  hintText: 'Conversation title',
                ),
                onChanged: (_) => setState(() {}),
                onSubmitted: isValid
                    ? (value) {
                        final title = value.trim();
                        if (title.isNotEmpty && title.length <= 200) {
                          Navigator.of(dialogContext).pop();
                          controller.rename(conversation.id, title);
                        }
                      }
                    : null,
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(dialogContext).pop(),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: isValid
                      ? () {
                          Navigator.of(dialogContext).pop();
                          controller.rename(conversation.id, trimmed);
                        }
                      : null,
                  child: const Text('Save'),
                ),
              ],
            );
          },
        );
      },
    );
  } finally {
    textController.dispose();
  }
}
