import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/alert_engine/repositories/json_alert_rule_repository.dart';
import 'package:bitcoin_checker/features/alert_engine/scheduler/scheduler_service.dart';
import 'package:bitcoin_checker/features/exchanges/base/exchange.dart';
import 'package:bitcoin_checker/features/exchanges/registry/exchange_registry.dart';
import 'package:bitcoin_checker/features/notifications/models/alert_dispatch_result.dart';
import 'package:bitcoin_checker/features/notifications/services/notification_service_interface.dart';

class _SpyNotificationService implements NotificationServiceInterface {
  int callCount = 0;

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
    return AlertDispatchResult.shown;
  }
}

class _SpyExchangeRegistry implements ExchangeRegistry {
  int getCallCount = 0;

  @override
  Exchange? get(String exchangeId) {
    getCallCount++;
    return null;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  test('IB-17b: SchedulerService skips local evaluation for tsetmc alerts', () async {
    final tmpDir = await Directory.systemTemp.createTemp('bourse_sched_guard_');
    addTearDown(() async {
      if (await tmpDir.exists()) await tmpDir.delete(recursive: true);
    });

    final repo = JsonAlertRuleRepository(
      fileProvider: () async => File('${tmpDir.path}/rules.json'),
    );
    await repo.init();

    final rule = AlertRule(
      uuid: 'bourse-guard-1',
      exchangeId: 'tsetmc',
      baseCurrency: 'عیار',
      counterCurrency: 'IRR',
      marketSymbol: '34144395039913458',
      conditionType: AlertConditionType.priceThreshold,
      direction: AlertDirection.above,
      targetPrice: 600000,
      isActive: true,
      createdAt: DateTime.now().subtract(const Duration(minutes: 5)),
    );
    await repo.saveRule(rule, syncToServer: false);

    final notif = _SpyNotificationService();
    final registry = _SpyExchangeRegistry();
    final scheduler = SchedulerService(
      alertRuleRepository: repo,
      exchangeRegistry: registry,
      notificationService: notif,
    );
    addTearDown(scheduler.dispose);

    final evaluated = await scheduler.evaluateSingleRule(rule, DateTime.now());
    expect(evaluated, isFalse);
    expect(registry.getCallCount, 0);
    expect(notif.callCount, 0);

    final stored = repo.allRules.single;
    expect(stored.isActive, isTrue);
    expect(stored.triggerCount, 0);
    expect(stored.lastCheckedAt, isNull);
  });
}
