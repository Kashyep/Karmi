import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import '../api/karmi_api.dart';
import '../theme/karmi_motion.dart';
import '../features/chat/chat_screen.dart';
import '../features/usage/usage_screen.dart';
import '../features/memory/memory_screen.dart';
import '../features/settings/settings_screen.dart';

class KarmiShell extends StatefulWidget {
  final KarmiApi api;
  final KarmiSettingsProvider settingsProvider;

  const KarmiShell({
    super.key,
    required this.api,
    required this.settingsProvider,
  });

  @override
  State<KarmiShell> createState() => _KarmiShellState();
}

class _KarmiShellState extends State<KarmiShell> {
  int _currentIndex = 0;

  late final List<Widget> _destinations;

  @override
  void initState() {
    super.initState();
    _destinations = [
      ChatScreen(api: widget.api),
      const Center(child: Text('Tasks (Coming Soon)')),
      UsageScreen(api: widget.api),
      MemoryScreen(api: widget.api),
      SettingsScreen(settingsProvider: widget.settingsProvider),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return GlassScaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: const GlassAppBar(
        title: Text('Karmi'),
      ),
      body: IndexedStack(
        index: _currentIndex,
        children: _destinations,
      ),
      bottomBar: GlassTabBar.bottom(
        selectedIndex: _currentIndex,
        onTabSelected: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        tabs: const [
          GlassTab(icon: Icon(Icons.chat_bubble_outline), label: 'Chat'),
          GlassTab(icon: Icon(Icons.check_box_outline_blank), label: 'Tasks'),
          GlassTab(icon: Icon(Icons.data_usage), label: 'Usage'),
          GlassTab(icon: Icon(Icons.memory), label: 'Memory'),
          GlassTab(icon: Icon(Icons.settings), label: 'Settings'),
        ],
      ),
    );
  }
}
