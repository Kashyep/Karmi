import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/features/plans/plan_selection_screen.dart';
import 'package:karmi_app/settings/karmi_settings.dart';
import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';

KarmiApi _api(http.Response Function(http.Request) handler) => KarmiApi(
  baseUrl: 'http://karmi.test',
  client: _Client(handler),
  token: 'test-token',
);

class _Client extends http.BaseClient {
  _Client(this.handler);
  final http.Response Function(http.Request) handler;
  final requests = <http.Request>[];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final body = await request.finalize().bytesToString();
    final copy = http.Request(request.method, request.url)..body = body;
    requests.add(copy);
    final response = handler(copy);
    return http.StreamedResponse(
      Stream.value(utf8.encode(response.body)),
      response.statusCode,
      headers: {'content-type': 'application/json'},
    );
  }
}

Future<void> _pump(
  WidgetTester tester,
  KarmiApi api, {
  Future<void> Function()? onChanged,
}) => tester.pumpWidget(
  MaterialApp(
    theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
    home: PlanSelectionScreen(
      currentPlanId: 'ananta',
      api: api,
      onPlanChanged: onChanged,
    ),
  ),
);

void main() {
  serverUrlTests();
  testWidgets('a valid access code unlocks the plan and refreshes state', (
    tester,
  ) async {
    var refreshed = 0;
    late _Client client;
    final api = KarmiApi(
      baseUrl: 'http://karmi.test',
      client: client = _Client(
        (_) => http.Response(
          jsonEncode({
            'plan_id': 'trika',
            'plan_label': 'Trika',
            'changed': true,
          }),
          200,
        ),
      ),
      token: 'test-token',
    );
    await _pump(tester, api, onChanged: () async => refreshed++);

    await tester.enterText(
      find.byKey(const ValueKey('access-code-field')),
      'TRIKA-AAAA',
    );
    await tester.tap(find.byKey(const ValueKey('access-code-apply')));
    await tester.pumpAndSettle();

    expect(find.text('Unlocked Trika. Enjoy the beta!'), findsOneWidget);
    expect(refreshed, 1);
    expect(jsonDecode(client.requests.single.body), {'code': 'TRIKA-AAAA'});
    expect(client.requests.single.url.path, '/v1/access-code');
  });

  testWidgets('an invalid code shows a calm error and changes nothing', (
    tester,
  ) async {
    var refreshed = 0;
    final api = _api(
      (_) => http.Response(jsonEncode({'detail': 'invalid access code'}), 404),
    );
    await _pump(tester, api, onChanged: () async => refreshed++);

    await tester.enterText(
      find.byKey(const ValueKey('access-code-field')),
      'nope',
    );
    await tester.tap(find.byKey(const ValueKey('access-code-apply')));
    await tester.pumpAndSettle();

    expect(find.textContaining('not valid'), findsOneWidget);
    expect(refreshed, 0);
  });

  testWidgets('without an api the code field is not shown', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
        home: const PlanSelectionScreen(currentPlanId: 'ananta'),
      ),
    );
    expect(find.byKey(const ValueKey('access-code-field')), findsNothing);
  });
}

void serverUrlTests() {
  test('server addresses must be https except local development hosts', () {
    expect(KarmiSettings.isValidServerUrl('https://karmi.example.com'), isTrue);
    expect(KarmiSettings.isValidServerUrl('http://10.0.2.2:8000'), isTrue);
    expect(KarmiSettings.isValidServerUrl('http://evil.example.com'), isFalse);
    expect(KarmiSettings.isValidServerUrl('https://'), isFalse);
    expect(KarmiSettings.isValidServerUrl('ftp://karmi.example.com'), isFalse);
    expect(
      KarmiSettings.isValidServerUrl('https://a.example.com/?x=1'),
      isFalse,
    );
  });
}
