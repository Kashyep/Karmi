import 'package:flutter/material.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_glass.dart';
import '../../theme/karmi_motion.dart';

class SettingsScreen extends StatelessWidget {
  final KarmiSettingsProvider settingsProvider;

  const SettingsScreen({super.key, required this.settingsProvider});

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).extension<KarmiColors>()!;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          'Settings',
          style: Theme.of(context).textTheme.displaySmall,
        ),
        const SizedBox(height: 24),
        KarmiGlassContainer(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Display',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 16),
              ListenableBuilder(
                listenable: settingsProvider,
                builder: (context, _) {
                  return Column(
                    children: [
                      SwitchListTile(
                        title: const Text('Reduce Transparency'),
                        subtitle: const Text(
                            'Disables glass effects and increases contrast'),
                        value: settingsProvider.reduceTransparency,
                        onChanged: (val) {
                          settingsProvider.setReduceTransparency(val);
                        },
                        activeThumbColor: colors.primary,
                      ),
                      const Divider(),
                      ListTile(
                        title: const Text('Theme'),
                        trailing: SegmentedButton<ThemeMode>(
                          segments: const [
                            ButtonSegment(
                                value: ThemeMode.light,
                                icon: Icon(Icons.light_mode)),
                            ButtonSegment(
                                value: ThemeMode.dark,
                                icon: Icon(Icons.dark_mode)),
                            ButtonSegment(
                                value: ThemeMode.system,
                                icon: Icon(Icons.brightness_auto)),
                          ],
                          selected: {settingsProvider.themeMode},
                          onSelectionChanged: (Set<ThemeMode> newSelection) {
                            settingsProvider.setThemeMode(newSelection.first);
                          },
                        ),
                      ),
                    ],
                  );
                },
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        KarmiGlassContainer(
          padding: const EdgeInsets.all(16),
          child: ListTile(
            leading: Icon(Icons.logout, color: colors.destructive),
            title: Text(
              'Sign Out',
              style: TextStyle(color: colors.destructive),
            ),
            onTap: () {
              // Sign out logic
            },
          ),
        ),
      ],
    );
  }
}
