import 'package:flutter/material.dart';

import '../../api/debug_meta.dart';
import '../../theme/karmi_colors.dart';
import '../../widgets/karmi_logo.dart';

/// Compile-time gate for the tester-only debug line (`--dart-define`).
const bool kDebugMetaEnabled = bool.fromEnvironment('KARMI_DEBUG_META');

/// Whether the debug line is shown: the env flag is on AND the reply carries
/// a `debug` object. Pure; the flag is injected so tests can exercise both.
bool showDebugMeta({required bool envFlag, required DebugMeta? debug}) =>
    envFlag && debug != null;

/// Single-line summary of [meta]; null parts are omitted.
///
/// The served model and provider are deliberately never shown: the assistant
/// identity in the app is always Karmi. Only operational diagnostics a tester
/// needs remain.
String debugMetaSummary(DebugMeta meta) {
  final parts = <String>[
    'attempts ${meta.attemptCount}',
    if (meta.fallbackUsed) 'fallback',
    if (meta.latencyMs != null) '${meta.latencyMs} ms',
    if (meta.inputTokens != null || meta.outputTokens != null)
      '${meta.inputTokens ?? '?'}/${meta.outputTokens ?? '?'} tokens',
    if (meta.harnessVersion.isNotEmpty) 'harness ${meta.harnessVersion}',
  ];
  return parts.join(' · ');
}

/// Muted, small, single-line diagnostics under an assistant reply, always
/// presented as Karmi with the logo mark.
class DebugMetaLine extends StatelessWidget {
  const DebugMetaLine({super.key, required this.meta});

  final DebugMeta meta;

  @override
  Widget build(BuildContext context) {
    final colors = KarmiColors.of(context);
    final text = Theme.of(context).textTheme;
    final style = text.labelSmall?.copyWith(color: colors.mutedForeground);
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const KarmiLogo(size: 14, semanticLabel: null),
          const SizedBox(width: 6),
          Text('Karmi', style: style?.copyWith(fontWeight: FontWeight.w600)),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              debugMetaSummary(meta),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: style,
            ),
          ),
        ],
      ),
    );
  }
}
