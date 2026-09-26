import 'package:flutter/material.dart';

/// App-wide accessibility flags that Flutter does not expose directly (§5.2–5.3).
///
/// `reduceTransparency` is the in-app Settings switch OR the platform high-contrast
/// flag. `reduceMotion` mirrors `MediaQuery.disableAnimationsOf`.
class KarmiAccessibility extends InheritedWidget {
  const KarmiAccessibility({
    super.key,
    required this.reduceTransparency,
    required this.reduceMotion,
    required super.child,
  });

  final bool reduceTransparency;
  final bool reduceMotion;

  static KarmiAccessibility? _maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<KarmiAccessibility>();

  static bool reduceTransparencyOf(BuildContext context) =>
      (_maybeOf(context)?.reduceTransparency ?? false) ||
      MediaQuery.highContrastOf(context);

  static bool reduceMotionOf(BuildContext context) =>
      _maybeOf(context)?.reduceMotion ??
      MediaQuery.disableAnimationsOf(context);

  @override
  bool updateShouldNotify(KarmiAccessibility oldWidget) =>
      oldWidget.reduceTransparency != reduceTransparency ||
      oldWidget.reduceMotion != reduceMotion;
}

/// Transition timings: 120–180ms normally (Design.md), [Duration.zero] under reduced motion.
abstract final class KarmiMotion {
  static const fast = Duration(milliseconds: 120);
  static const standard = Duration(milliseconds: 180);

  static Duration duration(
    BuildContext context, [
    Duration normal = standard,
  ]) => KarmiAccessibility.reduceMotionOf(context) ? Duration.zero : normal;

  /// A page route whose enter/exit transition honours reduced motion.
  static Route<T> route<T>(BuildContext context, WidgetBuilder builder) {
    final d = duration(context);
    return PageRouteBuilder<T>(
      transitionDuration: d,
      reverseTransitionDuration: d,
      pageBuilder: (context, _, _) => builder(context),
      transitionsBuilder: (context, animation, _, child) =>
          FadeTransition(opacity: animation, child: child),
    );
  }
}
