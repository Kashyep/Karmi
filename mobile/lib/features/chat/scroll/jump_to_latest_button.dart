import 'package:flutter/material.dart';

import '../../../theme/karmi_colors.dart';
import '../../../theme/karmi_motion.dart';
import '../../../theme/karmi_theme.dart';
import '../../../theme/karmi_tokens.dart';
import '../../../widgets/focus_ring.dart';

/// Floating button to jump to the latest messages in the chat stream.
///
/// Disappears smoothly with [AnimatedOpacity] and [AnimatedSlide] when not
/// visible, honoring [KarmiAccessibility.reduceMotionOf].
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
    final duration = KarmiMotion.duration(context, KarmiTokens.fast);

    final semanticsLabel = hasNewContent
        ? 'New messages, jump to latest'
        : 'Jump to latest message';
    final labelText = hasNewContent ? 'New messages' : 'Jump to latest';
    final tooltipMessage =
        hasNewContent ? 'New messages, jump to latest' : 'Jump to latest';

    final karmiColors = Theme.of(context).extension<KarmiColors>();
    final colorScheme = Theme.of(context).colorScheme;

    final Color backgroundColor;
    final Color foregroundColor;
    final Border? border;

    if (hasNewContent) {
      backgroundColor = karmiColors?.primary ?? colorScheme.primary;
      foregroundColor = karmiColors?.primaryForeground ?? colorScheme.onPrimary;
      border = null;
    } else {
      backgroundColor = karmiColors?.card ?? colorScheme.surface;
      foregroundColor = karmiColors?.foreground ?? colorScheme.onSurface;
      final borderColor = karmiColors?.border ?? colorScheme.outline;
      border = Border.all(color: borderColor, width: 1);
    }

    Widget innerContent = Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Ink(
          decoration: BoxDecoration(
            color: backgroundColor,
            borderRadius: BorderRadius.circular(999),
            border: border,
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.12),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              minWidth: 48,
              minHeight: 48,
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: KarmiTokens.s16,
                vertical: KarmiTokens.s8,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.arrow_downward,
                    size: 18,
                    color: foregroundColor,
                  ),
                  const SizedBox(width: KarmiTokens.s8),
                  Text(
                    labelText,
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                          color: foregroundColor,
                          fontWeight: FontWeight.w600,
                        ) ??
                        TextStyle(
                          color: foregroundColor,
                          fontWeight: FontWeight.w600,
                          fontSize: 12,
                        ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );

    final hasKarmiTheme = Theme.of(context).extension<KarmiColors>() != null &&
        Theme.of(context).extension<KarmiShape>() != null;

    if (hasKarmiTheme) {
      innerContent = KarmiFocusRing(
        radius: 999,
        child: innerContent,
      );
    }

    final button = Semantics(
      button: true,
      label: semanticsLabel,
      container: true,
      excludeSemantics: true,
      child: Tooltip(
        message: tooltipMessage,
        child: innerContent,
      ),
    );

    return IgnorePointer(
      ignoring: !visible,
      child: ExcludeSemantics(
        excluding: !visible,
        child: AnimatedSlide(
          duration: duration,
          curve: Curves.easeOut,
          offset: visible ? Offset.zero : const Offset(0, 0.5),
          child: AnimatedOpacity(
            duration: duration,
            curve: Curves.easeOut,
            opacity: visible ? 1.0 : 0.0,
            child: button,
          ),
        ),
      ),
    );
  }
}
