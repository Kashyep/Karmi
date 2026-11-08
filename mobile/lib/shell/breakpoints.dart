import 'package:flutter/widgets.dart';

/// Workspace breakpoint categories (§7 C).
///
/// - [compact]: width < 600 (phones).
/// - [medium]: 600 <= width <= 1024 (tablets).
/// - [expanded]: width > 1024 (desktops).
enum WorkspaceSize {
  compact,
  medium,
  expanded;

  /// Returns the [WorkspaceSize] for [width].
  static WorkspaceSize workspaceSizeOf(double width) =>
      _workspaceSizeOfWidth(width);

  /// Returns the [WorkspaceSize] for the current [context] viewport width using
  /// [MediaQuery.sizeOf].
  static WorkspaceSize workspaceSizeOfContext(BuildContext context) =>
      _workspaceSizeOfWidth(MediaQuery.sizeOf(context).width);

  /// Shorthand for [workspaceSizeOfContext].
  static WorkspaceSize of(BuildContext context) =>
      workspaceSizeOfContext(context);
}

WorkspaceSize _workspaceSizeOfWidth(double width) {
  if (width < 600) {
    return WorkspaceSize.compact;
  } else if (width <= 1024) {
    return WorkspaceSize.medium;
  } else {
    return WorkspaceSize.expanded;
  }
}

/// Computes the [WorkspaceSize] for the given [width].
WorkspaceSize workspaceSizeOf(double width) =>
    WorkspaceSize.workspaceSizeOf(width);

/// Computes the [WorkspaceSize] for the current [context] viewport using
/// [MediaQuery.sizeOf].
WorkspaceSize workspaceSizeOfContext(BuildContext context) =>
    WorkspaceSize.workspaceSizeOfContext(context);
