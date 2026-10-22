import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import '../models/alert_rule.dart';
import '../../../core/services/native_widget_sync_service.dart';
import '../../../core/services/server_alert_service.dart';

/// Local-First JSON File-based Repository for managing alert rules.
/// Stores rules in `<app_documents_dir>/alerts.json` with in-memory caching and atomic writes.
class JsonAlertRuleRepository {
  final String _storageDirectoryPath;
  final List<AlertRule> _rules = [];
  final StreamController<List<AlertRule>> _rulesStreamController =
      StreamController<List<AlertRule>>.broadcast();

  bool _isLoaded = false;

  /// True when alerts.json (and its .bak) could not be parsed on load.
  /// While set, _persist() and server sync must not overwrite the on-disk
  /// state with an empty list. A user-initiated add (saveRule / import)
  /// clears it.
  bool _loadFailed = false;

  JsonAlertRuleRepository(this._storageDirectoryPath);

  // ---------------------------------------------------------------------------
  // Cross-isolate file lock
  //
  // The main isolate and the background service isolate both persist the whole
  // alerts.json list. Without a lock, one write can silently overwrite the
  // other (lost update). We use an exclusive-create lock file:
  //   * File.createSync(exclusive: true) throws if the lock already exists.
  //   * A lock file older than 5s is considered stale and is removed.
  //   * Retry every 50ms, give up after 2s.
  // ---------------------------------------------------------------------------
  static const _lockFileName = 'alerts.json.lock';
  static const _staleLockMs = 5000;
  static const _lockRetryMs = 50;
  static const _lockTimeoutMs = 2000;

  Future<T> _withFileLock<T>(Future<T> Function() action) async {
    final lockFile = File('$_storageDirectoryPath/$_lockFileName');
    final deadline =
        DateTime.now().add(const Duration(milliseconds: _lockTimeoutMs));

    while (true) {
      try {
        if (!lockFile.parent.existsSync()) {
          lockFile.parent.createSync(recursive: true);
        }
        lockFile.createSync(exclusive: true);
        break; // acquired
      } on FileSystemException {
        // Lock exists. Check if it is stale.
        try {
          if (lockFile.existsSync()) {
            final ageMs =
                DateTime.now().difference(lockFile.statSync().modified).inMilliseconds;
            if (ageMs > _staleLockMs) {
              try {
                lockFile.deleteSync();
              } catch (_) {}
              continue;
            }
          }
        } catch (_) {}

        if (DateTime.now().isAfter(deadline)) {
          throw TimeoutException(
            'Could not acquire $_lockFileName within ${_lockTimeoutMs}ms',
          );
        }
        await Future<void>.delayed(const Duration(milliseconds: _lockRetryMs));
      }
    }

    try {
      return await action();
    } finally {
      try {
        if (lockFile.existsSync()) {
          lockFile.deleteSync();
        }
      } catch (_) {}
    }
  }

  File get _file => File('$_storageDirectoryPath/alerts.json');

  /// Read-only snapshot of current in-memory rules
  List<AlertRule> get allRules => List.unmodifiable(_rules);

  /// Read-only snapshot of active in-memory rules
  List<AlertRule> get activeRules =>
      List.unmodifiable(_rules.where((r) => r.isActive));

