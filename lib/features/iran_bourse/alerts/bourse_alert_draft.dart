import '../../alert_engine/models/alert_rule.dart';
import '../../exchanges/base/currency_pair.dart';
import '../models/bourse_instrument.dart';
import '../models/bourse_quote.dart';

/// Exchange id the server uses for the Iranian Bourse.
const String bourseExchangeId = 'tsetmc';

/// Counter currency of every Bourse alert: Rial (rule D1, no conversion).
const String bourseCurrency = 'IRR';

/// What the user wants to be warned about.
enum BourseAlertKind {
  /// Price reaches a level (Rial).
  price,

  /// Price moves by a percent versus yesterday's close.
  percentChange,

  /// Price moves by an amount in Rial versus yesterday's close.
  absoluteChange,
}

/// Why a draft cannot become an alert yet.
enum BourseAlertProblem {
  invalidInstrument,
  directionNotSupported,
  amountMissing,
  amountNotPositive,
  noPreviousClose,
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
/// changes are measured against **yesterday's close** (same as the server); only
/// above / below directions are offered in v1.
class BourseAlertDraft {
  final String instrumentId;
  final String ticker;
  final String name;
  final BourseAlertKind kind;
  final AlertDirection direction;

  /// Rial for [BourseAlertKind.price] and [BourseAlertKind.absoluteChange];
  /// percent (e.g. 3.0 for 3 %) for [BourseAlertKind.percentChange]. Null while empty.
  final double? amount;

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

  const BourseAlertDraft({
    required this.instrumentId,
    required this.ticker,
    required this.name,
    required this.kind,
    required this.direction,
    required this.amount,
    this.prevClose,
    this.lastPrice,
    this.upperLimit,
    this.lowerLimit,
    this.note,
    this.recurring = false,
  });

  /// Draft for the instrument of a loaded quote (the detail page's "create alert" callback).
  factory BourseAlertDraft.fromQuote(
    BourseQuote quote, {
    required BourseAlertKind kind,
    required AlertDirection direction,
    required double? amount,
    String? note,
    bool recurring = false,
  }) {
    return BourseAlertDraft(
      instrumentId: quote.symbol,
      ticker: quote.ticker,
      name: quote.name,
      kind: kind,
      direction: direction,
      amount: amount,
      prevClose: quote.prevClose,
      lastPrice: quote.price,
      upperLimit: quote.upperLimit,
      lowerLimit: quote.lowerLimit,
      note: note,
      recurring: recurring,
    );
  }

  /// Name shown in lists: the ticker, falling back to the full name, then the id.
  String get displayName {
    if (ticker.isNotEmpty) return ticker;
    if (name.isNotEmpty) return name;
    return instrumentId;
  }

  /// `null` when the draft can be turned into an alert.
  BourseAlertProblem? validate() {
    if (!BourseInstrument.isValidId(instrumentId)) return BourseAlertProblem.invalidInstrument;
    if (direction == AlertDirection.bothSides) return BourseAlertProblem.directionNotSupported;
    final a = amount;
    if (a == null || a.isNaN || a.isInfinite) return BourseAlertProblem.amountMissing;
    if (a <= 0) return BourseAlertProblem.amountNotPositive;
    if (kind != BourseAlertKind.price && !(prevClose != null && prevClose! > 0)) {
      return BourseAlertProblem.noPreviousClose;
    }
    return null;
  }

  /// The price this alert would need, in Rial, when it can be worked out (used for the hints).
  double? get triggerPrice {
    final a = amount;
    if (a == null || a.isNaN || a.isInfinite || a <= 0) return null;
    if (kind == BourseAlertKind.price) return a;
    final base = prevClose;
    if (base == null || base <= 0) return null;
    final sign = direction == AlertDirection.below ? -1.0 : 1.0;
    if (kind == BourseAlertKind.percentChange) return base * (1 + sign * a / 100.0);
    return base + sign * a; // absoluteChange
  }

  /// A hint about the target, or null. Never blocks creating the alert.
  BourseAlertWarning? warning() {
    final target = triggerPrice;
    if (target == null || direction == AlertDirection.bothSides) return null;
    final up = upperLimit;
    final low = lowerLimit;
    final last = lastPrice;
    if (direction == AlertDirection.above) {
      if (up != null && up > 0 && target > up) return BourseAlertWarning.unreachableToday;
      if (last != null && last > 0 && last >= target) return BourseAlertWarning.alreadyReached;
    } else {
      if (low != null && low > 0 && target < low) return BourseAlertWarning.unreachableToday;
      if (last != null && last > 0 && last <= target) return BourseAlertWarning.alreadyReached;
    }
    return null;
  }

  /// Builds the alert rule. Throws [ArgumentError] when [validate] reports a problem.
  ///
  /// The rule uses exchange `tsetmc`, the id as market symbol, the ticker as base currency
  /// and `IRR` as counter currency. `preferServerProxy` is on so any local check asks the server.
  AlertRule toRule({
    int checkIntervalSeconds = 60,
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
    final a = amount!;
    final AlertConditionType type;
    switch (kind) {
      case BourseAlertKind.price:
        type = AlertConditionType.priceThreshold;
        break;
      case BourseAlertKind.percentChange:
        type = AlertConditionType.percentChange;
        break;
      case BourseAlertKind.absoluteChange:
        type = AlertConditionType.absolutePriceChange;
        break;
    }

    final trimmedNote = note?.trim();
    final rule = AlertRule.create(
      pair: CurrencyPair(
        baseCurrency: displayName,
        counterCurrency: bourseCurrency,
        marketSymbol: instrumentId,
      ),
      exchangeId: bourseExchangeId,
      checkIntervalSeconds: checkIntervalSeconds,
      conditionType: type,
      direction: direction,
      targetPrice: kind == BourseAlertKind.price ? a : null,
      percent: kind == BourseAlertKind.percentChange ? a : null,
      deltaAbsolute: kind == BourseAlertKind.absoluteChange ? a : null,
      // Change alerts start from yesterday's close (the server's daily base);
      // a price-level alert starts from the last known price.
      currentPrice: (kind == BourseAlertKind.price ? lastPrice : prevClose)?.toDouble(),
      customNote: (trimmedNote == null || trimmedNote.isEmpty) ? null : trimmedNote,
      customSound: customSound,
      language: language,
      soundEnabled: soundEnabled,
      ttsEnabled: ttsEnabled,
      vibrationEnabled: vibrationEnabled,
      flashEnabled: flashEnabled,
      preferServerProxy: true,
    );
    // AlertRule.create makes absolute-change alerts recurring; the Bourse default is "fire once".
    return rule.copyWith(triggerMode: recurring ? TriggerMode.recurring : TriggerMode.oneShot);
  }
}
