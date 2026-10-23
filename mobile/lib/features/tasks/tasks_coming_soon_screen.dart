import 'package:flutter/material.dart';

import '../../theme/karmi_colors.dart';
import '../../theme/karmi_theme.dart';

/// Tasks tab placeholder: the feature is still being built, so the tab shows a
/// playful "construction site" instead of an empty list or an error.
///
/// Everything here is static and respects the text scale, so it stays readable
/// with large fonts and needs no animation policy of its own.
class TasksComingSoonScreen extends StatelessWidget {
  const TasksComingSoonScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final text = Theme.of(context).textTheme;

    return ColoredBox(
      color: colors.background,
      child: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const _HazardStripe(height: 10),
                  const SizedBox(height: 24),
                  Center(
                    child: Container(
                      width: 96,
                      height: 96,
                      decoration: BoxDecoration(
                        color: colors.primary.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(28),
                        border: Border.all(color: colors.hairline),
                      ),
                      child: Icon(
                        Icons.construction_rounded,
                        size: 48,
                        color: colors.primary,
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),
                  Text(
                    'Tasks are under construction',
                    textAlign: TextAlign.center,
                    style: text.headlineSmall?.copyWith(
                      color: colors.foreground,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'We are pouring the concrete on reminders, task lists and '
                    'follow-ups. The site opens soon — thanks for your patience.',
                    textAlign: TextAlign.center,
                    style: text.bodyLarge?.copyWith(
                      color: colors.mutedForeground,
                    ),
                  ),
                  const SizedBox(height: 24),
                  const _ProgressBoard(),
                  const SizedBox(height: 24),
                  const _HazardStripe(height: 10),
                  const SizedBox(height: 12),
                  Text(
                    'Hard hats recommended. Chat is open as usual.',
                    textAlign: TextAlign.center,
                    style: text.labelMedium?.copyWith(
                      color: colors.mutedForeground,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Diagonally striped border, like hazard tape.
class _HazardStripe extends StatelessWidget {
  const _HazardStripe({required this.height});

  final double height;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    return SizedBox(
      height: height,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(height / 2),
        child: CustomPaint(
          painter: _HazardPainter(
            stripe: colors.primary.withValues(alpha: 0.7),
            background: colors.muted,
          ),
        ),
      ),
    );
  }
}

class _HazardPainter extends CustomPainter {
  const _HazardPainter({required this.stripe, required this.background});

  final Color stripe;
  final Color background;

  @override
  void paint(Canvas canvas, Size size) {
    final bg = Paint()..color = background;
    canvas.drawRect(Offset.zero & size, bg);

    final paint = Paint()..color = stripe;
    const gap = 14.0;
    for (var x = -size.height; x < size.width + size.height; x += gap * 2) {
      final path = Path()
        ..moveTo(x, size.height)
        ..lineTo(x + size.height, 0)
        ..lineTo(x + size.height + gap, 0)
        ..lineTo(x + gap, size.height)
        ..close();
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(_HazardPainter oldDelegate) =>
      oldDelegate.stripe != stripe || oldDelegate.background != background;
}

/// A "site progress" board with a few playful, honest milestones.
class _ProgressBoard extends StatelessWidget {
  const _ProgressBoard();

  static const _steps = <(String, bool)>[
    ('Blueprints', true),
    ('Foundation', true),
    ('Walls', false),
    ('Roof', false),
  ];

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final text = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(KarmiShape.cardRadius),
        border: Border.all(color: colors.hairline),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Build progress',
            style: text.titleSmall?.copyWith(color: colors.foreground),
          ),
          const SizedBox(height: 12),
          for (final (label, done) in _steps)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                children: [
                  Icon(
                    done
                        ? Icons.check_circle_rounded
                        : Icons.radio_button_unchecked_rounded,
                    size: 18,
                    color: done ? colors.primary : colors.mutedForeground,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      label,
                      style: text.bodyMedium?.copyWith(
                        color: colors.foreground,
                      ),
                    ),
                  ),
                  if (!done)
                    Text(
                      'soon',
                      style: text.labelSmall?.copyWith(
                        color: colors.foreground,
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
