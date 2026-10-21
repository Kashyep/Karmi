import 'package:flutter/material.dart';

import '../../../theme/karmi_colors.dart';

const int longPasteThreshold = 2500;

class PasteChip extends StatelessWidget {
  const PasteChip({super.key, required this.text, required this.onRemove});

  final String text;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final charCount = text.length;
    final lines = text.split('\n').length;
    final label = lines > 1
        ? 'Pasted text · $lines lines'
        : 'Pasted text · $charCount chars';

    return Semantics(
      container: true,
      label: 'Pasted text, $charCount characters',
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
              Icons.content_paste,
              size: 14,
              color: colors.mutedForeground,
            ),
            const SizedBox(width: 4),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 200),
              child: Text(
                label,
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
              label: 'Remove pasted text',
              child: IconButton(
                icon: const Icon(Icons.close, size: 14),
                tooltip: 'Remove pasted text',
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
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
