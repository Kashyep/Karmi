import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/bug_report/uuid4.dart';

void main() {
  group('uuid4 generator (RFC 4122 v4)', () {
    test('generates 36 character string with correct hyphen placement', () {
      final uuid = generateUuidV4();
      expect(uuid.length, 36);
      expect(uuid[8], '-');
      expect(uuid[13], '-');
      expect(uuid[18], '-');
      expect(uuid[23], '-');
    });

    test('has version 4 nibble at position 14', () {
      for (var i = 0; i < 50; i++) {
        final uuid = generateUuidV4();
        expect(uuid[14], '4');
      }
    });

    test('has variant nibble (8, 9, a, or b) at position 19', () {
      final validVariants = {'8', '9', 'a', 'b'};
      for (var i = 0; i < 50; i++) {
        final uuid = generateUuidV4();
        expect(validVariants.contains(uuid[19].toLowerCase()), isTrue);
      }
    });

    test('matches canonical UUID regex pattern', () {
      final uuidRegex = RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
      );
      for (var i = 0; i < 50; i++) {
        final uuid = generateUuidV4();
        expect(uuidRegex.hasMatch(uuid), isTrue, reason: '$uuid did not match');
      }
    });

    test('generates distinct UUIDs across 1000 calls', () {
      final seen = <String>{};
      for (var i = 0; i < 1000; i++) {
        final uuid = generateUuidV4();
        expect(
          seen.add(uuid),
          isTrue,
          reason: 'Duplicate UUID generated: $uuid',
        );
      }
    });
  });
}
