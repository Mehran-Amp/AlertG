import '../../alert_engine/models/alert_rule.dart';
import '../../exchanges/base/currency_pair.dart';
import '../models/bourse_instrument.dart';
import '../models/bourse_quote.dart';

/// Exchange id the server uses for the Iranian Bourse.
const String bourseExchangeId = 'tsetmc';

/// Counter currency of every Bourse alert: Rial (rule D1, no conversion).
const String bourseCurrency = 'IRR';

/// Minimum check interval allowed for Iranian Bourse alerts (matches server 180s).
const int minBourseCheckIntervalSeconds = 180;

/// What the user wants to be warned about.
enum BourseAlertKind {
  /// Price reaches a level (Rial).
  price,

  /// Price moves by a percent versus yesterday's close.
  percentChange,

  /// Price moves by an amount in Rial versus yesterday's close.
  absoluteChange,

  /// Instrument enters a buy queue at today's upper limit.
  queueBuy,

  /// Instrument enters a sell queue at today's lower limit.
  queueSell,

  /// Today's cumulative traded share volume reaches a threshold.
  volumeAbove,
}

/// Which Bourse price field the server evaluates against (IB-8 `raw_rule.price_field`).
enum BoursePriceField {
  /// Last trade price (server default).
  last,

  /// Daily closing price (قیمت پایانی).
  close,
}

/// Why a draft cannot become an alert yet.
enum BourseAlertProblem {
  invalidInstrument,
  directionNotSupported,
  amountMissing,
  amountNotPositive,
  noPreviousClose,
  bothSidesTargetsMissing,
  invalidRange,
  intervalTooShort,
}

/// A softer hint: the alert can be created but may never (or immediately) fire.
enum BourseAlertWarning {
  /// The target lies outside today's allowed price band, so it cannot be reached today.
  unreachableToday,

  /// The condition is already true at the last price, so the alert would fire at once.
  alreadyReached,
}

/// The user's choices for one Bourse alert, before it becomes an [AlertRule].
///
/// Rules: the instrument id is a String (N6); every price is Rial (D1); percent and Rial
/// changes are measured against **yesterday's close** (same as the server); above, below
/// and both-sides directions are all supported.
class BourseAlertDraft {
  final String instrumentId;
  final String ticker;
  final String name;
  final BourseAlertKind kind;
  final AlertDirection direction;

  /// Rial for single-direction [BourseAlertKind.price] and for [BourseAlertKind.absoluteChange];
  /// percent (e.g. 3.0 for 3 %) for [BourseAlertKind.percentChange];
  /// share count for [BourseAlertKind.volumeAbove]. Null while empty or for queue alerts.
  final double? amount;

  /// Optional minimum queue volume (shares) for [BourseAlertKind.queueBuy] / [BourseAlertKind.queueSell].
  final double? minQueueVolume;

  /// Upper target price in Rial for two-way [BourseAlertKind.price] alerts.
  final double? upperAmount;

  /// Lower target price in Rial for two-way [BourseAlertKind.price] alerts.
  final double? lowerAmount;

  /// Optional dedicated note when the upper target is hit (two-way price alerts).
  final String? upperNote;

  /// Optional dedicated note when the lower target is hit (two-way price alerts).
  final String? lowerNote;

  /// Behavior after the first trigger on two-way price alerts (OCO vs Dual-Active).
  final BothWayBehavior bothWayBehavior;

  /// Yesterday's close (Rial): the daily base for change alerts.
  final num? prevClose;

  /// Last known price (Rial), used for the "already reached" hint and the list display.
  final num? lastPrice;

  /// Today's allowed price band (Rial).
  final num? upperLimit;
  final num? lowerLimit;

  final String? note;

  /// Fire again after each trigger. Default false: fire once, then wait to be re-armed.
  final bool recurring;

  /// Which price field the server checks (`last` by default, or `close`).
  final BoursePriceField priceField;

  /// Server evaluation interval / recurring cooldown in seconds (min 180s).
  final int checkIntervalSeconds;

