import 'package:flutter/foundation.dart';

/// Coordinates external actions (such as shell app bar buttons) with [ChatScreen].
class ChatController extends ChangeNotifier {
  void newChat() => notifyListeners();
}
