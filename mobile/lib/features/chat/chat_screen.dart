import 'package:flutter/material.dart';

import '../../api/conversations/conversations_api.dart';
import '../../api/karmi_api.dart';
import '../../api/stream/run_stream_client.dart';
import '../../shell/breakpoints.dart';
import '../../widgets/feedback.dart';
import '../../widgets/karmi_card.dart';
import '../history/conversation_list.dart';
import '../history/conversation_list_controller.dart';
import '../tasks/task_confirmation_sheet.dart';
import 'composer.dart';
import 'composer/draft_store.dart';
import 'error_card.dart';
import 'message_bubble.dart';
import 'processing_panel.dart';
import 'scroll/end_anchored_scroll.dart';
import 'scroll/jump_to_latest_button.dart';
import 'state/chat_controller.dart';

/// Chat tab: streaming messages, error recovery, history navigation, and rich rendering.
class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.api,
    this.onOpenPlans,
    this.conversationId,
    this.chatController,
    this.conversationListController,
    this.onConversationChanged,
    this.runStreamClient,
    this.conversationsApi,
    this.draftStore,
  });

  final KarmiApi api;
  final VoidCallback? onOpenPlans;
  final String? conversationId;
  final ChatController? chatController;
  final ConversationListController? conversationListController;
  final ValueChanged<String?>? onConversationChanged;
  final RunStreamClient? runStreamClient;
  final ConversationsApi? conversationsApi;
  final DraftStore? draftStore;

  /// Builds a history rail widget for wide layouts.
  static Widget historyRailBuilder({
    required BuildContext context,
    required ConversationListController controller,
    required ValueChanged<String> onOpen,
    required VoidCallback onNewChat,
  }) {
    return ConversationList(
      controller: controller,
      onOpen: onOpen,
      onNewChat: onNewChat,
    );
  }

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  late RunStreamClient _runStreamClient;
  late ConversationsApi _conversationsApi;
  late ChatController _chatController;
  late ConversationListController _conversationListController;
  late EndAnchoredScrollController _scrollController;
  bool _ownsChatController = false;
  bool _ownsConversationListController = false;
  bool _isLoadingMessages = false;
  String? _activeConversationId;

  final Map<String, FeedbackRating> _feedbackRatings = {};
  final Map<String, String> _feedbackReasons = {};
  final Set<String> _feedbackInFlight = {};
  ErrorCategory? _feedbackError;
  VoidCallback? _feedbackRetry;

  // Stable callbacks and memoized widget instances. A ChatScreen rebuild
  // (setState on a controller notify) must not hand Composer or unchanged
  // bubbles new instances; Flutter skips an element whose widget is identical.
  late final ValueChanged<ComposerSubmit> _composerSubmit = _submitComposer;
  late final VoidCallback _composerStop = _stopComposer;
  Widget? _composerWidget;
  String? _composerDraftKey;
  bool? _composerBusy;
  DraftStore? _composerDraftStore;
  final Map<String, _BubbleMemo> _bubbleMemos = {};
  @override
  void initState() {
    super.initState();
    _activeConversationId = widget.conversationId;
    _runStreamClient =
        widget.runStreamClient ?? RunStreamClient.fromApi(widget.api);
    _conversationsApi =
        widget.conversationsApi ??
        ConversationsApi(
          baseUrl: widget.api.baseUrl,
          tokenProvider: widget.api.tokenProvider,
          client: widget.api.client,
        );

    _scrollController = EndAnchoredScrollController();

    if (widget.chatController != null) {
      _chatController = widget.chatController!;
      _ownsChatController = false;
    } else {
      _chatController = ChatController(
        client: _runStreamClient,
        conversationId: _activeConversationId,
      );
      _ownsChatController = true;
    }
    _chatController.addListener(_onChatControllerChanged);

    if (widget.conversationListController != null) {
      _conversationListController = widget.conversationListController!;
      _ownsConversationListController = false;
    } else {
      _conversationListController = ConversationListController(
        api: _conversationsApi,
      );
      _ownsConversationListController = true;
      _conversationListController.refresh();
    }

    if (_activeConversationId != null && _chatController.messages.isEmpty) {
      _loadConversationMessages(_activeConversationId!);
    }
  }

  @override
  void didUpdateWidget(ChatScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.conversationId != oldWidget.conversationId &&
        widget.conversationId != _activeConversationId) {
      _activeConversationId = widget.conversationId;
      if (_activeConversationId != null) {
        _loadConversationMessages(_activeConversationId!);
      } else {
        _startNewChat();
      }
    }
  }

  @override
  void dispose() {
    _chatController.removeListener(_onChatControllerChanged);
    if (_ownsChatController) {
      _chatController.dispose();
    }
    if (_ownsConversationListController) {
      _conversationListController.dispose();
    }
    _scrollController.dispose();
    if (widget.conversationsApi == null) {
      _conversationsApi.close();
    }
    super.dispose();
  }

  void _onChatControllerChanged() {
    if (!mounted) return;
    if (_chatController.conversationId != null &&
        _chatController.conversationId != _activeConversationId) {
      _activeConversationId = _chatController.conversationId;
      widget.onConversationChanged?.call(_activeConversationId);
      _conversationListController.refresh();
    }
    setState(() {});
  }

  void _startNewChat() {
    if (_ownsChatController) {
      _chatController.removeListener(_onChatControllerChanged);
      _chatController.dispose();
      _activeConversationId = null;
      _chatController = ChatController(
        client: _runStreamClient,
        conversationId: null,
      );
      _chatController.addListener(_onChatControllerChanged);
    }
    widget.onConversationChanged?.call(null);
    _feedbackRatings.clear();
    _feedbackReasons.clear();
    _feedbackInFlight.clear();
    _feedbackError = null;
    _feedbackRetry = null;
    setState(() {});
  }

  Future<void> _loadConversationMessages(String conversationId) async {
    setState(() {
      _isLoadingMessages = true;
      _activeConversationId = conversationId;
    });

    if (_ownsChatController) {
      _chatController.stop();
    }

    try {
      final page = await _conversationsApi.messages(conversationId);
      if (!mounted) return;
      if (_activeConversationId != conversationId) return;

      if (_ownsChatController) {
        _chatController.removeListener(_onChatControllerChanged);
        _chatController.dispose();
        _chatController = ChatController(
          client: _runStreamClient,
          conversationId: conversationId,
          initialMessages: page.items,
        );
        _chatController.addListener(_onChatControllerChanged);
      }
      widget.onConversationChanged?.call(conversationId);
    } catch (e) {
      // In case of error loading messages, retain state
    } finally {
      if (mounted && _activeConversationId == conversationId) {
        setState(() => _isLoadingMessages = false);
      }
    }
  }

  Future<void> _onFeedback(
    ChatMessageView message,
    FeedbackRating rating,
  ) async {
    final runId = message.runId ?? _chatController.currentRunId;
    if (runId == null) return;

    setState(() {
      _feedbackRatings[message.id] = rating;
      if (rating == FeedbackRating.up) {
        _feedbackReasons.remove(message.id);
      }
      _feedbackInFlight.add(message.id);
      _feedbackError = null;
      _feedbackRetry = null;
    });

    try {
      await widget.api.sendFeedback(
        runId,
        rating: rating,
        reason: _feedbackReasons[message.id],
      );
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _feedbackError = ErrorCategory.internal;
        _feedbackRetry = () => _onFeedback(message, rating);
      });
    } finally {
      if (mounted) {
        setState(() {
          _feedbackInFlight.remove(message.id);
        });
      }
    }
  }

  Future<void> _onSelectReason(ChatMessageView message, String reason) async {
    final runId = message.runId ?? _chatController.currentRunId;
    if (runId == null) return;

    setState(() {
      _feedbackReasons[message.id] = reason;
      _feedbackInFlight.add(message.id);
      _feedbackError = null;
      _feedbackRetry = null;
    });

    try {
      await widget.api.sendFeedback(
        runId,
        rating: _feedbackRatings[message.id] ?? FeedbackRating.down,
        reason: reason,
      );
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _feedbackError = ErrorCategory.internal;
        _feedbackRetry = () => _onSelectReason(message, reason);
      });
    } finally {
      if (mounted) {
        setState(() {
          _feedbackInFlight.remove(message.id);
        });
      }
    }
  }

  void _retryLast() {
    if (_chatController.currentClientMessageId != null ||
        _chatController.currentRunId != null) {
      _chatController.resume();
      return;
    }
    final lastUser = _chatController.messages
        .where((m) => m.role == 'user')
        .lastOrNull;
    if (lastUser != null) {
      _chatController.send(lastUser.content);
    }
  }

  void _continueLast() {
    final lastAssistant = _chatController.messages
        .where((m) => m.role == 'assistant')
        .lastOrNull;
    if (lastAssistant != null) {
      _chatController.continueMessage(lastAssistant.id);
    }
  }

  bool get _isBusy =>
      _chatController.phase == ChatRunPhase.sending ||
      _chatController.phase == ChatRunPhase.streaming ||
      _chatController.phase == ChatRunPhase.stalled;

  void _openHistoryModal() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (sheetContext) => SizedBox(
        height: MediaQuery.sizeOf(sheetContext).height * 0.8,
        child: ConversationList(
          controller: _conversationListController,
          onOpen: (id) {
            Navigator.of(sheetContext).pop();
            _loadConversationMessages(id);
          },
          onNewChat: () {
            Navigator.of(sheetContext).pop();
            _startNewChat();
          },
        ),
      ),
    );
  }

  Widget _buildTopBar(BuildContext context) {
    final isExpanded = WorkspaceSize.of(context) == WorkspaceSize.expanded;
    if (isExpanded) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Row(
        children: [
          IconButton(
            icon: const Icon(Icons.history),
            tooltip: 'Conversation history',
            onPressed: _openHistoryModal,
          ),
          IconButton(
            icon: const Icon(Icons.add),
            tooltip: 'New chat',
            onPressed: _startNewChat,
          ),
          const Spacer(),
          if (widget.onOpenPlans != null)
            TextButton.icon(
              icon: const Icon(Icons.star_outline, size: 16),
              label: const Text('Plans'),
              onPressed: widget.onOpenPlans,
            ),
        ],
      ),
    );
  }

  void _submitComposer(ComposerSubmit submit) {
    final attachments = submit.attachments
        .map((a) => a.toFencedBlock())
        .toList();
    _chatController.send(submit.text, attachments);
  }

  void _stopComposer() => _chatController.stop();

  /// Returns the same Composer instance while its inputs are unchanged.
  Widget _buildComposer() {
    final draftKey = _activeConversationId ?? 'new';
    final busy = _isBusy;
    final draftStore = widget.draftStore;
    if (_composerWidget == null ||
        draftKey != _composerDraftKey ||
        busy != _composerBusy ||
        !identical(draftStore, _composerDraftStore)) {
      _composerDraftKey = draftKey;
      _composerBusy = busy;
      _composerDraftStore = draftStore;
      _composerWidget = Composer(
        draftKey: draftKey,
        draftStore: draftStore,
        busy: busy,
        onSubmit: _composerSubmit,
        onStop: _composerStop,
      );
    }
    return _composerWidget!;
  }

  /// Returns the cached bubble widget when the message object and every input
  /// the bubble reads are unchanged; otherwise builds and records a new one.
  Widget _memoBubble(
    ChatMessageView msg,
    int index,
    int count,
    int lastAssistantIndex,
  ) {
    final memo = _BubbleMemo(
      msg: msg,
      announce: index == count - 1 && msg.role == 'assistant',
      isLastAssistant: index == lastAssistantIndex,
      busy: _isBusy,
      feedbackRating: _feedbackRatings[msg.id],
      feedbackReason: _feedbackReasons[msg.id],
      isFeedbackInFlight: _feedbackInFlight.contains(msg.id),
    );
    final cached = _bubbleMemos[msg.id];
    if (cached != null && cached.sameInputs(memo)) {
      return cached.widget;
    }
    memo.widget = _buildChatBubble(msg, index, count, lastAssistantIndex);
    _bubbleMemos[msg.id] = memo;
    return memo.widget;
  }

  Widget _buildChatBubble(
    ChatMessageView msg,
    int index,
    int count,
    int lastAssistantIndex,
  ) {
    final isLastAssistant = index == lastAssistantIndex;
    return MessageBubble.chatMessage(
      key: ValueKey(msg.id),
      chatMessage: msg,
      announce: index == count - 1 && msg.role == 'assistant',
      onContinue: msg.finishReason == FinishReason.length
          ? () => _chatController.continueMessage(msg.id)
          : null,
      onResume:
          (msg.finishReason == FinishReason.interrupted ||
              msg.status == MessageStatus.interrupted)
          ? _chatController.resume
          : null,
      onRegenerate: isLastAssistant && !_isBusy
          ? () => _chatController.regenerate(msg.id)
          : null,
      onReviewDetails: msg.outcome == Outcome.askUser
          ? () => showTaskConfirmationSheet(
              context,
              MessageView(
                runId: msg.runId ?? msg.id,
                status: msg.status.wireName,
                outcome: Outcome.askUser,
                response: msg.content,
              ),
            )
          : null,
      onFeedback: msg.role == 'assistant'
          ? (rating) => _onFeedback(msg, rating)
          : null,
      onSelectReason: msg.role == 'assistant'
          ? (reason) => _onSelectReason(msg, reason)
          : null,
      feedbackRating: _feedbackRatings[msg.id],
      feedbackReason: _feedbackReasons[msg.id],
      isFeedbackInFlight: _feedbackInFlight.contains(msg.id),
    );
  }

  @override
  Widget build(BuildContext context) {
    final insets = karmiPageInsets(context);
    final messages = _chatController.messages;
    final lastAssistantIndex = messages.lastIndexWhere(
      (m) => m.role == 'assistant',
    );

    return Column(
      children: [
        _buildTopBar(context),
        if (_isLoadingMessages) const LinearProgressIndicator(minHeight: 2),
        Expanded(
          child: Stack(
            children: [
              EndAnchoredScroll(
                controller: _scrollController,
                builder: (context, scrollController, physics) {
                  if (messages.isEmpty) {
                    return ListView(
                      controller: scrollController,
                      physics: physics,
                      padding: insets.copyWith(bottom: 16),
                      children: const [
                        EmptyState(
                          quote:
                              'Ask a study question, or get help with maths or code.',
                          body:
                              'Each reply shows its status, such as "Completed" or '
                              '"Awaiting confirmation".',
                        ),
                      ],
                    );
                  }

                  return ListView.builder(
                    controller: scrollController,
                    physics: physics,
                    padding: insets.copyWith(bottom: 16),
                    itemCount: messages.length,
                    itemBuilder: (context, index) {
                      final msg = messages[index];
                      if (msg.status != MessageStatus.streaming) {
                        return _memoBubble(
                          msg,
                          index,
                          messages.length,
                          lastAssistantIndex,
                        );
                      }
                      // Only the streaming bubble rebuilds on each delta flush.
                      return ValueListenableBuilder<int>(
                        valueListenable: _chatController.streamRevision,
                        builder: (context, _, child) => _buildChatBubble(
                          _chatController.messageById(msg.id) ?? msg,
                          index,
                          messages.length,
                          lastAssistantIndex,
                        ),
                      );
                    },
                  );
                },
              ),
              Positioned(
                bottom: 12,
                right: 16,
                child: ValueListenableBuilder<bool>(
                  valueListenable: _scrollController.isAtBottom,
                  builder: (context, isAtBottom, _) {
                    return ValueListenableBuilder<bool>(
                      valueListenable: _scrollController.hasNewContent,
                      builder: (context, hasNewContent, _) {
                        return JumpToLatestButton(
                          visible: !isAtBottom,
                          hasNewContent: hasNewContent,
                          onTap: _scrollController.jumpToLatest,
                        );
                      },
                    );
                  },
                ),
              ),
            ],
          ),
        ),
        ProcessingPanel(phase: _chatController.phase),
        if (_chatController.error != null || _feedbackError != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: ErrorCard(
              category: _chatController.error ?? _feedbackError!,
              onRetry: _chatController.error != null
                  ? _retryLast
                  : _feedbackRetry,
              onContinue: _continueLast,
              onUpgrade: widget.onOpenPlans,
            ),
          ),
        Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.paddingOf(context).bottom,
          ),
          child: _buildComposer(),
        ),
      ],
    );
  }
}

/// Inputs a non-streaming bubble reads from ChatScreen state. Closures in the
/// cached widget read controller/state at call time, so equal inputs mean an
/// identical bubble.
class _BubbleMemo {
  _BubbleMemo({
    required this.msg,
    required this.announce,
    required this.isLastAssistant,
    required this.busy,
    required this.feedbackRating,
    required this.feedbackReason,
    required this.isFeedbackInFlight,
  });

  final ChatMessageView msg;
  final bool announce;
  final bool isLastAssistant;
  final bool busy;
  final FeedbackRating? feedbackRating;
  final String? feedbackReason;
  final bool isFeedbackInFlight;
  late Widget widget;

  bool sameInputs(_BubbleMemo other) =>
      identical(msg, other.msg) &&
      announce == other.announce &&
      isLastAssistant == other.isLastAssistant &&
      busy == other.busy &&
      feedbackRating == other.feedbackRating &&
      feedbackReason == other.feedbackReason &&
      isFeedbackInFlight == other.isFeedbackInFlight;
}