  /// Loads all rules from JSON file into memory.
  /// If the file is missing or corrupted, starts with an empty list without crashing.
    /// Loads all rules from JSON file into memory.
  /// Order of attempts:
  ///   1. alerts.json
  ///   2. alerts.json.bak (if the main file is missing or corrupt)
  ///   3. start empty + move the corrupt file aside to alerts_corrupt_<ts>.json
  ///      and set _loadFailed so we never overwrite the user's data with [].
  Future<void> load() async {
    _loadFailed = false;
    final mainFile = _file;
    final bakFile = File('${_file.path}.bak');

    // Helper: try to parse a file and return the list of rules, or null on failure.
    Future<List<AlertRule>?> _tryParse(File f) async {
      try {
        if (!await f.exists()) return null;
        final content = await f.readAsString();
        if (content.trim().isEmpty) return null;

        // Mojibake backup (unchanged behaviour)
        final bool hasMojibake = content.contains('Ã') ||
            content.contains('Ø') ||
            content.contains('Ù') ||
            content.contains('Â');
        if (hasMojibake && f.path == mainFile.path) {
          try {
            final initialBackup =
                File('$_storageDirectoryPath/alerts_original_corrupted.json.bak');
            if (!await initialBackup.exists()) {
              await f.copy(initialBackup.path);
              debugPrint('📦 [Backup] Preserved original pre-repair backup: ${initialBackup.path}');
            }
            final ts = DateTime.now().toIso8601String().replaceAll(':', '-');
            final timeBackup = File('$_storageDirectoryPath/alerts_backup_$ts.json');
            await f.copy(timeBackup.path);
            debugPrint('📦 [Backup] Created timestamped backup: ${timeBackup.path}');
          } catch (be) {
            debugPrint('⚠️ [Backup] Warning backing up alerts file: $be');
          }
        }

        final dynamic decoded = jsonDecode(content);
        final List<AlertRule> parsed = <AlertRule>[];
        if (decoded is Map<String, dynamic> && decoded['rules'] is List) {
          for (final item in decoded['rules'] as List<dynamic>) {
            if (item is Map<String, dynamic>) {
              try {
                parsed.add(AlertRule.fromJson(item));
              } catch (e) {
                debugPrint('Failed to parse rule item: $e');
              }
            }
          }
        } else if (decoded is List<dynamic>) {
          for (final item in decoded) {
            if (item is Map<String, dynamic>) {
              try {
                parsed.add(AlertRule.fromJson(item));
              } catch (e) {
                debugPrint('Failed to parse rule item: $e');
              }
            }
          }
        } else {
          return null; // unexpected shape
        }
        return parsed;
      } catch (e, stack) {
        debugPrint('Error parsing ${f.path}: $e\n$stack');
        return null;
      }
    }

    try {
      // 1. Try the main file.
      var parsed = await _tryParse(mainFile);
      if (parsed != null) {
        _rules
          ..clear()
          ..addAll(parsed);
        return;
      }

      // 2. Try the backup.
      final mainExists = await mainFile.exists();
      if (mainExists) {
        parsed = await _tryParse(bakFile);
        if (parsed != null) {
          debugPrint('♻️ [Repo] Recovered rules from ${bakFile.path}');
          _rules
            ..clear()
            ..addAll(parsed);
          return;
        }
      }

      // 3. Both missing/corrupt.
      if (mainExists) {
        // Preserve the corrupt file for debugging, then start empty.
        try {
          final ts = DateTime.now()
              .toIso8601String()
              .replaceAll(':', '-')
              .replaceAll('.', '-');
          final corruptPath = '$_storageDirectoryPath/alerts_corrupt_$ts.json';
          await mainFile.copy(corruptPath);
          debugPrint('🚨 [Repo] alerts.json is corrupt; moved to $corruptPath');
        } catch (ce) {
          debugPrint('⚠️ [Repo] Could not preserve corrupt file: $ce');
        }
        _loadFailed = true;
      }
      // No file at all -> normal first run, start empty, do NOT set _loadFailed.
    } finally {
      _isLoaded = true;
      _notify();
    }
  }

  /// Streams all alert rules maintaining the exact user custom order
  Stream<List<AlertRule>> watchAllRules() async* {
    yield List.unmodifiable(_rules);
    yield* _rulesStreamController.stream.map((list) => List.unmodifiable(list));
  }

