import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/karmi_api.dart';
import '../theme/karmi_tier.dart';
import 'app_icon.dart';

/// Thrown locally when activating a tier above the unlocked tier.
class LockedTierException implements Exception {
  const LockedTierException(this.tier, this.unlockedTier);

  final KarmiTier tier;
  final KarmiTier unlockedTier;
}

/// The tier axis of the theme (implementation_plan.md §2.1, §3).
///
/// - `unlocked_tier` / `active_theme` are server-authoritative (API-002); the
///   last server values are cached so the first frame already uses the right
///   tier, and are re-validated on every load.
/// - [effectiveTier] is what the UI renders: an active 10-second preview of a
///   locked tier, else the active theme (always ≤ unlocked).
/// - Preview: one timer at a time; a new preview, an activation, a server
///   update that unlocks the tier, sign-out and dispose all cancel it. Timer
///   callbacks carry a token so a cancelled/replaced preview can never revert
///   a newer one.
/// - Network results carry a generation number; a slower, older response can
///   never overwrite a newer one.
class ArmoryController extends ChangeNotifier {
  ArmoryController({
    required KarmiApi api,
    required SharedPreferences prefs,
    AppIconSwitcher appIcon = const MethodChannelAppIconSwitcher(),
    this.previewDuration = const Duration(seconds: 10),
  }) : _api = api,
       _prefs = prefs,
       _appIcon = appIcon {
    final unlocked =
        KarmiTier.fromId(_prefs.getInt(_keyUnlocked)) ?? KarmiTier.ananta;
    final active =
        KarmiTier.fromId(_prefs.getInt(_keyActive)) ?? KarmiTier.ananta;
    _unlocked = unlocked;
    _active = active > unlocked ? unlocked : active;
  }

  static const _keyUnlocked = 'armory_unlocked_tier';
  static const _keyActive = 'armory_active_theme';

  final KarmiApi _api;
  final SharedPreferences _prefs;
  final AppIconSwitcher _appIcon;
  final Duration previewDuration;

  late KarmiTier _unlocked;
  late KarmiTier _active;
  KarmiTier? _preview;
  DateTime? _previewEndsAt;
  Timer? _previewTimer;
  int _previewToken = 0;
  int _generation = 0;
  bool _busy = false;
  bool _loaded = false;
  bool _disposed = false;
  KarmiTier? _iconApplied;
  bool? _iconSupported;

  KarmiTier get unlockedTier => _unlocked;
  KarmiTier get activeTheme => _active;
  KarmiTier? get previewTier => _preview;
  bool get isPreviewing => _preview != null;
  bool get isBusy => _busy;

  /// True once the server state has been fetched this session.
  bool get isLoaded => _loaded;

  /// Null until the first icon switch attempt.
  bool? get appIconSupported => _iconSupported;

  /// The tier the UI renders.
  KarmiTier get effectiveTier => _preview ?? _active;

  bool isLocked(KarmiTier tier) => tier > _unlocked;

  Duration get previewRemaining {
    final ends = _previewEndsAt;
    if (ends == null) return Duration.zero;
    final left = ends.difference(DateTime.now());
    return left.isNegative ? Duration.zero : left;
  }

  /// Fetches `GET /v1/armory`. Keeps the cached state on failure.
  Future<void> load() async {
    final generation = ++_generation;
    final view = await _api.getArmory();
    if (_disposed || generation != _generation) return;
    _apply(view);
  }

  /// Activates an unlocked tier on the server. Locked tiers are refused
  /// locally; if the server still refuses (e.g. a downgrade raced the tap),
  /// the state is re-fetched so the UI shows the corrected tier.
  Future<void> activate(KarmiTier tier) async {
    if (isLocked(tier)) throw LockedTierException(tier, _unlocked);
    endPreview();
    final generation = ++_generation;
    _busy = true;
    notifyListeners();
    try {
      final view = await _api.setActiveTheme(tier);
      if (_disposed || generation != _generation) return;
      _apply(view);
    } on TierLockedException {
      if (_disposed) return;
      await load();
      rethrow;
    } finally {
      if (!_disposed) {
        _busy = false;
        notifyListeners();
      }
    }
  }

  /// Applies a locked [tier] locally for [previewDuration], then reverts.
  /// Returns false (and does nothing) for tiers that are already unlocked.
  bool startPreview(KarmiTier tier) {
    if (!isLocked(tier)) return false;
    _previewTimer?.cancel();
    final token = ++_previewToken;
    _preview = tier;
    _previewEndsAt = DateTime.now().add(previewDuration);
    _previewTimer = Timer(previewDuration, () {
      if (token == _previewToken) endPreview();
    });
    notifyListeners();
    return true;
  }

  void endPreview() {
    _previewTimer?.cancel();
    _previewTimer = null;
    _previewToken++;
    if (_preview == null) return;
    _preview = null;
    _previewEndsAt = null;
    if (!_disposed) notifyListeners();
  }

  /// Sign-out: forget the account's progression.
  Future<void> reset() async {
    _generation++;
    endPreview();
    _unlocked = KarmiTier.ananta;
    _active = KarmiTier.ananta;
    _loaded = false;
    notifyListeners();
    await _prefs.remove(_keyUnlocked);
    await _prefs.remove(_keyActive);
    await _syncIcon();
  }

  void _apply(ArmoryView view) {
    _unlocked = view.unlockedTier;
    // Server already enforces active <= unlocked; clamp defensively.
    _active = view.activeTheme > _unlocked ? _unlocked : view.activeTheme;
    _loaded = true;
    final preview = _preview;
    if (preview != null && !isLocked(preview)) endPreview();
    notifyListeners();
    _prefs.setInt(_keyUnlocked, _unlocked.id);
    _prefs.setInt(_keyActive, _active.id);
    _syncIcon();
  }

  Future<void> _syncIcon() async {
    final target = _active;
    if (_iconApplied == target) return;
    _iconApplied = target;
    final ok = await _appIcon.apply(target);
    if (_disposed) return;
    if (!ok) _iconApplied = null;
    if (_iconSupported != ok) {
      _iconSupported = ok;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _previewTimer?.cancel();
    _previewTimer = null;
    super.dispose();
  }
}
