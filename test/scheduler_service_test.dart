import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/alert_engine/repositories/json_alert_rule_repository.dart';
import 'package:bitcoin_checker/features/alert_engine/scheduler/scheduler_service.dart';
import 'package:bitcoin_checker/features/exchanges/base/exchange.dart';
import 'package:bitcoin_checker/features/exchanges/base/currency_pair.dart';
import 'package:bitcoin_checker/features/exchanges/base/models/market_ticker.dart';
import 'package:bitcoin_checker/features/exchanges/registry/exchange_registry.dart';
import 'package:bitcoin_checker/features/notifications/models/alert_dispatch_result.dart';
import 'package:bitcoin_checker/features/notifications/services/notification_service_interface.dart';

/// Fake notification service: returns a controlled result.
class _FakeNotificationService implements NotificationServiceInterface {
  AlertDispatchResult nextResult;
  int callCount = 0;
  _FakeNotificationService(this.nextResult);

  @override
  Future<AlertDispatchResult> enqueueCriticalAlert({
    required int id,
    required String title,
    required String body,
    String? payload,
    String? soundName,
    double volume = 1.0,
    bool soundEnabled = true,
    bool vibrationEnabled = true,
    bool flashEnabled = false,
    bool ttsEnabled = false,
    String? speechText,
    bool inAppFeedback = true,
    bool waitForSpeech = false,
    Duration maxWait = const Duration(seconds: 12),
  }) async {
    callCount++;
    return nextResult;
  }
}

/// Fake exchange that returns a fixed ticker (price > target).
class _FakeExchange extends Exchange {
  final double price;
  _FakeExchange(this.price);

  @override
  String get id => 'binance';

  @override
  String get name => 'Fake Binance';

  @override
  String get defaultCounterCurrency => 'USDT';

  @override
  Future<MarketTicker> fetchTicker(CurrencyPair pair) async {
    return MarketTicker(
      exchangeId: id,
      pair: pair,
      lastPrice: price,
      volume24h: 0,
      timestamp: DateTime.now(),
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// Fake exchange registry: only 'binance' is registered.
class _FakeExchangeRegistry implements ExchangeRegistry {
  final Exchange exchange;
  _FakeExchangeRegistry(this.exchange);

  @override
  Exchange? get(String exchangeId) =>
      exchangeId == exchange.id ? exchange : null;

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

AlertRule _makeOneShotRule({required String uuid}) {
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
    isActive: true,
    isTriggered: false,
    createdAt: DateTime.now(),
  );
}

void main() {
  group('SchedulerService.evaluateSingleRule', () {
    late Directory tmp;
    late JsonAlertRuleRepository repo;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('sched_test_');
      repo = JsonAlertRuleRepository(tmp.path);
    });

    tearDown(() {
      try {
        tmp.deleteSync(recursive: true);
      } catch (_) {}
    });

    test('failed dispatch keeps a one-shot rule active (not committed)', () async {
      await repo.load();
      final rule = _makeOneShotRule(uuid: 'rule-failed');
      await repo.saveRule(rule, syncToServer: false);

      final fakeNotif = _FakeNotificationService(AlertDispatchResult.failed);
      final fakeExchange = _FakeExchange(60000);
      final fakeRegistry = _FakeExchangeRegistry(fakeExchange);

      final scheduler = SchedulerService(
        alertRuleRepository: repo,
        exchangeRegistry: fakeRegistry,
        notificationService: fakeNotif,
      );

      final now = DateTime.now();
      final savedRule = repo.allRules.firstWhere((r) => r.uuid == 'rule-failed');
      await scheduler.evaluateSingleRule(savedRule, now);

      expect(fakeNotif.callCount, 1);
      final after = repo.allRules.firstWhere((r) => r.uuid == 'rule-failed');
      expect(after.isActive, isTrue);
      expect(after.isTriggered, isFalse);
      expect(after.lastTriggeredAt, isNull);
      expect(after.lastCheckedAt, isNotNull);
    });

    test('duplicate dispatch commits the rule state', () async {
      await repo.load();
      final rule = _makeOneShotRule(uuid: 'rule-dup');
      await repo.saveRule(rule, syncToServer: false);

      final fakeNotif = _FakeNotificationService(AlertDispatchResult.duplicate);
      final fakeExchange = _FakeExchange(60000);
      final fakeRegistry = _FakeExchangeRegistry(fakeExchange);

      final scheduler = SchedulerService(
        alertRuleRepository: repo,
        exchangeRegistry: fakeRegistry,
        notificationService: fakeNotif,
      );

      final now = DateTime.now();
      final savedRule = repo.allRules.firstWhere((r) => r.uuid == 'rule-dup');
      await scheduler.evaluateSingleRule(savedRule, now);

      expect(fakeNotif.callCount, 1);
      final after = repo.allRules.firstWhere((r) => r.uuid == 'rule-dup');
      expect(after.isActive, isFalse);
      expect(after.isTriggered, isTrue);
      expect(after.lastTriggeredAt, isNotNull);
      expect(after.triggerCount, 1);
    });

    test('user edits targetPrice during evaluation without being overwritten (Phase 2D-1b)', () async {
      await repo.load();
      final rule = _makeOneShotRule(uuid: 'rule-concurrent-user-edit');
      await repo.saveRule(rule, syncToServer: false);

      final fakeNotif = _FakeNotificationService(AlertDispatchResult.shown);
      final fakeExchange = _FakeExchange(48000);
      final fakeRegistry = _FakeExchangeRegistry(fakeExchange);

      final scheduler = SchedulerService(
        alertRuleRepository: repo,
        exchangeRegistry: fakeRegistry,
        notificationService: fakeNotif,
      );

      final staleRule = repo.allRules.firstWhere((r) => r.uuid == 'rule-concurrent-user-edit');

      // Meanwhile, user updates targetPrice on disk to 45000
      final userUpdated = staleRule.copyWith(targetPrice: 45000);
      await repo.saveRule(userUpdated, syncToServer: false);

      final now = DateTime.now();
      await scheduler.evaluateSingleRule(staleRule, now);

      // Verify on disk: targetPrice remains 45000 and lastCheckedPrice is 48000
      await repo.load();
      final onDisk = repo.allRules.firstWhere((r) => r.uuid == 'rule-concurrent-user-edit');
      expect(onDisk.targetPrice, 45000);
      expect(onDisk.lastCheckedPrice, 48000);
    });

    test('deleted rule during evaluation is not resurrected (Phase 2D-1b)', () async {
      await repo.load();
      final rule = _makeOneShotRule(uuid: 'rule-deleted-in-flight');
      await repo.saveRule(rule, syncToServer: false);

      final fakeNotif = _FakeNotificationService(AlertDispatchResult.shown);
      final fakeExchange = _FakeExchange(60000);
      final fakeRegistry = _FakeExchangeRegistry(fakeExchange);

      final scheduler = SchedulerService(
        alertRuleRepository: repo,
        exchangeRegistry: fakeRegistry,
        notificationService: fakeNotif,
      );

      final staleRule = repo.allRules.firstWhere((r) => r.uuid == 'rule-deleted-in-flight');

      // Rule is deleted while evaluation is in-flight
      await repo.deleteRule('rule-deleted-in-flight');
      expect(repo.allRules.any((r) => r.uuid == 'rule-deleted-in-flight'), isFalse);

      final now = DateTime.now();
      final result = await scheduler.evaluateSingleRule(staleRule, now);
      expect(result, isFalse);

      // Must NOT be resurrected on disk
      await repo.load();
      expect(repo.allRules.any((r) => r.uuid == 'rule-deleted-in-flight'), isFalse);
    });
  });
}