import 'package:flutter/material.dart';

import '../../../theme/karmi_colors.dart';

const int longPasteThreshold = 2500;

class PasteChip extends StatefulWidget {
  const PasteChip({super.key, required this.text, required this.onRemove});

  final String text;
  final VoidCallback onRemove;

  @override
  State<PasteChip> createState() => _PasteChipState();
}

class _PasteChipState extends State<PasteChip> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final charCount = widget.text.length;
    final label = 'Pasted text · $charCount chars';

    return Semantics(
      container: true,
      label: 'Pasted text, $charCount characters',
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        decoration: BoxDecoration(
          color: colors.muted,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: colors.borderSubtle),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const SizedBox(width: 8),
                Icon(
                  Icons.content_paste,
                  size: 16,
                  color: colors.mutedForeground,
                ),
                const SizedBox(width: 6),
                Expanded(
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
                IconButton(
                  icon: Icon(
                    _expanded ? Icons.expand_less : Icons.expand_more,
                    size: 18,
                    color: colors.foreground,
                  ),
                  tooltip: _expanded
                      ? 'Collapse pasted text'
                      : 'Expand pasted text',
                  onPressed: () => setState(() => _expanded = !_expanded),
                ),
                IconButton(
                  icon: Icon(Icons.close, size: 18, color: colors.foreground),
                  tooltip: 'Remove pasted text',
                  onPressed: widget.onRemove,
                ),
              ],
            ),
            if (_expanded)
              Container(
                constraints: const BoxConstraints(maxHeight: 120),
                padding: const EdgeInsets.all(8),
                margin: const EdgeInsets.fromLTRB(8, 0, 8, 8),
                decoration: BoxDecoration(
                  color: colors.card,
                  borderRadius: BorderRadius.circular(4),
                ),
                child: SingleChildScrollView(
                  child: Text(
                    widget.text,
                    style: TextStyle(
                      fontSize: 12,
                      color: colors.cardForeground,
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