  const BourseAlertDraft({
    required this.instrumentId,
    required this.ticker,
    required this.name,
    required this.kind,
    required this.direction,
    required this.amount,
    this.minQueueVolume,
    this.upperAmount,
    this.lowerAmount,
    this.upperNote,
    this.lowerNote,
    this.bothWayBehavior = BothWayBehavior.oco,
    this.prevClose,
    this.lastPrice,
    this.upperLimit,
    this.lowerLimit,
    this.note,
    this.recurring = false,
    this.priceField = BoursePriceField.last,
    this.checkIntervalSeconds = minBourseCheckIntervalSeconds,
  });

  /// Draft for the instrument of a loaded quote (the detail page's "create alert" callback).
  factory BourseAlertDraft.fromQuote(
    BourseQuote quote, {
    required BourseAlertKind kind,
    required AlertDirection direction,
    required double? amount,
    double? minQueueVolume,
    double? upperAmount,
    double? lowerAmount,
    String? upperNote,
    String? lowerNote,
    BothWayBehavior bothWayBehavior = BothWayBehavior.oco,
    String? note,
    bool recurring = false,
    BoursePriceField priceField = BoursePriceField.last,
    int checkIntervalSeconds = minBourseCheckIntervalSeconds,
  }) {
    return BourseAlertDraft(
      instrumentId: quote.symbol,
      ticker: quote.ticker,
      name: quote.name,
      kind: kind,
      direction: direction,
      amount: amount,
      minQueueVolume: minQueueVolume,
      upperAmount: upperAmount,
      lowerAmount: lowerAmount,
      upperNote: upperNote,
      lowerNote: lowerNote,
      bothWayBehavior: bothWayBehavior,
      prevClose: quote.prevClose,
      lastPrice: quote.price,
      upperLimit: quote.upperLimit,
      lowerLimit: quote.lowerLimit,
      note: note,
      recurring: recurring,
      priceField: priceField,
      checkIntervalSeconds: checkIntervalSeconds,
    );
  }

  bool get isQueue => kind == BourseAlertKind.queueBuy || kind == BourseAlertKind.queueSell;
  bool get isVolume => kind == BourseAlertKind.volumeAbove;
  bool get isPriceBased =>
      kind == BourseAlertKind.price ||
      kind == BourseAlertKind.percentChange ||
      kind == BourseAlertKind.absoluteChange;
  bool get isTwoWayPrice => kind == BourseAlertKind.price && direction == AlertDirection.bothSides;

  /// Name shown in lists: the ticker, falling back to the full name, then the id.
  String get displayName {
    if (ticker.isNotEmpty) return ticker;
    if (name.isNotEmpty) return name;
    return instrumentId;
  }

  static bool _isFiniteNum(double? v) => v != null && !v.isNaN && !v.isInfinite;

  /// `null` when the draft can be turned into an alert.
  BourseAlertProblem? validate() {
    if (!BourseInstrument.isValidId(instrumentId)) return BourseAlertProblem.invalidInstrument;
    if (checkIntervalSeconds < minBourseCheckIntervalSeconds) {
      return BourseAlertProblem.intervalTooShort;
    }

    if (isQueue) {
      final minVol = minQueueVolume;
      if (minVol != null && (!_isFiniteNum(minVol) || minVol < 0)) {
        return BourseAlertProblem.amountNotPositive;
      }
      return null;
    }

    if (isVolume) {
      final a = amount;
      if (!_isFiniteNum(a)) return BourseAlertProblem.amountMissing;
      if (a! <= 0) return BourseAlertProblem.amountNotPositive;
      return null;
    }

    if (isTwoWayPrice) {
      final up = upperAmount;
      final low = lowerAmount;
      if (!_isFiniteNum(up) || !_isFiniteNum(low)) {
        return BourseAlertProblem.bothSidesTargetsMissing;
      }
      if (up! <= 0 || low! <= 0) return BourseAlertProblem.amountNotPositive;
      if (up <= low) return BourseAlertProblem.invalidRange;
      return null;
    }

    final a = amount;
    if (!_isFiniteNum(a)) return BourseAlertProblem.amountMissing;
    if (a! <= 0) return BourseAlertProblem.amountNotPositive;
    if (kind != BourseAlertKind.price && !(prevClose != null && prevClose! > 0)) {
      return BourseAlertProblem.noPreviousClose;
    }
    return null;
  }

