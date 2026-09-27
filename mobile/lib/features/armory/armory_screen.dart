import 'dart:async';
import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

import '../../api/karmi_api.dart';
import '../../armory/armory_controller.dart';
import '../../theme/karmi_colors.dart';
import '../../theme/karmi_glass.dart';
import '../../theme/karmi_theme.dart';
import '../../theme/karmi_tier.dart';
import '../../widgets/feedback.dart';
import '../chat/status_chip.dart';

/// The Armory (implementation_plan.md §3.2): all four tier themes. Unlocked
/// tiers can be activated (server-enforced); locked tiers are blurred and
/// greyed, cannot be activated, and can be previewed for 10 seconds.
class ArmoryScreen extends StatefulWidget {
  const ArmoryScreen({super.key, required this.armory});

  final ArmoryController armory;

  @override
  State<ArmoryScreen> createState() => _ArmoryScreenState();
}

class _ArmoryScreenState extends State<ArmoryScreen> {
  bool _loading = false;
  bool _loadFailed = false;
  String? _actionError;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _loadFailed = false;
    });
    try {
      await widget.armory.load();
    } on KarmiApiException {
      if (mounted) setState(() => _loadFailed = true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _activate(KarmiTier tier) async {
    setState(() => _actionError = null);
    try {
      await widget.armory.activate(tier);
    } on LockedTierException {
      setState(() => _actionError = '${tier.label} is locked on your plan.');
    } on TierLockedException {
      if (mounted) {
        setState(
          () => _actionError =
              '${tier.label} is not available on your current plan. '
              'Your theme was reset to one you have unlocked.',
        );
      }
    } on KarmiApiException {
      if (mounted) {
        setState(
          () => _actionError =
              "Couldn't change the theme. Check your connection and try again.",
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final colors = KarmiColors.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Armory')),
      body: SafeArea(
        top: false,
        child: ListenableBuilder(
          listenable: widget.armory,
          builder: (context, _) {
            final armory = widget.armory;
            final list = ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text(
                  'Themes unlock with your plan. Your assistant works the same '
                  'in every theme.',
                  style: text.bodyLarge,
                ),
                const SizedBox(height: 8),
                Text(
                  armory.appIconSupported == false
                      ? 'This device keeps the default app icon.'
                      : 'Activating a theme also changes the app icon on your '
                            'home screen.',
                  style: text.bodyMedium?.copyWith(
                    color: colors.mutedForeground,
                  ),
                ),
                const SizedBox(height: 16),
                if (_loadFailed) ...[
                  ErrorBanner(
                    icon: Icons.cloud_off,
                    tone: ErrorTone.warning,
                    title: 'Showing your last known themes',
                    message:
                        "Karmi couldn't reach the server to check your plan.",
                    actionLabel: 'Retry',
                    onAction: _refresh,
                  ),
                  const SizedBox(height: 16),
                ],
                if (_actionError != null) ...[
                  ErrorBanner(
                    title: 'Theme not changed',
                    message: _actionError!,
                  ),
                  const SizedBox(height: 16),
                ],
                if (_loading && !armory.isLoaded)
                  const Padding(
                    padding: EdgeInsets.only(bottom: 16),
                    child: KarmiLoader(label: 'Checking your plan'),
                  ),
                for (final tier in KarmiTier.values) ...[
                  TierCard(
                    tier: tier,
                    armory: armory,
                    onActivate: () => _activate(tier),
                  ),
                  const SizedBox(height: 12),
                ],
              ],
            );
            // The preview banner stays pinned above the gallery, so the
            // countdown and "End preview" are visible wherever the user
            // has scrolled.
            return Column(
              children: [
                if (armory.isPreviewing)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                    child: ArmoryPreviewBanner(armory: armory),
                  ),
                Expanded(child: list),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// One tier in the gallery.
class TierCard extends StatelessWidget {
  const TierCard({
    super.key,
    required this.tier,
    required this.armory,
    required this.onActivate,
  });

  final KarmiTier tier;
  final ArmoryController armory;
  final VoidCallback onActivate;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final colors = KarmiColors.of(context);
    final locked = armory.isLocked(tier);
    final active = armory.activeTheme == tier;
    final previewing = armory.previewTier == tier;

    final status = active
        ? const StatusChip(
            label: 'Active',
            icon: Icons.check_circle_outline,
            tone: StatusTone.success,
          )
        : locked
        ? const StatusChip(
            label: 'Locked',
            icon: Icons.lock_outline,
            tone: StatusTone.neutral,
          )
        : const StatusChip(
            label: 'Unlocked',
            icon: Icons.lock_open,
            tone: StatusTone.info,
          );

    return Card(
      key: ValueKey('tier-card-${tier.name}'),
      clipBehavior: Clip.antiAlias,
      semanticContainer: false,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TierPreviewArt(tier: tier, locked: locked),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Semantics(
                  header: true,
                  child: Text(tier.label, style: text.titleLarge),
                ),
                status,
              ],
            ),
            Text(tier.tagline, style: text.bodyMedium),
            if (locked) ...[
              const SizedBox(height: 4),
              Text(
                'Unlocks with the ${tier.label} plan.',
                style: text.bodyMedium?.copyWith(color: colors.mutedForeground),
              ),
            ],
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              children: [
                if (!active)
                  FilledButton(
                    // Locked tiers cannot be activated.
                    onPressed: locked || armory.isBusy ? null : onActivate,
                    child: Text(
                      locked ? 'Locked' : 'Activate',
                      semanticsLabel: locked
                          ? 'Activate ${tier.label}, locked'
                          : 'Activate ${tier.label}',
                    ),
                  ),
                if (locked)
                  OutlinedButton.icon(
                    onPressed: previewing
                        ? armory.endPreview
                        : () => armory.startPreview(tier),
                    icon: Icon(previewing ? Icons.stop : Icons.visibility),
                    label: Text(
                      previewing ? 'End preview' : 'Preview 10 s',
                      semanticsLabel: previewing
                          ? 'End ${tier.label} preview'
                          : 'Preview ${tier.label} for 10 seconds',
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Tier icon plus its palette. Locked tiers: `blur(4px) grayscale(80%)` and a
/// padlock (implementation_plan.md §3.2).
class TierPreviewArt extends StatelessWidget {
  const TierPreviewArt({super.key, required this.tier, required this.locked});

  final KarmiTier tier;
  final bool locked;

  static const _grayscale80 = <double>[
    // 0.2 * identity + 0.8 * luminance
    0.3701, 0.5722, 0.0578, 0, 0, //
    0.1701, 0.7722, 0.0578, 0, 0, //
    0.1701, 0.5722, 0.2578, 0, 0, //
    0, 0, 0, 1, 0,
  ];

  @override
  Widget build(BuildContext context) {
    final brightness = Theme.of(context).brightness;
    final palette = KarmiColors.forTier(tier, brightness);
    final colors = KarmiColors.of(context);
    Widget art = ExcludeSemantics(
      child: Container(
        height: 96,
        decoration: BoxDecoration(
          color: palette.background,
          borderRadius: BorderRadius.circular(KarmiShape.controlRadius),
          border: Border.all(color: palette.borderSubtle),
        ),
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: Image.asset(
                'assets/app_icons/${tier.name}.webp',
                width: 72,
                height: 72,
                fit: BoxFit.cover,
              ),
            ),
            const SizedBox(width: 12),
            for (final swatch in [
              palette.primary,
              palette.header,
              palette.accent,
              palette.foreground,
            ]) ...[
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  color: swatch,
                  shape: BoxShape.circle,
                  border: Border.all(color: palette.border),
                ),
              ),
              const SizedBox(width: 8),
            ],
          ],
        ),
      ),
    );
    if (!locked) return art;
    art = ImageFiltered(
      key: ValueKey('locked-filter-${tier.name}'),
      imageFilter: ImageFilter.blur(sigmaX: 4, sigmaY: 4),
      child: ColorFiltered(
        colorFilter: const ColorFilter.matrix(_grayscale80),
        child: art,
      ),
    );
    return Stack(
      alignment: Alignment.center,
      children: [
        art,
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(color: colors.card, shape: BoxShape.circle),
          child: Icon(
            Icons.lock,
            color: colors.foreground,
            semanticLabel: '${tier.label} locked',
          ),
        ),
      ],
    );
  }
}

/// Glass banner shown while a locked tier is being previewed: tier name, a
/// live countdown and an "End preview" control.
class ArmoryPreviewBanner extends StatefulWidget {
  const ArmoryPreviewBanner({super.key, required this.armory});

  final ArmoryController armory;

  @override
  State<ArmoryPreviewBanner> createState() => _ArmoryPreviewBannerState();
}

class _ArmoryPreviewBannerState extends State<ArmoryPreviewBanner> {
  Timer? _tick;

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tier = widget.armory.previewTier;
    if (tier == null) return const SizedBox.shrink();
    final text = Theme.of(context).textTheme;
    final seconds = (widget.armory.previewRemaining.inMilliseconds / 1000)
        .ceil();
    return KarmiGlassSurface(
      key: const ValueKey('armory-preview-banner'),
      padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
      child: Row(
        children: [
          const Icon(Icons.visibility),
          const SizedBox(width: 12),
          Expanded(
            child: Semantics(
              liveRegion: true,
              child: Text(
                'Previewing ${tier.label} · ${seconds}s left',
                style: text.titleMedium,
              ),
            ),
          ),
          TextButton(
            onPressed: widget.armory.endPreview,
            child: const Text('End preview'),
          ),
        ],
      ),
    );
  }
}
