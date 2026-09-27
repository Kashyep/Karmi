import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../theme/karmi_tier.dart';

/// Switches the home-screen icon to the active tier through the native bridge
/// (implementation_plan.md §3.3):
/// - Android: enables one `<activity-alias>` (`.Launcher<Tier>`) and disables
///   the others (`MainActivity.kt`).
/// - iOS: `UIApplication.setAlternateIconName` (`AppDelegate.swift`).
///
/// This changes the real launcher icon; it is never simulated in-app.
abstract interface class AppIconSwitcher {
  /// Returns false when the platform cannot switch icons.
  Future<bool> apply(KarmiTier tier);
}

class MethodChannelAppIconSwitcher implements AppIconSwitcher {
  const MethodChannelAppIconSwitcher();

  static const channel = MethodChannel('ai.karmi.app/app_icon');

  @override
  Future<bool> apply(KarmiTier tier) async {
    if (kIsWeb) return false;
    try {
      return await channel.invokeMethod<bool>('setIcon', {'tier': tier.name}) ??
          false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }
}
