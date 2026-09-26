import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/karmi_colors.dart';
import '../theme/karmi_theme.dart';

/// Draws the `--ring` outline (2px, 3px under high contrast) around whichever
/// control inside [child] holds keyboard focus.
///
/// Used where a control's own focus feedback is a faint overlay (list tiles,
/// switches) or is not painted at all on device (GlassTabBar tabs). The ring
/// follows the focused node's on-screen rectangle, so it is drawn at full
/// width even when the control is scaled (the tab bar scales its contents).
/// Shown whenever focus arrived without a pointer press inside [child]:
/// on device, key traversal can leave Flutter in touch highlight mode, so the
/// ring cannot depend on [FocusHighlightMode.traditional] alone.
class KarmiFocusRing extends StatefulWidget {
  const KarmiFocusRing({
    super.key,
    required this.child,
    this.radius = KarmiShape.controlRadius,
  });

  final Widget child;
  final double radius;

  @override
  State<KarmiFocusRing> createState() => _KarmiFocusRingState();
}

class _KarmiFocusRingState extends State<KarmiFocusRing> {
  final _scope = FocusNode(canRequestFocus: false, skipTraversal: true);
  final _box = GlobalKey();
  Rect? _ring;

  /// Set by a pointer press inside the subtree; cleared by any key event.
  bool _pointer = false;

  @override
  void initState() {
    super.initState();
    FocusManager.instance.addListener(_update);
    FocusManager.instance.addHighlightModeListener(_onMode);
    HardwareKeyboard.instance.addHandler(_onKey);
  }

  @override
  void dispose() {
    FocusManager.instance.removeListener(_update);
    FocusManager.instance.removeHighlightModeListener(_onMode);
    HardwareKeyboard.instance.removeHandler(_onKey);
    _scope.dispose();
    super.dispose();
  }

  void _onMode(FocusHighlightMode _) => _update();

  bool _onKey(KeyEvent event) {
    _pointer = false;
    return false;
  }

  void _update() {
    if (!mounted) return;
    Rect? ring;
    final primary = FocusManager.instance.primaryFocus;
    final box = _box.currentContext?.findRenderObject() as RenderBox?;
    if (primary != null &&
        _scope.hasFocus &&
        box != null &&
        box.attached &&
        (!_pointer ||
            FocusManager.instance.highlightMode ==
                FocusHighlightMode.traditional)) {
      final rect = primary.rect;
      ring = Rect.fromPoints(
        box.globalToLocal(rect.topLeft),
        box.globalToLocal(rect.bottomRight),
      );
    }
    if (ring != _ring) setState(() => _ring = ring);
  }

  @override
  Widget build(BuildContext context) {
    return Focus(
      focusNode: _scope,
      includeSemantics: false,
      // Layout settles after focus moves (e.g. scrolling into view).
      onFocusChange: (_) =>
          WidgetsBinding.instance.addPostFrameCallback((_) => _update()),
      child: Listener(
        onPointerDown: (_) {
          _pointer = true;
          _update();
        },
        child: CustomPaint(
          key: _box,
          foregroundPainter: _RingPainter(
            rect: _ring,
            color: KarmiColors.of(context).ring,
            width: KarmiShape.of(context).focusRingWidth,
            radius: widget.radius,
          ),
          child: widget.child,
        ),
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  const _RingPainter({
    required this.rect,
    required this.color,
    required this.width,
    required this.radius,
  });

  final Rect? rect;
  final Color color;
  final double width;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    final r = rect;
    if (r == null) return;
    canvas.drawRRect(
      RRect.fromRectAndRadius(r.deflate(width / 2), Radius.circular(radius)),
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = width
        ..color = color,
    );
  }

  @override
  bool shouldRepaint(_RingPainter old) =>
      old.rect != rect ||
      old.color != color ||
      old.width != width ||
      old.radius != radius;
}