  /// The single trigger price in Rial for one-way alerts (null for both-sides / queue / volume alerts).
  double? get triggerPrice {
    if (!isPriceBased || direction == AlertDirection.bothSides) return null;
    final a = amount;
    if (!_isFiniteNum(a) || a! <= 0) return null;
    if (kind == BourseAlertKind.price) return a;
    final base = prevClose;
    if (base == null || base <= 0) return null;
    final sign = direction == AlertDirection.below ? -1.0 : 1.0;
    if (kind == BourseAlertKind.percentChange) return base * (1 + sign * a / 100.0);
    return base + sign * a; // absoluteChange
  }

  /// Upper trigger price in Rial when scanning upward or both sides.
  double? get upperTriggerPrice {
    if (!isPriceBased) return null;
    if (isTwoWayPrice) {
      return (_isFiniteNum(upperAmount) && upperAmount! > 0) ? upperAmount : null;
    }
    if (direction == AlertDirection.below) return null;
    final a = amount;
    if (!_isFiniteNum(a) || a! <= 0) return null;
    if (kind == BourseAlertKind.price) return a;
    final base = prevClose;
    if (base == null || base <= 0) return null;
    if (kind == BourseAlertKind.percentChange) return base * (1 + a / 100.0);
    return base + a;
  }

  /// Lower trigger price in Rial when scanning downward or both sides.
  double? get lowerTriggerPrice {
    if (!isPriceBased) return null;
    if (isTwoWayPrice) {
      return (_isFiniteNum(lowerAmount) && lowerAmount! > 0) ? lowerAmount : null;
    }
    if (direction == AlertDirection.above) return null;
    final a = amount;
    if (!_isFiniteNum(a) || a! <= 0) return null;
    if (kind == BourseAlertKind.price) return a;
    final base = prevClose;
    if (base == null || base <= 0) return null;
    final v = kind == BourseAlertKind.percentChange ? base * (1 - a / 100.0) : base - a;
    return v > 0 ? v : null;
  }

  /// A hint about the target, or null. Never blocks creating the alert.
  BourseAlertWarning? warning() {
    if (!isPriceBased) return null;
    final upLimit = upperLimit;
    final lowLimit = lowerLimit;
    final last = lastPrice;

    if (direction == AlertDirection.bothSides) {
      final upTarget = upperTriggerPrice;
      final lowTarget = lowerTriggerPrice;
      if (upTarget == null && lowTarget == null) return null;

      final upOut = upTarget != null && upLimit != null && upLimit > 0 && upTarget > upLimit;
      final lowOut = lowTarget != null && lowLimit != null && lowLimit > 0 && lowTarget < lowLimit;
      if (upOut && lowOut) return BourseAlertWarning.unreachableToday;

      final upHit = upTarget != null && last != null && last > 0 && last >= upTarget;
      final lowHit = lowTarget != null && last != null && last > 0 && last <= lowTarget;
      if (upHit || lowHit) return BourseAlertWarning.alreadyReached;
      return null;
    }

    final target = triggerPrice;
    if (target == null) return null;
    if (direction == AlertDirection.above) {
      if (upLimit != null && upLimit > 0 && target > upLimit) return BourseAlertWarning.unreachableToday;
      if (last != null && last > 0 && last >= target) return BourseAlertWarning.alreadyReached;
    } else {
      if (lowLimit != null && lowLimit > 0 && target < lowLimit) return BourseAlertWarning.unreachableToday;
      if (last != null && last > 0 && last <= target) return BourseAlertWarning.alreadyReached;
    }
    return null;
  }

  static String? _cleanNote(String? raw) {
    final t = raw?.trim();
    return (t == null || t.isEmpty) ? null : t;
  }

