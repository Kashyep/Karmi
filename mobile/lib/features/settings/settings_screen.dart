import 'package:flutter/material.dart';

import '../../auth/session.dart';
import '../../settings/karmi_settings.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_glass.dart';
import '../../widgets/karmi_card.dart';

/// Settings (T4.3): theme, reduce transparency, licences, sign out.
///
/// The header with the theme control is the one glass surface (§5.1); the rest
/// is opaque content.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({
    super.key,
    required this.settings,
    required this.session,
  });

  final KarmiSettings settings;
  final KarmiSession session;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final colors = KarmiColors.of(context);
    return ListenableBuilder(
      listenable: settings,
      builder: (context, _) => ListView(
        padding: karmiPageInsets(context),
        children: [
          const KarmiHeading('Settings'),
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
                SizedBox(
                  width: double.infinity,
                  child: SegmentedButton<ThemeMode>(
                    showSelectedIcon: false,
                    segments: const [
                      ButtonSegment(
                        value: ThemeMode.system,
                        icon: Icon(Icons.brightness_auto),
                        label: Text('System'),
                      ),
                      ButtonSegment(
                        value: ThemeMode.light,
                        icon: Icon(Icons.light_mode),
                        label: Text('Light'),
                      ),
                      ButtonSegment(
                        value: ThemeMode.dark,
                        icon: Icon(Icons.dark_mode),
                        label: Text('Dark'),
                      ),
                    ],
                    selected: {settings.themeMode},
                    onSelectionChanged: (selection) =>
                        settings.setThemeMode(selection.first),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          KarmiCard(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Column(
              children: [
                SwitchListTile(
                  title: const Text('Reduce transparency'),
                  subtitle: const Text(
                    'Replace glass with solid surfaces. On automatically when '
                    'the system asks for higher contrast.',
                  ),
                  value: settings.reduceTransparency,
                  onChanged: settings.setReduceTransparency,
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.description_outlined),
                  title: const Text('Licences'),
                  subtitle: const Text('Open-source and font licences'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => showLicensePage(
                    context: context,
                    applicationName: 'Karmi',
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          KarmiCard(
            padding: const EdgeInsets.symmetric(vertical: 4),
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
        ],
      ),
    );
  }
}
