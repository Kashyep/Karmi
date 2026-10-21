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
}) {
  return showDialog<void>(
    context: context,
    builder: (_) =>
        _RenameDialog(conversation: conversation, controller: controller),
  );
}

/// Owns the title [TextEditingController] for the rename dialog.
///
/// The controller is created and disposed by this [State], so it lives exactly
/// as long as the dialog subtree. Disposing it after `showDialog` returns is
/// too early: the route is still animating out and its [TextField] still uses
/// the controller.
class _RenameDialog extends StatefulWidget {
  const _RenameDialog({required this.conversation, required this.controller});

  final ConversationView conversation;
  final ConversationListController controller;

  @override
  State<_RenameDialog> createState() => _RenameDialogState();
}

class _RenameDialogState extends State<_RenameDialog> {
  late final TextEditingController _textController = TextEditingController(
    text: widget.conversation.title ?? '',
  );

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final trimmed = _textController.text.trim();
    final isValid = trimmed.isNotEmpty && trimmed.length <= 200;

    return AlertDialog(
      title: const Text('Rename conversation'),
      content: TextField(
        controller: _textController,
        autofocus: true,
        maxLength: 200,
        decoration: const InputDecoration(hintText: 'Conversation title'),
        onChanged: (_) => setState(() {}),
        onSubmitted: isValid
            ? (value) {
                final title = value.trim();
                if (title.isNotEmpty && title.length <= 200) {
                  Navigator.of(context).pop();
                  widget.controller.rename(widget.conversation.id, title);
                }
              }
            : null,
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: isValid
              ? () {
                  Navigator.of(context).pop();
                  widget.controller.rename(widget.conversation.id, trimmed);
                }
              : null,
          child: const Text('Save'),
        ),
      ],
    );
  }
}
