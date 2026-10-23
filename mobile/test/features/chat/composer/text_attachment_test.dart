import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/composer/text_attachment.dart';

void main() {
  group('TextAttachment', () {
    test('toFencedBlock includes extension and filename comment', () {
      const att = TextAttachment(name: 'main.py', content: 'print("hello")');
      expect(att.toFencedBlock(), '```py\n// main.py\nprint("hello")\n```');
    });

    test('toFencedBlock with no extension handles cleanly', () {
      const att = TextAttachment(name: 'Dockerfile', content: 'FROM scratch');
      expect(att.toFencedBlock(), '```\n// Dockerfile\nFROM scratch\n```');
    });
  });

  group('Attachment validator', () {
    test('accepts valid text attachments within limits', () {
      final attachments = [
        const TextAttachment(name: 'a.txt', content: 'hello'),
        const TextAttachment(name: 'b.dart', content: 'void main() {}'),
        const TextAttachment(name: 'c.json', content: '{"ok": true}'),
      ];
      final result = validateAttachments(attachments);
      expect(result.isValid, isTrue);
      expect(result.error, isNull);
    });

    test('accepts all allowed extensions', () {
      final exts = [
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
      ];
      for (final ext in exts) {
        final result = validateAttachments([
          TextAttachment(name: 'file$ext', content: 'content'),
        ]);
        expect(result.isValid, isTrue, reason: 'Failed for extension $ext');
      }
    });

    test('rejects unsupported file extension as notText', () {
      final result = validateAttachments([
        const TextAttachment(name: 'photo.png', content: 'image-data'),
      ]);
      expect(result.isValid, isFalse);
      expect(result.error, AttachmentValidationError.notText);
      expect(result.message, contains('not a supported text file'));
    });

    test('rejects binary file containing NUL character as notText', () {
      final result = validateAttachments([
        const TextAttachment(name: 'binary.txt', content: 'hello\u0000world'),
      ]);
      expect(result.isValid, isFalse);
      expect(result.error, AttachmentValidationError.notText);
      expect(result.message, contains('not a supported text file'));
    });

    test('rejects 4th file with tooMany error and message', () {
      final attachments = [
        const TextAttachment(name: '1.txt', content: 'a'),
        const TextAttachment(name: '2.txt', content: 'b'),
        const TextAttachment(name: '3.txt', content: 'c'),
        const TextAttachment(name: '4.txt', content: 'd'),
      ];
      final result = validateAttachments(attachments);
      expect(result.isValid, isFalse);
      expect(result.error, AttachmentValidationError.tooMany);
      expect(result.message, contains('Maximum 3 files allowed'));
    });

    test('rejects 40,001-char file with fileTooLarge error and message', () {
      final hugeContent = 'x' * 40001;
      final result = validateAttachments([
        TextAttachment(name: 'huge.txt', content: hugeContent),
      ]);
      expect(result.isValid, isFalse);
      expect(result.error, AttachmentValidationError.fileTooLarge);
      expect(result.message, contains('40,000 character limit'));
    });

    test('accepts 40,000-char file', () {
      final exactContent = 'x' * 40000;
      final result = validateAttachments([
        TextAttachment(name: 'exact.txt', content: exactContent),
      ]);
      expect(result.isValid, isTrue);
    });

    test(
      'rejects total 60,001 characters with totalTooLarge error and message',
      () {
        final attachments = [
          TextAttachment(name: '1.txt', content: 'a' * 30000),
          TextAttachment(name: '2.txt', content: 'b' * 30001),
        ];
        final result = validateAttachments(attachments);
        expect(result.isValid, isFalse);
        expect(result.error, AttachmentValidationError.totalTooLarge);
        expect(result.message, contains('60,000 character limit'));
      },
    );

    test('accepts total 60,000 characters', () {
      final attachments = [
        TextAttachment(name: '1.txt', content: 'a' * 30000),
        TextAttachment(name: '2.txt', content: 'b' * 30000),
      ];
      final result = validateAttachments(attachments);
      expect(result.isValid, isTrue);
    });
  });
}
