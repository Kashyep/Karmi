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

  testWidgets('floating snack bar sits above the tab bar and composer', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    BottomChrome.tabBarHeight = 80;
    BottomChrome.composerHeight = 120;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Stack(
            children: [
              Positioned(
                left: 0,
                right: 0,
                bottom: BottomChrome.tabBarHeight,
                height: BottomChrome.composerHeight,
                child: const ColoredBox(
                  key: ValueKey('fake-composer'),
                  color: Colors.white,
                ),
              ),
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                height: BottomChrome.tabBarHeight,
                child: const ColoredBox(
                  key: ValueKey('fake-tab-bar'),
                  color: Colors.black,
                ),
              ),
              Builder(
                builder: (context) => Center(
                  child: TextButton(
                    onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        behavior: SnackBarBehavior.floating,
                        margin: BottomChrome.snackBarMargin(gap: 12),
                        content: const Text('Chat deleted'),
                      ),
                    ),
                    child: const Text('show'),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );

    await tester.tap(find.text('show'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    final snackRect = tester.getRect(find.byType(SnackBar));
    final composerTop = tester
        .getTopLeft(find.byKey(const ValueKey('fake-composer')))
        .dy;
    final tabBarTop = tester
        .getTopLeft(find.byKey(const ValueKey('fake-tab-bar')))
        .dy;
    expect(snackRect.bottom, lessThanOrEqualTo(composerTop));
    expect(snackRect.bottom, lessThanOrEqualTo(tabBarTop));
  });
}
