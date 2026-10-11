import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import '../models/notification_log.dart';

/// Local-First JSON File-based Repository for reading and clearing notification trigger history.
class NotificationRepository {
  final String _storageDirectoryPath;
  final List<NotificationLog> _logs = [];
  final StreamController<List<NotificationLog>> _logsStreamController =
      StreamController<List<NotificationLog>>.broadcast();

  bool _isLoaded = false;

  NotificationRepository(this._storageDirectoryPath);

  File get _file => File('$_storageDirectoryPath/notifications.json');
  File get _tempFile => File('$_storageDirectoryPath/notifications.json.tmp');

  /// Loads notification history into memory
  Future<void> load() async {
    try {
      final file = _file;
      if (await file.exists()) {
        final content = await file.readAsString();
        if (content.trim().isNotEmpty) {
          final dynamic decoded = jsonDecode(content);
          if (decoded is Map<String, dynamic> && decoded['logs'] is List) {
            final list = decoded['logs'] as List<dynamic>;
            _logs.clear();
            for (final item in list) {
              if (item is Map<String, dynamic>) {
                try {
                  _logs.add(NotificationLog.fromJson(item));
                } catch (_) {}
              }
            }
          }
        }
      }
    } catch (e) {
      debugPrint('Error loading notification history: $e');
      _logs.clear();
    } finally {
      _isLoaded = true;
      _notify();
    }
  }

  /// Streams all notification logs sorted chronologically descending
  Stream<List<NotificationLog>> watchNotificationLogs() async* {
    yield _sortedLogs();
    yield* _logsStreamController.stream.map((_) => _sortedLogs());
  }

  List<NotificationLog> _sortedLogs() {
    final list = List<NotificationLog>.from(_logs);
    list.sort((a, b) => b.timestamp.compareTo(a.timestamp));
    return list;
  }

  /// Fetches all notification logs from local storage
  Future<List<NotificationLog>> getAllLogs() async {
    if (!_isLoaded) await load();
    return _sortedLogs();
  }

  /// Saves a newly triggered notification log
  Future<void> saveLog(NotificationLog log) async {
    if (!_isLoaded) await load();
    _logs.insert(0, log);
    // Keep max 200 logs
    if (_logs.length > 200) {
      _logs.removeRange(200, _logs.length);
    }
    _notify();
    await _persist();
  }

  /// Permanently removes all notification logs
  Future<void> clearAllLogs() async {
    if (!_isLoaded) await load();
    _logs.clear();
    _notify();
    await _persist();
  }

  void _notify() {
    if (!_logsStreamController.isClosed) {
      _logsStreamController.add(List.unmodifiable(_sortedLogs()));
    }
  }

  Future<void> _persist() async {
    try {
      final payload = {
        'version': 1,
        'logs': _logs.map((l) => l.toJson()).toList(),
      };
      final jsonString = jsonEncode(payload);

      final tempFile = _tempFile;
      final targetFile = _file;

      if (!await targetFile.parent.exists()) {
        await targetFile.parent.create(recursive: true);
      }

      await tempFile.writeAsString(jsonString, flush: true);
      if (await tempFile.exists()) {
        await tempFile.rename(targetFile.path);
      }
    } catch (e) {
      debugPrint('Error persisting notifications: $e');
    }
  }

  Future<void> dispose() async {
    await _logsStreamController.close();
  }
}
