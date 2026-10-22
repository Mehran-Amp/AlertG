import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'server_alert_service.dart';
import 'service_logger.dart';

/// Phase 2: durable, per-ack files for delivery acknowledgements.
///
/// Two isolates (FCM background + foreground service) may both ack the same
/// delivery. To avoid a lost update, each ack is a separate file
/// `acks/<deliveryId>.json` created atomically (tmp + rename). A shared
/// JSON file would reintroduce the write race we removed from alerts.json.
class DeliveryAckService {
  /// Injected for tests; falls back to the app documents dir.
  @visibleForTesting
  static Directory? baseDirOverride;

  /// Injected for tests; falls back to [ServerAlertService.post].
  @visibleForTesting
  static Future<bool> Function(String deliveryId)? postOverride;

  static const String _folderName = 'acks';
  static const Duration _maxAge = Duration(hours: 24);

  static bool _flushing = false;
  static Future<void>? _pendingFlush;

  static Future<Directory> _acksDir() async {
    final base = baseDirOverride ?? await getApplicationDocumentsDirectory();
    final dir = Directory('${base.path}/$_folderName');
    if (!dir.existsSync()) {
      dir.createSync(recursive: true);
    }
    return dir;
  }

  static String _safeId(String deliveryId) {
    final s = deliveryId.replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');
    return s.length > 120 ? s.substring(0, 120) : s;
  }

  static File _fileFor(Directory dir, String deliveryId) =>
      File('${dir.path}/${_safeId(deliveryId)}.json');

  /// Queue an ack for [deliveryId]. Idempotent: if the file already exists,
  /// it is left untouched.
  static Future<void> enqueueAck(String deliveryId, {bool shown = true}) async {
    if (deliveryId.trim().isEmpty) return;
    try {
      final dir = await _acksDir();
      final target = _fileFor(dir, deliveryId);
      if (target.existsSync()) return;
      final tmp = File('${target.path}.tmp');
      await tmp.writeAsString(
        jsonEncode({
          'delivery_id': deliveryId,
          'shown': shown,
          'queued_at': DateTime.now().toUtc().toIso8601String(),
        }),
        flush: true,
      );
      await tmp.rename(target.path);
    } catch (e, st) {
      await ServiceLogger.logError('ack.enqueue', e, st);
    }
  }

  /// Send all queued acks. Single-flight: concurrent calls coalesce.
  /// Removes a file only after a successful POST (2xx).
  static Future<void> flush() async {
    if (_flushing) {
      _pendingFlush ??= Completer<void>().future;
      return _pendingFlush!;
    }
    _flushing = true;
    final completer = Completer<void>();
    _pendingFlush = completer.future;
    try {
      final dir = await _acksDir();
      final now = DateTime.now().toUtc();
      final files = dir.listSync().whereType<File>().where((f) =>
          f.path.endsWith('.json') && !f.path.endsWith('.json.tmp')).toList();

      for (final f in files) {
        try {
          final stat = f.statSync();
          if (now.difference(stat.modified.toUtc()) > _maxAge) {
            try { f.deleteSync(); } catch (_) {}
            continue;
          }
          final content = await f.readAsString();
          final parsed = jsonDecode(content) as Map<String, dynamic>;
          final id = (parsed['delivery_id'] as String?) ?? '';
          final shown = parsed['shown'] as bool? ?? true;
          if (id.isEmpty) {
            try { f.deleteSync(); } catch (_) {}
            continue;
          }
          final ok = await _post(id, shown);
          if (ok) {
            try { f.deleteSync(); } catch (_) {}
          }
        } catch (e, st) {
          await ServiceLogger.logError('ack.flush.entry', e, st);
        }
      }
    } catch (e, st) {
      await ServiceLogger.logError('ack.flush', e, st);
    } finally {
      _flushing = false;
      if (!completer.isCompleted) completer.complete();
    }
    return completer.future;
  }

  static Future<bool> _post(String deliveryId, bool shown) async {
    final override = postOverride;
    if (override != null) {
      try {
        return await override(deliveryId);
      } catch (e) {
        return false;
      }
    }
    try {
      final res = await ServerAlertService.post(
        '/api/deliveries/${Uri.encodeComponent(deliveryId)}/ack',
        body: {'shown': shown},
      );
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}