import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/alert_engine/repositories/json_alert_rule_repository.dart';

// Helper to build a minimal valid AlertRule for tests.
AlertRule _makeRule({required String uuid}) {
  return AlertRule(
    uuid: uuid,
    baseCurrency: 'BTC',
    counterCurrency: 'USDT',
    marketSymbol: 'BTCUSDT',
    exchangeId: 'binance',
    checkIntervalSeconds: 60,
    conditionType: AlertConditionType.priceThreshold,
    direction: AlertDirection.above,
    triggerMode: TriggerMode.oneShot,
    targetPrice: 50000,
    createdAt: DateTime.now(),
  );
}

void main() {
  group('JsonAlertRuleRepository', () {
    late Directory tmp;
    late JsonAlertRuleRepository repoA;
    late JsonAlertRuleRepository repoB;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('alert_repo_test_');
      repoA = JsonAlertRuleRepository(tmp.path);
      repoB = JsonAlertRuleRepository(tmp.path);
    });

    tearDown(() {
      try {
        tmp.deleteSync(recursive: true);
      } catch (_) {}
    });

    test('1) concurrent saves from two instances keep both rules', () async {
      await repoA.load();
      await repoB.load();

      await Future.wait([
        repoA.saveRule(_makeRule(uuid: 'rule-a'), syncToServer: false),
        repoB.saveRule(_makeRule(uuid: 'rule-b'), syncToServer: false),
      ]);

      final file = File('${tmp.path}/alerts.json');
      expect(await file.exists(), isTrue);

      final decoded = jsonDecode(await file.readAsString()) as Map<String, dynamic>;
      final uuids = (decoded['rules'] as List)
          .cast<Map<String, dynamic>>()
          .map((r) => r['uuid'] as String)
          .toSet();

      expect(uuids, containsAll(<String>{'rule-a', 'rule-b'}));
    });

    test('2) corrupt alerts.json recovers from .bak', () async {
      await repoA.load();
      // First save creates alerts.json.
      await repoA.saveRule(_makeRule(uuid: 'good-rule-1'), syncToServer: false);
      // Second save creates alerts.json.bak from the first good file.
      await repoA.saveRule(_makeRule(uuid: 'good-rule-2'), syncToServer: false);

      // .bak must exist now.
      final bakFile = File('${tmp.path}/alerts.json.bak');
      expect(await bakFile.exists(), isTrue,
          reason: 'second save should have created alerts.json.bak');

      // Corrupt the main file.
      final mainFile = File('${tmp.path}/alerts.json');
      await mainFile.writeAsString('{ this is not json');

      // repoB must recover from .bak (which holds good-rule-1).
      await repoB.load();
      final rules = repoB.allRules;
      expect(rules.length, 1);
      expect(rules.first.uuid, 'good-rule-1');

      // Since .bak was valid, recovery succeeded and no corrupt-file
      // preservation is expected. The corrupt main file is simply ignored.
    });

    test('3) _loadFailed blocks empty overwrite and sync', () async {
      final mainFile = File('${tmp.path}/alerts.json');
      await mainFile.writeAsString('{ broken json');

      await repoA.load();
      expect(repoA.allRules, isEmpty);

      await repoA.clearLocalOnly();

      final afterContent = await mainFile.readAsString();
      expect(afterContent.contains('{ broken json'), isTrue,
          reason: '_loadFailed must prevent empty overwrite');

      await repoA.saveRule(_makeRule(uuid: 'fresh-rule'), syncToServer: false);

      final recovered = jsonDecode(await mainFile.readAsString()) as Map<String, dynamic>;
      final uuids = (recovered['rules'] as List)
          .cast<Map<String, dynamic>>()
          .map((r) => r['uuid'] as String)
          .toSet();
      expect(uuids, contains('fresh-rule'));
    });

    test('4) updateRule mutates fresh disk version without losing concurrent user edit (Phase 2D-1a)', () async {
      await repoA.load();
      await repoB.load();

      final initial = _makeRule(uuid: 'rule-race').copyWith(targetPrice: 50000);
      await repoA.saveRule(initial, syncToServer: false);

      // User in repoB updates targetPrice to 55000
      final userEdit = initial.copyWith(targetPrice: 55000);
      await repoB.saveRule(userEdit, syncToServer: false);

      // Scheduler in repoA updates only lastCheckedPrice using updateRule
      final updated = await repoA.updateRule(
        'rule-race',
        (current) => current.copyWith(lastCheckedPrice: 49500),
        syncToServer: false,
      );
      expect(updated, isTrue);

      // Verify on disk: targetPrice remains 55000 and lastCheckedPrice is 49500
      await repoB.load();
      final savedRule = repoB.allRules.firstWhere((r) => r.uuid == 'rule-race');
      expect(savedRule.targetPrice, 55000);
      expect(savedRule.lastCheckedPrice, 49500);
    });

    test('5) updateRule returns false when rule is deleted and does not resurrect (Phase 2D-1a)', () async {
      await repoA.load();
      await repoB.load();

      await repoA.saveRule(_makeRule(uuid: 'rule-to-delete'), syncToServer: false);
      expect(repoA.allRules.any((r) => r.uuid == 'rule-to-delete'), isTrue);

      // User deletes rule in repoB
      await repoB.deleteRule('rule-to-delete');

      // Scheduler in repoA attempts updateRule
      final result = await repoA.updateRule(
        'rule-to-delete',
        (current) => current.copyWith(lastCheckedPrice: 12345),
        syncToServer: false,
      );
      expect(result, isFalse);

      // Must NOT be resurrected on disk
      await repoB.load();
      expect(repoB.allRules.any((r) => r.uuid == 'rule-to-delete'), isFalse);
    });

    test('6) updateRule returns false and skips save when _loadFailed is true (Phase 2D-1a)', () async {
      final mainFile = File('${tmp.path}/alerts.json');
      await mainFile.writeAsString('{ broken json');

      await repoA.load();
      expect(repoA.loadFailed, isTrue);

      final result = await repoA.updateRule(
        'any-uuid',
        (current) => current.copyWith(lastCheckedPrice: 12345),
        syncToServer: false,
      );
      expect(result, isFalse);

      final content = await mainFile.readAsString();
      expect(content.contains('{ broken json'), isTrue,
          reason: 'updateRule must not overwrite corrupt file when _loadFailed is active');
    });
  });
}