import 'package:flutter/material.dart';

/// Heights of the bottom chrome that floating snackbars must clear.
///
/// The compact tab bar and the chat composer dock sit above the page body, but
/// the root [ScaffoldMessenger] snackbar is positioned from the screen bottom.
/// Each owner publishes its measured height here; snackbars read it when shown.
abstract final class BottomChrome {
  /// Height of the compact bottom tab bar, including the bottom safe area.
  static double tabBarHeight = 0;

  /// Measured height of the chat composer dock, including its bottom padding.
  static double composerHeight = 0;

  /// Bottom margin that keeps a floating snackbar above the tab bar and composer.
  static EdgeInsets snackBarMargin({double gap = 12}) =>
      EdgeInsets.fromLTRB(16, 0, 16, tabBarHeight + composerHeight + gap);
}
