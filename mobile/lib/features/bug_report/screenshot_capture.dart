import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';

import '../../api/bug_reports/bug_report_errors.dart';
import '../../api/bug_reports/bug_report_models.dart';

/// Maximum allowed screenshot size in bytes (5 MB).
const int kMaxScreenshotBytes = 5242880;

/// Plain words warning message when screenshot size exceeds 5 MB.
const String kScreenshotTooBigMessage =
    'That screenshot is too big. Turn off the screenshot or try again.';

/// Captures a PNG image from a [GlobalKey] attached to a [RepaintBoundary].
Future<Uint8List?> capturePngFromRepaintBoundary(
  GlobalKey boundaryKey, {
  double pixelRatio = 1.0,
}) async {
  try {
    final boundary =
        boundaryKey.currentContext?.findRenderObject()
            as RenderRepaintBoundary?;
    if (boundary == null) return null;
    final image = await boundary.toImage(pixelRatio: pixelRatio);
    final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
    if (byteData == null) return null;
    return byteData.buffer.asUint8List();
  } catch (_) {
    return null;
  }
}

/// Validates whether the screenshot payload is within the 5 MB limit.
bool isScreenshotSizeValid(int byteCount) {
  return byteCount <= kMaxScreenshotBytes;
}

/// Converts raw PNG bytes to [BugReportScreenshot] after enforcing the 5 MB limit.
BugReportScreenshot? prepareScreenshotPayload(Uint8List? bytes) {
  if (bytes == null) return null;
  if (!isScreenshotSizeValid(bytes.lengthInBytes)) {
    throw const BugReportPayloadTooLargeException(kScreenshotTooBigMessage);
  }
  return BugReportScreenshot(
    contentType: 'image/png',
    dataBase64: base64Encode(bytes),
  );
}
