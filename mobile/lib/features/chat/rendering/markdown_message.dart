import 'dart:convert';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:markdown/markdown.dart' as md;

import '../../../theme/karmi_colors.dart';
import 'citation_chip.dart';
import 'code_block.dart';
import 'file_chip.dart';
import 'long_output_fold.dart';
import 'safe_link.dart';
import 'table_view.dart';

/// Inline syntax that detects citation patterns like `[^1]`, `[1]`, or `[citation:1]`.
class CitationSyntax extends md.InlineSyntax {
  CitationSyntax()
    : super(r'\[(?:\^|citation:)?(\d+)\](?![\[\(])', startCharacter: 91);

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    final rawIndex = match[1]!;
    final index = int.tryParse(rawIndex) ?? 0;
    final element = md.Element('citation', [md.Text(rawIndex)])
      ..attributes['index'] = '$index';
    parser.addNode(element);
    return true;
  }
}

/// Rich rendering widget for markdown assistant messages.
///
/// Converts markdown AST into Flutter widgets, handling headings, lists,
/// tables, safe links, code blocks, file attachments, and citations.
class MarkdownMessage extends StatefulWidget {
  const MarkdownMessage({
    super.key,
    required this.text,
    required this.streaming,
    this.allowCollapse = true,
  });

  final String text;
  final bool streaming;
  final bool allowCollapse;

  @override
  State<MarkdownMessage> createState() => _MarkdownMessageState();
}

class _MarkdownMessageState extends State<MarkdownMessage> {
  String? _cachedText;
  List<md.Node>? _cachedNodes;
  final List<TapGestureRecognizer> _recognizers = [];

  List<md.Node> _getNodes() {
    if (_cachedText == widget.text && _cachedNodes != null) {
      return _cachedNodes!;
    }
    final document = md.Document(
      extensionSet: md.ExtensionSet.gitHubWeb,
      encodeHtml: true,
      inlineSyntaxes: [CitationSyntax()],
    );
    final lines = const LineSplitter().convert(widget.text);
    _cachedText = widget.text;
    _cachedNodes = document.parseLines(lines);
    return _cachedNodes!;
  }

  void _disposeRecognizers() {
    for (final r in _recognizers) {
      r.dispose();
    }
    _recognizers.clear();
  }

  @override
  void dispose() {
    _disposeRecognizers();
    super.dispose();
  }

  String _decodeText(String text) {
    return text
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&quot;', '"')
        .replaceAll('&apos;', "'")
        .replaceAll('&#39;', "'")
        .replaceAll('&amp;', '&');
  }

  InlineSpan _buildInlineSpan(
    md.Node node,
    BuildContext context,
    TextStyle baseStyle,
  ) {
    final colors = Theme.of(context).extension<KarmiColors>();
    final colorScheme = Theme.of(context).colorScheme;

    if (node is md.Text) {
      return TextSpan(text: _decodeText(node.text), style: baseStyle);
    }

    if (node is md.Element) {
      switch (node.tag) {
        case 'strong':
          return TextSpan(
            children: node.children
                ?.map(
                  (c) => _buildInlineSpan(
                    c,
                    context,
                    baseStyle.copyWith(fontWeight: FontWeight.bold),
                  ),
                )
                .toList(),
          );

        case 'em':
          return TextSpan(
            children: node.children
                ?.map(
                  (c) => _buildInlineSpan(
                    c,
                    context,
                    baseStyle.copyWith(fontStyle: FontStyle.italic),
                  ),
                )
                .toList(),
          );

        case 'del':
          return TextSpan(
            children: node.children
                ?.map(
                  (c) => _buildInlineSpan(
                    c,
                    context,
                    baseStyle.copyWith(decoration: TextDecoration.lineThrough),
                  ),
                )
                .toList(),
          );

        case 'code':
          final codeBg = colors?.muted ?? colorScheme.surfaceContainerHighest;
          final monoStyle = baseStyle.copyWith(
            fontFamily: 'monospace',
            backgroundColor: codeBg,
          );
          return TextSpan(
            children: node.children
                ?.map((c) => _buildInlineSpan(c, context, monoStyle))
                .toList(),
          );

        case 'a':
          final href = node.attributes['href'] ?? '';
          final uri = Uri.tryParse(href.trim());
          final isSafe = uri != null && isSafeLinkUri(uri);
          final linkColor = colors?.primaryText ?? colorScheme.primary;

          if (isSafe) {
            final recognizer = TapGestureRecognizer()
              ..onTap = () {
                openSafeLink(context, href);
              };
            _recognizers.add(recognizer);

            final linkStyle = baseStyle.copyWith(
              color: linkColor,
              decoration: TextDecoration.underline,
            );
            return TextSpan(
              recognizer: recognizer,
              children: node.children
                  ?.map((c) => _buildInlineSpan(c, context, linkStyle))
                  .toList(),
            );
          } else {
            return TextSpan(
              children: node.children
                  ?.map((c) => _buildInlineSpan(c, context, baseStyle))
                  .toList(),
            );
          }

        case 'img':
          final alt = node.attributes['alt'] ?? '';
          return TextSpan(text: alt.isNotEmpty ? alt : '', style: baseStyle);

        case 'citation':
          final index =
              int.tryParse(node.attributes['index'] ?? '') ??
              int.tryParse(node.textContent) ??
              0;
          return WidgetSpan(
            alignment: PlaceholderAlignment.middle,
            child: CitationChip(index: index),
          );

        default:
          return TextSpan(
            children: node.children
                ?.map((c) => _buildInlineSpan(c, context, baseStyle))
                .toList(),
          );
      }
    }

    return const TextSpan(text: '');
  }

