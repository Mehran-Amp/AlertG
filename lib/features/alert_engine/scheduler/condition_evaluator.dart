import '../../../core/utils/format_utils.dart';
import '../models/alert_rule.dart';

/// Result of evaluating an alert rule condition against current market data
class EvaluationResult {
  final bool isTriggered;
  final String title;
  final String message;
  final double? newBasePrice;
  final double? newBaseVolume;
  final bool newIsActive;
  final bool newIsTriggered;
  final DateTime? cooldownUntil;

  const EvaluationResult({
    required this.isTriggered,
    this.title = '',
    this.message = '',
    this.newBasePrice,
    this.newBaseVolume,
    this.newIsActive = true,
    this.newIsTriggered = false,
    this.cooldownUntil,
  });

  static const notTriggered = EvaluationResult(isTriggered: false);
}

/// Pure evaluation functions per condition type with color-coded emojis and arrow formatting.
abstract class ConditionEvaluator {
  /// Evaluates an [AlertRule] against current market price and volume
  static EvaluationResult evaluate({
    required AlertRule rule,
    required double currentPrice,
    double? currentVolume,
  }) {
    if (rule.isInCooldown) {
      return EvaluationResult.notTriggered;
    }

    switch (rule.conditionType) {
      case AlertConditionType.priceThreshold:
        return _evaluatePriceThreshold(rule, currentPrice);
      case AlertConditionType.percentChange:
        return _evaluatePercentChange(rule, currentPrice);
      case AlertConditionType.absolutePriceChange:
        return _evaluateAbsolutePriceChange(rule, currentPrice);
      case AlertConditionType.volumeChange:
        return _evaluateVolumeChange(rule, currentVolume ?? 0.0);
    }
  }

  static String _formatVal(double val, {String? currencySymbol}) {
    return FormatUtils.formatPrice(val, currencySymbol: currencySymbol);
  }

  static String getFormattedExchangeName(String exchangeId) {
    final ex = exchangeId.toLowerCase();
    switch (ex) {
      case 'nobitex': return 'Nobitex';
      case 'wallex': return 'Wallex';
      case 'binance': return 'Binance';
      case 'tabdeal': return 'Tabdeal';
      case 'ramzinex': return 'Ramzinex';
      case 'kucoin': return 'KuCoin';
      case 'mexc': return 'MEXC';
      case 'gateio':
      case 'gate': return 'Gate.io';
      case 'coinex': return 'CoinEx';
      case 'okx': return 'OKX';
      case 'bybit': return 'Bybit';
      case 'bitbarg': return 'BitBarg';
      case 'tetherland': return 'Tetherland';
      case 'abantether': return 'AbanTether';
      case 'global_stocks':
      case 'stocks':
      case 'wallstreet': return 'Global Stocks';
      case 'forex': return 'Forex';
      case 'macro':
      case 'bonds': return 'Macro / Bonds';
      case 'iran_market': return 'Iran Market';
      default: return exchangeId.isNotEmpty ? '${exchangeId[0].toUpperCase()}${exchangeId.substring(1)}' : 'Unknown';
    }
  }

  static String _buildBodyText(AlertRule rule, double currentPrice) {
    final exName = getFormattedExchangeName(rule.exchangeId);
    final customNote = rule.customNote?.trim();
    if (customNote != null && customNote.isNotEmpty) {
      final cleanNote = customNote.startsWith('📝') ? customNote : '📝 $customNote';
      return '🏛️ $exName\n$cleanNote';
    }
    return '🏛️ $exName';
  }

