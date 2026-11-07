import 'dart:io';

import 'package:flutter/material.dart';

import '../../api/bug_reports/bug_report_models.dart';
import '../../theme/karmi_motion.dart';

/// Collector for device and environment diagnostics strictly conforming to the allowlist.
class DiagnosticsCollector {
  const DiagnosticsCollector({
    this.appVersion = '0.1.0',
    this.buildNumber = '4',
    this.gitSha = 'ac3d16e',
  });

  final String appVersion;
  final String buildNumber;
  final String gitSha;

  /// Builds a [BugReportDiagnostics] instance.
  ///
  /// Guarantees that only allowlisted keys are populated and all limits are enforced.
  BugReportDiagnostics collect({
    BuildContext? context,
    String? screen,
    String? plan,
    String? runId,
    String? errorCode,
    List<String>? recentRequestIds,
    List<String>? recentErrorCodes,
    String? customOs,
    String? customOsVersion,
    String? customDeviceModel,
    String? customLocale,
    double? customTextScale,
    String? customTheme,
    bool? customReduceTransparency,
  }) {
    String? os;
    String? osVersion;
    String? deviceModel;
    String? locale;
    double? textScale = customTextScale;
    String? theme = customTheme;
    bool? reduceTransparency = customReduceTransparency;

    try {
      os = customOs ?? Platform.operatingSystem;
      osVersion = customOsVersion ?? Platform.operatingSystemVersion;
      deviceModel = customDeviceModel ?? Platform.localHostname;
      locale = customLocale ?? Platform.localeName;
    } catch (_) {
      // In web or restricted sandbox, catch io exceptions
    }

    if (context != null) {
      try {
        final mediaQuery = MediaQuery.maybeOf(context);
        if (mediaQuery != null) {
          textScale ??= mediaQuery.textScaler.scale(1.0);
        }
        final brightness = Theme.of(context).brightness;
        theme ??= brightness.name;
        reduceTransparency ??= KarmiAccessibility.reduceTransparencyOf(context);
        final loc = Localizations.maybeLocaleOf(context);
        if (loc != null) {
          locale = loc.toLanguageTag();
        }
      } catch (_) {}
    }

    return BugReportDiagnostics(
      appVersion: appVersion,
      buildNumber: buildNumber,
      gitSha: gitSha,
      os: os,
      osVersion: osVersion,
      deviceModel: deviceModel,
      locale: locale,
      textScale: textScale,
      theme: theme,
      reduceTransparency: reduceTransparency,
      plan: plan,
      screen: screen,
      recentRequestIds: recentRequestIds,
      recentErrorCodes: recentErrorCodes,
      runId: runId,
      errorCode: errorCode,
    );
  }
}
