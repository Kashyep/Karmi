import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/onboarding/onboarding.dart';

import '../../support/harness.dart';

String _boxes(WidgetTester tester) => [
  for (var i = 0; i < 6; i++)
    (tester.widget<Text>(
      find.descendant(
        of: find.byKey(ValueKey('otp_box_$i')),
        matching: find.byType(Text),
      ),
    )).data ??
        '',
].join();

void main() {
  Future<List<String>> pumpOtp(WidgetTester tester) async {
    final completed = <String>[];
    await pumpHost(
      tester,
      OtpField(onCompleted: completed.add),
    );
    return completed;
  }

  testWidgets('pasting 123456 fills all six boxes and completes once', (
    tester,
  ) async {
    final completed = await pumpOtp(tester);
    await tester.enterText(find.byKey(const ValueKey('otp_input')), '123456');
    await settle(tester);
    expect(_boxes(tester), '123456');
    expect(completed, ['123456']);
  });

  testWidgets('pasting with a space fills all six boxes (digits only)', (
    tester,
  ) async {
    final completed = await pumpOtp(tester);
    await tester.enterText(find.byKey(const ValueKey('otp_input')), '123 456');
    await settle(tester);
    expect(_boxes(tester), '123456');
    expect(completed, ['123456']);
  });

  testWidgets('pasting with dashes fills all six boxes', (tester) async {
    final completed = await pumpOtp(tester);
    await tester.enterText(find.byKey(const ValueKey('otp_input')), '12-34-56');
    await settle(tester);
    expect(_boxes(tester), '123456');
    expect(completed, ['123456']);
  });

  testWidgets('non-digits are ignored and length is capped at six', (
    tester,
  ) async {
    final completed = await pumpOtp(tester);
    await tester.enterText(
      find.byKey(const ValueKey('otp_input')),
      'a1b2c3d4e5f6g7',
    );
    await settle(tester);
    expect(_boxes(tester), '123456');
    expect(completed, ['123456']);
  });

  testWidgets('typing digits one at a time completes on the sixth', (
    tester,
  ) async {
    final completed = await pumpOtp(tester);
    for (var i = 1; i <= 6; i++) {
      await tester.enterText(
        find.byKey(const ValueKey('otp_input')),
        '${List.generate(i, (j) => j + 1).join()}',
      );
      await settle(tester);
    }
    expect(_boxes(tester), '123456');
    expect(completed, ['123456']);
  });

  testWidgets('backspace removes the last digit and cannot complete', (
    tester,
  ) async {
    final completed = <String>[];
    final controller = TextEditingController();
    await pumpHost(
      tester,
      OtpField(controller: controller, onCompleted: completed.add),
    );
    await tester.enterText(find.byKey(const ValueKey('otp_input')), '12345');
    await settle(tester);
    expect(_boxes(tester), '12345');

    await tester.sendKeyEvent(LogicalKeyboardKey.backspace);
    await settle(tester);
    expect(_boxes(tester), '1234');
    expect(controller.text, '1234');
    expect(completed, isEmpty);
  });
}
