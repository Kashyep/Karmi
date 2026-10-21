import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';

import '../../theme/karmi_colors.dart';
import '../../theme/karmi_glass.dart';
import '../../theme/karmi_motion.dart';
import '../../theme/karmi_theme.dart';
import 'composer/attachment_chip.dart';
import 'composer/composer_fill.dart';
import 'composer/draft_store.dart';
import 'composer/paste_chip.dart';
import 'composer/text_attachment.dart';

export 'composer/composer_fill.dart';

@immutable
class ComposerSubmit {
  const ComposerSubmit({required this.text, this.attachments = const []});

  final String text;
  final List<TextAttachment> attachments;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ComposerSubmit &&
          runtimeType == other.runtimeType &&
          text == other.text &&
          listEquals(attachments, other.attachments);

  @override
  int get hashCode => Object.hash(text, Object.hashAll(attachments));

  @override
  String toString() =>
      'ComposerSubmit(text: $text, attachments: ${attachments.length})';
}

/// Chat composer: a floating glass surface (§3.6, §5.5) holding an input field,
/// attachment/paste tray, and a morphing send/stop button.
class Composer extends StatefulWidget {
  const Composer({
    super.key,
    required this.draftKey,
    required this.busy,
    required this.onSubmit,
    required this.onStop,
    this.draftStore,
    this.onPickAttachments,
    this.fill,
  });

  final String draftKey;
  final bool busy;
  final ValueChanged<ComposerSubmit> onSubmit;
  final VoidCallback onStop;
  final DraftStore? draftStore;
  final FutureOr<List<TextAttachment>?> Function()? onPickAttachments;
  final ComposerFill? fill;

  @override
  State<Composer> createState() => _ComposerState();
}

class _ComposerState extends State<Composer> {
  final _controller = TextEditingController();
  late final FocusNode _focusNode;
  late DraftStore _draftStore;
  final _fallbackDrafts = MemoryDraftStore();

  final List<TextAttachment> _attachments = [];
  final List<String> _pasteChips = [];
  String? _limitError;

  String _previousText = '';
  bool _isHandlingPaste = false;
  Timer? _debounceTimer;

  @override
  void initState() {
    super.initState();
    _draftStore = widget.draftStore ?? _fallbackDrafts;
    _focusNode = FocusNode(
      debugLabel: 'ComposerTextFieldFocus',
      onKeyEvent: _handleKeyEvent,
    );
    _focusNode.addListener(_onFocusChanged);
    _controller.addListener(_onTextChanged);
    widget.fill?.addListener(_onFillChanged);
    _loadDraft(widget.draftKey);
  }

  void _onFocusChanged() {
    if (mounted) setState(() {});
  }

  void _onFillChanged() {
    final text = widget.fill?.text;
    if (text != null && text.isNotEmpty) {
      setState(() {
        _controller.text = text;
        _previousText = text;
        _controller.selection = TextSelection.collapsed(offset: text.length);
      });
      _scheduleDraftSave();
    }
  }