  /// 1. Price Threshold (One-shot or Both Way Channel):
  static EvaluationResult _evaluatePriceThreshold(
    AlertRule rule,
    double currentPrice,
  ) {
    // A. Both Way Mode: Range / Channel Breakout
    if (rule.direction == AlertDirection.bothSides) {
      final upper = rule.upperTargetPrice;
      final lower = rule.lowerTargetPrice;

      final isDualActive = rule.bothWayBehavior == BothWayBehavior.dualActive;
      final newActive = isDualActive;
      final newTriggered = !isDualActive;
      final cooldown = isDualActive
          ? DateTime.now().add(Duration(seconds: rule.checkIntervalSeconds > 30 ? rule.checkIntervalSeconds : 30))
          : null;

      if (upper != null && upper > 0 && currentPrice >= upper) {
        // Upper breakout hit (e.g. Resistance reached)
        double percentDiff = 0.0;
        if (rule.basePrice != null && rule.basePrice! > 0) {
          percentDiff = ((currentPrice - rule.basePrice!) / rule.basePrice!) * 100.0;
        } else {
          percentDiff = ((currentPrice - upper) / upper) * 100.0;
        }

        final pctStr = '+${percentDiff.abs().toStringAsFixed(2)}%';
        final formattedPrice = _formatVal(currentPrice, currencySymbol: rule.pair.counterCurrency);
        final note = (rule.upperNote != null && rule.upperNote!.trim().isNotEmpty)
            ? (rule.upperNote!.trim().startsWith('📝') ? rule.upperNote!.trim() : '📝 ${rule.upperNote!.trim()}')
            : _buildBodyText(rule, currentPrice);

        return EvaluationResult(
          isTriggered: true,
          title: '🟢 ${rule.pair.displayName} $pctStr $formattedPrice ▲',
          message: note,
          newIsActive: newActive,
          newIsTriggered: newTriggered,
          newBasePrice: currentPrice,
          cooldownUntil: cooldown,
        );
      } else if (lower != null && lower > 0 && currentPrice <= lower) {
        // Lower breakdown hit (e.g. Support broken)
        double percentDiff = 0.0;
        if (rule.basePrice != null && rule.basePrice! > 0) {
          percentDiff = ((currentPrice - rule.basePrice!) / rule.basePrice!) * 100.0;
        } else {
          percentDiff = ((currentPrice - lower) / lower) * 100.0;
        }

        final pctStr = '-${percentDiff.abs().toStringAsFixed(2)}%';
        final formattedPrice = _formatVal(currentPrice, currencySymbol: rule.pair.counterCurrency);
        final note = (rule.lowerNote != null && rule.lowerNote!.trim().isNotEmpty)
            ? (rule.lowerNote!.trim().startsWith('📝') ? rule.lowerNote!.trim() : '📝 ${rule.lowerNote!.trim()}')
            : _buildBodyText(rule, currentPrice);

        return EvaluationResult(
          isTriggered: true,
          title: '🔴 ${rule.pair.displayName} $pctStr $formattedPrice ▼',
          message: note,
          newIsActive: newActive,
          newIsTriggered: newTriggered,
          newBasePrice: currentPrice,
          cooldownUntil: cooldown,
        );
      }

      return EvaluationResult.notTriggered;
    }

    // B. Single Direction Mode (Above or Below)
    final target = rule.targetPrice ?? 0.0;
    if (target <= 0.0) return EvaluationResult.notTriggered;

    bool triggered = false;
    if (rule.direction == AlertDirection.above) {
      triggered = currentPrice >= target;
    } else if (rule.direction == AlertDirection.below) {
      triggered = currentPrice <= target;
    }

    if (!triggered) return EvaluationResult.notTriggered;

    double percentDiff = 0.0;
    if (rule.basePrice != null && rule.basePrice! > 0) {
      percentDiff = ((currentPrice - rule.basePrice!) / rule.basePrice!) * 100.0;
    } else if (target > 0) {
      percentDiff = ((currentPrice - target) / target) * 100.0;
    }

    final isUpward = rule.direction == AlertDirection.above;
    final emoji = isUpward ? '🟢' : '🔴';
    final arrow = isUpward ? '▲' : '▼';
    final sign = isUpward ? '+' : '-';
    final pctStr = '$sign${percentDiff.abs().toStringAsFixed(2)}%';
    final formattedPrice = _formatVal(currentPrice, currencySymbol: rule.pair.counterCurrency);

    return EvaluationResult(
      isTriggered: true,
      title: '$emoji ${rule.pair.displayName} $pctStr $formattedPrice $arrow',
      message: _buildBodyText(rule, currentPrice),
      newIsActive: false,     // One-shot: deactivates
      newIsTriggered: true,   // Marked as triggered in UI
      newBasePrice: currentPrice,
    );
  }

