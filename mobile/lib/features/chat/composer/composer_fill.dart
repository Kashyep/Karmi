import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Contract for starter-prompt fills into the composer (§3.1, §3.6).
class ComposerFill extends ChangeNotifier {
  String? _text;
  TextSelection? _selection;

  /// The most recent text filled into the composer, or null if none/cleared.
  String? get text => _text;

  /// The selection or cursor position for the filled text.
  TextSelection? get selection => _selection;

  /// Fills the composer with [text] and optional [selection] without auto-submitting.
  void fill(String text, {TextSelection? selection}) {
    _text = text;
    _selection = selection;
    notifyListeners();
  }

  /// Clears the filled text.
  void clear() {
    _text = null;
    _selection = null;
  }
}
