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
  });
}