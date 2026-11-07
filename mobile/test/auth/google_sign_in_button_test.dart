import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/auth/google_sign_in_button.dart';

Widget _wrap(Widget child, {Brightness brightness = Brightness.light}) {
  final theme = brightness == Brightness.dark
      ? ThemeData.dark()
      : ThemeData.light();
  return MaterialApp(
    theme: theme,
    home: Theme(
      data: theme,
      child: Scaffold(
        body: Center(child: SizedBox(width: 360, child: child)),
      ),
    ),
  );
}

void main() {
  group('GoogleSignInButton widget', () {
    testWidgets('renders button with label and accessible semantics', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      var pressed = false;
      await tester.pumpWidget(
        _wrap(
          GoogleSignInButton(
            onPressed: () {
              pressed = true;
            },
          ),
        ),
      );
      // Verifies label and semantics
      expect(find.text('Continue with Google'), findsOneWidget);
      final finder = find.bySemanticsLabel(RegExp('Continue with Google'));
      expect(finder, findsOneWidget);

      final semantics = tester.getSemantics(finder);
      expect(semantics.flagsCollection.isButton, isTrue);
      expect(semantics.flagsCollection.isEnabled, ui.Tristate.isTrue);
      expect(semantics.hasAction(ui.SemanticsAction.tap), isTrue);
      // Google logo painter is present
      expect(find.byType(CustomPaint), findsWidgets);
      expect(
        find.byWidgetPredicate(
          (w) => w is CustomPaint && w.painter is GoogleLogoPainter,
        ),
        findsOneWidget,
      );

      // Tap triggers onPressed
      await tester.tap(finder);
      await tester.pump();
      expect(pressed, isTrue);
      handle.dispose();
    });

    testWidgets(
      'excludes child semantics to avoid duplicate TalkBack announcement',
      (tester) async {
        await tester.pumpWidget(
          _wrap(
            GoogleSignInButton(
              onPressed: () {},
            ),
          ),
        );

        final semanticsFinder = find.descendant(
          of: find.byType(GoogleSignInButton),
          matching: find.byWidgetPredicate(
            (w) => w is Semantics && w.properties.label == 'Continue with Google',
          ),
        );
        expect(semanticsFinder, findsOneWidget);

        final semanticsWidget = tester.widget<Semantics>(semanticsFinder);
        expect(semanticsWidget.excludeSemantics, isTrue);
      },
    );

    testWidgets('disabled state when onPressed is null', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(_wrap(const GoogleSignInButton(onPressed: null)));

      final finder = find.bySemanticsLabel(RegExp('Continue with Google'));
      expect(finder, findsOneWidget);
      final semantics = tester.getSemantics(finder);
      expect(semantics.flagsCollection.isEnabled, ui.Tristate.isFalse);
      expect(semantics.hasAction(ui.SemanticsAction.tap), isFalse);
      final inkWell = tester.widget<InkWell>(find.byType(InkWell));
      expect(inkWell.onTap, isNull);
      handle.dispose();
    });

    testWidgets('loading state shows spinner and disables interaction', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      var pressed = false;
      await tester.pumpWidget(
        _wrap(
          GoogleSignInButton(
            onPressed: () {
              pressed = true;
            },
            isLoading: true,
          ),
        ),
      );

      // CircularProgressIndicator shown, logo hidden
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(
        find.byWidgetPredicate(
          (w) => w is CustomPaint && w.painter is GoogleLogoPainter,
        ),
        findsNothing,
      );

      // Interaction disabled in semantics and inkwell
      final finder = find.bySemanticsLabel(RegExp('Continue with Google'));
      expect(finder, findsOneWidget);
      final semantics = tester.getSemantics(finder);
      expect(semantics.flagsCollection.isEnabled, ui.Tristate.isFalse);
      expect(semantics.hasAction(ui.SemanticsAction.tap), isFalse);
      final inkWell = tester.widget<InkWell>(find.byType(InkWell));
      expect(inkWell.onTap, isNull);

      // Tapping does not fire callback
      await tester.tap(finder, warnIfMissed: false);
      await tester.pump();
      expect(pressed, isFalse);
      handle.dispose();
    });

    testWidgets('enforces minimum 48 dp height constraint', (tester) async {
      await tester.pumpWidget(_wrap(GoogleSignInButton(onPressed: () {})));

      final constrainedBox = tester.widget<ConstrainedBox>(
        find.descendant(
          of: find.byType(GoogleSignInButton),
          matching: find.byWidgetPredicate(
            (w) => w is ConstrainedBox && w.constraints.minHeight == 48,
          ),
        ),
      );
      expect(constrainedBox.constraints.minHeight, 48.0);

      final buttonSize = tester.getSize(find.byType(GoogleSignInButton));
      expect(buttonSize.height, greaterThanOrEqualTo(48.0));
    });

    testWidgets('applies distinct styling for light and dark themes', (
      tester,
    ) async {
      // Light theme
      await tester.pumpWidget(
        _wrap(
          GoogleSignInButton(onPressed: () {}),
          brightness: Brightness.light,
        ),
      );

      final lightMaterial = tester.widget<Material>(
        find.descendant(
          of: find.byType(GoogleSignInButton),
          matching: find.byType(Material),
        ),
      );
      expect(lightMaterial.color, Colors.white);

      final lightText = tester.widget<Text>(
        find.descendant(
          of: find.byType(GoogleSignInButton),
          matching: find.text('Continue with Google'),
        ),
      );
      expect(lightText.style?.color, const Color(0xFF1F1F1F));

      // Dark theme
      await tester.pumpWidget(
        _wrap(
          GoogleSignInButton(onPressed: () {}),
          brightness: Brightness.dark,
        ),
      );

      final darkMaterial = tester.widget<Material>(
        find.descendant(
          of: find.byType(GoogleSignInButton),
          matching: find.byType(Material),
        ),
      );
      expect(darkMaterial.color, const Color(0xFF131314));

      final darkText = tester.widget<Text>(
        find.descendant(
          of: find.byType(GoogleSignInButton),
          matching: find.text('Continue with Google'),
        ),
      );
      expect(darkText.style?.color, const Color(0xFFE3E3E3));
    });
  });

  group('GoogleLogoPainter', () {
    test('shouldRepaint returns false', () {
      const painter1 = GoogleLogoPainter();
      const painter2 = GoogleLogoPainter();
      expect(painter1.shouldRepaint(painter2), isFalse);
    });
  });
}
