import 'package:flutter/material.dart';

import '../../../theme/karmi_colors.dart';
import 'text_attachment.dart';

class AttachmentChip extends StatelessWidget {
  const AttachmentChip({
    super.key,
    required this.attachment,
    required this.onRemove,
  });

  final TextAttachment attachment;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final name = attachment.name;

    return Semantics(
      container: true,
      label: 'Attachment: $name',
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 2, horizontal: 2),
        padding: const EdgeInsets.only(left: 8, right: 2, top: 2, bottom: 2),
        decoration: BoxDecoration(
          color: colors.muted,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: colors.borderSubtle),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.description_outlined,
              size: 14,
              color: colors.mutedForeground,
            ),
            const SizedBox(width: 4),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 160),
              child: Text(
                name,
                style: TextStyle(
                  fontSize: 12,
                  color: colors.foreground,
                  fontWeight: FontWeight.w500,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            Semantics(
              button: true,
              label: 'Remove $name',
              child: IconButton(
                icon: const Icon(Icons.close, size: 14),
                tooltip: 'Remove $name',
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
                splashRadius: 14,
                onPressed: onRemove,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
