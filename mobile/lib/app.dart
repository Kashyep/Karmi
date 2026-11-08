import 'dart:async';

import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart';

import 'api/conversations/conversations_api.dart';
import 'armory/armory_controller.dart';
import 'auth/session.dart';
import 'features/admin/admin_controller.dart';
import 'features/admin/admin_shell.dart';
import 'features/history/conversation_list.dart';
import 'features/history/conversation_list_controller.dart';
import 'features/onboarding/onboarding.dart';
import 'features/plans/plan_selection_screen.dart';
import 'features/welcome/tester_notice.dart';
import 'features/welcome/tester_notice_screen.dart';
import 'notifications/karmi_notifications.dart';
import 'settings/karmi_settings.dart';
import 'shell/karmi_shell.dart';
import 'shell/chat_history_commands.dart';
import 'shell/history_panel.dart';
import 'theme/karmi_glass.dart';
import 'theme/karmi_motion.dart';
import 'theme/karmi_theme.dart';

/// Root widget and dual-axis theme provider (implementation_plan.md §2.1):
/// mode (System/Light/Dark, [KarmiSettings]) × tier ([ArmoryController]).
/// Both are applied once at the root — the Flutter equivalent of
/// `<html data-theme data-tier>` — by picking a cached [ThemeData].
class KarmiApp extends StatefulWidget {
  const KarmiApp({
    super.key,
    required this.settings,
    required this.session,
    required this.armory,
    this.adaptiveGlassQuality = true,
    this.clock,
    this.admin,
    this.requestNotificationPermission,
  });

  final KarmiSettings settings;
  final KarmiSession session;
  final ArmoryController armory;

  /// Runs liquid_glass_widgets' device benchmark. Off in widget tests.
  final bool adaptiveGlassQuality;

  /// Injected into the chat empty-state greeting; null uses the wall clock.
  final DateTime Function()? clock;

  /// Admin console controller; null disables the admin entry point.
  final AdminController? admin;

  /// Injected notification permission requester; null defaults to
  /// [KarmiNotifications.instance.requestPermission].
  final Future<bool> Function()? requestNotificationPermission;

  @override
  State<KarmiApp> createState() => _KarmiAppState();
}

class _KarmiAppState extends State<KarmiApp> {
  final _navigatorKey = GlobalKey<NavigatorState>();
  late bool _signedIn = widget.session.isSignedIn;
  final _historyCommands = ChatHistoryCommands();
  ConversationsApi? _conversationsApi;
  ConversationListController? _conversationListController;

  bool _notificationPromptScheduled = false;

  Future<bool> _requestNotificationPermission() {
    final requester =
        widget.requestNotificationPermission ??
        KarmiNotifications.instance.requestPermission;
    return requester();
  }

