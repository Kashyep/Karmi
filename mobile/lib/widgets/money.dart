/// Currency formatting for Indian Rupee (INR) amounts.
///
/// Ledger unit is `INR_MICRO` (1 rupee = 1,000,000 micro).
library;

String _formatIndianGrouping(int number) {
  final s = number.toString();
  if (s.length <= 3) return s;
  final lastThree = s.substring(s.length - 3);
  final remaining = s.substring(0, s.length - 3);
  final buffer = StringBuffer();
  for (var i = 0; i < remaining.length; i++) {
    if (i > 0 && (remaining.length - i) % 2 == 0) {
      buffer.write(',');
    }
    buffer.write(remaining[i]);
  }
  buffer.write(',');
  buffer.write(lastThree);
  return buffer.toString();
}

/// Formats an amount in INR micro (1 rupee = 1,000,000 micro) with Indian digit grouping.
///
/// Rules:
/// - Prefix `₹`, with `-` before `₹` for negative amounts (e.g. `-₹12.50`).
/// - Zero prints `₹0`.
/// - Non-zero amounts below one paisa (10,000 micro) print `<₹0.01` (or `-<₹0.01` if negative).
/// - Whole rupees print without decimals (e.g. `₹0`, `₹149`, `₹1,49,900`).
/// - Other amounts print exactly 2 decimals (e.g. `₹0.01`, `₹12.50`, `₹1,234.56`).
/// - Micro is rounded to paise with half-up rounding.
String formatInr(int micro) {
  if (micro == 0) return '₹0';
  final isNegative = micro < 0;
  final absMicro = micro.abs();

  // Non-zero amount below one paisa (1 paisa = 10,000 micro = 0.01 INR)
  if (absMicro < 10000) {
    return isNegative ? '-<₹0.01' : '<₹0.01';
  }

  // Half-up rounding from micro to paise (10,000 micro per paisa)
  final paise = (absMicro + 5000) ~/ 10000;
  final wholeRupees = paise ~/ 100;
  final paiseRemainder = paise % 100;

  final prefix = isNegative ? '-₹' : '₹';
  if (paiseRemainder == 0) {
    return '$prefix${_formatIndianGrouping(wholeRupees)}';
  }
  final paiseStr = paiseRemainder.toString().padLeft(2, '0');
  return '$prefix${_formatIndianGrouping(wholeRupees)}.$paiseStr';
}

/// Formats an amount in INR rupees ([rupees] as double) with Indian digit grouping.
///
/// Follows the same display rules as [formatInr].
///
/// Guard: If [rupees] is non-finite (`double.nan`, `double.infinity`, or
/// `double.negativeInfinity`), returns the safe fallback `'₹0'` rather than
/// printing invalid numeric tokens or throwing.
String formatInrRupees(double rupees) {
  if (!rupees.isFinite) return '₹0';
  if (rupees == 0.0) return '₹0';
  // Route through integer micro arithmetic (1 rupee = 1,000,000 micro)
  // to ensure identical half-paisa rounding and formatting.
  final micro = (rupees * 1000000).round();
  if (micro == 0) {
    return rupees < 0 ? '-<₹0.01' : '<₹0.01';
  }
  return formatInr(micro);
}
