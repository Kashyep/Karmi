import 'package:flutter/material.dart';

import '../../theme/karmi_colors.dart';
import '../../widgets/karmi_card.dart';
import 'admin_api.dart';
import 'admin_controller.dart';

/// Admin code entry. Wrong codes get one generic message; lockout reports the
/// wait in minutes. A 403 means the account is not an admin, so this screen
/// closes and the entry point disappears from Settings.
class AdminCodeScreen extends StatefulWidget {
  const AdminCodeScreen({super.key, required this.controller});

  final AdminController controller;

  @override
  State<AdminCodeScreen> createState() => _AdminCodeScreenState();
}

class _AdminCodeScreenState extends State<AdminCodeScreen> {
  final _code = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final code = _code.text.trim();
    if (code.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.controller.verifyCode(code);
      // Success: home switches to the admin shell, so drop Settings and this
      // screen from the stack.
      if (mounted) Navigator.of(context).popUntil((route) => route.isFirst);
      return;
    } on AdminForbidden {
      if (!mounted) return;
      Navigator.of(context).maybePop();
      return;
    } on AdminLockedOut catch (e) {
      _fail(_lockedOutMessage(e.retryAfter));
    } on AdminUnauthorized {
      _fail('Code not accepted. Check the code and try again.');
    } on AdminException {
      _fail('Could not check the code. Try again.');
    }
  }

  void _fail(String message) {
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = message;
    });
  }

  static String _lockedOutMessage(Duration retryAfter) {
    if (retryAfter <= Duration.zero) {
      return 'Too many attempts. Try again later.';
    }
    final minutes = (retryAfter.inSeconds / 60).ceil();
    final unit = minutes == 1 ? 'minute' : 'minutes';
    return 'Too many attempts. Try again in $minutes $unit.';
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final colors = KarmiColors.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Admin console')),
      body: ListView(
        padding: karmiPageInsets(context),
        children: [
          Text('Enter your admin access code', style: text.titleMedium),
          const SizedBox(height: 12),
          TextField(
            key: const ValueKey('admin_code_field'),
            controller: _code,
            obscureText: true,
            enableSuggestions: false,
            autocorrect: false,
            enabled: !_busy,
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => _submit(),
            decoration: const InputDecoration(
              labelText: 'Access code',
              border: OutlineInputBorder(),
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Semantics(
              liveRegion: true,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.error_outline, color: colors.destructive),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _error!,
                      key: const ValueKey('admin_code_error'),
                      style: text.bodyMedium?.copyWith(
                        color: colors.destructive,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 16),
          FilledButton(
            style: FilledButton.styleFrom(
              minimumSize: const Size(48, 48),
            ),
            onPressed: _busy ? null : _submit,
            child: _busy
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Continue'),
          ),
        ],
      ),
    );
  }
}
