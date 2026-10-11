import 'dart:async';
import '../../exchanges/base/models/market_ticker.dart';
import '../../exchanges/registry/exchange_registry.dart';
import '../../notifications/models/notification_log.dart';
import '../../notifications/repositories/notification_repository.dart';
import '../../notifications/services/notification_service.dart';
import '../../settings/services/settings_service.dart';
import '../models/alert_rule.dart';
import '../repositories/json_alert_rule_repository.dart';
import 'condition_evaluator.dart';
import '../../../core/services/native_widget_sync_service.dart';
import '../../../core/services/server_alert_service.dart';
import '../../../core/services/tts_service.dart';

/// Personal Price-Alert Polling Scheduler Service.
/// Wakes up on a 1-second fine tick, checks which individual alert rules are due
/// based on each rule's specific `checkIntervalSeconds`, fetches prices via pure REST on demand,
/// evaluates conditions, triggers notifications, and updates baseline prices for recurring rules.
class SchedulerService {
  final JsonAlertRuleRepository _alertRuleRepository;
  final ExchangeRegistry _exchangeRegistry;
  final NotificationService _notificationService;
  final NotificationRepository? _notificationRepository;
  final SettingsService? _settingsService;

  Timer? _tickTimer;
  final Set<String> _evaluatingRuleUuids = {};
  final Map<String, (MarketTicker, DateTime)> _recentTickers = {};

  final _triggeredController = StreamController<AlertRule>.broadcast();
  Stream<AlertRule> get onRuleTriggered => _triggeredController.stream;

  SchedulerService({
    required JsonAlertRuleRepository alertRuleRepository,
    required ExchangeRegistry exchangeRegistry,
    required NotificationService notificationService,
    NotificationRepository? notificationRepository,
    SettingsService? settingsService,
  })  : _alertRuleRepository = alertRuleRepository,
        _exchangeRegistry = exchangeRegistry,
        _notificationService = notificationService,
        _notificationRepository = notificationRepository,
        _settingsService = settingsService;

  /// Starts the scheduler to periodically check due alert rules
  void start() {
    _tickTimer?.cancel();
    _tickTimer = Timer.periodic(const Duration(seconds: 1), (_) => _runTick());
  }

  /// Evaluates all due alert rules against market prices
  Future<void> _runTick() async {
    final now = DateTime.now();
    final activeRules = _alertRuleRepository.allRules.where((r) => r.isActive).toList();

    for (final rule in activeRules) {
      if (_evaluatingRuleUuids.contains(rule.uuid)) continue;
      if (rule.isInCooldown) continue;

      final lastTime = rule.lastCheckedAt ?? rule.createdAt;
      final elapsedSecs = now.difference(lastTime).inSeconds;

      if (elapsedSecs >= rule.checkIntervalSeconds) {
        _evaluatingRuleUuids.add(rule.uuid);
        _evaluateSingleRule(rule, now).whenComplete(() {
          _evaluatingRuleUuids.remove(rule.uuid);
        });
      }
    }
  }

  Future<MarketTicker?> _getLiveTicker(AlertRule rule, DateTime now) async {
    final cacheKey = '${rule.exchangeId}:${rule.pair.marketSymbol}';
    final cached = _recentTickers[cacheKey];
    if (cached != null && now.difference(cached.$2).inSeconds < 2) {
      return cached.$1;
    }

    // 1. If rule was determined to prefer server proxy (during alert creation), try server proxy first!
    if (rule.preferServerProxy) {
      final serverPrice = await ServerAlertService.fetchPriceViaServer(rule.exchangeId, rule.pair.marketSymbol);
      if (serverPrice != null && serverPrice > 0) {
        final t = MarketTicker(
          exchangeId: rule.exchangeId,
          pair: rule.pair,
          lastPrice: serverPrice,
          volume24h: 0.0,
          timestamp: now,
        );
        _recentTickers[cacheKey] = (t, now);
        return t;
      }
    }

    // 2. Try direct local fetch (5-second timeout for weak internet)
    final exchange = _exchangeRegistry.get(rule.exchangeId);
    if (exchange != null) {
      try {
        final localTicker = await exchange.fetchTicker(rule.pair).timeout(const Duration(seconds: 5));
        if (localTicker.lastPrice > 0) {
          _recentTickers[cacheKey] = (localTicker, now);
          return localTicker;
        }
      } catch (_) {
        // Direct local fetch failed or timed out
      }
    }

    // 3. Fallback: Query server proxy if not already tried
    if (!rule.preferServerProxy) {
      final serverPrice = await ServerAlertService.fetchPriceViaServer(rule.exchangeId, rule.pair.marketSymbol);
      if (serverPrice != null && serverPrice > 0) {
        final t = MarketTicker(
          exchangeId: rule.exchangeId,
          pair: rule.pair,
          lastPrice: serverPrice,
          volume24h: 0.0,
          timestamp: now,
        );
        _recentTickers[cacheKey] = (t, now);
        return t;
      }
    }

    return null;
  }

