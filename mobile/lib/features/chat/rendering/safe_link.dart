import 'package:flutter/widgets.dart';
import 'package:url_launcher/url_launcher.dart';

/// Checks if [uri] is considered safe to open.
///
/// Returns `true` only for schemes `http`, `https`, and `mailto`
/// (case-insensitive). Schemes `http` and `https` require a non-empty host,
/// while `mailto` is permitted without a host.
bool isSafeLinkUri(Uri uri) {
  final scheme = uri.scheme.toLowerCase();
  if (scheme == 'http' || scheme == 'https') {
    return uri.host.isNotEmpty;
  }
  if (scheme == 'mailto') {
    return true;
  }
  return false;
}

/// Safely opens a raw URL string using the system handler.
///
/// If [rawUrl] cannot be parsed or [isSafeLinkUri] returns `false`, no action
/// is taken and this returns `false`. Otherwise, attempts to launch the URI
/// via [LaunchMode.externalApplication] inside a try/catch block.
Future<bool> openSafeLink(BuildContext? context, String rawUrl) async {
  try {
    final trimmed = rawUrl.trim();
    if (trimmed.isEmpty) {
      return false;
    }
    final uri = Uri.tryParse(trimmed);
    if (uri == null || !isSafeLinkUri(uri)) {
      return false;
    }
    return await launchUrl(uri, mode: LaunchMode.externalApplication);
  } catch (_) {
    return false;
  }
}
