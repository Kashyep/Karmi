/// Optional tester-only `debug` object on `/v1/messages` replies and the
/// `run.finished` SSE event. The backend omits the key for non-testers.
library;

/// Serving metadata for one run. Immutable.
final class DebugMeta {
  const DebugMeta({
    required this.servedModel,
    required this.servedProvider,
    required this.attemptCount,
    required this.fallbackUsed,
    required this.latencyMs,
    required this.inputTokens,
    required this.outputTokens,
    required this.harnessVersion,
  });

  /// Parses the `debug` value. Returns null when [json] is absent or not a map,
  /// so callers never observe an empty object for a missing key.
  static DebugMeta? fromJson(Object? json) {
    if (json is! Map) return null;
    return DebugMeta(
      servedModel: json['served_model'] as String?,
      servedProvider: json['served_provider'] as String?,
      attemptCount: (json['attempt_count'] as num?)?.toInt() ?? 0,
      fallbackUsed: (json['fallback_used'] as bool?) ?? false,
      latencyMs: (json['latency_ms'] as num?)?.toInt(),
      inputTokens: (json['input_tokens'] as num?)?.toInt(),
      outputTokens: (json['output_tokens'] as num?)?.toInt(),
      harnessVersion: (json['harness_version'] as String?) ?? '',
    );
  }

  final String? servedModel;
  final String? servedProvider;
  final int attemptCount;
  final bool fallbackUsed;
  final int? latencyMs;
  final int? inputTokens;
  final int? outputTokens;
  final String harnessVersion;
}
