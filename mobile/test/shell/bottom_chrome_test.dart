import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/shell/bottom_chrome.dart';

void main() {
  tearDown(() {
    BottomChrome.tabBarHeight = 0;
    BottomChrome.composerHeight = 0;
  });

  test('snack bar margin clears the tab bar and the composer dock', () {
    BottomChrome.tabBarHeight = 80;
    BottomChrome.composerHeight = 120;

    expect(
      BottomChrome.snackBarMargin(gap: 12),
      const EdgeInsets.fromLTRB(16, 0, 16, 212),
    );
  });

  test('snack bar margin is only the gap when no chrome is shown', () {
    expect(
      BottomChrome.snackBarMargin(gap: 12),
      const EdgeInsets.fromLTRB(16, 0, 16, 12),
    );
  });
}
