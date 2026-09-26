import 'package:flutter/material.dart';

import '../../api/karmi_api.dart';
import '../../auth/session.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_theme.dart';
import '../../widgets/feedback.dart';

/// Welcome / development sign-in (T4.4). Uses `POST /dev/token` only;
/// production auth is out of scope (ADR-0002 Q3).
class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({
    super.key,
    required this.session,
    this.devAuthEnabled = kDevAuthEnabled,
  });

  final KarmiSession session;
  final bool devAuthEnabled;

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen> {
  bool _loading = false;
  KarmiApiException? _error;

  Future<void> _signIn() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await widget.session.signInWithDevToken();
    } on KarmiApiException catch (error) {
      if (mounted) setState(() => _error = error);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final colors = KarmiColors.of(context);
    final expired = widget.session.lastEnd == SessionEnd.expired;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.all(24),
              children: [
                Icon(Icons.eco, size: 48, color: colors.primary),
                const SizedBox(height: 16),
                Semantics(
                  header: true,
                  child: Text('Karmi', style: text.displaySmall),
                ),
                const SizedBox(height: 8),
                Text(
                  'One assistant for your drafts, tasks and notes.',
                  style: KarmiText.of(context).quote,
                ),
                const SizedBox(height: 16),
                Text(
                  'Karmi uses AI. Replies can be wrong, and each one shows its '
                  'status. Your notes are stored on the Karmi server, not on '
                  'this phone.',
                  style: text.bodyMedium?.copyWith(
                    color: colors.mutedForeground,
                  ),
                ),
                const SizedBox(height: 24),
                if (expired && _error == null) ...[
                  const ErrorBanner(
                    icon: Icons.lock_clock,
                    tone: ErrorTone.info,
                    title: 'Session ended',
                    message: 'Your session is no longer valid. Sign in again.',
                  ),
                  const SizedBox(height: 16),
                ],
                if (_error != null) ...[
                  ErrorBanner(
                    icon: _error is NetworkException
                        ? Icons.cloud_off
                        : Icons.error_outline,
                    title: _error is NetworkException
                        ? "Can't reach Karmi"
                        : 'Sign-in unavailable',
                    message: _error is NetworkException
                        ? 'Check your connection and the server address, then retry.'
                        : 'The server did not issue a development session.',
                  ),
                  const SizedBox(height: 16),
                ],
                if (!widget.devAuthEnabled)
                  const ErrorBanner(
                    icon: Icons.info_outline,
                    tone: ErrorTone.info,
                    title: 'Sign-in not available yet',
                    message:
                        'This build has no sign-in method. Production sign-in '
                        'is not implemented.',
                  )
                else if (_loading)
                  const Center(child: KarmiLoader(label: 'Signing in'))
                else
                  FilledButton(
                    onPressed: _signIn,
                    child: Text(
                      _error == null
                          ? 'Continue (development sign-in)'
                          : 'Retry',
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
