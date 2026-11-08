import 'package:flutter/foundation.dart';

const int maxAttachmentCount = 3;
const int maxFileChars = 40000;
const int maxTotalChars = 60000;

const Set<String> allowedExtensions = {
  '.txt',
  '.md',
  '.csv',
  '.json',
  '.yaml',
  '.yml',
  '.log',
  '.py',
  '.dart',
  '.js',
  '.ts',
  '.sql',
  '.xml',
  '.html',
  '.css',
  '.sh',
};

enum AttachmentValidationError { tooMany, fileTooLarge, totalTooLarge, notText }

@immutable
class TextAttachment {
  const TextAttachment({required this.name, required this.content});

  final String name;
  final String content;

  int get charCount => content.length;

  /// Formats the attachment as a fenced code block per contract §D2.
  String toFencedBlock() {
    final dot = name.lastIndexOf('.');
    final ext = dot != -1 && dot < name.length - 1
        ? name.substring(dot + 1).toLowerCase()
        : '';
    return '```$ext\n// $name\n$content\n```';
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is TextAttachment &&
          runtimeType == other.runtimeType &&
          name == other.name &&
          content == other.content;

  @override
  int get hashCode => Object.hash(name, content);

  @override
  String toString() => 'TextAttachment(name: $name, chars: ${content.length})';
}

@immutable
class AttachmentLimitResult {
  const AttachmentLimitResult.valid()
    : isValid = true,
      error = null,
      message = null;

  const AttachmentLimitResult.invalid(this.error, this.message)
    : isValid = false;

  final bool isValid;
  final AttachmentValidationError? error;
  final String? message;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is AttachmentLimitResult &&
          isValid == other.isValid &&
          error == other.error &&
          message == other.message;

  @override
  int get hashCode => Object.hash(isValid, error, message);

  @override
  String toString() => isValid
      ? 'AttachmentLimitResult.valid'
      : 'AttachmentLimitResult.invalid($error: $message)';
}

bool hasAllowedExtension(String filename) {
  final lower = filename.toLowerCase();
  for (final ext in allowedExtensions) {
    if (lower.endsWith(ext)) return true;
  }
  return false;
}

bool isBinaryContent(String content) => content.contains('\u0000');

AttachmentLimitResult validateAttachments(
  Iterable<TextAttachment> attachments,
) {
  final list = attachments.toList();

  // 1. File count limit (max 3 files)
  if (list.length > maxAttachmentCount) {
    return const AttachmentLimitResult.invalid(
      AttachmentValidationError.tooMany,
      'Maximum 3 files allowed.',
    );
  }

  // 2. Validate each file: text extension, non-binary, size limit
  for (final file in list) {
    if (!hasAllowedExtension(file.name) || isBinaryContent(file.content)) {
      return AttachmentLimitResult.invalid(
        AttachmentValidationError.notText,
        'File "${file.name}" is not a supported text file.',
      );
    }
    if (file.content.length > maxFileChars) {
      return AttachmentLimitResult.invalid(
        AttachmentValidationError.fileTooLarge,
        'File "${file.name}" exceeds the 40,000 character limit.',
      );
    }
  }

  // 3. Validate total size across all files
  final totalChars = list.fold<int>(0, (sum, f) => sum + f.content.length);
  if (totalChars > maxTotalChars) {
    return const AttachmentLimitResult.invalid(
      AttachmentValidationError.totalTooLarge,
      'Total attachments exceed the 60,000 character limit.',
    );
  }

  return const AttachmentLimitResult.valid();
}

AttachmentLimitResult validateAttachment(
  TextAttachment attachment, {
  List<TextAttachment> existing = const [],
}) {
  return validateAttachments([...existing, attachment]);
}
