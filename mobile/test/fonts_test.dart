import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:karmi_app/fonts.dart';
import 'package:karmi_app/theme/karmi_theme.dart';

void main() {
  setUpAll(configureBundledFonts);

  test('runtime fetching is disabled', () {
    expect(GoogleFonts.config.allowRuntimeFetching, isFalse);
  });

  test(
    'every text style loads from bundled assets with fetching off',
    () async {
      final theme = KarmiTheme.light;
      final styles = <String, TextStyle?>{
        'displaySmall': theme.textTheme.displaySmall,
        'headlineSmall': theme.textTheme.headlineSmall,
        'titleLarge': theme.textTheme.titleLarge,
        'titleMedium': theme.textTheme.titleMedium,
        'labelLarge': theme.textTheme.labelLarge,
        'labelMedium': theme.textTheme.labelMedium,
        'bodyLarge': theme.textTheme.bodyLarge,
        'bodyMedium': theme.textTheme.bodyMedium,
        'labelSmall': theme.textTheme.labelSmall,
        'quote': KarmiTypography.quote(),
        'emphasis': KarmiTypography.emphasis(),
      };
      // Throws if any family/variant is missing from assets/google_fonts/.
      await GoogleFonts.pendingFonts();

      final expectedFamily = <String, String>{
        'displaySmall': 'Exo_700',
        'headlineSmall': 'Exo_600',
        'titleLarge': 'Exo_600',
        'titleMedium': 'Exo_600',
        'labelLarge': 'ProzaLibre_600',
        'labelMedium': 'Exo_500',
        'bodyLarge': 'ProzaLibre_regular',
        'bodyMedium': 'ProzaLibre_regular',
        'labelSmall': 'ProzaLibre_600',
        'quote': 'Trykker_regular',
        'emphasis': 'ProzaLibre_italic',
      };
      for (final MapEntry(key: name, value: style) in styles.entries) {
        expect(style, isNotNull, reason: name);
        expect(style!.fontFamily, expectedFamily[name], reason: name);
        expect(
          style.fontFamilyFallback,
          name == 'quote'
              ? KarmiTypography.serifFallback
              : KarmiTypography.sansFallback,
          reason: '$name must fall back to bundled Devanagari',
        );
      }
    },
  );

  testWidgets('every text style renders (Latin and Devanagari)', (
    tester,
  ) async {
    final theme = KarmiTheme.light;
    await tester.pumpWidget(
      MaterialApp(
        theme: theme,
        home: Builder(
          builder: (context) {
            final t = Theme.of(context).textTheme;
            return ListView(
              children: [
                for (final style in [
                  t.displaySmall,
                  t.headlineSmall,
                  t.titleLarge,
                  t.titleMedium,
                  t.labelLarge,
                  t.labelMedium,
                  t.bodyLarge,
                  t.bodyMedium,
                  t.labelSmall,
                  KarmiText.of(context).quote,
                  KarmiText.of(context).emphasis,
                ])
                  Text('Karmi नमस्ते', style: style),
              ],
            );
          },
        ),
      ),
    );
    await tester.runAsync(GoogleFonts.pendingFonts);
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.text('Karmi नमस्ते'), findsNWidgets(11));
  });
  testWidgets('Devanagari glyphs resolve through the Noto fallback', (
    tester,
  ) async {
    final body = KarmiTheme.light.textTheme.bodyLarge!;
    await tester.runAsync(GoogleFonts.pendingFonts);
    double width(TextStyle style) {
      final painter = TextPainter(
        text: TextSpan(text: 'नमस्ते दुनिया', style: style),
        textDirection: TextDirection.ltr,
      )..layout();
      final w = painter.width;
      painter.dispose();
      return w;
    }

    final withNoto = width(body);
    final withoutNoto = width(
      body.copyWith(fontFamilyFallback: const ['Missing Family']),
    );
    // Without a real fallback the test font draws fixed-width boxes; shaped
    // Devanagari from Noto is measurably narrower.
    expect(withNoto, isNot(closeTo(withoutNoto, 0.5)));
  });

  test('pubspec declares the Noto fallback families', () async {
    final manifest = await rootBundle.loadString('FontManifest.json');
    expect(manifest, contains('"Noto Sans Devanagari"'));
    expect(manifest, contains('"Noto Serif Devanagari"'));
  });

  test('licence registry lists the OFL for each bundled family', () async {
    final entries = await LicenseRegistry.licenses.toList();
    for (final family in kBundledFontLicences.keys) {
      final entry = entries.where((e) => e.packages.contains(family));
      expect(entry, hasLength(1), reason: family);
      final text = entry.single.paragraphs.map((p) => p.text).join('\n');
      expect(text, contains('SIL OPEN FONT LICENSE'), reason: family);
    }
  });

  testWidgets('licence page lists each font family', (tester) async {
    await tester.pumpWidget(
      MaterialApp(theme: KarmiTheme.light, home: const LicensePage()),
    );
    // LicensePage collects licences asynchronously.
    for (var i = 0; i < 20; i++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 50)),
      );
      await tester.pump(const Duration(milliseconds: 100));
    }
    for (final family in kBundledFontLicences.keys) {
      await tester.scrollUntilVisible(
        find.text(family),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text(family), findsOneWidget, reason: family);
    }
  });

  test('assets use google_fonts naming for each bundled variant', () async {
    final manifest = await AssetManifest.loadFromAssetBundle(rootBundle);
    final assets = manifest.listAssets();
    for (final file in [
      'Exo-Medium.ttf',
      'Exo-SemiBold.ttf',
      'Exo-Bold.ttf',
      'ProzaLibre-Regular.ttf',
      'ProzaLibre-Italic.ttf',
      'ProzaLibre-SemiBold.ttf',
      'Trykker-Regular.ttf',
      'NotoSansDevanagari-Regular.ttf',
      'NotoSerifDevanagari-Regular.ttf',
    ]) {
      expect(assets, contains('assets/google_fonts/$file'));
    }
  });
}
