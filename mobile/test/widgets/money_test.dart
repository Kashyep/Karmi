import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/widgets/money.dart';

void main() {
  group('formatInr (micro)', () {
    test('contract examples', () {
      expect(formatInr(0), '₹0');
      expect(formatInr(149000000), '₹149');
      expect(formatInr(149900000000), '₹1,49,900');
      expect(formatInr(10000000000000), '₹1,00,00,000');
      expect(formatInr(100000000000000), '₹10,00,00,000');
      expect(formatInr(10000), '₹0.01');
      expect(formatInr(12500000), '₹12.50');
      expect(formatInr(1234560000), '₹1,234.56');
      expect(formatInr(1), '<₹0.01');
      expect(formatInr(-12500000), '-₹12.50');
    });

    test('negative whole rupees', () {
      expect(formatInr(-1000000), '-₹1');
      expect(formatInr(-149000000), '-₹149');
      expect(formatInr(-149900000000), '-₹1,49,900');
    });

    test('negative sub-paisa rule: negative below paisa prints -<₹0.01', () {
      expect(formatInr(-1), '-<₹0.01');
      expect(formatInr(-5000), '-<₹0.01');
      expect(formatInr(-9999), '-<₹0.01');
    });

    test('positive sub-paisa amounts print <₹0.01', () {
      expect(formatInr(1), '<₹0.01');
      expect(formatInr(5000), '<₹0.01');
      expect(formatInr(9999), '<₹0.01');
    });

    test('micro to paise half-up rounding', () {
      // 10,000 micro = 1 paisa (₹0.01)
      expect(formatInr(10000), '₹0.01');
      // 14,999 micro rounds down to 1 paisa (₹0.01)
      expect(formatInr(14999), '₹0.01');
      // 15,000 micro rounds up to 2 paise (₹0.02)
      expect(formatInr(15000), '₹0.02');
      // 24,999 micro rounds down to 2 paise (₹0.02)
      expect(formatInr(24999), '₹0.02');
      // 25,000 micro rounds up to 3 paise (₹0.03)
      expect(formatInr(25000), '₹0.03');

      // Rounding with higher amounts
      expect(formatInr(12344999), '₹12.34');
      expect(formatInr(12345000), '₹12.35');
    });

    test('Indian grouping for 7+ digit amounts', () {
      // 1 lakh = 1,00,000 rupees (10^11 micro)
      expect(formatInr(100000000000), '₹1,00,000');
      // 10 lakh = 10,00,000 rupees (10^12 micro)
      expect(formatInr(1000000000000), '₹10,00,000');
      // 1 crore = 1,00,00,000 rupees (10^13 micro)
      expect(formatInr(10000000000000), '₹1,00,00,000');
      // 10 crore = 10,00,00,000 rupees (10^14 micro)
      expect(formatInr(100000000000000), '₹10,00,00,000');
      // 100 crore = 1,00,00,00,000 rupees (10^15 micro)
      expect(formatInr(1000000000000000), '₹1,00,00,00,000');
    });

    test('exact zero prints ₹0', () {
      expect(formatInr(0), '₹0');
    });
  });

  group('formatInrRupees (double)', () {
    test('contract examples', () {
      expect(formatInrRupees(12.5), '₹12.50');
      expect(formatInrRupees(149), '₹149');
      expect(formatInrRupees(1234.56), '₹1,234.56');
    });

    test('zero and signed zeros print ₹0', () {
      expect(formatInrRupees(0.0), '₹0');
      expect(formatInrRupees(-0.0), '₹0');
    });

    test('sub-paisa amounts', () {
      expect(formatInrRupees(0.001), '<₹0.01');
      expect(formatInrRupees(0.0099), '<₹0.01');
      expect(formatInrRupees(-0.001), '-<₹0.01');
      expect(formatInrRupees(-0.0099), '-<₹0.01');
    });

    test('sub-micro non-zero amounts print <₹0.01', () {
      expect(formatInrRupees(0.0000001), '<₹0.01');
      expect(formatInrRupees(-0.0000001), '-<₹0.01');
      expect(formatInrRupees(0.000000001), '<₹0.01');
      expect(formatInrRupees(-0.000000001), '-<₹0.01');
    });

    test('exact paise and negative decimals', () {
      expect(formatInrRupees(0.01), '₹0.01');
      expect(formatInrRupees(-0.01), '-₹0.01');
      expect(formatInrRupees(-12.5), '-₹12.50');
      expect(formatInrRupees(-149.0), '-₹149');
      expect(formatInrRupees(149900.0), '₹1,49,900');
    });

    test('half-paisa parity with formatInr', () {
      expect(formatInrRupees(0.015), formatInr(15000));
      expect(formatInrRupees(0.014), formatInr(14000));
      expect(formatInrRupees(-0.015), formatInr(-15000));
      expect(formatInrRupees(-0.014), formatInr(-14000));
    });
  });
}
