import 'package:flutter/material.dart';
import '../../api/karmi_api.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_glass.dart';

class MemoryScreen extends StatefulWidget {
  final KarmiApi api;

  const MemoryScreen({super.key, required this.api});

  @override
  State<MemoryScreen> createState() => _MemoryScreenState();
}

class _MemoryScreenState extends State<MemoryScreen> {
  // Mock data for Phase 4 scaffold since endpoints are placeholder
  final List<NoteView> _notes = [
    NoteView(id: '1', content: 'User prefers concise answers.'),
    NoteView(id: '2', content: 'User timezone is Asia/Kolkata.'),
  ];

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).extension<KarmiColors>()!;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          'Memory',
          style: Theme.of(context).textTheme.displaySmall,
        ),
        const SizedBox(height: 24),
        if (_notes.isEmpty)
          Center(
            child: Text(
              'No memory notes yet.',
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    color: colors.mutedForeground,
                  ),
            ),
          )
        else
          ..._notes
              .map((note) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: KarmiGlassContainer(
                      padding: const EdgeInsets.all(16),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              note.content,
                              style: Theme.of(context).textTheme.bodyLarge,
                            ),
                          ),
                          IconButton(
                            icon: Icon(Icons.delete_outline,
                                color: colors.destructive),
                            onPressed: () {
                              // Call DELETE /v1/notes logic here
                            },
                          ),
                        ],
                      ),
                    ),
                  ))
              ,
      ],
    );
  }
}
