import 'package:flutter/material.dart';

import 'admin_support.dart';

class AdminDialogOption {
  const AdminDialogOption(this.value, this.label);

  final String value;
  final String label;
}

class AdminDialogField {
  const AdminDialogField({
    required this.name,
    required this.label,
    this.initial = '',
    this.options,
    this.keyboardType,
    this.validator,
  });

  final String name;
  final String label;
  final String initial;

  /// When set, the field is a dropdown whose selected value is [initial].
  final List<AdminDialogOption>? options;
  final TextInputType? keyboardType;

  /// Returns an error message, or null when the value is acceptable.
  final String? Function(String value)? validator;
}

class AdminActionInput {
  const AdminActionInput({required this.reason, required this.values});

  final String reason;
  final Map<String, String> values;

  String? operator [](String name) => values[name];
}

/// Confirm dialog for every admin mutation. The reason is always required;
/// the confirm button stays disabled until the form is valid. When
/// [requireTyped] is set, the user must also type that exact word.
Future<AdminActionInput?> showAdminActionDialog(
  BuildContext context, {
  required String title,
  required String confirmLabel,
  String? description,
  List<AdminDialogField> fields = const [],
  String? requireTyped,
  bool destructive = false,
}) {
  return showDialog<AdminActionInput>(
    context: context,
    builder: (_) => AdminActionDialog(
      title: title,
      confirmLabel: confirmLabel,
      description: description,
      fields: fields,
      requireTyped: requireTyped,
      destructive: destructive,
    ),
  );
}

class AdminActionDialog extends StatefulWidget {
  const AdminActionDialog({
    super.key,
    required this.title,
    required this.confirmLabel,
    this.description,
    this.fields = const [],
    this.requireTyped,
    this.destructive = false,
  });

  final String title;
  final String confirmLabel;
  final String? description;
  final List<AdminDialogField> fields;
  final String? requireTyped;
  final bool destructive;

  @override
  State<AdminActionDialog> createState() => _AdminActionDialogState();
}

class _AdminActionDialogState extends State<AdminActionDialog> {
  final _reason = TextEditingController();
  final _typed = TextEditingController();
  late final Map<String, TextEditingController> _text = {
    for (final f in widget.fields)
      if (f.options == null) f.name: TextEditingController(text: f.initial),
  };
  late final Map<String, String> _choice = {
    for (final f in widget.fields)
      if (f.options != null) f.name: f.initial,
  };

  @override
  void initState() {
    super.initState();
    for (final c in [_reason, _typed]) {
      c.addListener(_changed);
    }
    for (final c in _text.values) {
      c.addListener(_changed);
    }
  }

  @override
  void dispose() {
    _reason.dispose();
    _typed.dispose();
    for (final c in _text.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _changed() => setState(() {});

  String _valueOf(AdminDialogField f) =>
      f.options == null ? _text[f.name]!.text.trim() : _choice[f.name]!;

  String? _fieldError(AdminDialogField f) => f.validator?.call(_valueOf(f));

  bool get _typedOk =>
      widget.requireTyped == null || _typed.text.trim() == widget.requireTyped;

  bool get _reasonOk => _reason.text.trim().length >= kAdminReasonMinLength;

  bool get _valid =>
      _reasonOk &&
      _typedOk &&
      widget.fields.every((f) => _fieldError(f) == null);

  void _submit() {
    if (!_valid) return;
    Navigator.of(context).pop(
      AdminActionInput(
        reason: _reason.text.trim(),
        values: {for (final f in widget.fields) f.name: _valueOf(f)},
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final typedRequired = widget.requireTyped;
    return AlertDialog(
      title: Text(widget.title),
      scrollable: true,
      content: Semantics(
        container: true,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (widget.description != null) ...[
              Text(widget.description!, style: text.bodyMedium),
              const SizedBox(height: 12),
            ],
            for (final f in widget.fields) ...[
              _buildField(f),
              const SizedBox(height: 12),
            ],
            TextField(
              controller: _reason,
              minLines: 1,
              maxLines: 3,
              maxLength: kAdminReasonMaxLength,
              textInputAction: TextInputAction.done,
              onChanged: (_) => _changed(),
              decoration: const InputDecoration(
                labelText: 'Reason (required)',
                hintText: 'Why this action is needed',
                helperText: 'At least $kAdminReasonMinLength characters',
                prefixIcon: Icon(Icons.edit_note),
              ),
            ),
            if (typedRequired != null) ...[
              const SizedBox(height: 12),
              TextField(
                controller: _typed,
                decoration: InputDecoration(
                  labelText: 'Type $typedRequired to confirm',
                  prefixIcon: const Icon(Icons.warning_amber_rounded),
                ),
              ),
            ],
            if (!_valid)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                  _hint(),
                  style: text.bodySmall,
                ),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          style: kAdminButtonStyle,
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          style: kAdminButtonStyle,
          onPressed: _valid ? _submit : null,
          icon: Icon(
            widget.destructive ? Icons.delete_outline : Icons.check,
            size: 18,
          ),
          label: Text(widget.confirmLabel),
        ),
      ],
    );
  }

  Widget _buildField(AdminDialogField f) {
    final options = f.options;
    if (options != null) {
      return DropdownButtonFormField<String>(
        initialValue: _choice[f.name],
        decoration: InputDecoration(labelText: f.label),
        items: [
          for (final o in options)
            DropdownMenuItem(value: o.value, child: Text(o.label)),
        ],
        onChanged: (v) {
          if (v == null) return;
          setState(() => _choice[f.name] = v);
        },
      );
    }
    return TextField(
      controller: _text[f.name],
      keyboardType: f.keyboardType,
      decoration: InputDecoration(
        labelText: f.label,
        errorText: _fieldError(f),
      ),
    );
  }

  String _hint() {
    if (!_reasonOk) {
      return 'Enter a reason of at least $kAdminReasonMinLength characters to continue.';
    }
    if (!_typedOk) return 'Type ${widget.requireTyped} exactly to continue.';
    return 'Fix the highlighted field to continue.';
  }
}
