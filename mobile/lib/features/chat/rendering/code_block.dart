import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../fonts.dart';
import '../../../theme/karmi_colors.dart';
import '../../../theme/karmi_theme.dart';
import 'long_output_fold.dart';

/// Common named HTML entities. Models emit these in code; unknown names are left as written.
const Map<String, String> _namedEntities = {
  'amp': '&',
  'lt': '<',
  'gt': '>',
  'quot': '"',
  'apos': "'",
  'nbsp': '\u00A0',
  'copy': '©',
  'reg': '®',
  'trade': '™',
  'deg': '°',
  'plusmn': '±',
  'times': '×',
  'divide': '÷',
  'minus': '−',
  'micro': 'µ',
  'middot': '·',
  'sect': '§',
  'para': '¶',
  'laquo': '«',
  'raquo': '»',
  'sup1': '¹',
  'sup2': '²',
  'sup3': '³',
  'frac12': '½',
  'frac14': '¼',
  'frac34': '¾',
  'euro': '€',
  'pound': '£',
  'yen': '¥',
  'cent': '¢',
  'ndash': '–',
  'mdash': '—',
  'lsquo': '‘',
  'rsquo': '’',
  'ldquo': '“',
  'rdquo': '”',
  'bull': '•',
  'hellip': '…',
  'larr': '←',
  'uarr': '↑',
  'rarr': '→',
  'darr': '↓',
  'harr': '↔',
  'lArr': '⇐',
  'rArr': '⇒',
  'hArr': '⇔',
  'ne': '≠',
  'le': '≤',
  'ge': '≥',
  'asymp': '≈',
  'infin': '∞',
  'sum': '∑',
  'prod': '∏',
  'radic': '√',
  'alpha': 'α',
  'beta': 'β',
  'gamma': 'γ',
  'delta': 'δ',
  'theta': 'θ',
  'lambda': 'λ',
  'pi': 'π',
  'sigma': 'σ',
  'omega': 'ω',
  'Delta': 'Δ',
  'Sigma': 'Σ',
  'Omega': 'Ω',
};

final RegExp _entityPattern = RegExp(
  r'&(?:#[xX]([0-9a-fA-F]{1,8})|#([0-9]{1,10})|([A-Za-z][A-Za-z0-9]{1,31}));',
);

/// Decodes named (`&quot;`) and numeric (`&#39;`, `&#x27;`) entities in one pass.
/// Unknown or invalid references are left exactly as written.
String unescapeHtmlEntities(String text) {
  if (!text.contains('&')) return text;
  return text.replaceAllMapped(_entityPattern, (match) {
    final name = match[3];
    if (name != null) return _namedEntities[name] ?? match[0]!;
    final hex = match[1];
    final codePoint = hex != null
        ? int.parse(hex, radix: 16)
        : int.parse(match[2]!);
    if (codePoint == 0 ||
        codePoint > 0x10FFFF ||
        (codePoint >= 0xD800 && codePoint <= 0xDFFF)) {
      return match[0]!;
    }
    return String.fromCharCode(codePoint);
  });
}

/// Decodes text taken from a fenced block. The markdown parser escapes code once
/// (`"` becomes `&quot;`), and the model may have escaped it again (`&quot;` in
/// the source becomes `&amp;quot;`), so two decode levels are applied.
String decodeCodeText(String markdownEscaped) =>
    unescapeHtmlEntities(unescapeHtmlEntities(markdownEscaped));

/// Renders a code block with language indicator, copy-to-clipboard,
/// wrap toggle, and folding for outputs over 40 lines.
class CodeBlock extends StatefulWidget {
  const CodeBlock({super.key, required this.code, this.language});

  final String code;
  final String? language;

  @override
  State<CodeBlock> createState() => _CodeBlockState();
}

class _CodeBlockState extends State<CodeBlock> {
  bool _isWrapped = false;
  bool _copied = false;
  Timer? _copyTimer;

  @override
  void dispose() {
    _copyTimer?.cancel();
    super.dispose();
  }

