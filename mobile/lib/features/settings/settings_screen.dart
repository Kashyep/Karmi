import 'package:flutter/material.dart';

import '../../auth/session.dart';
import '../../settings/karmi_settings.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_glass.dart';
import '../../widgets/focus_ring.dart';
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
                _ThemeModeChoice(
                  selected: settings.themeMode,
                  onSelected: settings.setThemeMode,
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
