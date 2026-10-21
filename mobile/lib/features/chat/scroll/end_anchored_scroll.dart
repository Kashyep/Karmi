import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import '../../../theme/karmi_motion.dart';
import '../../../theme/karmi_tokens.dart';

/// Controller coordinating end-anchored scroll state.
///
/// Extends [ChangeNotifier] and owns an underlying [ScrollController] (or wraps
/// a provided one). If instantiated without an existing controller, it disposes
/// the owned [ScrollController] on [dispose].
class EndAnchoredScrollController extends ChangeNotifier {
  EndAnchoredScrollController({
    ScrollController? scrollController,
    this.bottomThreshold = 48.0,
    bool initialPinned = true,
  })  : _scrollController = scrollController ?? ScrollController(),
        _ownsScrollController = scrollController == null,
        _isAtBottom = ValueNotifier<bool>(initialPinned),
        _hasNewContent = ValueNotifier<bool>(false);

  final ScrollController _scrollController;
  final bool _ownsScrollController;

  /// Distance from [ScrollMetrics.maxScrollExtent] considered "at bottom".
  double bottomThreshold;

  final ValueNotifier<bool> _isAtBottom;
  final ValueNotifier<bool> _hasNewContent;

  /// Duration callback provided by [EndAnchoredScroll] based on the current
  /// [BuildContext] and motion preferences.
  Duration Function()? _durationResolver;

  /// The underlying [ScrollController] attached to the scrollable view.
  ScrollController get scrollController => _scrollController;

  /// True when scroll position is within [bottomThreshold] of the bottom.
  ValueListenable<bool> get isAtBottom => _isAtBottom;

  /// Convenient getter for current pinned / at-bottom state.
  bool get isPinned => _isAtBottom.value;

  /// True when content has grown while the user is scrolled away from the bottom.
  ValueListenable<bool> get hasNewContent => _hasNewContent;

  /// Updates whether the position is at bottom.
  void updateAtBottom(bool value) {
    if (_isAtBottom.value != value) {
      _isAtBottom.value = value;
      notifyListeners();
    }
  }

  /// Updates whether there is unread new content below the current viewport.
  void updateHasNewContent(bool value) {
    if (_hasNewContent.value != value) {
      _hasNewContent.value = value;
      notifyListeners();
    }
  }

  /// Marks any pending new content as seen.
  void markContentSeen() {
    updateHasNewContent(false);
  }

  /// Animates (or jumps if reduced motion is enabled) to the latest content at
  /// the bottom of the scroll view.
  ///
  /// Clears [hasNewContent] and updates [isAtBottom] to true.
  void jumpToLatest({
    Duration? duration,
    Curve curve = Curves.easeOut,
    BuildContext? context,
  }) {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    final target = position.maxScrollExtent;

    final resolvedDuration = duration ??
        (context != null
            ? KarmiMotion.duration(context, KarmiTokens.standard)
            : null) ??
        _durationResolver?.call() ??
        KarmiTokens.standard;

    if (resolvedDuration == Duration.zero) {
      _scrollController.jumpTo(target);
    } else {
      _scrollController.animateTo(
        target,
        duration: resolvedDuration,
        curve: curve,
      );
    }
    _isAtBottom.value = true;
    _hasNewContent.value = false;
    notifyListeners();
  }

  @override
  void dispose() {
    _isAtBottom.dispose();
    _hasNewContent.dispose();
    if (_ownsScrollController) {
      _scrollController.dispose();
    }
    super.dispose();
  }
}

/// A widget that anchors scrolling to the end of a scrollable view.
///
/// Behaviour:
/// - When pinned ([controller.isAtBottom] is true) and content grows (detected
///   post-frame via [ScrollMetrics.maxScrollExtent] change), automatically jumps
///   to the new max extent so streaming content remains visible.
/// - When unpinned (user scrolled up past [bottomThreshold]), does NOT move the
///   scroll position on content growth; instead sets [controller.hasNewContent]
///   to true.
/// - When the user scrolls back within [bottomThreshold], re-pins and clears
///   [controller.hasNewContent].
/// - Honors user scroll gestures without yanking.
/// - Reverse-agnostic: operates on standard top-to-bottom scroll views.
class EndAnchoredScroll extends StatefulWidget {
  const EndAnchoredScroll({
    super.key,
    required this.controller,
    this.builder,
    this.child,
    this.pinned,
    this.bottomThreshold,
  }) : assert(
          builder != null || child != null,
          'Either builder or child must be provided to EndAnchoredScroll',
        );

  /// Controller managing scroll metrics and bottom anchoring.
  final EndAnchoredScrollController controller;

  /// Recommended builder giving the child list access to the configured
  /// [ScrollController] and [ScrollPhysics].
  final Widget Function(
    BuildContext context,
    ScrollController scrollController,
    ScrollPhysics physics,
  )? builder;

  /// Direct scrollable child, fallback if [builder] is not provided.
  final Widget? child;

  /// Explicit override to initialize or update pinned state.
  final bool? pinned;

  /// Optional override for bottom detection threshold.
  final double? bottomThreshold;

  @override
  State<EndAnchoredScroll> createState() => _EndAnchoredScrollState();
}

