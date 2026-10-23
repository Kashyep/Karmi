import 'dart:async';

import 'package:flutter/material.dart';

import '../theme/karmi_glass.dart';
import 'armory_controller.dart';

/// Compact glass pill shown while a locked tier is being previewed.
///
/// Houses the active preview tier name, a 1-second countdown, and an
/// "End preview" button. The countdown ticks inside a [ValueNotifier] so only
/// the [Text] widget rebuilds every second, not the surrounding chrome.
class ArmoryPreviewBanner extends StatefulWidget {
  const ArmoryPreviewBanner({super.key, required this.armory});

  final ArmoryController armory;

  @override
  State<ArmoryPreviewBanner> createState() => _ArmoryPreviewBannerState();
}

class _ArmoryPreviewBannerState extends State<ArmoryPreviewBanner> {
  late final ValueNotifier<int> _secondsRemaining;
  Timer? _tick;

  int _currentSeconds() =>
      (widget.armory.previewRemaining.inMilliseconds / 1000).ceil();

  @override
  void initState() {
    super.initState();
    _secondsRemaining = ValueNotifier<int>(_currentSeconds());
    widget.armory.addListener(_onArmoryChanged);
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) {
        _secondsRemaining.value = _currentSeconds();
      }
    });
  }

  void _onArmoryChanged() {
    if (mounted) {
      _secondsRemaining.value = _currentSeconds();
      setState(() {});
    }
  }

  @override
  void didUpdateWidget(covariant ArmoryPreviewBanner oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.armory != widget.armory) {
      oldWidget.armory.removeListener(_onArmoryChanged);
      widget.armory.addListener(_onArmoryChanged);
      _secondsRemaining.value = _currentSeconds();
    }
  }

  @override
  void dispose() {
    widget.armory.removeListener(_onArmoryChanged);
    _tick?.cancel();
    _secondsRemaining.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tier = widget.armory.previewTier;
    if (tier == null) return const SizedBox.shrink();
    final text = Theme.of(context).textTheme;

    return KarmiGlassSurface(
      key: const ValueKey('armory-preview-banner'),
      radius: 20,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.visibility, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: ValueListenableBuilder<int>(
              valueListenable: _secondsRemaining,
              builder: (context, seconds, _) => Semantics(
                liveRegion: true,
                child: Text(
                  'Previewing ${tier.label} · ${seconds}s left',
                  style: text.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),
          TextButton(
            style: TextButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              minimumSize: const Size(44, 32),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            onPressed: widget.armory.endPreview,
            child: const Text('End preview'),
          ),
        ],
      ),
    );
  }
}
