import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../theme/karmi_colors.dart';

/// Six-digit verification code.
///
/// One hidden text input owns the code, so paste (long-press menu, keyboard
/// clipboard, SMS/email one-time-code autofill) and backspace behave like a
/// normal text field. Non-digits are dropped, so "123 456" and "12-34-56"
/// fill all boxes. The six boxes only display the input's text.
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
  late final TextEditingController _internalController;
  final _focusNode = FocusNode();

  TextEditingController get _effectiveController =>
      widget.controller ?? _internalController;

  @override
  void initState() {
    super.initState();
    _internalController = TextEditingController();
    _effectiveController.addListener(_onTextChanged);
    _focusNode.addListener(_onFocusChanged);
  }

  @override
  void dispose() {
    _effectiveController.removeListener(_onTextChanged);
    _focusNode.removeListener(_onFocusChanged);
    _internalController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _onFocusChanged() => setState(() {});

  void _onTextChanged() {
    final code = _effectiveController.text;
    setState(() {});
    widget.onChanged?.call(code);
    if (code.length == widget.length) {
      widget.onCompleted?.call(code);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final textTheme = Theme.of(context).textTheme;
    final code = _effectiveController.text;
    final focused = _focusNode.hasFocus;
    final activeIndex = code.length.clamp(0, widget.length - 1);

    return Semantics(
      label:
          'Verification code input, ${widget.length} digits. Current code entered: $code',
      textField: true,
      child: Stack(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: List.generate(widget.length, (index) {
              final char = index < code.length ? code[index] : '';
              final isActive = focused && index == activeIndex;
              final borderColor = widget.hasError
                  ? colors.destructive
                  : isActive
                  ? colors.primary
                  : colors.borderSubtle;
              return Container(
                key: ValueKey('otp_box_$index'),
                width: 48,
                height: 56,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: colors.card,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: borderColor,
                    width: isActive ? 2.0 : 1.5,
                  ),
                ),
                child: Text(
                  char,
                  style: textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    fontFeatures: const [FontFeature.tabularFigures()],
                    color: colors.foreground,
                  ),
                ),
              );
            }),
          ),
          // Covers the boxes so taps and long-press paste reach the input.
          Positioned.fill(
            child: Opacity(
              opacity: 0,
              child: TextField(
                key: const ValueKey('otp_input'),
                controller: _effectiveController,
                focusNode: _focusNode,
                keyboardType: TextInputType.number,
                autofillHints: const [AutofillHints.oneTimeCode],
                showCursor: false,
                maxLength: widget.length,
                decoration: const InputDecoration(
                  counterText: '',
                  border: InputBorder.none,
                ),
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