  /// Reorders rules dynamically via drag-and-drop and persists instantly
  Future<void> reorderRules(int oldIndex, int newIndex) async {
    if (!_isLoaded) await load();
    if (oldIndex < 0 || oldIndex >= _rules.length) return;
    if (newIndex < 0) newIndex = 0;
    if (newIndex > _rules.length) newIndex = _rules.length;

    if (oldIndex < newIndex) {
      newIndex -= 1;
    }

    await _withFileLock(() async {
      await _reloadFromDiskUnderLock();
      // Re-validate indexes against the re-read list.
      if (oldIndex < 0 || oldIndex >= _rules.length) return;
      final effectiveNew = newIndex > _rules.length ? _rules.length : newIndex;
      final rule = _rules.removeAt(oldIndex);
      _rules.insert(effectiveNew, rule);
      await _persistRawLocked();
    });

    _notify();
  }

  /// Fetches all active rules for a specific exchange and market symbol
  Future<List<AlertRule>> getActiveRulesForSymbol({
    required String exchangeId,
    required String marketSymbol,
  }) async {
    if (!_isLoaded) await load();
    return _rules
        .where((r) =>
            r.isActive &&
            r.exchangeId.toLowerCase() == exchangeId.toLowerCase() &&
            r.marketSymbol.toUpperCase() == marketSymbol.toUpperCase())
        .toList();
  }

  /// Saves or updates an alert rule using its UUID and persists to disk
  Future<void> saveRule(AlertRule rule, {bool syncToServer = true}) async {
    if (!_isLoaded) await load();
    // A user-initiated add is authoritative: clear the load-failure guard
    // so subsequent persists/syncs are allowed again.
    _loadFailed = false;

    await _withFileLock(() async {
      // Re-read the file under the lock so we never overwrite another
      // isolate's just-written rule.
      await _reloadFromDiskUnderLock();

      final index = _rules.indexWhere((r) => r.uuid == rule.uuid);
      if (index >= 0) {
        _rules[index] = rule;
      } else {
        _rules.add(rule);
      }

      await _persistRawLocked();
    });

    _notify(syncToServer: syncToServer);
  }

  /// Clear all rules in local storage only (used when switching accounts/sign out without deleting from cloud server)
  Future<void> clearLocalOnly() async {
    _rules.clear();
    _notify(syncToServer: false);
    await _persist();
  }

  /// Deletes an alert rule by UUID and persists to disk
  Future<bool> deleteRule(String uuid) async {
    if (!_isLoaded) await load();
    var removed = false;

    await _withFileLock(() async {
      await _reloadFromDiskUnderLock();
      final initialLength = _rules.length;
      _rules.removeWhere((r) => r.uuid == uuid);
      removed = _rules.length < initialLength;
      if (removed) {
        await _persistRawLocked();
      }
    });

    if (removed) {
      _notify();
      // Remove from Python server immediately to stop monitoring
      ServerAlertService.deleteAlertFromServer(uuid).ignore();
    }
    return removed;
  }

  /// Puts a rule into cooldown / updates last triggered status
  Future<void> setCooldown({
    required String uuid,
    required Duration cooldownDuration,
  }) async {
    if (!_isLoaded) await load();
    final index = _rules.indexWhere((r) => r.uuid == uuid);
    if (index >= 0) {
      final existing = _rules[index];
      _rules[index] = existing.copyWith(
        lastTriggeredAt: DateTime.now(),
      );
      _notify();
      await _persist();
    }
  }

  /// Manually re-arms a triggered one-shot rule
  Future<void> rearmRule(String uuid) async {
    if (!_isLoaded) await load();
    final index = _rules.indexWhere((r) => r.uuid == uuid);
    if (index >= 0) {
      final existing = _rules[index];
      _rules[index] = existing.copyWith(
        isActive: true,
        isTriggered: false,
      );
      _notify();
      await _persist();
    }
  }

