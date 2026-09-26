import 'package:flutter/material.dart';

import '../../api/karmi_api.dart';
import '../../theme/karmi_colors.dart';
import '../../widgets/feedback.dart';
import '../../widgets/karmi_card.dart';

/// Memory (T4.2): saved notes via `GET/POST/DELETE /v1/notes`.
class MemoryScreen extends StatefulWidget {
  const MemoryScreen({super.key, required this.api});

  final KarmiApi api;

  @override
  State<MemoryScreen> createState() => _MemoryScreenState();
}

class _MemoryScreenState extends State<MemoryScreen> {
  final _input = TextEditingController();
  List<NoteView>? _notes;
  bool _loading = true;
  bool _loadFailed = false;
  bool _saving = false;
  String? _pendingKey;
  String? _actionError;
  bool _deleted = false;
  final Set<String> _deleting = {};

  @override
  void initState() {
    super.initState();
    _input.addListener(() => setState(() {}));
    _load();
  }

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadFailed = false;
    });
    try {
      final notes = await widget.api.listNotes();
      if (mounted) setState(() => _notes = notes);
    } on KarmiApiException {
      if (mounted) setState(() => _loadFailed = true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _add() async {
    final content = _input.text.trim();
    if (content.isEmpty || _saving) return;
    // A retry of the same unsaved text reuses its idempotency key.
    _pendingKey ??= KarmiApi.newIdempotencyKey();
    setState(() {
      _saving = true;
      _actionError = null;
      _deleted = false;
    });
    try {
      final note = await widget.api.createNote(
        content,
        idempotencyKey: _pendingKey!,
      );
      if (!mounted) return;
      setState(() {
        _notes = [...?_notes, note];
        _pendingKey = null;
        _input.clear();
      });
    } on KarmiApiException {
      if (mounted) {
        setState(() => _actionError = 'The note was not saved. Try again.');
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _confirmDelete(NoteView note) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this note?'),
        content: Text(
          'Karmi will stop using "${_preview(note.content)}" as context. '
          'This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: KarmiColors.of(context).destructive,
              foregroundColor: KarmiColors.of(context).destructiveForeground,
            ),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _deleting.add(note.id);
      _actionError = null;
      _deleted = false;
    });
    try {
      await widget.api.deleteNote(note.id);
      if (!mounted) return;
      setState(() {
        _notes = [...?_notes?.where((n) => n.id != note.id)];
        _deleted = true;
      });
    } on KarmiApiException {
      if (mounted) {
        setState(() => _actionError = 'The note was not deleted. Try again.');
      }
    } finally {
      if (mounted) setState(() => _deleting.remove(note.id));
    }
  }

  static String _preview(String text) =>
      text.length <= 60 ? text : '${text.substring(0, 57)}...';

  @override
  Widget build(BuildContext context) {
    final notes = _notes;
    final text = Theme.of(context).textTheme;
    final colors = KarmiColors.of(context);
    return RefreshIndicator(
      onRefresh: _load,
      edgeOffset: MediaQuery.paddingOf(context).top,
      child: ListView(
        padding: karmiPageInsets(context),
        children: [
          const KarmiHeading('Memory'),
          Text(
            'Notes Karmi may use as context for your replies.',
            style: text.bodyMedium?.copyWith(color: colors.mutedForeground),
          ),
          const SizedBox(height: 16),
          KarmiCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  controller: _input,
                  minLines: 1,
                  maxLines: 4,
                  enabled: !_saving,
                  decoration: const InputDecoration(labelText: 'New note'),
                  onChanged: (_) => _pendingKey = null,
                ),
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerRight,
                  child: _saving
                      ? const KarmiLoader(label: 'Saving note')
                      : FilledButton.icon(
                          onPressed: _input.text.trim().isEmpty ? null : _add,
                          icon: const Icon(Icons.add),
                          label: const Text('Add note'),
                        ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          if (_deleted) ...[
            const ErrorBanner(
              icon: Icons.check_circle_outline,
              tone: ErrorTone.info,
              title: 'Note deleted',
              message: 'Karmi will no longer use it as context.',
            ),
            const SizedBox(height: 12),
          ],
          if (_actionError != null) ...[
            ErrorBanner(title: 'Something went wrong', message: _actionError!),
            const SizedBox(height: 12),
          ],
          if (_loading && notes == null)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Center(child: KarmiLoader(label: 'Loading notes')),
            )
          else if (_loadFailed && notes == null)
            ErrorBanner(
              icon: Icons.cloud_off,
              tone: ErrorTone.warning,
              title: 'Notes unavailable',
              message: "Karmi couldn't load your notes right now.",
              actionLabel: 'Retry',
              onAction: _load,
            )
          else if (notes == null || notes.isEmpty)
            const EmptyState(
              icon: Icons.bookmark_border,
              quote: 'Nothing saved yet.',
              body:
                  'Add a note above, or ask Karmi in Chat to remember something.',
            )
          else
            for (final note in notes) ...[
              _NoteTile(
                note: note,
                deleting: _deleting.contains(note.id),
                onDelete: () => _confirmDelete(note),
              ),
              const SizedBox(height: 12),
            ],
        ],
      ),
    );
  }
}

class _NoteTile extends StatelessWidget {
  const _NoteTile({
    required this.note,
    required this.deleting,
    required this.onDelete,
  });

  final NoteView note;
  final bool deleting;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    return KarmiCard(
      padding: const EdgeInsets.fromLTRB(16, 8, 4, 8),
      child: Row(
        children: [
          Expanded(
            child: Text(
              note.content,
              style: Theme.of(context).textTheme.bodyLarge,
            ),
          ),
          deleting
              ? const Padding(
                  padding: EdgeInsets.all(12),
                  child: KarmiLoader(label: 'Deleting'),
                )
              : IconButton(
                  tooltip: 'Delete note',
                  onPressed: onDelete,
                  icon: Icon(
                    Icons.delete_outline,
                    color: KarmiColors.of(context).destructive,
                  ),
                ),
        ],
      ),
    );
  }
}
