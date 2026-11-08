import 'dart:async';
import 'dart:convert';

/// A parsed Server-Sent Events (SSE) message frame.
class SseMessage {
  const SseMessage({this.event, this.data = '', this.id});

  /// The event name (e.g. 'run.started', 'message.delta', 'run.finished').
  final String? event;

  /// The message data payload, with multiple `data:` lines joined by `\n`.
  final String data;

  /// The event identifier, if set by an `id:` field.
  final String? id;

  /// Convenience accessor parsing [id] as an integer sequence number.
  int? get idAsInt => id != null ? int.tryParse(id!) : null;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is SseMessage &&
          runtimeType == other.runtimeType &&
          event == other.event &&
          data == other.data &&
          id == other.id;

  @override
  int get hashCode => Object.hash(event, data, id);

  @override
  String toString() => 'SseMessage(event: $event, id: $id, data: $data)';
}

/// A pure Dart SSE line and frame parser.
///
/// Converts a [Stream] of bytes (`List<int>`) or strings into a [Stream] of
/// [SseMessage] instances. Handles:
/// - Frames split arbitrarily across chunk boundaries.
/// - Multi-line `data:` fields joined with `\n`.
/// - SSE comments (lines starting with `:`) and heartbeat-only comment lines.
/// - `id:` and `event:` fields.
/// - CRLF (`\r\n`), LF (`\n`), and CR (`\r`) line terminators.
/// - Blank line frame terminators.
/// - Ignores unknown fields (e.g. `retry`).
/// - Terminal frame without trailing blank line on stream closure.
class SseParser<S> extends StreamTransformerBase<S, SseMessage> {
  const SseParser();

  @override
  Stream<SseMessage> bind(Stream<S> stream) => parse(stream);

  /// Parses [stream], automatically decoding byte chunks as UTF-8 or processing
  /// string chunks directly.
  static Stream<SseMessage> parse(Stream<dynamic> stream) {
    if (stream is Stream<List<int>>) {
      return parseBytes(stream);
    }
    if (stream is Stream<String>) {
      return parseStrings(stream);
    }
    return parseStrings(
      stream.transform(
        StreamTransformer<dynamic, String>.fromHandlers(
          handleData: (data, sink) {
            if (data is List<int>) {
              sink.add(utf8.decode(data, allowMalformed: true));
            } else if (data is String) {
              sink.add(data);
            }
          },
        ),
      ),
    );
  }

  /// Parses a stream of raw byte chunks as UTF-8 Server-Sent Events.
  static Stream<SseMessage> parseBytes(Stream<List<int>> stream) {
    return parseStrings(utf8.decoder.bind(stream));
  }

  /// Parses a stream of text chunks into SSE frames.
  static Stream<SseMessage> parseStrings(Stream<String> stream) async* {
    String buffer = '';
    bool isFirstChunk = true;

    String? currentEvent;
    final List<String> currentDataLines = [];
    String? currentId;
    bool hasField = false;

    SseMessage? flushEvent() {
      if (currentEvent != null ||
          currentDataLines.isNotEmpty ||
          currentId != null) {
        final msg = SseMessage(
          event: currentEvent,
          data: currentDataLines.join('\n'),
          id: currentId,
        );
        currentEvent = null;
        currentDataLines.clear();
        currentId = null;
        hasField = false;
        return msg;
      }
      hasField = false;
      return null;
    }

    void processLine(String line, List<SseMessage> out) {
      if (line.isEmpty) {
        if (hasField) {
          final msg = flushEvent();
          if (msg != null) out.add(msg);
        }
        return;
      }

      if (line.startsWith(':')) {
        // SSE comment or heartbeat line (e.g. ": heartbeat") -> ignore.
        return;
      }

      final colonIndex = line.indexOf(':');
      final String field;
      final String value;
      if (colonIndex == -1) {
        field = line;
        value = '';
      } else {
        field = line.substring(0, colonIndex);
        var v = line.substring(colonIndex + 1);
        if (v.startsWith(' ')) {
          v = v.substring(1);
        }
        value = v;
      }

      switch (field) {
        case 'event':
          currentEvent = value;
          hasField = true;
          break;
        case 'data':
          currentDataLines.add(value);
          hasField = true;
          break;
        case 'id':
          currentId = value;
          hasField = true;
          break;
        default:
          // Ignore unknown fields (e.g. retry, custom headers).
          break;
      }
    }

    await for (final rawChunk in stream) {
      var chunk = rawChunk;
      if (isFirstChunk) {
        isFirstChunk = false;
        if (chunk.startsWith('\uFEFF')) {
          chunk = chunk.substring(1);
        }
      }
      buffer += chunk;

      int scanIndex = 0;
      final out = <SseMessage>[];

      while (scanIndex < buffer.length) {
        final cr = buffer.indexOf('\r', scanIndex);
        final lf = buffer.indexOf('\n', scanIndex);

        if (cr == -1 && lf == -1) {
          break;
        }

        final int breakPos;
        final int delimLength;

        if (cr != -1 && (lf == -1 || cr < lf)) {
          if (cr + 1 == buffer.length) {
            // Trailing \r could be part of CRLF arriving in next chunk.
            break;
          }
          breakPos = cr;
          if (buffer.codeUnitAt(cr + 1) == 0x0A /* \n */ ) {
            delimLength = 2;
          } else {
            delimLength = 1;
          }
        } else {
          breakPos = lf;
          delimLength = 1;
        }

        final line = buffer.substring(scanIndex, breakPos);
        scanIndex = breakPos + delimLength;
        processLine(line, out);
      }

      if (scanIndex > 0) {
        buffer = buffer.substring(scanIndex);
      }

      for (final msg in out) {
        yield msg;
      }
    }

    final out = <SseMessage>[];
    if (buffer.isNotEmpty) {
      if (buffer.endsWith('\r')) {
        buffer = buffer.substring(0, buffer.length - 1);
      }
      if (buffer.isNotEmpty) {
        processLine(buffer, out);
      }
    }

    // Handle terminal frame without trailing blank line when stream closes.
    final trailingMsg = flushEvent();
    if (trailingMsg != null) {
      out.add(trailingMsg);
    }

    for (final msg in out) {
      yield msg;
    }
  }
}