  KeyEventResult _handleKeyEvent(FocusNode node, KeyEvent event) {
    if (event is KeyDownEvent && event.logicalKey == LogicalKeyboardKey.enter) {
      if (HardwareKeyboard.instance.isShiftPressed) {
        // Shift+Enter inserts newline; let TextField handle it
        return KeyEventResult.ignored;
      }
      if (_controller.value.composing.isValid) {
        // IME composing active; let IME handle Enter
        return KeyEventResult.ignored;
      }
      // Plain Enter sends if allowed, otherwise consumes to prevent empty newlines
      if (_canSend) {
        _send();
      }
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  void didUpdateWidget(Composer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.fill != widget.fill) {
      oldWidget.fill?.removeListener(_onFillChanged);
      widget.fill?.addListener(_onFillChanged);
    }
    if (oldWidget.draftStore != widget.draftStore) {
      _draftStore = widget.draftStore ?? _fallbackDrafts;
    }
    if (oldWidget.draftKey != widget.draftKey) {
      _debounceTimer?.cancel();
      _saveDraft(oldWidget.draftKey, _controller.text);
      _controller.clear();
      _previousText = '';
      _loadDraft(widget.draftKey);
    }
  }

  @override
  void dispose() {
    _debounceTimer?.cancel();
    _saveDraft(widget.draftKey, _controller.text);
    _controller.dispose();
    _focusNode.removeListener(_onFocusChanged);
    _focusNode.dispose();
    widget.fill?.removeListener(_onFillChanged);
    super.dispose();
  }

  Future<void> _loadDraft(String key) async {
    final draft = await _draftStore.load(key);
    if (!mounted || key != widget.draftKey) return;
    if (draft != null && draft.isNotEmpty && _controller.text.isEmpty) {
      setState(() {
        _controller.text = draft;
        _previousText = draft;
        _controller.selection = TextSelection.collapsed(offset: draft.length);
      });
    }
  }

  void _scheduleDraftSave() {
    _debounceTimer?.cancel();
    _debounceTimer = Timer(const Duration(milliseconds: 300), () {
      _saveDraft(widget.draftKey, _controller.text);
    });
  }

  Future<void> _saveDraft(String key, String text) async {
    await _draftStore.save(key, text);
  }

  void _onTextChanged() {
    if (_isHandlingPaste) return;
    final newText = _controller.text;
    final diff = newText.length - _previousText.length;

    if (diff > longPasteThreshold) {
      _isHandlingPaste = true;

      int prefixLen = 0;
      while (prefixLen < _previousText.length &&
          prefixLen < newText.length &&
          _previousText[prefixLen] == newText[prefixLen]) {
        prefixLen++;
      }

      int suffixLen = 0;
      while (suffixLen < (_previousText.length - prefixLen) &&
          suffixLen < (newText.length - prefixLen) &&
          _previousText[_previousText.length - 1 - suffixLen] ==
              newText[newText.length - 1 - suffixLen]) {
        suffixLen++;
      }

      final inserted = newText.substring(prefixLen, newText.length - suffixLen);
      if (inserted.length > longPasteThreshold) {
        final remaining =
            _previousText.substring(0, prefixLen) +
            _previousText.substring(_previousText.length - suffixLen);
        _pasteChips.add(inserted);
        _controller.value = TextEditingValue(
          text: remaining,
          selection: TextSelection.collapsed(offset: prefixLen),
        );
        _previousText = remaining;
        _isHandlingPaste = false;
        setState(() {});
        _scheduleDraftSave();
        return;
      }
      _isHandlingPaste = false;
    }

    _previousText = newText;
    setState(() {});
    _scheduleDraftSave();
  }

  bool get _hasContent =>
      _controller.text.trim().isNotEmpty ||
      _pasteChips.isNotEmpty ||
      _attachments.isNotEmpty;

  bool get _canSend => !widget.busy && _hasContent;

  void _showLimitError(String message) {
    setState(() {
      _limitError = message;
    });
    // ignore: deprecated_member_use
    SemanticsService.announce(message, TextDirection.ltr);
  }

  Future<void> _pickAttachments() async {
    if (widget.onPickAttachments == null) return;
    final picked = await widget.onPickAttachments!();
    if (picked == null || picked.isEmpty) return;

    final candidate = [..._attachments, ...picked];
    final result = validateAttachments(candidate);
    if (!result.isValid) {
      _showLimitError(result.message ?? 'Invalid attachment');
      return;
    }
    setState(() {
      _attachments.addAll(picked);
      _limitError = null;
    });
  }

  void _send() {
    if (!_canSend) return;

    final textParts = <String>[];
    final trimmed = _controller.text.trim();
    if (trimmed.isNotEmpty) {
      textParts.add(trimmed);
    }
    for (final chip in _pasteChips) {
      final chipTrimmed = chip.trim();
      if (chipTrimmed.isNotEmpty) {
        textParts.add(chipTrimmed);
      }
    }
    final fullText = textParts.join('\n\n');
    final attachments = List<TextAttachment>.unmodifiable(_attachments);

    final submission = ComposerSubmit(text: fullText, attachments: attachments);

    // Optimistic send: clear state immediately
    _controller.clear();
    _previousText = '';
    _pasteChips.clear();
    _attachments.clear();
    _limitError = null;
    _debounceTimer?.cancel();
    _draftStore.clear(widget.draftKey);
    setState(() {});

    widget.onSubmit(submission);
  }

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final isDark = colors.brightness == Brightness.dark;
    final rimColor = _focusNode.hasFocus
        ? colors.glassSpecularRimFocused
        : colors.glassSpecularRim;
    final hasAttachments = _attachments.isNotEmpty || _pasteChips.isNotEmpty;

    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          if (isDark)
            Positioned.fill(
              child: IgnorePointer(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(
                      KarmiShape.composerRadius,
                    ),
                    gradient: RadialGradient(
                      center: const Alignment(0, 1.0),
                      radius: 1.2,
                      colors: [
                        colors.ambientGlow,
                        colors.ambientGlow.withValues(alpha: 0),
                      ],
                      stops: const [0.0, 0.7],
                    ),
                  ),
                ),
              ),
            ),
          KarmiGlassSurface(
            key: const ValueKey('composer-surface'),
            radius: KarmiShape.composerRadius,
            padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 14),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_limitError != null)
                  Semantics(
                    liveRegion: true,
                    child: Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: Row(
                        children: [
                          Icon(
                            Icons.error_outline,
                            size: 16,
                            color: colors.destructive,
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                              _limitError!,
                              style: TextStyle(
                                color: colors.destructive,
                                fontSize: 12,
                              ),
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.close, size: 14),
                            tooltip: 'Dismiss error',
                            padding: EdgeInsets.zero,
                            constraints: const BoxConstraints(
                              minWidth: 24,
                              minHeight: 24,
                            ),
                            onPressed: () => setState(() => _limitError = null),
                          ),
                        ],
                      ),
                    ),
                  ),
                AnimatedSize(
                  duration: KarmiMotion.duration(
                    context,
                    KarmiMotion.composerDuration,
                  ),
                  curve: KarmiMotion.composerCurve,
                  child: KeyedSubtree(
                    key: const ValueKey('composer-attachment-tray'),
                    child: hasAttachments
                        ? Column(
                            mainAxisSize: MainAxisSize.min,
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              SingleChildScrollView(
                                scrollDirection: Axis.horizontal,
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    for (
                                      int i = 0;
                                      i < _attachments.length;
                                      i++
                                    )
                                      Padding(
                                        padding: const EdgeInsets.only(
                                          right: 6,
                                        ),
                                        child: AttachmentChip(
                                          attachment: _attachments[i],
                                          onRemove: () => setState(
                                            () => _attachments.removeAt(i),
                                          ),
                                        ),
                                      ),
                                    for (
                                      int i = 0;
                                      i < _pasteChips.length;
                                      i++
                                    )
                                      Padding(
                                        padding: const EdgeInsets.only(
                                          right: 6,
                                        ),
                                        child: PasteChip(
                                          text: _pasteChips[i],
                                          onRemove: () => setState(
                                            () => _pasteChips.removeAt(i),
                                          ),
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 6),
                              Container(height: 1, color: colors.hairline),
                              const SizedBox(height: 6),
                            ],
                          )
                        : const SizedBox.shrink(),
                  ),
                ),
                FocusTraversalGroup(
                  policy: OrderedTraversalPolicy(),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      if (widget.onPickAttachments != null) ...[
                        FocusTraversalOrder(
                          order: const NumericFocusOrder(2),
                          child: IconButton(
                            tooltip: 'Attach files',
                            onPressed: widget.busy ? null : _pickAttachments,
                            icon: const Icon(Icons.attach_file),
                          ),
                        ),
                        const SizedBox(width: 4),
                      ],
                      Expanded(
                        child: FocusTraversalOrder(
                          order: const NumericFocusOrder(1),
                          child: Focus(
                            onKeyEvent: _handleKeyEvent,
                            child: TextField(
                              focusNode: _focusNode,
                              controller: _controller,
                              minLines: 1,
                              maxLines: 6,
                              keyboardType: TextInputType.multiline,
                              decoration: const InputDecoration(
                                hintText: 'Message Karmi',
                                labelText: 'Message',
                                floatingLabelBehavior:
                                    FloatingLabelBehavior.never,
                              ),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      FocusTraversalOrder(
                        order: const NumericFocusOrder(3),
                        child: Semantics(
                          button: true,
                          label: widget.busy ? 'Stop response' : 'Send',
                          child: AnimatedContainer(
                            duration: KarmiMotion.duration(
                              context,
                              KarmiMotion.composerDuration,
                            ),
                            curve: KarmiMotion.composerCurve,
                            width: 34,
                            height: 34,
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(
                                widget.busy ? 8 : 17,
                              ),
                            ),
                            clipBehavior: Clip.antiAlias,
                            child: IconButton.filled(
                              key: const ValueKey('composer-send-button'),
                              tooltip: widget.busy
                                  ? 'Stop generating'
                                  : 'Send message',
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints.tightFor(
                                width: 34,
                                height: 34,
                              ),
                              style: IconButton.styleFrom(
                                backgroundColor: colors.primary,
                                foregroundColor: colors.primaryForeground,
                                disabledBackgroundColor: colors.muted,
                                disabledForegroundColor: colors.mutedForeground,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(
                                    widget.busy ? 8 : 17,
                                  ),
                                ),
                                minimumSize: const Size(34, 34),
                                fixedSize: const Size(34, 34),
                                padding: EdgeInsets.zero,
                              ).copyWith(
                                side: WidgetStateProperty.resolveWith(
                                  (states) =>
                                      states.contains(WidgetState.focused)
                                          ? BorderSide(
                                              color: colors.primaryForeground,
                                              width: KarmiShape.of(
                                                context,
                                              ).focusRingWidth,
                                            )
                                          : null,
                                ),
                              ),
                              onPressed: widget.busy
                                  ? widget.onStop
                                  : (_canSend ? _send : null),
                              icon: AnimatedSwitcher(
                                duration: KarmiMotion.duration(
                                  context,
                                  KarmiMotion.composerDuration,
                                ),
                                switchInCurve: KarmiMotion.composerCurve,
                                switchOutCurve: KarmiMotion.composerCurve,
                                child: widget.busy
                                    ? const Icon(
                                        Icons.stop,
                                        key: ValueKey('composer-stop-icon'),
                                        size: 20,
                                      )
                                    : const Icon(
                                        Icons.arrow_upward,
                                        key: ValueKey('composer-send-icon'),
                                        size: 20,
                                      ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Positioned.fill(
            child: IgnorePointer(
              child: CustomPaint(
                painter: _TopSpecularRimPainter(
                  color: rimColor,
                  radius: KarmiShape.composerRadius,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TopSpecularRimPainter extends CustomPainter {
  const _TopSpecularRimPainter({
    required this.color,
    required this.radius,
  });

  final Color color;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 0 || size.height <= 0) return;
    final r = radius.clamp(0.0, size.height / 2);
    final path = Path()
      ..moveTo(0.5, r)
      ..arcToPoint(Offset(r, 0.5), radius: Radius.circular(r))
      ..lineTo(size.width - r - 0.5, 0.5)
      ..arcToPoint(Offset(size.width - 0.5, r), radius: Radius.circular(r));

    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0;

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_TopSpecularRimPainter oldDelegate) =>
      oldDelegate.color != color || oldDelegate.radius != radius;
}