  void _checkAndPromptNotificationPermission(bool isShowingShell) {
    if (isShowingShell &&
        !widget.settings.notificationPermissionRequested &&
        !_notificationPromptScheduled) {
      _notificationPromptScheduled = true;
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        if (!mounted) return;
        if (widget.settings.notificationPermissionRequested) return;
        await widget.settings.setNotificationPermissionRequested(true);
        if (!mounted) return;
        await _requestNotificationPermission();
      });
    }
  }

  @override
  void initState() {
    super.initState();
    widget.session.addListener(_onSession);
    if (_signedIn) {
      _loadArmory();
      _ensureConversationController();
      unawaited(widget.admin?.probe());
    }
  }

  @override
  void dispose() {
    widget.session.removeListener(_onSession);
    _historyCommands.dispose();
    super.dispose();
    _conversationListController?.dispose();
    _conversationsApi?.close();
  }

  ConversationListController _ensureConversationController() {
    final existing = _conversationListController;
    if (existing != null) return existing;
    final api = _conversationsApi ??= ConversationsApi(
      baseUrl: widget.session.api.baseUrl,
      client: widget.session.api.client,
      tokenProvider:
          widget.session.api.tokenProvider ??
          () async => widget.session.api.token,
    );
    final controller = ConversationListController(api: api);
    _conversationListController = controller;
    unawaited(controller.refresh());
    return controller;
  }

  /// Progression is server-authoritative; a failed fetch keeps the cached
  /// (already clamped) tier, and 401s are handled by the session.
  Future<void> _loadArmory() async {
    try {
      await widget.armory.load();
    } on Exception {
      // Keep the cached tier; the Armory screen offers a retry.
    }
  }

  /// Sign-in loads the tier; sign-out or 401 drops pushed routes so Welcome
  /// is on top and forgets the account's tier.
  void _onSession() {
    final signedIn = widget.session.isSignedIn;
    if (_signedIn && !signedIn) {
      _navigatorKey.currentState?.popUntil((route) => route.isFirst);
      widget.armory.reset();
      widget.admin?.reset();
      _conversationListController?.dispose();
      _conversationListController = null;
      _conversationsApi?.close();
      _conversationsApi = null;
    } else if (!_signedIn && signedIn) {
      _loadArmory();
      _ensureConversationController();
      unawaited(widget.admin?.probe());
    }
    setState(() => _signedIn = signedIn);
  }

  void _openPlanSelection([String? preselectedPlanId]) {
    final nav = _navigatorKey.currentState;
    if (nav == null) return;
    nav.push(
      KarmiMotion.route<void>(
        nav.context,
        (_) => PlanSelectionScreen(
          currentPlanId: widget.armory.unlockedTier.planId,
          preselectedPlanId: preselectedPlanId,
          api: widget.session.api,
          onPlanChanged: widget.armory.load,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([
        widget.settings,
        widget.armory,
        if (widget.admin != null) widget.admin!,
      ]),
      builder: (context, _) {
        final tier = widget.armory.effectiveTier;
        final bool showTesterNotice = !widget.settings
            .isTesterNoticeAcknowledged(kTesterNoticeVersion);
        final bool showAdminShell = _signedIn && widget.admin?.isActive == true;
        final bool showShell =
            _signedIn && widget.settings.hasCompletedOnboarding;
        final bool isShowingShell =
            !showTesterNotice && !showAdminShell && showShell;

        _checkAndPromptNotificationPermission(isShowingShell);
        return LiquidGlassWidgets.wrap(
          theme: KarmiGlass.themeData(tier),
          brightnessResolver: Theme.maybeBrightnessOf,
          adaptiveQuality: widget.adaptiveGlassQuality,
          child: MaterialApp(
            navigatorKey: _navigatorKey,
            title: 'Karmi',
            debugShowCheckedModeBanner: false,
            theme: KarmiTheme.of(tier, Brightness.light),
            darkTheme: KarmiTheme.of(tier, Brightness.dark),
            highContrastTheme: KarmiTheme.of(
              tier,
              Brightness.light,
              highContrast: true,
            ),
            highContrastDarkTheme: KarmiTheme.of(
              tier,
              Brightness.dark,
              highContrast: true,
            ),
            themeMode: widget.settings.themeMode,
            themeAnimationDuration: Duration.zero,
            builder: karmiAccessibilityBuilder(widget.settings),
            home: showTesterNotice
                ? TesterNoticeScreen(
                    key: const ValueKey('tester_notice'),
                    onAcknowledge: () => widget.settings
                        .acknowledgeTesterNotice(kTesterNoticeVersion),
                  )
                : showAdminShell
                ? AdminShell(
                    key: const ValueKey('admin_shell'),
                    controller: widget.admin!,
                  )
                : showShell
                ? KarmiShell(
                    key: const ValueKey('shell'),
                    api: widget.session.api,
                    settings: widget.settings,
                    session: widget.session,
                    clock: widget.clock,
                    armory: widget.armory,
                    admin: widget.admin,
                    historyCommands: _historyCommands,
                    historyRailBuilder: (context) => Builder(
                      builder: (innerContext) =>
                          ValueListenableBuilder<String?>(
                            valueListenable: _historyCommands.activeId,
                            builder: (_, activeId, __) => ConversationList(
                              controller: _ensureConversationController(),
                              activeConversationId: activeId,
                              clock: widget.clock,
                              onOpen: (id) {
                                _historyCommands.openConversation?.call(id);
                                HistoryPanelScope.maybeOf(
                                  innerContext,
                                )?.closeHistory();
                                final scaffold = Scaffold.maybeOf(innerContext);
                                if (scaffold != null && scaffold.isDrawerOpen) {
                                  scaffold.closeDrawer();
                                }
                              },
                              onNewChat: () {
                                _historyCommands.newChat?.call();
                                HistoryPanelScope.maybeOf(
                                  innerContext,
                                )?.closeHistory();
                                final scaffold = Scaffold.maybeOf(innerContext);
                                if (scaffold != null && scaffold.isDrawerOpen) {
                                  scaffold.closeDrawer();
                                }
                              },
                            ),
                          ),
                    ),
                  )
                : OnboardingFlow(
                    key: const ValueKey('onboarding_flow'),
                    session: widget.session,
                    settings: widget.settings,
                    requestNotificationPermission: () async {
                      _notificationPromptScheduled = true;
                      await widget.settings.setNotificationPermissionRequested(
                        true,
                      );
                      return _requestNotificationPermission();
                    },
                    onComplete: (selectedPlanId) {
                      _notificationPromptScheduled = true;
                      unawaited(
                        widget.settings.setNotificationPermissionRequested(
                          true,
                        ),
                      );
                      if (selectedPlanId != null &&
                          selectedPlanId != 'ananta') {
                        WidgetsBinding.instance.addPostFrameCallback((_) {
                          _openPlanSelection(selectedPlanId);
                        });
                        WidgetsBinding.instance.ensureVisualUpdate();
                      }
                    },
                  ),
          ),
        );
      },
    );
  }
}

/// `MaterialApp.builder`: resolves reduce transparency (setting OR platform
/// high contrast) and reduced motion once, for Karmi widgets and glass widgets.
TransitionBuilder karmiAccessibilityBuilder(KarmiSettings settings) =>
    (context, child) {
      final reduceTransparency =
          settings.reduceTransparency || MediaQuery.highContrastOf(context);
      final reduceMotion = MediaQuery.disableAnimationsOf(context);
      return KarmiAccessibility(
        reduceTransparency: reduceTransparency,
        reduceMotion: reduceMotion,
        child: GlassAccessibilityScope(
          reduceTransparency: reduceTransparency,
          reduceMotion: reduceMotion,
          // liquid_glass_widgets "Known Limitations": no yellow underlines.
          child: Material(type: MaterialType.transparency, child: child),
        ),
      );
    };
