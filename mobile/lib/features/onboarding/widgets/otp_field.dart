import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../theme/karmi_colors.dart';

/// 6-box segmented pin field with auto-advance, backspace handling, clipboard paste, and error styling.
class OtpField extends StatefulWidget {
  const OtpField({
    super.key,
    this.length = 6,
    this.onChanged,
    this.onCompleted,
    this.hasError = false,
    this.controller,
  });

  final int length;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onCompleted;
  final bool hasError;
  final TextEditingController? controller;

  @override
  State<OtpField> createState() => _OtpFieldState();
}

class _OtpFieldState extends State<OtpField> {
  late final List<TextEditingController> _boxControllers;
  late final List<FocusNode> _focusNodes;
  late final TextEditingController _internalController;

  TextEditingController get _effectiveController =>
      widget.controller ?? _internalController;

  @override
  void initState() {
    super.initState();
    _internalController = TextEditingController();
    _boxControllers = List.generate(
      widget.length,
      (index) => TextEditingController(),
    );
    _focusNodes = List.generate(widget.length, (index) => FocusNode());

    _effectiveController.addListener(_syncFromMainController);
    _syncFromMainController();
  }

  void _syncFromMainController() {
    final text = _effectiveController.text;
    for (int i = 0; i < widget.length; i++) {
      final char = i < text.length ? text[i] : '';
      if (_boxControllers[i].text != char) {
        _boxControllers[i].text = char;
      }
    }
  }

  void _updateMainController() {
    final code = _boxControllers.map((c) => c.text).join();
    if (_effectiveController.text != code) {
      _effectiveController.text = code;
    }
    widget.onChanged?.call(code);
    if (code.length == widget.length) {
      widget.onCompleted?.call(code);
    }
  }

  @override
  void dispose() {
    _effectiveController.removeListener(_syncFromMainController);
    _internalController.dispose();
    for (final c in _boxControllers) {
      c.dispose();
    }
    for (final f in _focusNodes) {
      f.dispose();
    }
    super.dispose();
  }

  void _onDigitChanged(int index, String value) {
    if (value.length > 1) {
      // Handles pasting or typing multiple characters
      final digits = value.replaceAll(RegExp(r'\D'), '');
      if (digits.isNotEmpty) {
        for (int i = 0; i < digits.length && (index + i) < widget.length; i++) {
          _boxControllers[index + i].text = digits[i];
        }
        final nextIndex = (index + digits.length).clamp(0, widget.length - 1);
        _focusNodes[nextIndex].requestFocus();
        _updateMainController();
        return;
      }
    }

    if (value.isNotEmpty) {
      if (index < widget.length - 1) {
        _focusNodes[index + 1].requestFocus();
      } else {
        _focusNodes[index].unfocus();
      }
    }
    _updateMainController();
  }

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final currentCode = _boxControllers.map((c) => c.text).join();

    return Semantics(
      label:
          'Verification code input, ${widget.length} digits. Current code entered: $currentCode',
      textField: true,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: List.generate(widget.length, (index) {
          return SizedBox(
            width: 48,
            height: 56,
            child: RawKeyboardListener(
              focusNode: FocusNode(skipTraversal: true),
              onKey: (event) {
                if (event is RawKeyDownEvent &&
                    event.logicalKey == LogicalKeyboardKey.backspace) {
                  if (_boxControllers[index].text.isEmpty && index > 0) {
                    _boxControllers[index - 1].clear();
                    _focusNodes[index - 1].requestFocus();
                    _updateMainController();
                  }
                }
              },
              child: TextField(
                key: ValueKey('otp_box_$index'),
                controller: _boxControllers[index],
                focusNode: _focusNodes[index],
                textAlign: TextAlign.center,
                keyboardType: TextInputType.number,
                maxLength: 1,
                style: textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                  fontFeatures: const [FontFeature.tabularFigures()],
                  color: colors.foreground,
                ),
                inputFormatters: [
                  FilteringTextInputFormatter.digitsOnly,
                ],
                decoration: InputDecoration(
                  counterText: '',
                  contentPadding: const EdgeInsets.symmetric(vertical: 12),
                  filled: true,
                  fillColor: colors.card,
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide: BorderSide(
                      color: widget.hasError
                          ? colors.destructive
                          : colors.borderSubtle,
                      width: 1.5,
                    ),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide: BorderSide(
                      color: widget.hasError
                          ? colors.destructive
                          : colors.primary,
                      width: 2.0,
                    ),
                  ),
                ),
                onChanged: (val) => _onDigitChanged(index, val),
              ),
            ),
          );
        }),
      ),
    );
  }
}
