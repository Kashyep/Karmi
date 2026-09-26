import 'dart:convert';
import 'package:http/http.dart' as http;
import 'dart:math';

enum Outcome { ACCEPT, REPAIR, ESCALATE, ASK_USER, SAFE_STOP, DEFERRED }

class MessageView {
  final String runId;
  final String status;
  final Outcome outcome;
  final String response;
  final String route;

  MessageView({
    required this.runId,
    required this.status,
    required this.outcome,
    required this.response,
    required this.route,
  });

  factory MessageView.fromJson(Map<String, dynamic> json) {
    return MessageView(
      runId: json['run_id'],
      status: json['status'],
      outcome: Outcome.values.firstWhere((e) => e.name == json['outcome']),
      response: json['response'],
      route: json['route'],
    );
  }
}

class UsageView {
  final String planId;
  final String planLabel;
  final int everydayUsed;
  final int everydayLimit;
  final int reservedMicro;
  final int settledMicro;
  final int spendLimitMicro;
  final String resetAt;
  final String periodResetAt;
  final String policyVersion;

  UsageView({
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
  });

  factory UsageView.fromJson(Map<String, dynamic> json) {
    return UsageView(
      planId: json['plan_id'],
      planLabel: json['plan_label'],
      everydayUsed: json['everyday_used'],
      everydayLimit: json['everyday_limit'],
      reservedMicro: json['reserved_micro'],
      settledMicro: json['settled_micro'],
      spendLimitMicro: json['spend_limit_micro'],
      resetAt: json['reset_at'],
      periodResetAt: json['period_reset_at'],
      policyVersion: json['policy_version'],
    );
  }
}

class NoteView {
  final String id;
  final String content;

  NoteView({required this.id, required this.content});

  factory NoteView.fromJson(Map<String, dynamic> json) {
    return NoteView(
      id: json['id'],
      content: json['content'],
    );
  }
}

class KarmiApi {
  final String baseUrl;
  final String token;
  final http.Client _client;

  KarmiApi({
    required this.baseUrl,
    required this.token,
    http.Client? client,
  }) : _client = client ?? http.Client();

  Map<String, String> get _headers => {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      };

  static String generateIdempotencyKey() {
    final rand = Random.secure();
    final bytes = List<int>.generate(16, (i) => rand.nextInt(256));
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('');
  }

  Future<MessageView> sendMessage(String text, {String? idempotencyKey}) async {
    final key = idempotencyKey ?? generateIdempotencyKey();

    final response = await _client.post(
      Uri.parse('$baseUrl/v1/messages'),
      headers: _headers,
      body: jsonEncode({
        'text': text,
        'idempotency_key': key,
      }),
    );

    if (response.statusCode == 200) {
      return MessageView.fromJson(jsonDecode(response.body));
    } else if (response.statusCode == 409) {
      throw Exception('ReservationInFlight: 409 Conflict');
    } else {
      throw Exception('Failed to send message: ${response.statusCode}');
    }
  }

  Future<UsageView> getUsage() async {
    final response = await _client.get(
      Uri.parse('$baseUrl/v1/usage'),
      headers: _headers,
    );

    if (response.statusCode == 200) {
      return UsageView.fromJson(jsonDecode(response.body));
    } else {
      throw Exception('Failed to load usage');
    }
  }

  // Tasks and notes endpoints placeholder
}