  /// 2. Percent Change (Recurring):
  static EvaluationResult _evaluatePercentChange(
    AlertRule rule,
    double currentPrice,
  ) {
    final base = rule.basePrice ?? currentPrice;
    final targetPercent = rule.percent ?? 0.0;
    if (base <= 0.0 || targetPercent <= 0.0) return EvaluationResult.notTriggered;

    final diff = currentPrice - base;
    final actualPercent = (diff / base) * 100.0;

    bool triggered = false;
    if (rule.direction == AlertDirection.above) {
      triggered = actualPercent >= targetPercent;
    } else if (rule.direction == AlertDirection.below) {
      triggered = actualPercent <= -targetPercent;
    } else {
      triggered = actualPercent.abs() >= targetPercent;
    }

    if (!triggered) return EvaluationResult.notTriggered;

    final isUpward = actualPercent >= 0;
    final emoji = isUpward ? '🟢' : '🔴';
    final arrow = isUpward ? '▲' : '▼';
    final sign = isUpward ? '+' : '-';
    final pctStr = '$sign${actualPercent.abs().toStringAsFixed(2)}%';
    final formattedPrice = _formatVal(currentPrice, currencySymbol: rule.pair.counterCurrency);

    final isBothSides = rule.direction == AlertDirection.bothSides;
    final minCooldownSecs = rule.checkIntervalSeconds > 15 ? rule.checkIntervalSeconds : 30;
    final cooldown = DateTime.now().add(Duration(seconds: minCooldownSecs));

    return EvaluationResult(
      isTriggered: true,
      title: '$emoji ${rule.pair.displayName} $pctStr $formattedPrice $arrow',
      message: _buildBodyText(rule, currentPrice),
      newBasePrice: currentPrice, // Update baseline for next cycle to latest price!
      newIsActive: isBothSides,   // Only Both Way stays active (🔄 Active); Above & Below close!
      newIsTriggered: !isBothSides, // Above & Below close with ✅ Done; Both Way does not get Done
      cooldownUntil: cooldown,
    );
  }

  /// 3. Absolute Price Change (Recurring):
  static EvaluationResult _evaluateAbsolutePriceChange(
    AlertRule rule,
    double currentPrice,
  ) {
    final base = rule.basePrice ?? currentPrice;
    final delta = rule.deltaAbsolute ?? 0.0;
    if (delta <= 0.0) return EvaluationResult.notTriggered;

    final diff = currentPrice - base;

    bool triggered = false;
    if (rule.direction == AlertDirection.above) {
      triggered = diff >= delta;
    } else if (rule.direction == AlertDirection.below) {
      triggered = diff <= -delta;
    } else {
      triggered = diff.abs() >= delta;
    }

    if (!triggered) return EvaluationResult.notTriggered;

    final isUpward = diff >= 0;
    final actualPercent = base > 0 ? (diff / base) * 100.0 : 0.0;
    final emoji = isUpward ? '🟢' : '🔴';
    final arrow = isUpward ? '▲' : '▼';
    final sign = isUpward ? '+' : '-';
    final pctStr = '$sign${actualPercent.abs().toStringAsFixed(2)}%';
    final formattedPrice = _formatVal(currentPrice, currencySymbol: rule.pair.counterCurrency);
    final minCooldownSecs = rule.checkIntervalSeconds > 15 ? rule.checkIntervalSeconds : 30;
    final cooldown = DateTime.now().add(Duration(seconds: minCooldownSecs));

    return EvaluationResult(
      isTriggered: true,
      title: '$emoji ${rule.pair.displayName} $pctStr $formattedPrice $arrow',
      message: _buildBodyText(rule, currentPrice),
      newBasePrice: currentPrice,
      newIsActive: true,
      newIsTriggered: false,
      cooldownUntil: cooldown,
    );
  }

  /// 4. Volume Change (Recurring):
  static EvaluationResult _evaluateVolumeChange(
    AlertRule rule,
    double currentVolume,
  ) {
    final baseVolume = rule.baseVolume ?? currentVolume;
    final volumePercent = rule.volumePercent ?? 0.0;
    if (baseVolume <= 0.0 || volumePercent <= 0.0) {
      return EvaluationResult.notTriggered;
    }

    final diff = currentVolume - baseVolume;
    final actualPercent = (diff / baseVolume) * 100.0;

    if (actualPercent >= volumePercent) {
      final isUpward = actualPercent >= 0;
      final emoji = isUpward ? '🟢' : '🔴';
      final arrow = isUpward ? '▲' : '▼';
      final sign = isUpward ? '+' : '-';
      final pctStr = '$sign${actualPercent.abs().toStringAsFixed(2)}%';
      final currentPrice = rule.lastCheckedPrice ?? 0.0;
      final formattedPrice = _formatVal(currentPrice, currencySymbol: rule.pair.counterCurrency);
      final minCooldownSecs = rule.checkIntervalSeconds > 15 ? rule.checkIntervalSeconds : 30;
      final cooldown = DateTime.now().add(Duration(seconds: minCooldownSecs));

      return EvaluationResult(
        isTriggered: true,
        title: '$emoji ${rule.pair.displayName} $pctStr $formattedPrice $arrow',
        message: _buildBodyText(rule, currentPrice),
        newBaseVolume: currentVolume,
        newIsActive: true,
        newIsTriggered: false,
        cooldownUntil: cooldown,
      );
    }

    return EvaluationResult.notTriggered;
  }
}
