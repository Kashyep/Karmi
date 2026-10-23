import 'package:flutter/material.dart';

import '../../api/debug_meta.dart';
import '../../theme/karmi_colors.dart';

/// Compile-time gate for the tester-only debug line (`--dart-define`).
const bool kDebugMetaEnabled = bool.fromEnvironment('KARMI_DEBUG_META');

/// Whether the debug line is shown: the env flag is on AND the reply carries
/// a `debug` object. Pure; the flag is injected so tests can exercise both.
bool showDebugMeta({required bool envFlag, required DebugMeta? debug}) =>
    envFlag && debug != null;

/// Single-line summary of [meta]; null parts are omitted.
String debugMetaSummary(DebugMeta meta) {
  final parts = <String>[
    ?meta.servedModel,
    ?meta.servedProvider,
    'attempts ${meta.attemptCount}',
    if (meta.fallbackUsed) 'fallback',
    if (meta.latencyMs != null) '${meta.latencyMs} ms',
    if (meta.inputTokens != null || meta.outputTokens != null)
      '${meta.inputTokens ?? '?'}/${meta.outputTokens ?? '?'} tokens',
    if (meta.harnessVersion.isNotEmpty) 'harness ${meta.harnessVersion}',
  ];
  return parts.join(' · ');
}

/// Muted, small, single-line debug text under an assistant reply.
class DebugMetaLine extends StatelessWidget {
  const DebugMetaLine({super.key, required this.meta});

  final DebugMeta meta;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final text = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Text(
        debugMetaSummary(meta),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: text.labelSmall?.copyWith(color: colors.mutedForeground),
      ),
    );
  }
}
