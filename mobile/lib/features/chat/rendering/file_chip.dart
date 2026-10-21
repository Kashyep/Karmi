import 'dart:convert';

import 'package:flutter/material.dart';

import '../../../theme/karmi_colors.dart';

/// Card showing file attachment metadata with a lazy monospace content preview.
class FileCard extends StatefulWidget {
  const FileCard({
    super.key,
    required this.name,
    required this.content,
  });

  final String name;
  final String content;

  @override
  State<FileCard> createState() => _FileCardState();
}

class _FileCardState extends State<FileCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).extension<KarmiColors>();
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    final cardBg = colors?.card ?? colorScheme.surfaceContainerHighest;
    final previewBg = colors?.background ?? colorScheme.surface;
    final borderColor = colors?.borderSubtle ?? colorScheme.outlineVariant;
    final fgColor = colors?.foreground ?? colorScheme.onSurface;
    final mutedFg = colors?.mutedForeground ?? colorScheme.onSurfaceVariant;

    final lineCount = const LineSplitter().convert(widget.content).length;
    final charCount = widget.content.length;

    return Semantics(
      container: true,
      label: 'File ${widget.name}',
      child: Container(
        decoration: BoxDecoration(
          color: cardBg,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: borderColor, width: 0.5),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Row(
                children: [
                  Icon(
                    Icons.description_outlined,
                    size: 20,
                    color: fgColor,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          widget.name,
                          style: (textTheme.titleSmall ?? const TextStyle()).copyWith(
                            color: fgColor,
                            fontWeight: FontWeight.w600,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        Text(
                          '$lineCount lines · $charCount chars',
                          style: (textTheme.bodySmall ?? const TextStyle()).copyWith(
                            color: mutedFg,
                          ),
                        ),
                      ],
                    ),
                  ),
                  TextButton.icon(
                    onPressed: () {
                      setState(() {
                        _expanded = !_expanded;
                      });
                    },
                    icon: Icon(
                      _expanded ? Icons.expand_less : Icons.expand_more,
                      size: 18,
                    ),
                    label: Text(_expanded ? 'Hide' : 'Show'),
                  ),
                ],
              ),
            ),
            if (_expanded) ...[
              Divider(
                height: 1,
                thickness: 0.5,
                color: borderColor,
              ),
              Container(
                color: previewBg,
                padding: const EdgeInsets.all(12),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 240),
                  child: Scrollbar(
                    child: SingleChildScrollView(
                      child: SelectableText(
                        widget.content,
                        style: (textTheme.bodySmall ?? const TextStyle()).copyWith(
                          fontFamily: 'monospace',
                          color: fgColor,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
