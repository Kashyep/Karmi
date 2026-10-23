import 'package:flutter/material.dart';

import 'admin_api.dart';
import 'admin_controller.dart';

/// Width at which the admin shell switches to a NavigationRail.
const double kAdminWideBreakpoint = 840;

/// Page gutter for admin sections; the shell draws its own header above.
const kAdminPagePadding = EdgeInsets.fromLTRB(16, 8, 16, 24);

/// Every admin button keeps a 48px touch target.
const kAdminButtonStyle = ButtonStyle(
  minimumSize: WidgetStatePropertyAll(Size(48, 48)),
);

/// Copy shown wherever the server did not report a value.
/// Minimum trimmed length of an admin action reason (backend rule).
const kAdminReasonMinLength = 3;

/// Maximum length of an admin action reason (backend rule).
const kAdminReasonMaxLength = 500;

const kAdminUnavailable = 'Unavailable';

/// Plan ids accepted by the backend for tier filters and tier changes.
const kAdminTiers = ['ananta', 'yanta', 'trika', 'parth'];

/// Display label for a plan id, e.g. `ananta` → `Ananta`.
String adminTierLabel(String id) =>
    id.isEmpty ? id : '${id[0].toUpperCase()}${id.substring(1)}';

/// Runs [call] with the live admin token. A rejected or expired session ends
/// the admin session on [controller]; the error is rethrown to the caller.
Future<T> runAdminCall<T>(
  AdminController controller,
  Future<T> Function(AdminApi api, String token) call,
) async {
  final token = controller.token;
  if (token == null) throw const AdminUnauthorized();
  try {
    return await call(controller.api, token);
  } on AdminUnauthorized {
    controller.sessionLost();
    rethrow;
  }
}

/// User-facing copy for an admin failure. Never shows raw exception text.
String adminErrorMessage(Object error) => switch (error) {
  AdminForbidden() => 'Admin access is no longer available.',
  AdminUnauthorized() => 'The admin session ended. Sign in again to continue.',
  AdminLockedOut() => 'Admin is locked after too many attempts.',
  _ => "Karmi couldn't complete that. Try again.",
};

String formatUsd(double value) => '\$${value.toStringAsFixed(2)}';

String formatAdminDateTime(BuildContext context, DateTime? at) {
  if (at == null) return kAdminUnavailable;
  final local = at.toLocal();
  final l10n = MaterialLocalizations.of(context);
  return '${l10n.formatMediumDate(local)}, '
      '${l10n.formatTimeOfDay(TimeOfDay.fromDateTime(local))}';
}

String formatAdminTime(BuildContext context, DateTime at) {
  final l10n = MaterialLocalizations.of(context);
  return l10n.formatTimeOfDay(TimeOfDay.fromDateTime(at.toLocal()));
}
