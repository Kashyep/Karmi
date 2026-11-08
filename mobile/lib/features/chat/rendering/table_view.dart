import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../theme/karmi_colors.dart';
import '../../../theme/karmi_theme.dart';

/// Renders a markdown table with horizontal scroll, cell padding, and borders.
class TableView extends StatefulWidget {
  const TableView({super.key, required this.rows, required this.alignments});

  /// The rows of table cells. The first row is the table header.
  final List<List<Widget>> rows;

  /// Text alignments per column.
  final List<TextAlign> alignments;

  static Alignment toAlignment(TextAlign align) => _toAlignment(align);

  static Alignment _toAlignment(TextAlign align) {
    switch (align) {
      case TextAlign.center:
        return Alignment.center;
      case TextAlign.right:
      case TextAlign.end:
        return Alignment.centerRight;
      case TextAlign.left:
      case TextAlign.start:
      case TextAlign.justify:
        return Alignment.centerLeft;
    }
  }

  @override
  State<TableView> createState() => _TableViewState();
}

class _TableViewState extends State<TableView> {
  final ScrollController _scrollController = ScrollController();
  final FocusNode _focusNode = FocusNode(debugLabel: 'TableView');

  @override
  void dispose() {
    _focusNode.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollBy(double delta) {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    if (!position.hasContentDimensions) return;
    final target = (position.pixels + delta).clamp(
      position.minScrollExtent,
      position.maxScrollExtent,
    );
    _scrollController.animateTo(
      target,
      duration: const Duration(milliseconds: 100),
      curve: Curves.easeOut,
    );
  }

  KeyEventResult _handleKeyEvent(FocusNode node, KeyEvent event) {
    if (event is KeyDownEvent || event is KeyRepeatEvent) {
      if (event.logicalKey == LogicalKeyboardKey.arrowLeft) {
        _scrollBy(-48.0);
        return KeyEventResult.handled;
      } else if (event.logicalKey == LogicalKeyboardKey.arrowRight) {
        _scrollBy(48.0);
        return KeyEventResult.handled;
      }
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    if (widget.rows.isEmpty) {
      return const SizedBox.shrink();
    }

    final colors = Theme.of(context).extension<KarmiColors>();
    final colorScheme = Theme.of(context).colorScheme;
    final hairline = colors?.hairline ?? colorScheme.outlineVariant;
    final headerBg =
        colors?.codeHeaderSurface ?? colorScheme.surfaceContainerHighest;
    final fgColor = colors?.foreground ?? colorScheme.onSurface;

    final rowCount = widget.rows.length;
    final colCount = widget.rows.first.length;

    final tableRows = <TableRow>[];
    for (var r = 0; r < rowCount; r++) {
      final isHeader = r == 0;
      final row = widget.rows[r];
      final cellWidgets = <Widget>[];

      for (var c = 0; c < row.length; c++) {
        final align = c < widget.alignments.length
            ? widget.alignments[c]
            : TextAlign.left;
        final cell = row[c];

        cellWidgets.add(
          Container(
            alignment: TableView._toAlignment(align),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: isHeader
                ? DefaultTextStyle.merge(
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: fgColor,
                    ),
                    textAlign: align,
                    child: cell,
                  )
                : DefaultTextStyle.merge(
                    style: TextStyle(color: fgColor),
                    textAlign: align,
                    child: cell,
                  ),
          ),
        );
      }

      tableRows.add(
        TableRow(
          decoration: isHeader ? BoxDecoration(color: headerBg) : null,
          children: cellWidgets,
        ),
      );
    }

    return Semantics(
      container: true,
      label: 'Table with $rowCount rows and $colCount columns',
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          maxWidth: KarmiShape.readableColumnMaxWidth,
        ),
        child: Focus(
          focusNode: _focusNode,
          onFocusChange: (_) => setState(() {}),
          onKeyEvent: _handleKeyEvent,
          child: Container(
            decoration: _focusNode.hasFocus
                ? BoxDecoration(
                    borderRadius: BorderRadius.circular(
                      KarmiShape.controlRadius,
                    ),
                    border: Border.all(
                      color: colors?.ring ?? colorScheme.primary,
                      width: 2,
                    ),
                  )
                : null,
            child: Scrollbar(
              controller: _scrollController,
              thumbVisibility: true,
              child: SingleChildScrollView(
                controller: _scrollController,
                scrollDirection: Axis.horizontal,
                child: Table(
                  defaultColumnWidth: const IntrinsicColumnWidth(),
                  border: TableBorder.all(color: hairline, width: 0.5),
                  children: tableRows,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
