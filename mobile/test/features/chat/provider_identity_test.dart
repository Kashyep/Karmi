import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/provider_identity.dart';

void main() {
  group('providerNickname', () {
    test('shortens real model ids to one friendly word', () {
      expect(
        providerNickname(model: 'nvidia/nemotron-3.5-lightning:free'),
        'Nemotron',
      );
      expect(providerNickname(model: 'openai/gpt-oss-20b'), 'GPT');
      expect(
        providerNickname(model: 'meta-llama/llama-3.3-70b-instruct'),
        'Llama',
      );
      expect(providerNickname(model: 'anthropic/claude-sonnet-4.5'), 'Claude');
    });

    test('never leaks the raw id, vendor or :free suffix', () {
      const raw = 'nvidia/nemotron-3.5-lightning:free';
      final name = providerNickname(model: raw);
      expect(name, isNot(contains('/')));
      expect(name, isNot(contains(':')));
      expect(name, isNot(equals(raw)));
    });

    test('falls back to the provider, then to Assistant', () {
      expect(providerNickname(provider: 'openrouter'), 'Openrouter');
      expect(providerNickname(), 'Assistant');
      expect(providerNickname(model: ''), 'Assistant');
    });
  });

  group('ProviderAvatar', () {
    testWidgets('is deterministic and shows the first letter', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(child: ProviderAvatar(name: 'Nemotron')),
          ),
        ),
      );

      expect(find.text('N'), findsOneWidget);
      final box = tester.widget<Container>(find.byType(Container).first);
      final decoration = box.decoration! as BoxDecoration;
      expect(decoration.color, isNotNull);
    });

    testWidgets('hides itself from the a11y tree by default', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(child: ProviderAvatar(name: 'Nemotron')),
          ),
        ),
      );

      expect(find.bySemanticsLabel('Nemotron'), findsNothing);
      handle.dispose();
    });
  });
}
