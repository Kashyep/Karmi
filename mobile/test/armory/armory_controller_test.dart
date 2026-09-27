import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:karmi_app/api/karmi_api.dart';
import 'package:karmi_app/armory/armory_controller.dart';
import 'package:karmi_app/theme/karmi_tier.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/fake_backend.dart';
import '../support/harness.dart';

Future<(ArmoryController, FakeBackend, FakeAppIcons, SharedPreferences)> make({
  int unlocked = 1,
  int active = 1,
  Map<String, Object> prefs = const {},
}) async {
  SharedPreferences.setMockInitialValues(prefs);
  final p = await SharedPreferences.getInstance();
  final backend = FakeBackend()
    ..unlockedTier = unlocked
    ..activeTheme = active
    ..routeArmory();
  final icons = FakeAppIcons();
  final c = ArmoryController(api: backend.api(), prefs: p, appIcon: icons);
  addTearDown(c.dispose);
  return (c, backend, icons, p);
}

void main() {
  group('initialization', () {
    test('defaults to Ananta with no cached state', () async {
      final (c, _, _, _) = await make();
      expect(c.unlockedTier, KarmiTier.ananta);
      expect(c.effectiveTier, KarmiTier.ananta);
      expect(c.isLoaded, isFalse);
    });

    test('restores the cached tier before the server answers', () async {
      final (c, _, _, _) = await make(
        prefs: {'armory_unlocked_tier': 3, 'armory_active_theme': 3},
      );
      expect(c.effectiveTier, KarmiTier.trika);
    });

    test('corrupt cache: invalid ids fall back, active is clamped', () async {
      final (bad, _, _, _) = await make(
        prefs: {'armory_unlocked_tier': 9, 'armory_active_theme': 0},
      );
      expect(bad.unlockedTier, KarmiTier.ananta);
      expect(bad.activeTheme, KarmiTier.ananta);
      final (tampered, _, _, _) = await make(
        prefs: {'armory_unlocked_tier': 2, 'armory_active_theme': 4},
      );
      expect(tampered.activeTheme, KarmiTier.yanta);
    });

    test('load() adopts server state, persists it and sets the icon', () async {
      final (c, _, icons, prefs) = await make(unlocked: 4, active: 3);
      await c.load();
      expect(c.unlockedTier, KarmiTier.parth);
      expect(c.activeTheme, KarmiTier.trika);
      expect(prefs.getInt('armory_unlocked_tier'), 4);
      expect(prefs.getInt('armory_active_theme'), 3);
      await pumpEventQueue();
      expect(icons.applied, [KarmiTier.trika]);
    });

    test('malformed server tiers are rejected, cache kept', () async {
      final (c, backend, _, _) = await make(
        prefs: {'armory_unlocked_tier': 2, 'armory_active_theme': 2},
      );
      backend.on(
        'GET',
        '/v1/armory',
        (_) => jsonResponse({'unlocked_tier': 7, 'active_theme': 'x'}),
      );
      await expectLater(c.load(), throwsA(isA<ServerException>()));
      expect(c.activeTheme, KarmiTier.yanta);
    });
  });

  group('activation', () {
    test('unlocked tier activates via the server', () async {
      final (c, backend, icons, _) = await make(unlocked: 3);
      await c.load();
      await c.activate(KarmiTier.trika);
      expect(c.activeTheme, KarmiTier.trika);
      expect(backend.activeTheme, 3);
      await pumpEventQueue();
      expect(icons.applied.last, KarmiTier.trika);
    });

    test('locked tier is refused locally without a request', () async {
      final (c, backend, _, _) = await make(unlocked: 2);
      await c.load();
      final before = backend.requests.length;
      expect(
        () => c.activate(KarmiTier.parth),
        throwsA(isA<LockedTierException>()),
      );
      expect(backend.requests.length, before);
      expect(c.activeTheme, KarmiTier.ananta);
    });

    test('server 403 (downgrade raced the tap) re-syncs state', () async {
      final (c, backend, _, _) = await make(unlocked: 4, active: 4);
      await c.load();
      // Subscription downgraded server-side after the client loaded.
      backend
        ..unlockedTier = 2
        ..activeTheme = 2;
      await expectLater(
        c.activate(KarmiTier.trika),
        throwsA(isA<TierLockedException>()),
      );
      expect(c.unlockedTier, KarmiTier.yanta);
      expect(c.activeTheme, KarmiTier.yanta);
    });
  });

  group('upgrades and downgrades', () {
    test('upgrade unlocks higher tiers and keeps the active theme', () async {
      final (c, backend, _, _) = await make(unlocked: 1);
      await c.load();
      backend.unlockedTier = 4;
      await c.load();
      expect(c.unlockedTier, KarmiTier.parth);
      expect(c.activeTheme, KarmiTier.ananta);
      expect(c.isLocked(KarmiTier.parth), isFalse);
    });

    test('downgrade corrects the active theme', () async {
      final (c, backend, _, prefs) = await make(unlocked: 4, active: 4);
      await c.load();
      backend.unlockedTier = 2; // fake server clamps active on GET
      await c.load();
      expect(c.activeTheme, KarmiTier.yanta);
      expect(prefs.getInt('armory_active_theme'), 2);
    });

    test('client clamps even if a server reports active > unlocked', () async {
      final (c, backend, _, _) = await make();
      backend.on(
        'GET',
        '/v1/armory',
        (_) => jsonResponse({'unlocked_tier': 2, 'active_theme': 4}),
      );
      await c.load();
      expect(c.activeTheme, KarmiTier.yanta);
    });

    test('stale response cannot overwrite a newer one', () async {
      final (c, backend, _, _) = await make(unlocked: 4);
      final slow = Completer<http.Response>();
      var calls = 0;
      backend.on('GET', '/v1/armory', (_) {
        calls++;
        if (calls == 1) return slow.future;
        return jsonResponse({'unlocked_tier': 4, 'active_theme': 3});
      });
      final first = c.load();
      await c.load();
      slow.complete(jsonResponse({'unlocked_tier': 1, 'active_theme': 1}));
      await first;
      expect(c.activeTheme, KarmiTier.trika);
      expect(c.unlockedTier, KarmiTier.parth);
    });

    test('sign-out reset forgets progression', () async {
      final (c, _, icons, prefs) = await make(unlocked: 4, active: 4);
      await c.load();
      await c.reset();
      expect(c.effectiveTier, KarmiTier.ananta);
      expect(prefs.getInt('armory_active_theme'), isNull);
      expect(icons.applied.last, KarmiTier.ananta);
    });
  });

  group('10-second preview', () {
    test('previews a locked tier then reverts after 10 s', () async {
      final (c, _, _, _) = await make();
      fakeAsync((async) {
        expect(c.startPreview(KarmiTier.parth), isTrue);
        expect(c.effectiveTier, KarmiTier.parth);
        async.elapse(const Duration(milliseconds: 9999));
        expect(c.effectiveTier, KarmiTier.parth);
        async.elapse(const Duration(milliseconds: 1));
        expect(c.effectiveTier, KarmiTier.ananta);
        expect(c.isPreviewing, isFalse);
        expect(async.pendingTimers, isEmpty);
      });
    });

    test('unlocked tiers are not previewed', () async {
      final (c, _, _, _) = await make(unlocked: 3);
      await c.load();
      expect(c.startPreview(KarmiTier.yanta), isFalse);
      expect(c.isPreviewing, isFalse);
    });

    test('a new preview replaces the old timer (no early revert)', () async {
      final (c, _, _, _) = await make();
      fakeAsync((async) {
        c.startPreview(KarmiTier.yanta);
        async.elapse(const Duration(seconds: 8));
        c.startPreview(KarmiTier.trika);
        expect(async.pendingTimers, hasLength(1));
        async.elapse(const Duration(seconds: 3));
        // The first timer (due at 10 s) must not end the second preview.
        expect(c.effectiveTier, KarmiTier.trika);
        async.elapse(const Duration(seconds: 7));
        expect(c.effectiveTier, KarmiTier.ananta);
      });
    });

    test('ending early cancels the timer', () async {
      final (c, _, _, _) = await make();
      fakeAsync((async) {
        c.startPreview(KarmiTier.parth);
        c.endPreview();
        expect(c.effectiveTier, KarmiTier.ananta);
        expect(async.pendingTimers, isEmpty);
      });
    });

    test('activation ends a running preview', () async {
      final (c, _, _, _) = await make(unlocked: 2);
      await c.load();
      c.startPreview(KarmiTier.parth);
      await c.activate(KarmiTier.yanta);
      expect(c.isPreviewing, isFalse);
      expect(c.effectiveTier, KarmiTier.yanta);
    });

    test(
      'an upgrade that unlocks the previewed tier ends the preview',
      () async {
        final (c, backend, _, _) = await make();
        await c.load();
        c.startPreview(KarmiTier.trika);
        backend.unlockedTier = 3;
        await c.load();
        expect(c.isPreviewing, isFalse);
        expect(c.effectiveTier, KarmiTier.ananta);
      },
    );

    test('dispose cancels the preview timer', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      fakeAsync((async) {
        final c = ArmoryController(
          api: FakeBackend().api(),
          prefs: prefs,
          appIcon: FakeAppIcons(),
        );
        c.startPreview(KarmiTier.parth);
        c.dispose();
        expect(async.pendingTimers, isEmpty);
      });
    });

    test('previews never reach the server', () async {
      final (c, backend, icons, _) = await make();
      fakeAsync((async) {
        c.startPreview(KarmiTier.parth);
        async.elapse(const Duration(seconds: 11));
      });
      expect(backend.requests, isEmpty);
      expect(backend.activeTheme, 1);
      expect(icons.applied, isEmpty);
    });
  });
}