  /// Duplicates an existing alert rule with a new UUID
  Future<AlertRule?> duplicateRule(String uuid) async {
    if (!_isLoaded) await load();
    final existing = _rules.where((r) => r.uuid == uuid).firstOrNull;
    if (existing == null) return null;

    final duplicated = AlertRule.create(
      pair: existing.pair,
      exchangeId: existing.exchangeId,
      checkIntervalSeconds: existing.checkIntervalSeconds,
      conditionType: existing.conditionType,
      direction: existing.direction,
      targetPrice: existing.targetPrice,
      percent: existing.percent,
      deltaAbsolute: existing.deltaAbsolute,
      volumePercent: existing.volumePercent,
      currentPrice: existing.basePrice,
      currentVolume: existing.baseVolume,
    );

    await saveRule(duplicated);
    return duplicated;
  }

  /// Exports all alert rules to a formatted JSON string
  Future<String> exportAlertsToJson() async {
    if (!_isLoaded) await load();
    final payload = {
      'version': 1,
      'exportedAt': DateTime.now().toIso8601String(),
      'rules': _rules.map((r) => r.toJson()).toList(),
    };
    return const JsonEncoder.withIndent('  ').convert(payload);
  }

  /// Imports alert rules from a JSON string into local storage
  Future<int> importAlertsFromJson(String jsonString) async {
    if (!_isLoaded) await load();
    try {
      final dynamic decoded = jsonDecode(jsonString);
      var importedCount = 0;

      List<dynamic> items = [];
      if (decoded is Map<String, dynamic> && decoded['rules'] is List) {
        items = decoded['rules'] as List<dynamic>;
      } else if (decoded is List<dynamic>) {
        items = decoded;
      }

      for (final item in items) {
        if (item is Map<String, dynamic>) {
          try {
            final rule = AlertRule.fromJson(item);
            final index = _rules.indexWhere((r) => r.uuid == rule.uuid);
            if (index >= 0) {
              _rules[index] = rule;
            } else {
              _rules.add(rule);
            }
            importedCount++;
          } catch (e) {
            debugPrint('Error importing rule: $e');
          }
        }
      }

      if (importedCount > 0) {
        // Imported rules are authoritative user data: clear the guard.
        _loadFailed = false;
        _notify();
        await _persist();
      }

      return importedCount;
    } catch (e) {
      debugPrint('Failed to parse import JSON: $e');
      return 0;
    }
  }

  void _notify({bool syncToServer = true}) {
    if (!_rulesStreamController.isClosed) {
      _rulesStreamController.add(List.unmodifiable(_rules));
    }
    NativeWidgetSyncService.syncAlerts(_rules);
    if (syncToServer) {
      if (_loadFailed) {
        debugPrint('⏸️ [Repo] Skipping server sync: load failed (local rules may be incomplete).');
      } else {
        ServerAlertService.syncAllRulesToServer(_rules);
      }
    }
  }

  Completer<void>? _pendingPersist;
  bool _isPersisting = false;

