import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/api/chat/chat_events.dart';
import 'package:karmi_app/api/debug_meta.dart';
import 'package:karmi_app/api/models.dart';

Map<String, dynamic> _debugJson() => {
  'served_model': 'model-x',
  'served_provider': 'prov-y',
  'attempt_count': 2,
  'fallback_used': true,
  'latency_ms': 1234,
  'input_tokens': 100,
  'output_tokens': 40,
  'harness_version': '4.1.0',
};

Map<String, dynamic> _messageJson({Object? debug = _absent}) => {
  'run_id': 'run-1',
  'status': 'COMPLETED',
  'outcome': 'ACCEPT',
  'response': 'hi',
  if (!identical(debug, _absent)) 'debug': debug,
};

const _absent = Object();

void main() {
  group('DebugMeta.fromJson', () {
    test('absent or non-map value yields null, not an empty object', () {
      expect(DebugMeta.fromJson(null), isNull);
      expect(DebugMeta.fromJson('debug'), isNull);
      expect(DebugMeta.fromJson(42), isNull);
    });

    test('parses every field of a present debug object', () {
      final meta = DebugMeta.fromJson(_debugJson());
      expect(meta, isNotNull);
      expect(meta!.servedModel, 'model-x');
      expect(meta.servedProvider, 'prov-y');
      expect(meta.attemptCount, 2);
      expect(meta.fallbackUsed, isTrue);
      expect(meta.latencyMs, 1234);
      expect(meta.inputTokens, 100);
      expect(meta.outputTokens, 40);
      expect(meta.harnessVersion, '4.1.0');
    });

    test('nullable fields accept explicit nulls', () {
      final meta = DebugMeta.fromJson({
        'served_model': null,
        'served_provider': null,
        'attempt_count': 1,
        'fallback_used': false,
        'latency_ms': null,
        'input_tokens': null,
        'output_tokens': null,
        'harness_version': '4.1.0',
      });
      expect(meta!.servedModel, isNull);
      expect(meta.servedProvider, isNull);
      expect(meta.latencyMs, isNull);
      expect(meta.inputTokens, isNull);
      expect(meta.outputTokens, isNull);
    });
  });

  group('MessageView.fromJson debug', () {
    test('debug present is parsed', () {
      final view = MessageView.fromJson(_messageJson(debug: _debugJson()));
      expect(view.debug, isNotNull);
      expect(view.debug!.harnessVersion, '4.1.0');
    });

    test('debug absent yields null and leaves other fields unchanged', () {
      final view = MessageView.fromJson(_messageJson());
      expect(view.debug, isNull);
      expect(view.runId, 'run-1');
      expect(view.response, 'hi');
      expect(view.outcome, Outcome.accept);
    });
  });

  group('RunFinishedEvent.fromJson debug', () {
    test('debug present is parsed', () {
      final event = RunFinishedEvent.fromJson({
        'finish_reason': 'stop',
        'debug': _debugJson(),
      });
      expect(event.debug, isNotNull);
      expect(event.debug!.attemptCount, 2);
    });

    test('debug absent yields null', () {
      final event = RunFinishedEvent.fromJson({'finish_reason': 'stop'});
      expect(event.debug, isNull);
    });
  });
}
