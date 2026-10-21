import 'package:flutter/material.dart';

import '../../api/conversations/conversations_api.dart';
import '../../api/karmi_api.dart';
import '../../api/stream/run_stream_client.dart';
import '../../shell/breakpoints.dart';
import '../../widgets/feedback.dart';
import '../../widgets/karmi_card.dart';
import '../history/conversation_list.dart';
import '../history/conversation_list_controller.dart';
import 'composer.dart';
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
  });

  final KarmiApi api;
  final VoidCallback? onOpenPlans;
  final String? conversationId;
  final ChatController? chatController;
  final ConversationListController? conversationListController;
  final ValueChanged<String?>? onConversationChanged;

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

  @override
  void initState() {
    super.initState();
    _activeConversationId = widget.conversationId;
    _runStreamClient = RunStreamClient.fromApi(widget.api);
    _conversationsApi = ConversationsApi(
      baseUrl: widget.api.baseUrl,
      tokenProvider: widget.api.tokenProvider,
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
    _conversationsApi.close();
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
    setState(() {});
  }

  Future<void> _loadConversationMessages(String conversationId) async {
    setState(() {
      _isLoadingMessages = true;
      _activeConversationId = conversationId;
    });

    try {
      final page = await _conversationsApi.messages(conversationId);
      if (!mounted) return;

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
      if (mounted) {
        setState(() => _isLoadingMessages = false);
      }
    }
  }

  void _retryLast() {
    final lastUser =
        _chatController.messages.where((m) => m.role == 'user').lastOrNull;
    if (lastUser != null) {
      _chatController.send(lastUser.content);
    }
  }

  void _continueLast() {
    final lastAssistant =
        _chatController.messages.where((m) => m.role == 'assistant').lastOrNull;
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
        if (_isLoadingMessages)
          const LinearProgressIndicator(minHeight: 2),
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
                      final isLastAssistant = index == lastAssistantIndex;
                      return MessageBubble.chatMessage(
                        key: ValueKey(msg.id),
                        chatMessage: msg,
                        announce: index == messages.length - 1 &&
                            msg.role == 'assistant',
                        onContinue: msg.finishReason == FinishReason.length
                            ? () => _chatController.continueMessage(msg.id)
                            : null,
                        onResume: (msg.finishReason == FinishReason.interrupted ||
                                msg.status == MessageStatus.interrupted)
                            ? _chatController.resume
                            : null,
                        onRegenerate: isLastAssistant && !_isBusy
                            ? () => _chatController.regenerate(msg.id)
                            : null,
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
        if (_chatController.error != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: ErrorCard(
              category: _chatController.error!,
              onRetry: _retryLast,
              onContinue: _continueLast,
              onUpgrade: widget.onOpenPlans,
            ),
          ),
        Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.paddingOf(context).bottom,
          ),
          child: Composer(
            draftKey: _activeConversationId ?? 'new',
            busy: _isBusy,
            onSubmit: (submit) {
              final attachments = submit.attachments
                  .map((a) => a.toFencedBlock())
                  .toList();
              _chatController.send(submit.text, attachments);
            },
            onStop: _chatController.stop,
          ),
        ),
      ],
    );
  }
}