  Widget _buildBlockNode(md.Node node, BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final colors = Theme.of(context).extension<KarmiColors>();
    final colorScheme = Theme.of(context).colorScheme;
    final bodyStyle = textTheme.bodyMedium ?? const TextStyle();

    if (node is md.Text) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text.rich(
          TextSpan(text: _decodeText(node.text), style: bodyStyle),
        ),
      );
    }

    if (node is md.Element) {
      switch (node.tag) {
        case 'h1':
          final style = (textTheme.headlineMedium ?? const TextStyle())
              .copyWith(fontWeight: FontWeight.bold);
          return Padding(
            padding: const EdgeInsets.only(top: 16, bottom: 8),
            child: Text.rich(
              TextSpan(
                children: node.children
                    ?.map((c) => _buildInlineSpan(c, context, style))
                    .toList(),
              ),
            ),
          );

        case 'h2':
          final style = (textTheme.headlineSmall ?? const TextStyle()).copyWith(
            fontWeight: FontWeight.bold,
          );
          return Padding(
            padding: const EdgeInsets.only(top: 14, bottom: 6),
            child: Text.rich(
              TextSpan(
                children: node.children
                    ?.map((c) => _buildInlineSpan(c, context, style))
                    .toList(),
              ),
            ),
          );

        case 'h3':
          final style = (textTheme.titleLarge ?? const TextStyle()).copyWith(
            fontWeight: FontWeight.bold,
          );
          return Padding(
            padding: const EdgeInsets.only(top: 12, bottom: 6),
            child: Text.rich(
              TextSpan(
                children: node.children
                    ?.map((c) => _buildInlineSpan(c, context, style))
                    .toList(),
              ),
            ),
          );

        case 'h4':
          final style = (textTheme.titleMedium ?? const TextStyle()).copyWith(
            fontWeight: FontWeight.bold,
          );
          return Padding(
            padding: const EdgeInsets.only(top: 10, bottom: 4),
            child: Text.rich(
              TextSpan(
                children: node.children
                    ?.map((c) => _buildInlineSpan(c, context, style))
                    .toList(),
              ),
            ),
          );

        case 'h5':
          final style = (textTheme.titleSmall ?? const TextStyle()).copyWith(
            fontWeight: FontWeight.bold,
          );
          return Padding(
            padding: const EdgeInsets.only(top: 8, bottom: 4),
            child: Text.rich(
              TextSpan(
                children: node.children
                    ?.map((c) => _buildInlineSpan(c, context, style))
                    .toList(),
              ),
            ),
          );

        case 'h6':
          final style = (textTheme.bodyLarge ?? const TextStyle()).copyWith(
            fontWeight: FontWeight.bold,
          );
          return Padding(
            padding: const EdgeInsets.only(top: 6, bottom: 2),
            child: Text.rich(
              TextSpan(
                children: node.children
                    ?.map((c) => _buildInlineSpan(c, context, style))
                    .toList(),
              ),
            ),
          );

        case 'p':
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text.rich(
              TextSpan(
                children: node.children
                    ?.map((c) => _buildInlineSpan(c, context, bodyStyle))
                    .toList(),
              ),
            ),
          );

        case 'blockquote':
          return _buildBlockquote(node, context);

        case 'hr':
          return Divider(
            color: colors?.borderSubtle ?? colorScheme.outlineVariant,
            height: 24,
            thickness: 1,
          );

        case 'pre':
          return _buildPreBlock(node, context);

        case 'table':
          return _buildTable(node, context);

        case 'ul':
          return _buildList(node, context, isOrdered: false);

        case 'ol':
          return _buildList(node, context, isOrdered: true);

        default:
          final childrenWidgets = <Widget>[];
          if (node.children != null) {
            for (final child in node.children!) {
              childrenWidgets.add(_buildBlockNode(child, context));
            }
          }
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: childrenWidgets,
          );
      }
    }

    return const SizedBox.shrink();
  }

  Widget _buildTable(md.Element tableElement, BuildContext context) {
    final trs = _extractTableRows(tableElement);
    if (trs.isEmpty) {
      return const SizedBox.shrink();
    }

    final alignments = <TextAlign>[];
    final headerRow = trs.first;
    if (headerRow.children != null) {
      for (final cell in headerRow.children!) {
        if (cell is md.Element) {
          final alignAttr = cell.attributes['align']?.toLowerCase();
          if (alignAttr == 'center') {
            alignments.add(TextAlign.center);
          } else if (alignAttr == 'right') {
            alignments.add(TextAlign.right);
          } else {
            alignments.add(TextAlign.left);
          }
        }
      }
    }

    final textTheme = Theme.of(context).textTheme;
    final bodyStyle = textTheme.bodyMedium ?? const TextStyle();

    final rows = <List<Widget>>[];
    for (final tr in trs) {
      final rowWidgets = <Widget>[];
      if (tr.children != null) {
        for (final cell in tr.children!) {
          if (cell is md.Element) {
            final spans =
                cell.children
                    ?.map((c) => _buildInlineSpan(c, context, bodyStyle))
                    .toList() ??
                [];
            rowWidgets.add(Text.rich(TextSpan(children: spans)));
          }
        }
      }
      if (rowWidgets.isNotEmpty) {
        rows.add(rowWidgets);
      }
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: TableView(rows: rows, alignments: alignments),
    );
  }

  List<md.Element> _extractTableRows(md.Element tableElement) {
    final trs = <md.Element>[];
    if (tableElement.children == null) return trs;
    for (final child in tableElement.children!) {
      if (child is md.Element) {
        if (child.tag == 'tr') {
          trs.add(child);
        } else if (child.tag == 'thead' || child.tag == 'tbody') {
          if (child.children != null) {
            for (final subChild in child.children!) {
              if (subChild is md.Element && subChild.tag == 'tr') {
                trs.add(subChild);
              }
            }
          }
        }
      }
    }
    return trs;
  }

  Widget _buildPreBlock(md.Element preElement, BuildContext context) {
    md.Element? codeElement;
    if (preElement.children != null) {
      for (final child in preElement.children!) {
        if (child is md.Element && child.tag == 'code') {
          codeElement = child;
          break;
        }
      }
    }

    var codeText = codeElement != null
        ? codeElement.textContent
        : preElement.textContent;
    if (codeText.endsWith('\n')) {
      codeText = codeText.substring(0, codeText.length - 1);
    }

    String? language;
    final classAttr = codeElement?.attributes['class'] ?? '';
    if (classAttr.startsWith('language-')) {
      language = classAttr.substring('language-'.length);
    }

    if (language != null && language.startsWith('file:')) {
      final fileName = language.substring('file:'.length).trim();
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: FileCard(name: fileName, content: codeText),
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: CodeBlock(code: codeText, language: language),
    );
  }

  Widget _buildBlockquote(md.Element blockquoteElement, BuildContext context) {
    final colors = Theme.of(context).extension<KarmiColors>();
    final colorScheme = Theme.of(context).colorScheme;
    final borderColor = colors?.border ?? colorScheme.outlineVariant;
    final bgTint =
        colors?.muted ??
        colorScheme.surfaceContainerHighest.withValues(alpha: 0.3);

    final innerWidgets = <Widget>[];
    if (blockquoteElement.children != null) {
      for (final child in blockquoteElement.children!) {
        innerWidgets.add(_buildBlockNode(child, context));
      }
    }

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 6),
      padding: const EdgeInsets.only(left: 12, top: 4, bottom: 4, right: 8),
      decoration: BoxDecoration(
        color: bgTint,
        border: Border(left: BorderSide(color: borderColor, width: 3)),
        borderRadius: const BorderRadius.only(
          topRight: Radius.circular(4),
          bottomRight: Radius.circular(4),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: innerWidgets.isNotEmpty
            ? innerWidgets
            : [const SizedBox.shrink()],
      ),
    );
  }

  Widget _buildList(
    md.Element listElement,
    BuildContext context, {
    required bool isOrdered,
    int depth = 0,
  }) {
    final items = <Widget>[];
    var index = isOrdered
        ? int.tryParse(listElement.attributes['start'] ?? '1') ?? 1
        : 1;

    final textTheme = Theme.of(context).textTheme;
    final colors = Theme.of(context).extension<KarmiColors>();
    final colorScheme = Theme.of(context).colorScheme;
    final bodyStyle = textTheme.bodyMedium ?? const TextStyle();
    final fgColor = colors?.foreground ?? colorScheme.onSurface;

    if (listElement.children != null) {
      for (final child in listElement.children!) {
        if (child is md.Element && child.tag == 'li') {
          final liChildren = <Widget>[];
          final inlineSpans = <InlineSpan>[];

          if (child.children != null) {
            for (final liChild in child.children!) {
              if (liChild is md.Element &&
                  (liChild.tag == 'ul' || liChild.tag == 'ol')) {
                if (inlineSpans.isNotEmpty) {
                  liChildren.add(
                    Text.rich(TextSpan(children: List.of(inlineSpans))),
                  );
                  inlineSpans.clear();
                }
                liChildren.add(
                  _buildList(
                    liChild,
                    context,
                    isOrdered: liChild.tag == 'ol',
                    depth: depth + 1,
                  ),
                );
              } else if (liChild is md.Element && liChild.tag == 'p') {
                if (liChild.children != null) {
                  for (final pChild in liChild.children!) {
                    inlineSpans.add(
                      _buildInlineSpan(pChild, context, bodyStyle),
                    );
                  }
                }
              } else {
                inlineSpans.add(_buildInlineSpan(liChild, context, bodyStyle));
              }
            }
          }

          if (inlineSpans.isNotEmpty) {
            liChildren.add(Text.rich(TextSpan(children: List.of(inlineSpans))));
            inlineSpans.clear();
          }

          final bulletText = isOrdered ? '$index. ' : '• ';
          index++;

          items.add(
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: isOrdered ? 24 : 16,
                    child: Text(
                      bulletText,
                      style: bodyStyle.copyWith(
                        color: fgColor,
                        fontWeight: isOrdered
                            ? FontWeight.w500
                            : FontWeight.bold,
                      ),
                    ),
                  ),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: liChildren.isNotEmpty
                          ? liChildren
                          : [const SizedBox.shrink()],
                    ),
                  ),
                ],
              ),
            ),
          );
        }
      }
    }

    return Padding(
      padding: EdgeInsets.only(left: depth > 0 ? 12.0 : 0.0, bottom: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: items,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    _disposeRecognizers();

    final nodes = _getNodes();
    final blockWidgets = <Widget>[];

    for (final node in nodes) {
      blockWidgets.add(_buildBlockNode(node, context));
    }

    Widget content = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: blockWidgets,
    );

    final lines = const LineSplitter().convert(widget.text);
    final isLong = widget.text.length > 4000 || lines.length > 60;
    final shouldCollapse = widget.allowCollapse && !widget.streaming && isLong;

    if (shouldCollapse) {
      content = LongOutputFold(
        collapsible: true,
        maxHeight: 480,
        child: content,
      );
    }

    return Semantics(
      container: true,
      label: 'Assistant message',
      child: SelectionArea(child: content),
    );
  }
}