  Future<void> _handleCopy() async {
    await Clipboard.setData(ClipboardData(text: widget.code));
    _copyTimer?.cancel();
    if (mounted) {
      setState(() {
        _copied = true;
      });
      _copyTimer = Timer(const Duration(seconds: 2), () {
        if (mounted) {
          setState(() {
            _copied = false;
          });
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).extension<KarmiColors>();
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    final headerBg =
        colors?.codeHeaderSurface ?? colorScheme.surfaceContainerHighest;
    final codeAreaBg = colors?.codeSurface ?? colorScheme.surfaceContainer;
    final borderColor = colors?.borderSubtle ?? colorScheme.outlineVariant;
    final hairline = colors?.hairline ?? borderColor;
    final fgColor = colors?.foreground ?? colorScheme.onSurface;
    final mutedFg = colors?.mutedForeground ?? colorScheme.onSurfaceVariant;
    final successColor = colors?.success ?? const Color(0xFF2DD4BF);

    final langLabel =
        (widget.language != null && widget.language!.trim().isNotEmpty)
        ? widget.language!.trim()
        : 'text';

    final langStyle = (textTheme.labelSmall ?? KarmiTypography.toolbarCaption())
        .copyWith(color: mutedFg, fontWeight: FontWeight.w600);
    final lineCount = const LineSplitter().convert(widget.code).length;
    final isLong = lineCount > 40;

    final monoStyle = (textTheme.bodySmall ?? const TextStyle()).copyWith(
      fontFamily: 'JetBrains Mono',
      fontFamilyFallback: [...kGlyphFallbackFamilies, 'monospace'],
      color: fgColor,
    );

    Widget codeDisplay = SelectableText(widget.code, style: monoStyle);

    if (!_isWrapped) {
      codeDisplay = SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: codeDisplay,
      );
    }

    Widget content = Container(
      color: codeAreaBg,
      padding: const EdgeInsets.all(12),
      width: double.infinity,
      child: codeDisplay,
    );

    if (isLong) {
      content = LongOutputFold(
        collapsible: true,
        maxHeight: 480,
        child: content,
      );
    }

    return Container(
      decoration: BoxDecoration(
        color: codeAreaBg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: borderColor, width: 0.5),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            color: headerBg,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
            child: Row(
              children: [
                Text(langLabel, style: langStyle),
                const Spacer(),
                Tooltip(
                  message: _isWrapped ? 'Disable line wrap' : 'Wrap long lines',
                  child: Semantics(
                    label: _isWrapped ? 'Disable wrap' : 'Wrap code',
                    button: true,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(
                        minWidth: 44,
                        minHeight: 44,
                      ),
                      child: TextButton.icon(
                        style: TextButton.styleFrom(
                          foregroundColor: mutedFg,
                          minimumSize: const Size(44, 44),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 4,
                          ),
                          textStyle: textTheme.labelSmall,
                          tapTargetSize: MaterialTapTargetSize.padded,
                        ),
                        onPressed: () {
                          setState(() {
                            _isWrapped = !_isWrapped;
                          });
                        },
                        icon: Icon(
                          _isWrapped
                              ? Icons.wrap_text
                              : Icons.wrap_text_outlined,
                          size: 16,
                        ),
                        label: Text(_isWrapped ? 'No wrap' : 'Wrap'),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 4),
                Tooltip(
                  message: _copied ? 'Copied' : 'Copy code',
                  child: Semantics(
                    label: _copied ? 'Copied' : 'Copy code',
                    button: true,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(
                        minWidth: 44,
                        minHeight: 44,
                      ),
                      child: TextButton.icon(
                        style: TextButton.styleFrom(
                          foregroundColor: _copied ? successColor : mutedFg,
                          minimumSize: const Size(44, 44),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 4,
                          ),
                          textStyle: textTheme.labelSmall,
                          tapTargetSize: MaterialTapTargetSize.padded,
                        ),
                        onPressed: _handleCopy,
                        icon: Icon(
                          _copied ? Icons.check : Icons.copy,
                          size: 16,
                        ),
                        label: Text(_copied ? 'Copied' : 'Copy'),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          Divider(height: 1, thickness: 0.5, color: hairline),
          content,
        ],
      ),
    );
  }
}
