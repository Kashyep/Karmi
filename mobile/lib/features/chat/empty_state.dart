import 'package:flutter/material.dart';

import '../../theme/karmi_colors.dart';
import '../../theme/karmi_theme.dart';
import 'composer/composer_fill.dart';

/// Starter prompt fill text and cursor offset.
class StarterChipFill {
  const StarterChipFill({required this.text, required this.cursorOffset});

  final String text;
  final int cursorOffset;

  TextSelection get selection => TextSelection.collapsed(offset: cursorOffset);
}

/// Empty New Chat state showing a time-of-day greeting, model/capability pill,
/// capability caption, and 4 starter prompt chips (§3.1, §5.3, §5.6).
class ChatEmptyState extends StatelessWidget {
  const ChatEmptyState({
    super.key = const ValueKey('new-chat-empty-state'),
    this.onStarterPicked,
    this.clock = _defaultClock,
    this.onPromptTap,
    this.name,
    this.prompts = starterPrompts,
    this.composerFill,
  });

  static DateTime _defaultClock() => DateTime.now();

  /// Callback when a starter prompt chip is tapped.
  final ValueChanged<String>? onStarterPicked;

  /// Optional alias for [onStarterPicked].
  final ValueChanged<String>? onPromptTap;

  /// Optional composer fill handle to populate the composer without sending.
  final ComposerFill? composerFill;

  /// Injectable clock for deterministic tests.
  final DateTime Function()? clock;

  /// Optional user name for personalized greeting.
  final String? name;

  /// List of starter prompts to show (defaults to [starterPrompts]).
  final List<String> prompts;

  /// Exactly 4 starter prompts, role-agnostic for a study app.
  static const List<String> starterPrompts = [
    'Explain a concept step by step',
    'Help me solve a maths problem',
    'Review my code for bugs',
    'Summarise my notes into key points',
  ];

  /// Mapping from starter prompt label to starter template text and cursor offset.
  static StarterChipFill starterFillFor(String prompt) {
    switch (prompt) {
      case 'Explain a concept step by step':
        return const StarterChipFill(
          text: 'Explain  step by step',
          cursorOffset: 8,
        );
      case 'Help me solve a maths problem':
        return const StarterChipFill(text: 'Help me solve ', cursorOffset: 14);
      case 'Review my code for bugs':
        return const StarterChipFill(text: 'Review  for bugs', cursorOffset: 7);
      case 'Summarise my notes into key points':
        return const StarterChipFill(
          text: 'Summarise  into key points',
          cursorOffset: 10,
        );
      default:
        return StarterChipFill(text: prompt, cursorOffset: prompt.length);
    }
  }

  static const List<String> defaultStarterPrompts = starterPrompts;

  /// Returns greeting string personalized by time of day:
  /// - 05:00 to 11:59: 'Good morning'
  /// - 12:00 to 16:59: 'Good afternoon'
  /// - 17:00 to 04:59 (including hour 0 midnight): 'Good evening'
  static String greetingFor(DateTime time, {String? name}) {
    final hour = time.hour;
    final String base;
    if (hour >= 5 && hour < 12) {
      base = 'Good morning';
    } else if (hour >= 12 && hour < 17) {
      base = 'Good afternoon';
    } else {
      base = 'Good evening';
    }
    if (name != null && name.trim().isNotEmpty) {
      return '$base, ${name.trim()}';
    }
    return base;
  }

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final theme = Theme.of(context);
    final now = (clock ?? _defaultClock)();
    final greeting = greetingFor(now, name: name);

    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          maxWidth: KarmiShape.readableColumnMaxWidth,
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              // Time-of-day greeting
              Text(
                greeting,
                style: KarmiTypography.greeting().copyWith(
                  color: colors.foreground,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              // Capability line beneath greeting
              Text(
                'Ask a study question, or get help with maths or code.',
                style: KarmiTypography.toolbarCaption().copyWith(
                  color: Color.lerp(
                    colors.mutedForeground,
                    colors.foreground,
                    0.4,
                  )!,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              // 4 starter prompt chips
              Wrap(
                alignment: WrapAlignment.center,
                spacing: 8,
                runSpacing: 8,
                children: prompts.map((prompt) {
                  return Semantics(
                    button: true,
                    label: prompt,
                    child: Material(
                      color: colors.card,
                      shape: StadiumBorder(
                        side: BorderSide(color: colors.borderSubtle),
                      ),
                      clipBehavior: Clip.antiAlias,
                      child: InkWell(
                        onTap: () {
                          final fill = starterFillFor(prompt);
                          composerFill?.fill(
                            fill.text,
                            selection: fill.selection,
                          );
                          onStarterPicked?.call(prompt);
                          onPromptTap?.call(prompt);
                        },
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(
                            minHeight: 48,
                            minWidth: 48,
                          ),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 14,
                              vertical: 10,
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Flexible(
                                  child: Text(
                                    prompt,
                                    style:
                                        (theme.textTheme.labelSmall ??
                                                KarmiTypography.toolbarCaption())
                                            .copyWith(color: colors.foreground),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Backward compatibility typedef for NewChatEmptyState.
typedef NewChatEmptyState = ChatEmptyState;
