import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

/// Bundled families and their SIL OFL 1.1 licence files (assets/google_fonts/).
const Map<String, String> kBundledFontLicences = {
  'Exo': 'assets/google_fonts/Exo-OFL.txt',
  'Proza Libre': 'assets/google_fonts/ProzaLibre-OFL.txt',
  'Trykker': 'assets/google_fonts/Trykker-OFL.txt',
  'Noto Sans Devanagari': 'assets/google_fonts/NotoSansDevanagari-OFL.txt',
  'Noto Serif Devanagari': 'assets/google_fonts/NotoSerifDevanagari-OFL.txt',
};

bool _registered = false;

/// Offline fonts: never fetch from fonts.gstatic.com (google_fonts 8.2.1
/// `GoogleFontsConfig.allowRuntimeFetching`), and list each OFL on the licences page.
void configureBundledFonts() {
  GoogleFonts.config.allowRuntimeFetching = false;
  if (_registered) return;
  _registered = true;
  LicenseRegistry.addLicense(_fontLicences);
}

Stream<LicenseEntry> _fontLicences() async* {
  for (final MapEntry(key: family, value: path)
      in kBundledFontLicences.entries) {
    yield LicenseEntryWithLineBreaks([
      family,
    ], await rootBundle.loadString(path));
  }
}