  Future<bool> _evaluateSingleRule(AlertRule rule, DateTime now) async {
    try {
      // 1. Fetch current price & volume via smart dual-route (Server proxy for filtered exchanges, local for domestic)
      final ticker = await _getLiveTicker(rule, now);

      // Never process non-positive or corrupted prices
      if (ticker == null || ticker.lastPrice <= 0) {
        final updatedRule = rule.copyWith(lastCheckedAt: now);
        await _alertRuleRepository.saveRule(updatedRule, syncToServer: false);
        return false;
      }

      // 2. Evaluate condition synchronously (pure functions, zero I/O)
      final result = ConditionEvaluator.evaluate(
        rule: rule,
        currentPrice: ticker.lastPrice,
        currentVolume: ticker.volume24h,
      );

      // 3. Prepare updated rule state with authentic live price and historical previous price
      final prevPrice = (rule.lastCheckedPrice != null && (rule.lastCheckedPrice! - ticker.lastPrice).abs() > 1e-8)
          ? rule.lastCheckedPrice
          : (rule.previousPrice ?? rule.basePrice);

      var updatedRule = rule.copyWith(
        lastCheckedAt: now,
        lastCheckedPrice: ticker.lastPrice,
        previousPrice: prevPrice,
      );

      if (result.isTriggered) {
        // Dispatch Notification with custom note and custom sound
        final finalBody = result.message;

        // Master Settings Override Logic:
        // If master setting is OFF, it suppresses all alerts; if ON, individual alert preference is honored!
        final settings = _settingsService?.settings;
        final effectiveSound = (settings?.soundEnabled ?? true) && rule.soundEnabled;
        final effectiveVibration = (settings?.vibrationEnabled ?? true) && rule.vibrationEnabled;
        final effectiveTts = (settings?.ttsEnabled ?? true) && rule.ttsEnabled;

        final speechText = effectiveTts
            ? TtsService.buildAlertSpeech(
                symbol: rule.pair.displayName,
                baseCurrency: rule.baseCurrency,
                counterCurrency: rule.counterCurrency,
                price: ticker.lastPrice,
                customNote: rule.note,
              )
            : null;

        // Use sequential alert queue so notification + sound + vibration + voice run sequentially
        _notificationService.enqueueCriticalAlert(
          id: rule.uuid.hashCode,
          title: result.title,
          body: finalBody,
          payload: rule.uuid,
          soundName: rule.customSound ?? 'alarm_siren',
          volume: settings?.alarmVolume ?? 1.0,
          soundEnabled: effectiveSound,
          vibrationEnabled: effectiveVibration,
          ttsEnabled: effectiveTts,
          speechText: speechText,
        );

        // Save notification log
        if (_notificationRepository != null) {
          final log = NotificationLog(
            uuid: DateTime.now().microsecondsSinceEpoch.toString(),
            ruleUuid: rule.uuid,
            exchangeId: rule.exchangeId,
            marketSymbol: rule.marketSymbol,
            title: result.title,
            message: finalBody,
            triggeredPrice: ticker.lastPrice,
            previousPrice: prevPrice,
            customNote: rule.note,
            conditionType: rule.conditionType.name,
            timestamp: now,
          );
          await _notificationRepository.saveLog(log);
        }

        // Update rule state per trigger mode
        updatedRule = updatedRule.copyWith(
          isActive: result.newIsActive,
          isTriggered: result.newIsTriggered,
          basePrice: result.newBasePrice, // New base price for subsequent % move calculations
          baseVolume: result.newBaseVolume,
          cooldownUntil: result.cooldownUntil,
          lastTriggeredAt: now,
          triggerCount: rule.triggerCount + 1,
        );

        _triggeredController.add(updatedRule);
      }

      // 4. Save updated rule to repository (only sync to cloud server when alert state changes)
      await _alertRuleRepository.saveRule(updatedRule, syncToServer: result.isTriggered);
      NativeWidgetSyncService.syncAlerts(_alertRuleRepository.allRules);
      return true;
    } catch (_) {
      // On offline / network failure: keep the last known valid price intact in repository
      return false;
    }
  }

  /// Trigger an immediate manual check for a specific rule
  Future<bool> checkRuleNow(AlertRule rule) async {
    return await _evaluateSingleRule(rule, DateTime.now());
  }

  /// Stops the scheduler
  void stop() {
    _tickTimer?.cancel();
    _tickTimer = null;
  }

  void dispose() {
    stop();
    _triggeredController.close();
  }
}
