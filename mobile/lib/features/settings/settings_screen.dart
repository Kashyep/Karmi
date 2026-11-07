import 'dart:async';

import 'package:flutter/material.dart';

import '../../api/bug_reports/bug_reports_api.dart';
import '../../armory/armory_controller.dart';
import '../../auth/session.dart';
import '../../settings/karmi_settings.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_glass.dart';
import '../../widgets/focus_ring.dart';
import '../../widgets/karmi_card.dart';
import '../admin/admin_code_screen.dart';
import '../admin/admin_controller.dart';
import '../bug_report/bug_report_queue.dart';
import '../bug_report/bug_report_screen.dart';
import '../bug_report/bug_report_service.dart';
import '../bug_report/screenshot_capture.dart';

/// Settings (T4.3): theme mode, tier theme (Armory), reduce transparency,
/// licences, sign out.
///
/// The header with the theme controls is the one glass surface (§5.1); the
/// rest is opaque content.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({
    super.key,
    required this.settings,
    required this.session,
    required this.armory,
    required this.onOpenArmory,
    this.onOpenPlans,
    this.admin,
  });

  final KarmiSettings settings;
  final KarmiSession session;
  final ArmoryController armory;
  final VoidCallback onOpenArmory;
  final VoidCallback? onOpenPlans;
  final AdminController? admin;
  static final GlobalKey _boundaryKey = GlobalKey();

  Future<void> _openBugReport(BuildContext context) async {
    final uid = session.userId;
    if (uid != null && uid.isNotEmpty) {
      unawaited(
        BugReportService(
          api: BugReportsApi.fromApi(session.api),
          queue: BugReportQueue(),
          userId: uid,
        ).flushQueue().catchError((_) => 0),
      );
    }
    final screenshotBytes = await capturePngFromRepaintBoundary(_boundaryKey);
    if (!context.mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => BugReportScreen(
          api: session.api,
          session: session,
          userId: uid,
          initialScreen: 'settings',
          screenshotBytes: screenshotBytes,
        ),
      ),
    );
  }

  void _openAdmin(BuildContext context) {
    final controller = admin;
    if (controller == null) return;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => AdminCodeScreen(controller: controller),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final colors = KarmiColors.of(context);
    return RepaintBoundary(
      key: _boundaryKey,
      child: ListenableBuilder(
        listenable: Listenable.merge([
        settings,
        armory,
        if (admin != null) admin!,
      ]),
      builder: (context, _) => ListView(
        padding: karmiPageInsets(context),
        children: [
          KarmiGlassSurface(
            key: const ValueKey('settings-header'),
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Semantics(
                  header: true,
                  child: Text('Theme', style: text.titleMedium),
                ),
                const SizedBox(height: 12),
                _ThemeModeChoice(
                  selected: settings.themeMode,
                  onSelected: settings.setThemeMode,
                ),
                const SizedBox(height: 16),
                KarmiFocusRing(
                  // Own Material so ink shows on the glass/opaque platter.
                  child: Material(
                    type: MaterialType.transparency,
                    child: ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.palette_outlined),
                      title: const Text('Armory'),
                      subtitle: Text('Tier theme: ${armory.activeTheme.label}'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: onOpenArmory,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          KarmiCard(
            padding: const EdgeInsets.symmetric(vertical: 4),
            semanticContainer: false,
            child: Column(
              children: [
                KarmiFocusRing(
                  child: SwitchListTile(
                    title: const Text('Reduce transparency'),
                    subtitle: const Text(
                      'Replace glass with solid surfaces. On automatically when '
                      'the system asks for higher contrast.',
                    ),
                    value: settings.reduceTransparency,
                    onChanged: settings.setReduceTransparency,
                  ),
                ),
                if (onOpenPlans != null) ...[
                  const Divider(height: 1),
                  KarmiFocusRing(
                    child: ListTile(
                      leading: const Icon(Icons.vpn_key_outlined),
                      title: const Text('Plans and access code'),
                      subtitle: const Text('Unlock a beta tier with a code'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: onOpenPlans,
                    ),
                  ),
                ],
                if (admin?.canEnter ?? false) ...[
                  const Divider(height: 1),
                  KarmiFocusRing(
                    child: ListTile(
                      key: const ValueKey('admin_console_tile'),
                      leading: const Icon(Icons.admin_panel_settings_outlined),
                      title: const Text('Admin console'),
                      subtitle: const Text('Users, monitor and audit'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => _openAdmin(context),
                    ),
                  ),
                ],
                const Divider(height: 1),
                KarmiFocusRing(
                  child: ListTile(
                    key: const ValueKey('report_bug_tile'),
                    leading: const Icon(Icons.bug_report_outlined),
                    title: const Text('Report a bug'),
                    subtitle: const Text('Send diagnostics or report an issue'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => _openBugReport(context),
                  ),
                ),
                const Divider(height: 1),
                KarmiFocusRing(
                  child: ListTile(
                    leading: const Icon(Icons.description_outlined),
                    title: const Text('Licences'),
                    subtitle: const Text('Open-source and font licences'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => showLicensePage(
                      context: context,
                      applicationName: 'Karmi',
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          KarmiCard(
            padding: const EdgeInsets.symmetric(vertical: 4),
            semanticContainer: false,
            child: KarmiFocusRing(
              child: ListTile(
                leading: Icon(Icons.logout, color: colors.destructive),
                title: Text(
                  'Sign out',
                  style: text.bodyLarge?.copyWith(color: colors.destructive),
                ),
                subtitle: const Text('Removes the session from this device'),
                onTap: session.signOut,
              ),
            ),
          ),
        ],
      ),
      ),
    );
  }
}

/// System / Light / Dark as three separate buttons, so keyboard focus rings
/// one choice at a time (a SegmentedButton shares one outline across its
/// segments, which hid which segment had focus on device).
class _ThemeModeChoice extends StatelessWidget {
  const _ThemeModeChoice({required this.selected, required this.onSelected});

  final ThemeMode selected;
  final ValueChanged<ThemeMode> onSelected;

  static const _options = [
    (ThemeMode.system, Icons.brightness_auto, 'System'),
    (ThemeMode.light, Icons.light_mode, 'Light'),
    (ThemeMode.dark, Icons.dark_mode, 'Dark'),
  ];

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final (mode, icon, label) in _options)
          OutlinedButton.icon(
            style: mode == selected
                ? OutlinedButton.styleFrom(
                    backgroundColor: colors.secondary,
                    foregroundColor: colors.secondaryForeground,
                  )
                : null,
            onPressed: () => onSelected(mode),
            icon: Icon(icon),
            // Inside the button so the state merges into the button's node.
            label: Semantics(
              selected: mode == selected,
              inMutuallyExclusiveGroup: true,
              child: Text(label),
            ),
          ),
      ],
    );
  }
}
