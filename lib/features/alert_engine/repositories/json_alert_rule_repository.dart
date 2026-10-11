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

  JsonAlertRuleRepository(this._storageDirectoryPath);

  File get _file => File('$_storageDirectoryPath/alerts.json');

  /// Read-only snapshot of current in-memory rules
  List<AlertRule> get allRules => List.unmodifiable(_rules);

  /// Read-only snapshot of active in-memory rules
  List<AlertRule> get activeRules =>
      List.unmodifiable(_rules.where((r) => r.isActive));

  /// Loads all rules from JSON file into memory.
  /// If the file is missing or corrupted, starts with an empty list without crashing.
  Future<void> load() async {
    try {
      final file = _file;
      if (await file.exists()) {
        final content = await file.readAsString();
        if (content.trim().isNotEmpty) {
          // Backup only if Mojibake corruption is detected before repair
          final bool hasMojibake = content.contains('Ã') ||
              content.contains('Ø') ||
              content.contains('Ù') ||
              content.contains('Â');

          if (hasMojibake) {
            try {
              // 1. Permanent first-time original backup (never overwritten)
              final initialBackup = File('$_storageDirectoryPath/alerts_original_corrupted.json.bak');
              if (!await initialBackup.exists()) {
                await file.copy(initialBackup.path);
                debugPrint('📦 [Backup] Preserved original pre-repair backup: ${initialBackup.path}');
              }
              // 2. Timestamped backup
              final ts = DateTime.now().toIso8601String().replaceAll(':', '-');
              final timeBackup = File('$_storageDirectoryPath/alerts_backup_$ts.json');
              await file.copy(timeBackup.path);
              debugPrint('📦 [Backup] Created timestamped backup: ${timeBackup.path}');
            } catch (be) {
              debugPrint('⚠️ [Backup] Warning backing up alerts file: $be');
            }
          }
          final dynamic decoded = jsonDecode(content);
          if (decoded is Map<String, dynamic> && decoded['rules'] is List) {
            final rulesList = decoded['rules'] as List<dynamic>;
            _rules.clear();
            for (final item in rulesList) {
              if (item is Map<String, dynamic>) {
                try {
                  _rules.add(AlertRule.fromJson(item));
                } catch (e) {
                  debugPrint('Failed to parse rule item: $e');
                }
              }
            }
          } else if (decoded is List<dynamic>) {
            // Backward compatibility for raw list
            _rules.clear();
            for (final item in decoded) {
              if (item is Map<String, dynamic>) {
                try {
                  _rules.add(AlertRule.fromJson(item));
                } catch (e) {
                  debugPrint('Failed to parse rule item: $e');
                }
              }
            }
          }
        }
      }
    } catch (e, stack) {
      debugPrint('Error loading alerts.json (starting fresh): $e\n$stack');
      _rules.clear();
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
    final rule = _rules.removeAt(oldIndex);
    _rules.insert(newIndex, rule);
    _notify();
    await _persist();
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
    final index = _rules.indexWhere((r) => r.uuid == rule.uuid);
    if (index >= 0) {
      _rules[index] = rule;
    } else {
      _rules.add(rule);
    }
    _notify(syncToServer: syncToServer);
    await _persist();
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
    final initialLength = _rules.length;
    _rules.removeWhere((r) => r.uuid == uuid);
    final removed = _rules.length < initialLength;
    if (removed) {
      _notify();
      await _persist();
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
      ServerAlertService.syncAllRulesToServer(_rules);
    }
  }

  Completer<void>? _pendingPersist;
  bool _isPersisting = false;

  /// Asynchronous atomic write: persists in-memory rules safely without file rename race conditions
  Future<void> _persist() async {
    if (_isPersisting) {
      _pendingPersist ??= Completer<void>();
      return _pendingPersist!.future;
    }
    _isPersisting = true;
    try {
      final payload = {
        'version': 1,
        'rules': _rules.map((r) => r.toJson()).toList(),
      };
      final jsonString = jsonEncode(payload);
      final targetFile = _file;

      // Ensure directory exists
      if (!await targetFile.parent.exists()) {
        await targetFile.parent.create(recursive: true);
      }

      // Safe atomic direct flush write
      await targetFile.writeAsString(jsonString, flush: true);
    } catch (e, stack) {
      debugPrint('Error persisting rules to JSON: $e\n$stack');
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

  Future<void> dispose() async {
    await _rulesStreamController.close();
  }
}
