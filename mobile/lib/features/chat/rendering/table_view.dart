import 'package:flutter/material.dart';

import '../../../theme/karmi_colors.dart';

/// Renders a markdown table with horizontal scroll, cell padding, and borders.
class TableView extends StatelessWidget {
  const TableView({super.key, required this.rows, required this.alignments});

  /// The rows of table cells. The first row is the table header.
  final List<List<Widget>> rows;

  /// Text alignments per column.
  final List<TextAlign> alignments;

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
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return const SizedBox.shrink();
    }

    final colors = Theme.of(context).extension<KarmiColors>();
    final colorScheme = Theme.of(context).colorScheme;
    final borderColor = colors?.borderSubtle ?? colorScheme.outlineVariant;
    final headerBg = colors?.muted ?? colorScheme.surfaceContainerHighest;

    final rowCount = rows.length;
    final colCount = rows.first.length;

    final tableRows = <TableRow>[];
    for (var r = 0; r < rowCount; r++) {
      final isHeader = r == 0;
      final row = rows[r];
      final cellWidgets = <Widget>[];

      for (var c = 0; c < row.length; c++) {
        final align = c < alignments.length ? alignments[c] : TextAlign.left;
        final cell = row[c];

        cellWidgets.add(
          Container(
            alignment: _toAlignment(align),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: isHeader
                ? DefaultTextStyle.merge(
                    style: const TextStyle(fontWeight: FontWeight.bold),
                    textAlign: align,
                    child: cell,
                  )
                : DefaultTextStyle.merge(textAlign: align, child: cell),
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
      child: Scrollbar(
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Table(
            defaultColumnWidth: const IntrinsicColumnWidth(),
            border: TableBorder.all(color: borderColor, width: 0.5),
            children: tableRows,
          ),
        ),
      ),
    );
  }
}
