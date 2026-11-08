import 'dart:math' as math;

import 'package:flutter/material.dart';

/// WCAG 2.x contrast ratio between [a] and [b], in the range 1.0–21.0.
///
/// Uses relative luminance from [Color.computeLuminance]. Order does not
/// matter; the lighter colour is always the numerator.
double contrastRatio(Color a, Color b) {
  final la = a.computeLuminance();
  final lb = b.computeLuminance();
  final lighter = math.max(la, lb);
  final darker = math.min(la, lb);
  return (lighter + 0.05) / (darker + 0.05);
}
