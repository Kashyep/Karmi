import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/features/plans/plan_catalog.dart';
import 'package:karmi_app/features/plans/plan_selection_screen.dart';

import 'package:karmi_app/theme/karmi_theme.dart';
import 'package:karmi_app/theme/karmi_tier.dart';

Widget _testBed(Widget child) => MaterialApp(
  theme: KarmiTheme.of(KarmiTier.ananta, Brightness.light),
  home: Scaffold(body: child),
);

void main() {
  group('PlanCard', () {
    testWidgets('renders ₹ price from priceInr with / month suffix', (
      tester,
    ) async {
      const plan = PlanInfo('yanta', 'Yanta', 100, priceInr: 149);
      await tester.pumpWidget(_testBed(const PlanCard(plan: plan)));

      expect(find.text('₹149 / month'), findsOneWidget);
      expect(find.textContaining(r'$'), findsNothing);
      expect(find.textContaining('USD'), findsNothing);
    });

    testWidgets('renders ₹0 / month for free tier (priceInr: 0)', (
      tester,
    ) async {
      const plan = PlanInfo('ananta', 'Ananta', 20, priceInr: 0);
      await tester.pumpWidget(_testBed(const PlanCard(plan: plan)));

      expect(find.text('₹0 / month'), findsOneWidget);
    });

    testWidgets('renders higher tier prices accurately in INR', (tester) async {
      const plan = PlanInfo('parth', 'Parth', 500, priceInr: 899);
      await tester.pumpWidget(_testBed(const PlanCard(plan: plan)));

      expect(find.text('₹899 / month'), findsOneWidget);
    });

    testWidgets('omits price row when priceInr is null', (tester) async {
      const plan = PlanInfo('ananta', 'Ananta', 20);
      await tester.pumpWidget(_testBed(const PlanCard(plan: plan)));

      expect(find.textContaining('/ month'), findsNothing);
      expect(find.textContaining('₹'), findsNothing);
      expect(find.textContaining(r'$'), findsNothing);
    });
  });

  group('PlanSelectionScreen', () {
    testWidgets('fetches plans from server and renders ₹ prices', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(800, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      final mockClient = MockClient((request) async {
        if (request.url.path == '/v1/plans') {
          return http.Response(
            jsonEncode([
              {
                'id': 'ananta',
                'label': 'Ananta',
                'price_inr': 0,
                'everyday_limit': 20,
              },
              {
                'id': 'yanta',
                'label': 'Yanta',
                'price_inr': 149,
                'everyday_limit': 100,
              },
              {
                'id': 'trika',
                'label': 'Trika',
                'price_inr': 399,
                'everyday_limit': 250,
              },
              {
                'id': 'parth',
                'label': 'Parth',
                'price_inr': 899,
                'everyday_limit': 500,
              },
            ]),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('not found', 404);
      });

      final api = KarmiApi(baseUrl: 'http://karmi.test', client: mockClient);

      await tester.pumpWidget(
        _testBed(PlanSelectionScreen(currentPlanId: 'ananta', api: api)),
      );
      await tester.pumpAndSettle();

      expect(find.text('₹0 / month'), findsOneWidget);
      expect(find.text('₹149 / month'), findsOneWidget);
      expect(find.text('₹399 / month'), findsOneWidget);
      expect(find.text('₹899 / month'), findsOneWidget);
      expect(find.textContaining(r'$'), findsNothing);
      expect(find.textContaining('USD'), findsNothing);
    });

    testWidgets('gracefully falls back to kPlans when api fails', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(800, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      final mockClient = MockClient((request) async {
        return http.Response('internal server error', 500);
      });

      final api = KarmiApi(baseUrl: 'http://karmi.test', client: mockClient);

      await tester.pumpWidget(
        _testBed(PlanSelectionScreen(currentPlanId: 'ananta', api: api)),
      );
      await tester.pumpAndSettle();

      // Cards render without crashing and without prices
      expect(find.byType(PlanCard), findsNWidgets(4));
      expect(find.textContaining(r'$'), findsNothing);
    });

    testWidgets('preselected card scrolls into view at small viewport', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(360, 640);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        _testBed(
          const PlanSelectionScreen(
            currentPlanId: 'ananta',
            preselectedPlanId: 'parth',
          ),
        ),
      );
      await tester.pumpAndSettle();

      final parthCard = find.byKey(
        const ValueKey('plan_card_parth_highlighted'),
      );
      expect(parthCard, findsOneWidget);
      final rect = tester.getRect(parthCard);
      expect(rect.top, greaterThanOrEqualTo(0.0));
      expect(rect.bottom, lessThanOrEqualTo(640.0));
    });
  });

  group('CustomerPlansApi extension', () {
    test('getPlans parses PlanView objects correctly', () async {
      final mockClient = MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/v1/plans');
        return http.Response(
          jsonEncode([
            {
              'id': 'yanta',
              'label': 'Yanta',
              'price_inr': 149,
              'everyday_limit': 100,
              'daily_token_limit': 300000,
              'input_tokens': 8000,
              'output_tokens': 2000,
              'request_cost_cap_micro': 4000,
              'period_cost_cap_micro': 4000000,
              'model_classes': ['economy'],
              'min_class': 'economy',
            },
          ]),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final api = KarmiApi(baseUrl: 'http://karmi.test', client: mockClient);

      final plans = await api.getPlans();
      expect(plans.length, 1);
      expect(plans.first.id, 'yanta');
      expect(plans.first.label, 'Yanta');
      expect(plans.first.priceInr, 149);
      expect(plans.first.everydayLimit, 100);
    });
  });
}
