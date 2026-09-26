import 'package:flutter/material.dart';

/// Opaque `--card` content surface (§5.1). Never glass.
class KarmiCard extends StatelessWidget {
  const KarmiCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) => Card(
    clipBehavior: Clip.antiAlias,
    child: Padding(padding: padding, child: child),
  );
}

/// Scroll padding that clears the glass bars (the shell reports their size
/// through `MediaQuery.padding`) plus the 16px page gutter.
EdgeInsets karmiPageInsets(BuildContext context) {
  final pad = MediaQuery.paddingOf(context);
  return EdgeInsets.fromLTRB(16, pad.top + 16, 16, pad.bottom + 24);
}

/// Screen heading used at the top of each tab's content.
class KarmiHeading extends StatelessWidget {
  const KarmiHeading(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: Semantics(
      header: true,
      child: Text(text, style: Theme.of(context).textTheme.headlineSmall),
    ),
  );
}

/// Width of ~70 characters of 16px Proza Libre body text, scaled with the
/// user's text size, so chat prose stays within 65–75 characters per line
/// (Design.md). Pinned by test/widgets/prose_width_test.dart.
const double kProseEms = 38;

double readableProseWidth(BuildContext context) =>
    MediaQuery.textScalerOf(context).scale(16) * kProseEms;
