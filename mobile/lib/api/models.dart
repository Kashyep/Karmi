/// Wire models mirroring `src/daily_agent/schemas.py`.
library;

import '../theme/karmi_tier.dart';

/// `schemas.Outcome`. Unknown wire values parse to [Outcome.unknown] instead of throwing.
enum Outcome {
  accept('ACCEPT'),
  repair('REPAIR'),
  escalate('ESCALATE'),
  askUser('ASK_USER'),
  safeStop('SAFE_STOP'),
  deferred('DEFERRED'),
  unknown('');

  const Outcome(this.wireName);

  final String wireName;

  static Outcome fromWire(Object? value) {
    for (final outcome in values) {
      if (outcome != unknown && outcome.wireName == value) return outcome;
    }
    return unknown;
  }
}

enum FeedbackRating {
  up('up'),
  down('down');

  const FeedbackRating(this.wireName);
  final String wireName;

  static FeedbackRating? fromWire(Object? value) {
    for (final r in values) {
      if (r.wireName == value) return r;
    }
    return null;
  }
}

enum FeedbackReason {
  wrong('wrong', 'Wrong'),
  unclear('unclear', 'Unclear'),
  tooSlow('too_slow', 'Too slow'),
  other('other', 'Other');

  const FeedbackReason(this.wireName, this.label);
  final String wireName;
  final String label;

  static FeedbackReason? fromWire(Object? value) {
    for (final r in values) {
      if (r.wireName == value) return r;
    }
    return null;
  }
}

class RunFeedbackView {
  const RunFeedbackView({
    required this.runId,
    required this.rating,
    this.reason,
  });

  factory RunFeedbackView.fromJson(Map<String, dynamic> json) =>
      RunFeedbackView(
        runId: json['run_id'] as String,
        rating: FeedbackRating.fromWire(json['rating']) ?? FeedbackRating.up,
        reason: json['reason'] as String?,
      );

  final String runId;
  final FeedbackRating rating;
  final String? reason;
}

class MessageView {
  const MessageView({
    required this.runId,
    required this.status,
    required this.outcome,
    required this.response,
    this.route,
    this.previousRunId,
  });

  factory MessageView.fromJson(Map<String, dynamic> json) => MessageView(
    runId: json['run_id'] as String,
    status: json['status'] as String,
    outcome: Outcome.fromWire(json['outcome']),
    response: json['response'] as String,
    route: json['route'] as String?,
    previousRunId: json['previous_run_id'] as String?,
  );

  final String runId;
  final String status;
  final Outcome outcome;
  final String response;
  final String? route;
  final String? previousRunId;
}

class UsageView {
  const UsageView({
    required this.planId,
    required this.planLabel,
    required this.everydayUsed,
    required this.everydayLimit,
    required this.reservedMicro,
    required this.settledMicro,
    required this.spendLimitMicro,
    required this.resetAt,
    required this.periodResetAt,
    required this.policyVersion,
    required this.synthetic,
  });

  factory UsageView.fromJson(Map<String, dynamic> json) => UsageView(
    planId: json['plan_id'] as String,
    planLabel: json['plan_label'] as String,
    everydayUsed: json['everyday_used'] as int,
    everydayLimit: json['everyday_limit'] as int,
    reservedMicro: json['reserved_micro'] as int,
    settledMicro: json['settled_micro'] as int,
    spendLimitMicro: json['spend_limit_micro'] as int,
    resetAt: DateTime.parse(json['reset_at'] as String),
    periodResetAt: DateTime.parse(json['period_reset_at'] as String),
    policyVersion: json['policy_version'] as String,
    synthetic: json['synthetic'] as bool? ?? true,
  );

  final String planId;
  final String planLabel;
  final int everydayUsed;
  final int everydayLimit;
  final int reservedMicro;
  final int settledMicro;
  final int spendLimitMicro;
  final DateTime resetAt;
  final DateTime periodResetAt;
  final String policyVersion;
  final bool synthetic;
}

class NoteView {
  const NoteView({
    required this.id,
    required this.content,
    required this.version,
  });

  factory NoteView.fromJson(Map<String, dynamic> json) => NoteView(
    id: json['id'] as String,
    content: json['content'] as String,
    version: json['version'] as int,
  );

  final String id;
  final String content;
  final int version;
}

class TaskView {
  const TaskView({
    required this.id,
    required this.title,
    required this.completed,
  });

  factory TaskView.fromJson(Map<String, dynamic> json) => TaskView(
    id: json['id'] as String,
    title: json['title'] as String,
    completed: json['completed'] as bool,
  );

  final String id;
  final String title;
  final bool completed;
}

/// `GET /v1/armory` (API-002): progression is server-authoritative.
class ArmoryView {
  const ArmoryView({required this.unlockedTier, required this.activeTheme});

  /// Throws [FormatException] when either tier is not an integer 1–4.
  factory ArmoryView.fromJson(Map<String, dynamic> json) {
    final unlocked = KarmiTier.fromId(json['unlocked_tier']);
    final active = KarmiTier.fromId(json['active_theme']);
    if (unlocked == null || active == null) {
      throw const FormatException('armory tiers must be integers 1-4');
    }
    // The server enforces active <= unlocked; clamp defensively anyway.
    return ArmoryView(
      unlockedTier: unlocked,
      activeTheme: active > unlocked ? unlocked : active,
    );
  }

  final KarmiTier unlockedTier;
  final KarmiTier activeTheme;
}

/// Result of redeeming a beta access code (`POST /v1/access-code`).
class AccessCodeResult {
  const AccessCodeResult({
    required this.planId,
    required this.planLabel,
    required this.changed,
  });

  factory AccessCodeResult.fromJson(Map<String, dynamic> json) =>
      AccessCodeResult(
        planId: json['plan_id'] as String,
        planLabel: json['plan_label'] as String,
        changed: json['changed'] as bool,
      );

  final String planId;
  final String planLabel;
  final bool changed;
}