    /// Atomic write: write to `alerts.json.tmp`, back up the previous good file to
  /// `alerts.json.bak`, then rename tmp -> alerts.json (atomic on the same filesystem).
  /// A crash or power loss can only leave the old file intact or a complete new one;
  /// never a half-written file.
  Future<void> _persist() async {
    if (_isPersisting) {
      _pendingPersist ??= Completer<void>();
      return _pendingPersist!.future;
    }
    _isPersisting = true;
    try {
      // Safety: never overwrite the on-disk state with an empty list while
      // the previous load failed. A user-initiated add clears _loadFailed.
      if (_loadFailed) {
        debugPrint('⏸️ [Repo] Skipping _persist(): load failed, refusing to overwrite with ${_rules.length} rule(s).');
        return;
      }
      final payload = {
        'version': 1,
        'rules': _rules.map((r) => r.toJson()).toList(),
      };
      final jsonString = jsonEncode(payload);
      final targetFile = _file;
      final tmpFile = File('${targetFile.path}.tmp');
      final bakFile = File('${targetFile.path}.bak');

      // Ensure directory exists
      if (!await targetFile.parent.exists()) {
        await targetFile.parent.create(recursive: true);
      }

      // 1. Write the new content to a temp file (flush to disk before rename).
      await tmpFile.writeAsString(jsonString, flush: true);

      // 2. Back up the current good file (only if it exists and parses).
      //    If parsing fails, keep the existing .bak untouched so we never
      //    overwrite the last known-good copy with a corrupt one.
      if (await targetFile.exists()) {
        try {
          final previous = await targetFile.readAsString();
          if (previous.trim().isNotEmpty) {
            jsonDecode(previous); // throws if corrupt
            await targetFile.copy(bakFile.path);
          }
        } catch (_) {
          // Current file is corrupt; do not overwrite the .bak.
        }
      }

      // 3. Atomic rename: on the same filesystem this is a single OS operation.
      await tmpFile.rename(targetFile.path);
    } catch (e, stack) {
      debugPrint('Error persisting rules to JSON: $e\n$stack');
      // Best-effort cleanup of a leftover tmp file.
      try {
        final tmpFile = File('${_file.path}.tmp');
        if (await tmpFile.exists()) {
          await tmpFile.delete();
        }
      } catch (_) {}
    } finally {
      _isPersisting = false;
      if (_pendingPersist != null) {
        final next = _pendingPersist;
        _pendingPersist = null;
        _persist().then((_) {
          if (!(next?.isCompleted ?? true)) next?.complete();
        }).catchError((e) {
          if (!(next?.isCompleted ?? true)) next?.completeError(e);
        });
      }
    }
  }

    /// Re-reads alerts.json into memory while the file lock is held.
  /// If the file is missing or corrupt, memory is left unchanged so the
  /// caller's in-memory rule is not lost.
  Future<void> _reloadFromDiskUnderLock() async {
    try {
      final f = _file;
      if (!await f.exists()) return;
      final content = await f.readAsString();
      if (content.trim().isEmpty) return;
      final dynamic decoded = jsonDecode(content);
      final List<AlertRule> parsed = <AlertRule>[];
      if (decoded is Map<String, dynamic> && decoded['rules'] is List) {
        for (final item in decoded['rules'] as List<dynamic>) {
          if (item is Map<String, dynamic>) {
            try {
              parsed.add(AlertRule.fromJson(item));
            } catch (_) {}
          }
        }
      } else if (decoded is List<dynamic>) {
        for (final item in decoded) {
          if (item is Map<String, dynamic>) {
            try {
              parsed.add(AlertRule.fromJson(item));
            } catch (_) {}
          }
        }
      } else {
        return;
      }
      _rules
        ..clear()
        ..addAll(parsed);
    } catch (e) {
      debugPrint('⚠️ [Repo] _reloadFromDiskUnderLock failed (keeping memory): $e');
    }
  }

  /// Writes the in-memory rules to disk without acquiring the lock again.
  /// Must only be called while the file lock is held.
  Future<void> _persistRawLocked() async {
    try {
      final payload = {
        'version': 1,
        'rules': _rules.map((r) => r.toJson()).toList(),
      };
      final jsonString = jsonEncode(payload);
      final targetFile = _file;
      final tmpFile = File('${targetFile.path}.tmp');
      final bakFile = File('${targetFile.path}.bak');

      if (!await targetFile.parent.exists()) {
        await targetFile.parent.create(recursive: true);
      }

      await tmpFile.writeAsString(jsonString, flush: true);

      if (await targetFile.exists()) {
        try {
          final previous = await targetFile.readAsString();
          if (previous.trim().isNotEmpty) {
            jsonDecode(previous);
            await targetFile.copy(bakFile.path);
          }
        } catch (_) {}
      }

      await tmpFile.rename(targetFile.path);
    } catch (e, stack) {
      debugPrint('Error persisting rules (locked): $e\n$stack');
      try {
        final tmpFile = File('${_file.path}.tmp');
        if (await tmpFile.exists()) {
          await tmpFile.delete();
        }
      } catch (_) {}
    }
  }

  Future<void> dispose() async {
    await _rulesStreamController.close();
  }
}
