import 'package:flutter/material.dart';

import '../../api/karmi_api.dart';
import '../../widgets/feedback.dart';
import '../../widgets/karmi_card.dart';
import '../chat/status_chip.dart';

/// Tasks tab (T4.5): account-shared tasks from `GET /v1/tasks`, with
/// `PATCH /v1/tasks/{id}/complete`.
class TasksScreen extends StatefulWidget {
  const TasksScreen({super.key, required this.api});

  final KarmiApi api;

  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen> {
  List<TaskView>? _tasks;
  bool _loading = true;
  bool _loadFailed = false;
  final Set<String> _completing = {};
  String? _completeFailedTitle;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadFailed = false;
    });
    try {
      final tasks = await widget.api.listTasks();
      if (mounted) setState(() => _tasks = tasks);
    } on KarmiApiException {
      if (mounted) setState(() => _loadFailed = true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _complete(TaskView task) async {
    setState(() {
      _completing.add(task.id);
      _completeFailedTitle = null;
    });
    try {
      final updated = await widget.api.completeTask(task.id);
      if (!mounted) return;
      setState(() {
        final open = [
          for (final t in _tasks!)
            if (t.id == updated.id) updated else t,
        ];
        // Mirror the server order: open first, completed after.
        _tasks = [
          ...open.where((t) => !t.completed),
          ...open.where((t) => t.completed),
        ];
      });
    } on KarmiApiException {
      if (mounted) setState(() => _completeFailedTitle = task.title);
    } finally {
      if (mounted) setState(() => _completing.remove(task.id));
    }
  }

  @override
  Widget build(BuildContext context) {
    final tasks = _tasks;
    return RefreshIndicator(
      onRefresh: _load,
      edgeOffset: MediaQuery.paddingOf(context).top,
      child: ListView(
        padding: karmiPageInsets(context),
        children: [
          const KarmiHeading('Tasks'),
          if (_completeFailedTitle != null) ...[
            ErrorBanner(
              title: 'Could not complete task',
              message:
                  '"$_completeFailedTitle" is still open. Check your '
                  'connection and try again.',
            ),
            const SizedBox(height: 12),
          ],
          if (_loading && tasks == null)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Center(child: KarmiLoader(label: 'Loading tasks')),
            )
          else if (_loadFailed && tasks == null)
            ErrorBanner(
              title: 'Tasks unavailable',
              message: "Karmi couldn't load your tasks right now.",
              actionLabel: 'Retry',
              onAction: _load,
            )
          else if (tasks == null || tasks.isEmpty)
            const EmptyState(
              icon: Icons.check_circle_outline,
              quote: 'Nothing on your list yet.',
              body: 'Ask Karmi in Chat to add a task.',
            )
          else
            for (final task in tasks) ...[
              _TaskTile(
                task: task,
                busy: _completing.contains(task.id),
                onComplete: () => _complete(task),
              ),
              const SizedBox(height: 12),
            ],
        ],
      ),
    );
  }
}

class _TaskTile extends StatelessWidget {
  const _TaskTile({
    required this.task,
    required this.busy,
    required this.onComplete,
  });

  final TaskView task;
  final bool busy;
  final VoidCallback onComplete;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return KarmiCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(task.title, style: text.bodyLarge),
          const SizedBox(height: 8),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              StatusChip.task(completed: task.completed),
              if (!task.completed)
                busy
                    ? const KarmiLoader(label: 'Completing')
                    : OutlinedButton.icon(
                        onPressed: onComplete,
                        icon: const Icon(Icons.done),
                        label: Text(
                          'Mark complete',
                          semanticsLabel: 'Mark "${task.title}" complete',
                        ),
                      ),
            ],
          ),
        ],
      ),
    );
  }
}
