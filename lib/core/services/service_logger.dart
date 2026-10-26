import 'dart:io';
import 'dart:isolate';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

/// Appends diagnostic lines to `<documents>/service_log.txt`.
///
/// Used by the background service isolate to record every init step and every
/// error. This file is not shown in the UI; it is pulled from the device when
/// debugging "why did the 24/7 service stop?". Capped at 200 KB: when the file
/// exceeds that, the oldest half is dropped.
///
/// DEV-5: every log line is prefixed with the current isolate tag
/// (`ui`, `service`, `fcm`) so the three error sites can be told apart.
class ServiceLogger {
  static const String _fileName = 'service_log.txt';
  static const int _maxBytes = 200 * 1024; // 200 KB
  static const int _trimToBytes = 100 * 1024; // keep the newest 100 KB

  static File? _cachedFile;

  /// DEV-5: current isolate tag. Defaults to the debug name of the current
  /// isolate, or 'ui' when no name was set (the main isolate).
  @visibleForTesting
  static String? isolateTagOverride;

  static String get isolateTag {
    if (isolateTagOverride != null) return isolateTagOverride!;
    final name = Isolate.current.debugName;
    if (name == null || name.isEmpty) return 'ui';
    return name;
  }

  static Future<File> _file() async {
    if (_cachedFile != null) return _cachedFile!;
    final dir = await getApplicationDocumentsDirectory();
    final f = File('${dir.path}/$_fileName');
    if (!f.existsSync()) {
      f.createSync(recursive: true);
    }
    return _cachedFile = f;
  }

  /// Writes `[ISO8601] [tag] [step] message` to the log file. Never throws.
  static Future<void> log(String step, String message) async {
    final tag = isolateTag;
    final line = '[${DateTime.now().toIso8601String()}] [$tag] [$step] $message\n';
    debugPrint('📋 [ServiceLog] $line');
    try {
      final f = await _file();
      await f.writeAsString(line, mode: FileMode.append, flush: true);
      await _trimIfNeeded(f);
    } catch (e) {
      debugPrint('⚠️ [ServiceLogger] write failed: $e');
    }
  }

  /// Writes an error with stack trace. Never throws.
  static Future<void> logError(String step, Object error, [StackTrace? stack]) async {
    final tag = isolateTag;
    final line = '[${DateTime.now().toIso8601String()}] [$tag] [$step] ERROR: $error${stack != null ? '\n$stack' : ''}\n';
    debugPrint('📋 [ServiceLog] $line');
    try {
      final f = await _file();
      await f.writeAsString(line, mode: FileMode.append, flush: true);
      await _trimIfNeeded(f);
    } catch (e) {
      debugPrint('⚠️ [ServiceLogger] write failed: $e');
    }
  }

  static Future<void> _trimIfNeeded(File f) async {
    try {
      final length = await f.length();
      if (length <= _maxBytes) return;
      final raf = await f.open(mode: FileMode.read);
      final bytes = await raf.read(_trimToBytes);
      await raf.close();
      final tmp = File('${f.path}.tmp');
      await tmp.writeAsBytes(bytes, flush: true);
      await tmp.rename(f.path);
    } catch (_) {}
  }
}