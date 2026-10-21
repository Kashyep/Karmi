import 'package:flutter/material.dart';

import '../../../theme/karmi_colors.dart';
import '../../../theme/karmi_glass.dart';
import '../../../theme/karmi_motion.dart';
import '../../../theme/karmi_theme.dart';
import '../../../theme/karmi_tokens.dart';
import '../../../widgets/focus_ring.dart';

/// Floating glass pill to jump to the latest messages in the chat stream
/// (spec §3.1 "↓ Jump to latest").
///
/// Fades with [AnimatedOpacity] (honouring [KarmiMotion]) and is not hit-testable
/// or announced while [visible] is false.
class JumpToLatestButton extends StatelessWidget {
  const JumpToLatestButton({
    super.key,
    required this.visible,
    required this.onTap,
    this.hasNewContent = false,
  });

  /// Whether the button is visible on screen.
  final bool visible;

  /// Invoked when the user taps the button.
  final VoidCallback onTap;

  /// True when new content has arrived while scrolled up.
  final bool hasNewContent;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final semanticsLabel = hasNewContent
        ? 'New messages, jump to latest'
        : 'Jump to latest message';
    final labelText = hasNewContent ? 'New messages' : 'Jump to latest';

    final labelStyle = (Theme.of(context).textTheme.labelMedium ??
            const TextStyle(fontSize: 13))
        .copyWith(color: colors.foreground, fontWeight: FontWeight.w600);

    Widget pill = KarmiGlassSurface(
      key: const ValueKey('jump-to-latest'),
      radius: 999,
      semanticLabel: semanticsLabel,
      onTap: onTap,
      padding: const EdgeInsets.symmetric(horizontal: KarmiTokens.s16),
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          minWidth: KarmiShape.minTapTarget,
          minHeight: KarmiShape.minTapTarget,
        ),
        child: ExcludeSemantics(
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (hasNewContent) ...[
                Container(
                  key: const ValueKey('jump-to-latest-dot'),
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: colors.primary,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: KarmiTokens.s8),
              ],
              Icon(Icons.arrow_downward, size: 18, color: colors.foreground),
              const SizedBox(width: KarmiTokens.s8),
              Text(labelText, style: labelStyle),
            ],
          ),
        ),
      ),
    );

    final hasKarmiTheme =
        Theme.of(context).extension<KarmiColors>() != null &&
        Theme.of(context).extension<KarmiShape>() != null;
    if (hasKarmiTheme) {
      pill = KarmiFocusRing(radius: 999, child: pill);
    }

    return IgnorePointer(
      ignoring: !visible,
      child: ExcludeSemantics(
        excluding: !visible,
        child: AnimatedOpacity(
          duration: KarmiMotion.duration(context, KarmiMotion.standard),
          curve: Curves.easeOut,
          opacity: visible ? 1.0 : 0.0,
          child: Tooltip(message: semanticsLabel, child: pill),
        ),
      ),
    );
  }
}
