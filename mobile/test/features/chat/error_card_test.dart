import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/chat/chat_models.dart';
import 'package:karmi_app/features/chat/error_card.dart';

void main() {
  group('ErrorCard pure helpers', () {
    test('messageFor returns expected copy for all categories', () {
      expect(
        ErrorCard.messageFor(ErrorCategory.quotaExhausted),
        "You've reached your plan limit for now.",
      );
      expect(
        ErrorCard.messageFor(ErrorCategory.capacityFull),
        'Karmi is busy right now.',
      );
      expect(
        ErrorCard.messageFor(ErrorCategory.providerUnavailable),
        'The model service had a problem.',
      );
      expect(
        ErrorCard.messageFor(ErrorCategory.validationFailed),
        'This reply was blocked or came back empty.',
      );
      expect(
        ErrorCard.messageFor(ErrorCategory.unauthorized),
        'Your session expired. Sign in again.',
      );
      expect(
        ErrorCard.messageFor(ErrorCategory.resumeUnavailable),
        'Connection lost. Partial reply kept.',
      );
      expect(
        ErrorCard.messageFor(ErrorCategory.network),
        'You appear to be offline.',
      );
      expect(
        ErrorCard.messageFor(ErrorCategory.internal),
        'Something went wrong.',
      );
    });

    test('isRetryable returns correct classification for all categories', () {
      expect(ErrorCard.isRetryable(ErrorCategory.capacityFull), isTrue);
      expect(ErrorCard.isRetryable(ErrorCategory.providerUnavailable), isTrue);
      expect(ErrorCard.isRetryable(ErrorCategory.validationFailed), isTrue);
      expect(ErrorCard.isRetryable(ErrorCategory.network), isTrue);
      expect(ErrorCard.isRetryable(ErrorCategory.internal), isTrue);

      expect(ErrorCard.isRetryable(ErrorCategory.quotaExhausted), isFalse);
      expect(ErrorCard.isRetryable(ErrorCategory.unauthorized), isFalse);
      expect(ErrorCard.isRetryable(ErrorCategory.resumeUnavailable), isFalse);
    });
  });

  group('ErrorCard widgets', () {
    testWidgets(
      'quotaExhausted shows message and "View plans" only when onUpgrade is non-null',
      (tester) async {
        var upgraded = false;

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ErrorCard(
                category: ErrorCategory.quotaExhausted,
                onUpgrade: () => upgraded = true,
              ),
            ),
          ),
        );

        expect(
          find.text("You've reached your plan limit for now."),
          findsOneWidget,
        );
        expect(find.text('View plans'), findsOneWidget);

        await tester.tap(find.text('View plans'));
        expect(upgraded, isTrue);

        // Without onUpgrade, no button
        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(
              body: ErrorCard(category: ErrorCategory.quotaExhausted),
            ),
          ),
        );
        expect(find.text('View plans'), findsNothing);

        // With onRetry or onContinue instead of onUpgrade, still no button
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ErrorCard(
                category: ErrorCategory.quotaExhausted,
                onRetry: () {},
                onContinue: () {},
              ),
            ),
          ),
        );
        expect(find.byType(TextButton), findsNothing);
      },
    );

    testWidgets(
      'capacityFull shows message and "Try again" action when onRetry provided',
      (tester) async {
        var retried = false;

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ErrorCard(
                category: ErrorCategory.capacityFull,
                onRetry: () => retried = true,
              ),
            ),
          ),
        );

        expect(find.text('Karmi is busy right now.'), findsOneWidget);
        expect(find.text('Try again'), findsOneWidget);

        await tester.tap(find.text('Try again'));
        expect(retried, isTrue);

        // Null callback hides button
        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(
              body: ErrorCard(category: ErrorCategory.capacityFull),
            ),
          ),
        );
        expect(find.text('Try again'), findsNothing);
      },
    );

    testWidgets(
      'providerUnavailable shows message and "Retry" action when onRetry provided',
      (tester) async {
        var retried = false;

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ErrorCard(
                category: ErrorCategory.providerUnavailable,
                onRetry: () => retried = true,
              ),
            ),
          ),
        );

        expect(find.text('The model service had a problem.'), findsOneWidget);
        expect(find.text('Retry'), findsOneWidget);

        await tester.tap(find.text('Retry'));
        expect(retried, isTrue);
      },
    );

    testWidgets(
      'validationFailed shows message and "Regenerate" action when onRetry provided',
      (tester) async {
        var retried = false;

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ErrorCard(
                category: ErrorCategory.validationFailed,
                onRetry: () => retried = true,
              ),
            ),
          ),
        );

        expect(
          find.text('This reply was blocked or came back empty.'),
          findsOneWidget,
        );
        expect(find.text('Regenerate'), findsOneWidget);

        await tester.tap(find.text('Regenerate'));
        expect(retried, isTrue);
      },
    );

    testWidgets(
      'unauthorized shows message and "Sign in" only when onRetry provided',
      (tester) async {
        var signedIn = false;

        // No callback -> no button
        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(
              body: ErrorCard(category: ErrorCategory.unauthorized),
            ),
          ),
        );

        expect(
          find.text('Your session expired. Sign in again.'),
          findsOneWidget,
        );
        expect(find.byType(TextButton), findsNothing);

        // onRetry provided -> "Sign in" button
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ErrorCard(
                category: ErrorCategory.unauthorized,
                onRetry: () => signedIn = true,
              ),
            ),
          ),
        );

        expect(find.text('Sign in'), findsOneWidget);
        await tester.tap(find.text('Sign in'));
        expect(signedIn, isTrue);
      },
    );

    testWidgets(
      'resumeUnavailable shows message and "Continue" action when onContinue provided',
      (tester) async {
        var continued = false;

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ErrorCard(
                category: ErrorCategory.resumeUnavailable,
                onContinue: () => continued = true,
              ),
            ),
          ),
        );

        expect(
          find.text('Connection lost. Partial reply kept.'),
          findsOneWidget,
        );
        expect(find.text('Continue'), findsOneWidget);

        await tester.tap(find.text('Continue'));
        expect(continued, isTrue);

        // Null callback hides button
        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(
              body: ErrorCard(category: ErrorCategory.resumeUnavailable),
            ),
          ),
        );
        expect(find.text('Continue'), findsNothing);
      },
    );

    testWidgets(
      'network shows message and "Retry" action when onRetry provided',
      (tester) async {
        var retried = false;

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ErrorCard(
                category: ErrorCategory.network,
                onRetry: () => retried = true,
              ),
            ),
          ),
        );

        expect(find.text('You appear to be offline.'), findsOneWidget);
        expect(find.text('Retry'), findsOneWidget);

        await tester.tap(find.text('Retry'));
        expect(retried, isTrue);
      },
    );

    testWidgets(
      'internal shows message and "Retry" action when onRetry provided',
      (tester) async {
        var retried = false;

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ErrorCard(
                category: ErrorCategory.internal,
                onRetry: () => retried = true,
              ),
            ),
          ),
        );

        expect(find.text('Something went wrong.'), findsOneWidget);
        expect(find.text('Retry'), findsOneWidget);

        await tester.tap(find.text('Retry'));
        expect(retried, isTrue);
      },
    );

    testWidgets('has Semantics container, liveRegion, and tooltip on action', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ErrorCard(category: ErrorCategory.network, onRetry: () {}),
          ),
        ),
      );

      final semanticsFinder = find.byWidgetPredicate(
        (w) =>
            w is Semantics &&
            w.container == true &&
            w.properties.liveRegion == true,
      );
      expect(semanticsFinder, findsOneWidget);

      final semantics = tester.widget<Semantics>(semanticsFinder);
      expect(semantics.properties.label, equals('You appear to be offline.'));

      final tooltipFinder = find.byType(Tooltip);
      expect(tooltipFinder, findsOneWidget);
      expect(tester.widget<Tooltip>(tooltipFinder).message, equals('Retry'));
    });

    testWidgets(
      'uses errorContainer/onErrorContainer colors and rounded 12 shape',
      (tester) async {
        const errorBg = Color(0xFFFFDAD6);
        const errorFg = Color(0xFF410002);

        await tester.pumpWidget(
          MaterialApp(
            theme: ThemeData(
              colorScheme: ColorScheme.fromSeed(
                seedColor: Colors.blue,
                errorContainer: errorBg,
                onErrorContainer: errorFg,
              ),
            ),
            home: Scaffold(
              body: ErrorCard(category: ErrorCategory.internal, onRetry: () {}),
            ),
          ),
        );

        final cardFinder = find.byType(Card);
        expect(cardFinder, findsOneWidget);
        final card = tester.widget<Card>(cardFinder);
        expect(card.color, equals(errorBg));

        final shape = card.shape as RoundedRectangleBorder;
        expect(shape.borderRadius, equals(BorderRadius.circular(12)));

        final iconFinder = find.byType(Icon);
        expect(iconFinder, findsOneWidget);
        final icon = tester.widget<Icon>(iconFinder);
        expect(icon.color, equals(errorFg));
      },
    );
  });
}
