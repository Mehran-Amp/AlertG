import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

/// Appends diagnostic lines to `<documents>/service_log.txt`.
///
/// Used by the background service isolate to record every init step and every
/// error. This file is not shown in the UI; it is pulled from the device when
/// debugging "why did the 24/7 service stop?". Capped at 200 KB: when the file
/// exceeds that, the oldest half is dropped.
class ServiceLogger {
  static const String _fileName = 'service_log.txt';
  static const int _maxBytes = 200 * 1024; // 200 KB
  static const int _trimToBytes = 100 * 1024; // keep the newest 100 KB

  static File? _cachedFile;

  static Future<File> _file() async {
    if (_cachedFile != null) return _cachedFile!;
    final dir = await getApplicationDocumentsDirectory();
    final f = File('${dir.path}/$_fileName');
    if (!f.existsSync()) {
      f.createSync(recursive: true);
    }
    return _cachedFile = f;
  }

  /// Writes `[ISO8601] [step] message` to the log file. Never throws.
  static Future<void> log(String step, String message) async {
    final line = '[${DateTime.now().toIso8601String()}] [$step] $message\n';
    debugPrint('📋 [ServiceLog] $line');
    try {
      final f = await _file();
      await f.writeAsString(line, mode: FileMode.append, flush: true);
      await _trimIfNeeded(f);
    } catch (e) {
      debugPrint('⚠️ [ServiceLogger] write failed: $e');
    }
  }

  /// Convenience wrapper for caught exceptions.
  static Future<void> logError(String step, Object error, [StackTrace? st]) async {
    await log(step, 'ERROR: $error${st != null ? "\n$st" : ""}');
  }

  static Future<void> _trimIfNeeded(File f) async {
    try {
      final len = await f.length();
      if (len <= _maxBytes) return;
      final content = await f.readAsString();
      final keepFrom = (content.length - _trimToBytes).clamp(0, content.length);
      final trimmed = content.substring(keepFrom);
      await f.writeAsString(trimmed, flush: true);
      debugPrint('📋 [ServiceLogger] trimmed log from $len to ${trimmed.length} bytes');
    } catch (e) {
      debugPrint('⚠️ [ServiceLogger] trim failed: $e');
    }
  }
}