  /// Builds the alert rule. Throws [ArgumentError] when [validate] reports a problem.
  ///
  /// The rule uses exchange `tsetmc`, the id as market symbol, the ticker as base currency
  /// and `IRR` as counter currency. `preferServerProxy` is on so any local check asks the server.
  AlertRule toRule({
    int? checkIntervalSeconds,
    String language = 'fa',
    String? customSound,
    bool soundEnabled = true,
    bool ttsEnabled = false,
    bool vibrationEnabled = true,
    bool flashEnabled = false,
  }) {
    final problem = validate();
    if (problem != null) {
      throw ArgumentError('Bourse alert draft is not valid: ${problem.name}');
    }

    final AlertConditionType type;
    final AlertDirection effectiveDirection;
    switch (kind) {
      case BourseAlertKind.price:
        type = AlertConditionType.priceThreshold;
        effectiveDirection = direction;
        break;
      case BourseAlertKind.percentChange:
        type = AlertConditionType.percentChange;
        effectiveDirection = direction;
        break;
      case BourseAlertKind.absoluteChange:
        type = AlertConditionType.absolutePriceChange;
        effectiveDirection = direction;
        break;
      case BourseAlertKind.queueBuy:
        type = AlertConditionType.queueBuy;
        effectiveDirection = AlertDirection.above;
        break;
      case BourseAlertKind.queueSell:
        type = AlertConditionType.queueSell;
        effectiveDirection = AlertDirection.below;
        break;
      case BourseAlertKind.volumeAbove:
        type = AlertConditionType.volumeAbove;
        effectiveDirection = AlertDirection.above;
        break;
    }

    final cleanedNote = _cleanNote(note);
    final cleanedUpperNote = isTwoWayPrice ? _cleanNote(upperNote) : null;
    final cleanedLowerNote = isTwoWayPrice ? _cleanNote(lowerNote) : null;
    final effectiveMinQueue = (isQueue && minQueueVolume != null && minQueueVolume! > 0) ? minQueueVolume : null;

    final rule = AlertRule.create(
      pair: CurrencyPair(
        baseCurrency: displayName,
        counterCurrency: bourseCurrency,
        marketSymbol: instrumentId,
      ),
      exchangeId: bourseExchangeId,
      checkIntervalSeconds: checkIntervalSeconds ?? this.checkIntervalSeconds,
      conditionType: type,
      direction: effectiveDirection,
      bothWayBehavior: isTwoWayPrice ? bothWayBehavior : BothWayBehavior.oco,
      targetPrice: (kind == BourseAlertKind.price && !isTwoWayPrice) || isVolume ? amount : null,
      upperTargetPrice: isTwoWayPrice ? upperAmount : null,
      upperNote: cleanedUpperNote,
      lowerTargetPrice: isTwoWayPrice ? lowerAmount : null,
      lowerNote: cleanedLowerNote,
      percent: kind == BourseAlertKind.percentChange ? amount : null,
      deltaAbsolute: kind == BourseAlertKind.absoluteChange ? amount : null,
      // Change alerts start from yesterday's close (the server's daily base);
      // price-level, queue, and volume alerts store the last known price.
      currentPrice: ((kind == BourseAlertKind.percentChange || kind == BourseAlertKind.absoluteChange)
              ? prevClose
              : lastPrice)
          ?.toDouble(),
      customNote: isTwoWayPrice ? (cleanedNote ?? cleanedUpperNote ?? cleanedLowerNote) : cleanedNote,
      customSound: customSound,
      language: language,
      soundEnabled: soundEnabled,
      ttsEnabled: ttsEnabled,
      vibrationEnabled: vibrationEnabled,
      flashEnabled: flashEnabled,
      preferServerProxy: true,
      priceField: (isPriceBased && priceField == BoursePriceField.close) ? 'close' : null,
      minQueueVolume: effectiveMinQueue,
    );

    final effectiveRecurring = isTwoWayPrice
        ? bothWayBehavior == BothWayBehavior.dualActive
        : recurring;
    // AlertRule.create makes absolute-change and bothSides percent alerts recurring;
    // the Bourse default is "fire once" unless recurring / dualActive is selected.
    return rule.copyWith(triggerMode: effectiveRecurring ? TriggerMode.recurring : TriggerMode.oneShot);
  }
}
