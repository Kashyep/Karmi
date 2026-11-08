import 'package:flutter/material.dart';

/// Short, friendly nickname for the model that answered a reply.
///
/// The raw model id is never shown. Vendor prefixes, `:free` suffixes and
/// version tokens are dropped, so `nvidia/nemotron-3.5-lightning:free` becomes
/// `Nemotron` and `openai/gpt-oss-20b` becomes `GPT`.
String providerNickname({String? model, String? provider}) {
  final raw = (model ?? provider ?? '').trim();
  if (raw.isEmpty) return 'Assistant';

  var name = raw.split(':').first; // drop ':free' style suffixes
  name = name.split('/').last; // drop the vendor prefix
  name = name.replaceAll('_', '-');

  final parts = name
      .split('-')
      .where((part) => part.isNotEmpty)
      .toList(growable: false);
  if (parts.isEmpty) return 'Assistant';

  // Skip pure version / size tokens such as "3.5" or "20b".
  final versionToken = RegExp(r'^[0-9][0-9.]*[a-z]?$');
  final word = parts.firstWhere(
    (part) => !versionToken.hasMatch(part),
    orElse: () => parts.first,
  );
  final letters = word.replaceAll(RegExp(r'[^A-Za-z]'), '');
  if (letters.isEmpty) return 'Assistant';

  final lower = letters.toLowerCase();
  // Keep short model acronyms (gpt, llm) in caps; title-case the rest.
  if (lower.length <= 4) return lower.toUpperCase();
  return '${lower[0].toUpperCase()}${lower.substring(1)}';
}

/// Auto-generated avatar for a provider nickname.
///
/// There is no image asset: the colour is derived from the nickname so a given
/// provider always looks the same, and the initials make it recognisable at a
/// glance. Purely decorative next to the visible name.
class ProviderAvatar extends StatelessWidget {
  const ProviderAvatar({
    super.key,
    required this.name,
    this.size = 24,
    this.semanticLabel,
  });

  /// Nickname from [providerNickname]; also the colour seed.
  final String name;

  /// Edge length of the square avatar.
  final double size;

  /// Screen-reader label; null hides the avatar from the a11y tree.
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final hue = _hueFor(name);
    final background = HSLColor.fromAHSL(1, hue, 0.42, 0.42).toColor();
    final initials = name.isEmpty
        ? '?'
        : (size >= 28 ? name.substring(0, name.length >= 2 ? 2 : 1) : name[0])
              .toUpperCase();

    final avatar = Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(size * 0.32),
      ),
      alignment: Alignment.center,
      child: Text(
        initials,
        style: TextStyle(
          color: Colors.white,
          fontSize: initials.length > 1 ? size * 0.4 : size * 0.52,
          fontWeight: FontWeight.w700,
          height: 1,
          letterSpacing: 0,
        ),
      ),
    );

    if (semanticLabel == null) return ExcludeSemantics(child: avatar);
    return Semantics(label: semanticLabel, image: true, child: avatar);
  }

  /// Stable hue in [0, 360) from the nickname.
  static double _hueFor(String name) {
    var hash = 0;
    for (final unit in name.codeUnits) {
      hash = (hash * 31 + unit) & 0x7fffffff;
    }
    return (hash % 360).toDouble();
  }
}
