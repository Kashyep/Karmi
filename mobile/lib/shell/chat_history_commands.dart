import 'package:flutter/foundation.dart';

/// Bridge between the app-level history rail (app.dart) and ChatScreen.
class ChatHistoryCommands {
  ChatHistoryCommands({String? activeConversationId})
      : activeId = ValueNotifier<String?>(activeConversationId);

  /// Set by ChatScreen in initState; cleared (null) in dispose.
  ValueChanged<String>? openConversation;
  VoidCallback? newChat;

  /// Written by ChatScreen whenever its active conversation changes (null = new chat).
  final ValueNotifier<String?> activeId;

  void dispose() => activeId.dispose();
}
