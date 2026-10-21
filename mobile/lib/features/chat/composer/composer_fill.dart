import 'package:flutter/foundation.dart';

/// Contract for starter-prompt fills into the composer (§3.1, §3.6).
class ComposerFill extends ChangeNotifier {
  String? _text;

  /// The most recent text filled into the composer, or null if none/cleared.
  String? get text => _text;

  /// Fills the composer with [text] without auto-submitting.
  void fill(String text) {
    _text = text;
    notifyListeners();
  }

  /// Clears the filled text.
  void clear() {
    _text = null;
  }
}
