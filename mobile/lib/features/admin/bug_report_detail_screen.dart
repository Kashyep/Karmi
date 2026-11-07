import 'package:flutter/material.dart';

import '../../widgets/feedback.dart';
import '../../widgets/karmi_card.dart';
import 'admin_action_dialog.dart';
import 'admin_api.dart';
import 'admin_controller.dart';
import 'admin_support.dart';

/// Full details of a bug report and admin actions (status transitions, notes).
class BugReportDetailScreen extends StatefulWidget {
  const BugReportDetailScreen({
    super.key,
    required this.controller,
    required this.reportId,
  });

  final AdminController controller;
  final String reportId;

  @override
  State<BugReportDetailScreen> createState() => _BugReportDetailScreenState();
}

class _BugReportDetailScreenState extends State<BugReportDetailScreen> {
  AdminBugReportDetail? _detail;
  Object? _error;
  bool _loading = false;
  bool _busy = false;
  bool _changed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final detail = await runAdminCall(
        widget.controller,
        (api, token) => api.getBugReport(token, widget.reportId),
      );
      if (!mounted) return;
      setState(() => _detail = detail);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _act(
    Future<void> Function(AdminApi api, String token, AdminActionInput input)
    call, {
    required String title,
    required String confirmLabel,
    required List<AdminDialogField> fields,
    String? success,
  }) async {
    final input = await showAdminActionDialog(
      context,
      title: title,
      confirmLabel: confirmLabel,
      fields: fields,
    );
    if (input == null || !mounted) return;

    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await runAdminCall(
        widget.controller,
        (api, token) => call(api, token, input),
      );
      if (!mounted) return;
      _changed = true;
      if (success != null) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(success)));
      }
      await _load();
    } on AdminException catch (e) {
      if (!mounted) return;
      setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _updateStatus() async {
    final detail = _detail;
    if (detail == null) return;
    final allowed = kAllowedBugReportTransitions[detail.status] ?? const {};
    if (allowed.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No further transitions available.')),
      );
      return;
    }

    await _act(
      (api, token, input) async {
        final newStatus = input['status'];
        final notesInput = input['admin_notes']?.trim();
        final currentNotes = (detail.adminNotes ?? '').trim();
        final notesChanged = notesInput != currentNotes;
        final statusChanged = newStatus != null && newStatus != detail.status;

        await api.patchBugReport(
          token,
          detail.id,
          status: statusChanged ? newStatus : null,
          adminNotes: notesChanged ? (notesInput ?? '') : null,
          reason: input.reason,
        );
      },
      title: 'Update status',
      confirmLabel: 'Update',
      fields: [
        AdminDialogField(
          name: 'status',
          label: 'New status',
          initial: allowed.first,
          options: [
            for (final s in allowed)
              AdminDialogOption(s, bugReportStatusLabel(s)),
          ],
        ),
        AdminDialogField(
          name: 'admin_notes',
          label: 'Admin notes (optional, max 4000)',
          initial: detail.adminNotes ?? '',
          validator: (v) => v.length > 4000 ? 'Maximum 4000 characters' : null,
        ),
      ],
      success: 'Status updated.',
    );
  }

  Future<void> _editNotes() async {
    final detail = _detail;
    if (detail == null) return;

    await _act(
      (api, token, input) async {
        final notes = input['admin_notes'] ?? '';
        await api.patchBugReport(
          token,
          detail.id,
          adminNotes: notes,
          reason: input.reason,
        );
      },
      title: 'Edit admin notes',
      confirmLabel: 'Save notes',
      fields: [
        AdminDialogField(
          name: 'admin_notes',
          label: 'Admin notes (max 4000)',
          initial: detail.adminNotes ?? '',
          validator: (v) => v.length > 4000 ? 'Maximum 4000 characters' : null,
        ),
      ],
      success: 'Admin notes updated.',
    );
  }

  Future<void> _viewScreenshot() async {
    setState(() => _busy = true);
    try {
      final bytes = await runAdminCall(
        widget.controller,
        (api, token) => api.getBugReportScreenshot(token, widget.reportId),
      );
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Screenshot'),
          content: InteractiveViewer(child: Image.memory(bytes)),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('Close'),
            ),
          ],
        ),
      );
    } on AdminException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(adminErrorMessage(e))));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Screenshot not found.')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _row(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 140,
            child: Text(
              label,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }

  Widget _actionButton({
    required IconData icon,
    required String label,
    required VoidCallback onPressed,
  }) {
    return FilledButton.tonalIcon(
      icon: Icon(icon, size: 18),
      label: Text(label),
      onPressed: _busy ? null : onPressed,
    );
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    final text = Theme.of(context).textTheme;

    return PopScope(
      canPop: !_busy,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop && _changed) {
          // Parent inbox will reload on pop
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: Text(detail?.ticket ?? 'Bug Report'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: () => Navigator.of(context).pop(_changed),
          ),
          actions: [
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: _busy || _loading ? null : _load,
            ),
          ],
        ),
        body: _loading && detail == null
            ? const Center(child: KarmiLoader(label: 'Loading bug report'))
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  if (_error != null) ...[
                    ErrorBanner(
                      title: "Couldn't load bug report",
                      message: adminErrorMessage(_error!),
                      actionLabel: 'Retry',
                      onAction: _load,
                    ),
                    const SizedBox(height: 12),
                  ],
                  if (detail != null) ...[
                    // Status, Category, and Action header
                    KarmiCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(detail.ticket, style: text.headlineSmall),
                              Chip(
                                label: Text(
                                  bugReportStatusLabel(detail.status),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'Category: ${bugReportCategoryLabel(detail.category)}',
                            style: text.bodyLarge,
                          ),
                          const SizedBox(height: 16),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              _actionButton(
                                icon: Icons.update,
                                label: 'Update status',
                                onPressed: _updateStatus,
                              ),
                              _actionButton(
                                icon: Icons.note_alt_outlined,
                                label: 'Edit notes',
                                onPressed: _editNotes,
                              ),
                              if (detail.hasScreenshot)
                                _actionButton(
                                  icon: Icons.image_outlined,
                                  label: 'View screenshot',
                                  onPressed: _viewScreenshot,
                                ),
                            ],
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Description
                    KarmiCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Description', style: text.titleMedium),
                          const SizedBox(height: 8),
                          SelectableText(
                            detail.description,
                            style: text.bodyMedium,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),

                    // User Summary
                    KarmiCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('User Summary', style: text.titleMedium),
                          const SizedBox(height: 8),
                          _row('User ID', detail.user?.id ?? kAdminUnavailable),
                          _row(
                            'Display Name',
                            detail.user?.displayName.isNotEmpty == true
                                ? detail.user!.displayName
                                : kAdminUnavailable,
                          ),
                          _row(
                            'Plan',
                            detail.user?.plan != null &&
                                    detail.user!.plan!.isNotEmpty
                                ? adminTierLabel(detail.user!.plan!)
                                : kAdminUnavailable,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Diagnostics Table
                    KarmiCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Diagnostics', style: text.titleMedium),
                          const SizedBox(height: 8),
                          if (detail.diagnostics.isEmpty)
                            Text(
                              'No diagnostics reported.',
                              style: text.bodyMedium,
                            )
                          else
                            Table(
                              border: TableBorder.all(
                                color: Theme.of(
                                  context,
                                ).colorScheme.outlineVariant,
                                width: 0.5,
                              ),
                              columnWidths: const {
                                0: IntrinsicColumnWidth(),
                                1: FlexColumnWidth(),
                              },
                              children: [
                                for (final e in detail.diagnostics.entries)
                                  TableRow(
                                    children: [
                                      Padding(
                                        padding: const EdgeInsets.all(8),
                                        child: Text(
                                          e.key,
                                          style: text.labelMedium?.copyWith(
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                      ),
                                      Padding(
                                        padding: const EdgeInsets.all(8),
                                        child: SelectableText(
                                          '${e.value}',
                                          style: text.bodyMedium,
                                        ),
                                      ),
                                    ],
                                  ),
                              ],
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Admin Notes
                    KarmiCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Admin Notes', style: text.titleMedium),
                          const SizedBox(height: 8),
                          SelectableText(
                            detail.adminNotes != null &&
                                    detail.adminNotes!.isNotEmpty
                                ? detail.adminNotes!
                                : 'None',
                            style: text.bodyMedium,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Timestamps
                    KarmiCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Timestamps', style: text.titleMedium),
                          const SizedBox(height: 8),
                          _row(
                            'Created',
                            formatAdminDateTime(context, detail.createdAt),
                          ),
                          _row(
                            'Updated',
                            formatAdminDateTime(context, detail.updatedAt),
                          ),
                          _row(
                            'Triaged',
                            formatAdminDateTime(context, detail.triagedAt),
                          ),
                          _row(
                            'Resolved',
                            formatAdminDateTime(context, detail.resolvedAt),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
      ),
    );
  }
}
