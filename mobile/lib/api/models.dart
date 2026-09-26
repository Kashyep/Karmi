/// Wire models mirroring `src/daily_agent/schemas.py`.
library;

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

class MessageView {
  const MessageView({
    required this.runId,
    required this.status,
    required this.outcome,
    required this.response,
    this.route,
  });

  factory MessageView.fromJson(Map<String, dynamic> json) => MessageView(
    runId: json['run_id'] as String,
    status: json['status'] as String,
    outcome: Outcome.fromWire(json['outcome']),
    response: json['response'] as String,
    route: json['route'] as String?,
  );

  final String runId;
  final String status;
  final Outcome outcome;
  final String response;
  final String? route;
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
