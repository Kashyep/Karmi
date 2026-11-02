import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../theme/karmi_colors.dart';
import '../../widgets/feedback.dart';
import '../../widgets/karmi_card.dart';
import 'admin_action_dialog.dart';
import 'admin_api.dart';
import 'admin_controller.dart';
import 'admin_support.dart';

/// Profile, usage and admin actions for one user. Every mutation goes
/// through [showAdminActionDialog] so a reason is always recorded. Pops with
/// `true` when the user list needs a refresh.
class UserDetailScreen extends StatefulWidget {
  const UserDetailScreen({
    super.key,
    required this.controller,
    required this.userId,
  });

  final AdminController controller;
  final String userId;

  @override
  State<UserDetailScreen> createState() => _UserDetailScreenState();
}

class _UserDetailScreenState extends State<UserDetailScreen> {
  AdminUserDetail? _detail;
  Object? _loadError;
  bool _loading = false;
  bool _busy = false;
  bool _changed = false;
  String? _notice;
  Object? _noticeError;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final detail = await runAdminCall(
        widget.controller,
        (api, token) => api.getUser(token, widget.userId),
      );
      if (!mounted) return;
      setState(() => _detail = detail);
    } on AdminException catch (e) {
      // Keep the last good detail on screen; surface the failure beside it.
      if (mounted) setState(() => _loadError = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Confirm, run [call], then refresh. Success and failure both show inline.
  Future<void> _act({
    required String title,
    required String confirmLabel,
    required String success,
    required Future<void> Function(
      AdminApi api,
      String token,
      AdminActionInput input,
    )
    call,
    String? description,
    List<AdminDialogField> fields = const [],
    String? requireTyped,
    bool destructive = false,
    bool deletesUser = false,
  }) async {
    final input = await showAdminActionDialog(
      context,
      title: title,
      confirmLabel: confirmLabel,
      description: description,
      fields: fields,
      requireTyped: requireTyped,
      destructive: destructive,
    );
    if (input == null || !mounted) return;
    setState(() {
      _busy = true;
      _notice = null;
      _noticeError = null;
    });
    try {
      await runAdminCall(
        widget.controller,
        (api, token) => call(api, token, input),
      );
      if (!mounted) return;
      _changed = true;
      if (deletesUser) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(success)));
        Navigator.of(context).pop(true);
        return;
      }
      setState(() => _notice = success);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(success)));
      await _load();
    } on AdminException catch (e) {
      if (mounted) setState(() => _noticeError = e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _export() async {
    final input = await showAdminActionDialog(
      context,
      title: 'Export user data',
      confirmLabel: 'Export',
      description: 'The export is recorded in the audit log with this reason.',
    );
    if (input == null || !mounted) return;
    setState(() {
      _busy = true;
      _notice = null;
      _noticeError = null;
    });
    try {
      final json = await runAdminCall(
        widget.controller,
        (api, token) =>
            api.exportUser(token, widget.userId, reason: input.reason),
      );
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => _ExportDialog(json: json),
      );
    } on AdminException catch (e) {
      if (mounted) setState(() => _noticeError = e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop && mounted) Navigator.of(context).pop(_changed);
      },
      child: Scaffold(
        appBar: AppBar(
          title: Text(
            detail?.user.displayName.isNotEmpty == true
                ? detail!.user.displayName
                : 'User',
          ),
        ),
        body: detail == null
            ? _loadingOrError()
            : ListView(
                padding: kAdminPagePadding,
                children: [
                  if (_loadError != null) ...[
                    _errorBanner(_loadError!, 'Could not refresh this user'),
                    const SizedBox(height: 12),
                  ],
                  _profile(detail),
                  const SizedBox(height: 12),
                  _planCard(detail.user),
                  const SizedBox(height: 12),
                  _usage(detail.usage),
                  _actions(detail.user),
                  if (_notice != null) ...[
                    const SizedBox(height: 12),
                    _successLine(_notice!),
                  ],
                  if (_noticeError != null) ...[
                    const SizedBox(height: 12),
                    _errorBanner(_noticeError!, 'Action failed'),
                  ],
                ],
              ),
      ),
    );
  }

  Widget _loadingOrError() {
    if (_loadError != null) {
      return Padding(
        padding: kAdminPagePadding,
        child: _errorBanner(_loadError!, "Couldn't load user"),
      );
    }
    return const Center(child: KarmiLoader(label: 'Loading user'));
  }

  Widget _errorBanner(Object error, String title) {
    return ErrorBanner(
      icon: Icons.error_outline,
      title: title,
      message: adminErrorMessage(error),
      actionLabel: 'Retry',
      onAction: _loading || _busy ? null : _load,
    );
  }

  Widget _successLine(String message) {
    final colors = KarmiColors.of(context);
    return Semantics(
      liveRegion: true,
      child: Row(
        children: [
          Icon(Icons.check_circle_outline, color: colors.success, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(message, style: Theme.of(context).textTheme.bodyMedium),
          ),
        ],
      ),
    );
  }

  Widget _profile(AdminUserDetail detail) {
    final text = Theme.of(context).textTheme;
    final user = detail.user;
    return KarmiCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Profile', style: text.titleMedium),
          const SizedBox(height: 8),
          _row(
            'Name',
            user.displayName.isEmpty ? kAdminUnavailable : user.displayName,
          ),
          _row('Tier', user.tier),
          _row('Status', user.disabled ? 'Suspended' : 'Active'),
          _row('Tester', user.tester ? 'Yes' : 'No'),
          _row('Tester label', user.testerLabel ?? kAdminUnavailable),
          _row('Admin notes', user.adminNotes ?? kAdminUnavailable),
          const SizedBox(height: 8),
          _actionButton(
            icon: Icons.edit_outlined,
            label: 'Edit profile',
            onPressed: () => _act(
              title: 'Edit user',
              confirmLabel: 'Save',
              success: 'User updated.',
              fields: [
                AdminDialogField(
                  name: 'display_name',
                  label: 'Display name',
                  initial: user.displayName,
                ),
                AdminDialogField(
                  name: 'tester',
                  label: 'Tester (yes/no)',
                  initial: user.tester ? 'yes' : 'no',
                ),
                AdminDialogField(
                  name: 'tester_label',
                  label: 'Tester label',
                  initial: user.testerLabel ?? '',
                ),
                AdminDialogField(
                  name: 'admin_notes',
                  label: 'Admin notes',
                  initial: user.adminNotes ?? '',
                ),
              ],
              call: (api, token, input) => api.editUser(
                token,
                user.id,
                displayName: input['display_name'],
                tester: input['tester']?.toLowerCase() == 'yes',
                testerLabel: input['tester_label'],
                adminNotes: input['admin_notes'],
                reason: input.reason,
              ),
            ),
          ),
          _row(
            'Created',
            user.createdAt == null
                ? kAdminUnavailable
                : formatAdminDateTime(context, user.createdAt),
          ),
          _row(
            'Last active',
            user.lastActiveAt == null
                ? kAdminUnavailable
                : formatAdminDateTime(context, user.lastActiveAt),
          ),
        ],
      ),
    );
  }

  Widget _planCard(AdminUser user) {
    final index = kAdminTiers.indexOf(user.tier);
    return KarmiCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Plan', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          _row('Effective plan', user.effectivePlan ?? user.tier),
          _row(
            'Expires',
            user.planExpiresAt == null
                ? kAdminUnavailable
                : formatAdminDateTime(context, user.planExpiresAt),
          ),
          _row('Reverts to', user.revertPlanId ?? kAdminUnavailable),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              if (index >= 0 && index < kAdminTiers.length - 1)
                _actionButton(
                  icon: Icons.arrow_upward,
                  label: 'Promote',
                  onPressed: () => _changePlan(user, kAdminTiers[index + 1]),
                ),
              if (index > 0)
                _actionButton(
                  icon: Icons.arrow_downward,
                  label: 'Demote',
                  onPressed: () => _changePlan(user, kAdminTiers[index - 1]),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _changePlan(AdminUser user, String target) => _act(
    title: 'Set plan',
    confirmLabel: 'Set plan',
    success: 'Plan updated.',
    fields: [
      AdminDialogField(
        name: 'tier',
        label: 'Plan',
        initial: target,
        options: [
          for (final tier in kAdminTiers)
            AdminDialogOption(tier, adminTierLabel(tier)),
        ],
      ),
      const AdminDialogField(
        name: 'expires_at',
        label: 'Expiry (ISO date, optional)',
      ),
    ],
    call: (api, token, input) => api.changeTier(
      token,
      user.id,
      tier: input['tier']!,
      reason: input.reason,
      expiresAt: DateTime.tryParse(input['expires_at'] ?? ''),
    ),
  );

  Widget _usage(AdminUsage usage) {
    final text = Theme.of(context).textTheme;
    return KarmiCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Usage', style: text.titleMedium),
          const SizedBox(height: 8),
          _row(
            'Requests today',
            usage.todayRequests?.toString() ?? kAdminUnavailable,
          ),
          _row(
            'Spend this month',
            usage.monthSpendUsd == null
                ? kAdminUnavailable
                : formatUsd(usage.monthSpendUsd!),
          ),
          _row(
            'Credits remaining',
            usage.creditsRemaining == null
                ? kAdminUnavailable
                : formatUsd(usage.creditsRemaining!),
          ),
          _row(
            'Active sessions',
            usage.sessions?.toString() ?? kAdminUnavailable,
          ),
        ],
      ),
    );
  }

  Widget _row(String label, String value) {
    final text = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Semantics(
        label: '$label: $value',
        excludeSemantics: true,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(flex: 2, child: Text(label, style: text.bodyMedium)),
            const SizedBox(width: 8),
            Expanded(
              flex: 3,
              child: Text(
                value,
                style: text.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _actions(AdminUser user) {
    final id = user.id;
    return KarmiCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Actions', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (user.disabled)
                _actionButton(
                  icon: Icons.lock_open,
                  label: 'Unsuspend',
                  onPressed: () => _act(
                    title: 'Unsuspend user',
                    confirmLabel: 'Unsuspend',
                    success: 'User unsuspended.',
                    call: (api, token, input) =>
                        api.unsuspend(token, id, reason: input.reason),
                  ),
                )
              else
                _actionButton(
                  icon: Icons.block,
                  label: 'Suspend',
                  destructive: true,
                  onPressed: () => _act(
                    title: 'Suspend user',
                    confirmLabel: 'Suspend',
                    success: 'User suspended.',
                    destructive: true,
                    call: (api, token, input) =>
                        api.suspend(token, id, reason: input.reason),
                  ),
                ),
              _actionButton(
                icon: Icons.logout,
                label: 'Revoke sessions',
                onPressed: () => _act(
                  title: 'Revoke sessions',
                  confirmLabel: 'Revoke',
                  success: 'Sessions revoked.',
                  call: (api, token, input) =>
                      api.revokeSessions(token, id, reason: input.reason),
                ),
              ),
              _actionButton(
                icon: Icons.workspace_premium_outlined,
                label: 'Change tier',
                onPressed: () => _act(
                  title: 'Change tier',
                  confirmLabel: 'Change tier',
                  success: 'Tier updated.',
                  fields: [
                    AdminDialogField(
                      name: 'tier',
                      label: 'New tier',
                      initial: kAdminTiers.contains(user.tier)
                          ? user.tier
                          : kAdminTiers.first,
                      options: [
                        for (final t in kAdminTiers)
                          AdminDialogOption(t, adminTierLabel(t)),
                      ],
                    ),
                  ],
                  call: (api, token, input) => api.changeTier(
                    token,
                    id,
                    tier: input['tier']!,
                    reason: input.reason,
                    expiresAt:
                        input['expires_at'] == null ||
                            input['expires_at']!.isEmpty
                        ? null
                        : DateTime.tryParse(input['expires_at']!),
                  ),
                ),
              ),
              _actionButton(
                icon: Icons.account_balance_wallet_outlined,
                label: 'Adjust credits',
                onPressed: () => _act(
                  title: 'Adjust credits',
                  confirmLabel: 'Apply',
                  success: 'Credits adjusted.',
                  fields: [
                    const AdminDialogField(
                      name: 'mode',
                      label: 'Adjustment',
                      initial: 'delta',
                      options: [
                        AdminDialogOption('delta', 'Add or remove (delta USD)'),
                        AdminDialogOption('budget', 'Set budget (USD)'),
                      ],
                    ),
                    AdminDialogField(
                      name: 'amount',
                      label: 'Amount in USD',
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                        signed: true,
                      ),
                      validator: (v) =>
                          double.tryParse(v) == null ? 'Enter a number' : null,
                    ),
                  ],
                  call: (api, token, input) {
                    final amount = double.parse(input['amount']!);
                    final isBudget = input['mode'] == 'budget';
                    return api.adjustCredits(
                      token,
                      id,
                      deltaUsd: isBudget ? null : amount,
                      budgetUsd: isBudget ? amount : null,
                      reason: input.reason,
                    );
                  },
                ),
              ),
              _actionButton(
                icon: Icons.file_download_outlined,
                label: 'Export',
                onPressed: _export,
              ),
              _actionButton(
                icon: Icons.delete_outline,
                label: 'Delete user',
                destructive: true,
                onPressed: () => _act(
                  title: 'Delete user',
                  confirmLabel: 'Delete',
                  success: 'User deleted.',
                  description: 'This cannot be undone.',
                  requireTyped: 'DELETE',
                  destructive: true,
                  deletesUser: true,
                  call: (api, token, input) =>
                      api.deleteUser(token, id, reason: input.reason),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _actionButton({
    required IconData icon,
    required String label,
    required VoidCallback onPressed,
    bool destructive = false,
  }) {
    final enabled = !_busy && !_loading;
    final colors = KarmiColors.of(context);
    final style = kAdminButtonStyle.copyWith(
      foregroundColor: destructive
          ? WidgetStatePropertyAll(colors.destructive)
          : null,
    );
    return OutlinedButton.icon(
      style: style,
      onPressed: enabled ? onPressed : null,
      icon: Icon(icon, size: 18),
      label: Text(label),
    );
  }
}

class _ExportDialog extends StatelessWidget {
  const _ExportDialog({required this.json});

  final String json;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Export'),
      scrollable: true,
      content: SizedBox(
        width: double.maxFinite,
        height: 360,
        child: SingleChildScrollView(
          child: SelectableText(
            json,
            style: const TextStyle(fontFamily: 'monospace'),
          ),
        ),
      ),
      actions: [
        TextButton(
          style: kAdminButtonStyle,
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
        FilledButton.icon(
          style: kAdminButtonStyle,
          icon: const Icon(Icons.copy, size: 18),
          label: const Text('Copy'),
          onPressed: () async {
            await Clipboard.setData(ClipboardData(text: json));
            if (!context.mounted) return;
            ScaffoldMessenger.maybeOf(context)?.showSnackBar(
              const SnackBar(content: Text('Copied to clipboard.')),
            );
          },
        ),
      ],
    );
  }
}