class _EndAnchoredScrollState extends State<EndAnchoredScroll> {
  double _lastMaxScrollExtent = 0.0;
  bool _postFrameCheckScheduled = false;
  bool _isUserInteracting = false;

  @override
  void initState() {
    super.initState();
    _applyThreshold();
    if (widget.pinned != null) {
      widget.controller.updateAtBottom(widget.pinned!);
    }
    widget.controller._durationResolver = _resolveDuration;
    widget.controller.scrollController.addListener(_onScroll);
    _schedulePostFrameCheck();
  }

  @override
  void didUpdateWidget(EndAnchoredScroll oldWidget) {
    super.didUpdateWidget(oldWidget);
    _applyThreshold();
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller.scrollController.removeListener(_onScroll);
      if (oldWidget.controller._durationResolver == _resolveDuration) {
        oldWidget.controller._durationResolver = null;
      }
      widget.controller.scrollController.addListener(_onScroll);
      widget.controller._durationResolver = _resolveDuration;
    }
    if (widget.pinned != null && widget.pinned != oldWidget.pinned) {
      widget.controller.updateAtBottom(widget.pinned!);
    }
    _schedulePostFrameCheck();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    widget.controller._durationResolver = _resolveDuration;
  }

  @override
  void dispose() {
    widget.controller.scrollController.removeListener(_onScroll);
    if (widget.controller._durationResolver == _resolveDuration) {
      widget.controller._durationResolver = null;
    }
    super.dispose();
  }

  void _applyThreshold() {
    if (widget.bottomThreshold != null) {
      widget.controller.bottomThreshold = widget.bottomThreshold!;
    }
  }

  Duration _resolveDuration() {
    return KarmiMotion.duration(context, KarmiTokens.standard);
  }

  void _onScroll() {
    if (!widget.controller.scrollController.hasClients) return;
    final position = widget.controller.scrollController.positions.first;
    if (!position.hasContentDimensions) return;

    final max = position.maxScrollExtent;
    final pixels = position.pixels;

    if (max != _lastMaxScrollExtent) {
      _schedulePostFrameCheck();
      return;
    }

    final distanceToBottom = max - pixels;
    final atBottom = distanceToBottom <= widget.controller.bottomThreshold;

    if (atBottom != widget.controller.isAtBottom.value) {
      widget.controller.updateAtBottom(atBottom);
    }

    // User scrolling back into threshold re-pins and clears hasNewContent.
    if (atBottom && widget.controller.hasNewContent.value) {
      widget.controller.updateHasNewContent(false);
    }
  }

  void _schedulePostFrameCheck() {
    if (_postFrameCheckScheduled) return;
    _postFrameCheckScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _postFrameCheckScheduled = false;
      if (!mounted) return;
      _checkExtentAndPosition();
    });
  }

  void _checkExtentAndPosition() {
    if (!widget.controller.scrollController.hasClients) return;
    final position = widget.controller.scrollController.positions.first;
    if (!position.hasContentDimensions) return;

    final currentMax = position.maxScrollExtent;
    final currentPixels = position.pixels;
    final previousMax = _lastMaxScrollExtent;
    _lastMaxScrollExtent = currentMax;

    if (currentMax > previousMax) {
      // Content extent grew.
      if (widget.controller.isAtBottom.value && !_isUserInteracting) {
        // Pinned and user is not actively gesturing: keep anchored at latest.
        if (position.pixels != currentMax) {
          widget.controller.scrollController.jumpTo(currentMax);
        }
        widget.controller.updateAtBottom(true);
        widget.controller.updateHasNewContent(false);
      } else {
        // User scrolled up or actively dragging: do not yank position.
        widget.controller.updateHasNewContent(true);
        final distanceToBottom = currentMax - currentPixels;
        widget.controller.updateAtBottom(
          distanceToBottom <= widget.controller.bottomThreshold,
        );
      }
    } else {
      final distanceToBottom = currentMax - currentPixels;
      final atBottom = distanceToBottom <= widget.controller.bottomThreshold;
      widget.controller.updateAtBottom(atBottom);
      if (atBottom) {
        widget.controller.updateHasNewContent(false);
      }
    }
  }

  bool _handleNotification(Notification notification) {
    if (notification is ScrollMetricsNotification) {
      if (notification.metrics.maxScrollExtent != _lastMaxScrollExtent) {
        _checkExtentAndPosition();
      }
    } else if (notification is ScrollNotification) {
      if (notification is ScrollStartNotification) {
        if (notification.dragDetails != null) {
          _isUserInteracting = true;
        }
      } else if (notification is UserScrollNotification) {
        if (notification.direction == ScrollDirection.idle) {
          _isUserInteracting = false;
        } else {
          _isUserInteracting = true;
        }
      } else if (notification is ScrollEndNotification) {
        _isUserInteracting = false;
      }

      if (notification.metrics.maxScrollExtent != _lastMaxScrollExtent) {
        _schedulePostFrameCheck();
      }
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    _schedulePostFrameCheck();

    final Widget content = widget.builder != null
        ? widget.builder!(
            context,
            widget.controller.scrollController,
            const AlwaysScrollableScrollPhysics(),
          )
        : PrimaryScrollController(
            controller: widget.controller.scrollController,
            child: widget.child!,
          );

    return NotificationListener<Notification>(
      onNotification: _handleNotification,
      child: content,
    );
  }
}
