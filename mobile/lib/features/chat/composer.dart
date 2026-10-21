import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';

import '../../theme/karmi_colors.dart';
import '../../theme/karmi_glass.dart';
import '../../theme/karmi_theme.dart';
import 'composer/attachment_chip.dart';
import 'composer/draft_store.dart';
import 'composer/paste_chip.dart';
import 'composer/text_attachment.dart';

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

/// Chat composer: a glass tray (§5.1) holding an opaque text field,
/// attachment/paste chips, and a send/stop button.
class Composer extends StatefulWidget {
  const Composer({
    super.key,
    required this.draftKey,
    required this.busy,
    required this.onSubmit,
    required this.onStop,
    this.draftStore,
    this.onPickAttachments,
  });

  final String draftKey;
  final bool busy;
  final ValueChanged<ComposerSubmit> onSubmit;
  final VoidCallback onStop;
  final DraftStore? draftStore;
  final FutureOr<List<TextAttachment>?> Function()? onPickAttachments;

  @override
  State<Composer> createState() => _ComposerState();
}

class _ComposerState extends State<Composer> {
  final _controller = TextEditingController();
  late final FocusNode _focusNode;
  late DraftStore _draftStore;

  final List<TextAttachment> _attachments = [];
  final List<String> _pasteChips = [];
  String? _limitError;

  String _previousText = '';
  bool _isHandlingPaste = false;
  Timer? _debounceTimer;

  @override
  void initState() {
    super.initState();
    _draftStore = widget.draftStore ?? const SharedPrefsDraftStore();
    _focusNode = FocusNode(
      debugLabel: 'ComposerTextFieldFocus',
      onKeyEvent: _handleKeyEvent,
    );
    _controller.addListener(_onTextChanged);
    _loadDraft(widget.draftKey);
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
    if (oldWidget.draftStore != widget.draftStore) {
      _draftStore = widget.draftStore ?? const SharedPrefsDraftStore();
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
    _focusNode.dispose();
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

    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      child: KarmiGlassSurface(
        key: const ValueKey('composer-tray'),
        padding: const EdgeInsets.all(8),
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
            if (_attachments.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Wrap(
                  spacing: 4,
                  runSpacing: 4,
                  children: [
                    for (int i = 0; i < _attachments.length; i++)
                      AttachmentChip(
                        attachment: _attachments[i],
                        onRemove: () =>
                            setState(() => _attachments.removeAt(i)),
                      ),
                  ],
                ),
              ),
            if (_pasteChips.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (int i = 0; i < _pasteChips.length; i++)
                      PasteChip(
                        text: _pasteChips[i],
                        onRemove: () => setState(() => _pasteChips.removeAt(i)),
                      ),
                  ],
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
                            floatingLabelBehavior: FloatingLabelBehavior.never,
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
                      label: widget.busy ? 'Stop generating' : 'Send message',
                      child: IconButton.filled(
                        tooltip: widget.busy ? 'Stop generating' : 'Send message',
                        style:
                            IconButton.styleFrom(
                              backgroundColor: colors.primary,
                              foregroundColor: colors.primaryForeground,
                              disabledBackgroundColor: colors.muted,
                              disabledForegroundColor: colors.mutedForeground,
                            ).copyWith(
                              side: WidgetStateProperty.resolveWith(
                                (states) => states.contains(WidgetState.focused)
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
                        icon: Icon(widget.busy ? Icons.stop : Icons.arrow_upward),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
