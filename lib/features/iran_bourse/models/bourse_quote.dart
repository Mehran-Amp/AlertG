import 'bourse_instrument.dart';

/// How the server classifies a Bourse quote (`state` in `GET /api/iran-bourse/quote/{id}`).
enum BourseState {
  /// Fresh price, market open. The only state in which alerts can fire.
  live,

  /// Market closed (outside hours, holiday, or the feed is quiet). Price is the last known one.
  closed,

  /// The instrument has not traded today.
  noTradeToday,

  /// The data feed is old; do not trust the price.
  stale,

  /// A state this app version does not know (forward compatible).
  unknown;

  static BourseState parse(Object? raw) {
    switch (raw is String ? raw.toUpperCase() : '') {
      case 'LIVE':
        return BourseState.live;
      case 'CLOSED':
        return BourseState.closed;
      case 'NO_TRADE_TODAY':
        return BourseState.noTradeToday;
      case 'STALE':
        return BourseState.stale;
      default:
        return BourseState.unknown;
    }
  }
}

/// Top-of-book order level (best bid or best ask) from `GET /api/iran-bourse/quote/{id}`.
class BourseOrderLevel {
  /// Price in Rial (IRR).
  final num price;

  /// Share volume waiting at this price level.
  final num volume;

  /// Number of queued orders at this level, when provided by the feed.
  final int? orders;

  const BourseOrderLevel({
    required this.price,
    required this.volume,
    this.orders,
  });

  static BourseOrderLevel? tryParse(Object? json) {
    if (json is! Map) return null;
    final p = _n(json['price']);
    if (p == null || p <= 0) return null;
    final v = _n(json['volume']) ?? 0;
    final o = _n(json['orders']);
    return BourseOrderLevel(
      price: p,
      volume: v,
      orders: o?.toInt(),
    );
  }
}

/// One Bourse quote from `GET /api/iran-bourse/quote/{id}`.
/// All prices are Rial (IRR). [symbol] is the instrument id and always a String (rule N6).
class BourseQuote {
  final String symbol;
  final String ticker;
  final String name;

  /// Price in Rial; null when the instrument has no usable price.
  final num? price;
  final BourseState state;

  /// True only when the server would let an alert fire on this price (state LIVE).
  final bool alertEligible;

  /// `last` or `close`, which price [price] is.
  final String? priceField;

  /// When the server last refreshed this data (UTC), computed on the server's own clock.
  final DateTime? asOf;

  /// Time of the last trade on the exchange, `HH:mm:ss` (Tehran).
  final String? lastTradeTime;

  final num? prevClose;
  final num? close;
  final double? changePct;
  final num? high;
  final num? low;
  final num? volume;
  final bool tradedToday;
  final bool isStale;
  final num? upperLimit;
  final num? lowerLimit;
  final num? nav;
  final Object? queueRaw;
  final BourseOrderLevel? bestBid;
  final BourseOrderLevel? bestAsk;

  final String? marketCode;
  final String? market;
  final String? typeCode;
  final String? type;
  final String? sectorCode;
  final String? sector;
  final String unit;
  final bool cached;

  const BourseQuote({
    required this.symbol,
    required this.ticker,
    required this.name,
    required this.state,
    this.price,
    this.alertEligible = false,
    this.priceField,
    this.asOf,
    this.lastTradeTime,
    this.prevClose,
    this.close,
    this.changePct,
    this.high,
    this.low,
    this.volume,
    this.tradedToday = false,
    this.isStale = false,
    this.upperLimit,
    this.lowerLimit,
    this.nav,
    this.queueRaw,
    this.bestBid,
    this.bestAsk,
    this.marketCode,
    this.market,
    this.typeCode,
    this.type,
    this.sectorCode,
    this.sector,
    this.unit = 'IRR',
    this.cached = false,
  });

  /// Parses the server's quote object. Returns `null` when it is unusable
  /// (no string instrument id). Never throws.
  static BourseQuote? tryParse(Object? json) {
    if (json is! Map) return null;
    final id = json['symbol'];
    if (id is! String || !BourseInstrument.isValidId(id)) return null; // N6
    final asOfRaw = json['asOf'];
    return BourseQuote(
      symbol: id,
      ticker: _s(json['ticker']) ?? '',
      name: _s(json['name']) ?? '',
      state: BourseState.parse(json['state']),
      price: _n(json['price']),
      alertEligible: json['alert_eligible'] == true,
      priceField: _s(json['price_field']),
      asOf: asOfRaw is num
          ? DateTime.fromMillisecondsSinceEpoch(asOfRaw.toInt() * 1000, isUtc: true)
          : null,
      lastTradeTime: _s(json['last_trade_time']),
      prevClose: _n(json['prev_close']),
      close: _n(json['close']),
      changePct: _n(json['change_pct'])?.toDouble(),
      high: _n(json['high']),
      low: _n(json['low']),
      volume: _n(json['volume']),
      tradedToday: json['traded_today'] == true,
      isStale: json['is_stale'] == true,
      upperLimit: _n(json['upper_limit']),
      lowerLimit: _n(json['lower_limit']),
      nav: _n(json['nav']),
      queueRaw: json['queue'],
      bestBid: BourseOrderLevel.tryParse(json['best_bid']),
      bestAsk: BourseOrderLevel.tryParse(json['best_ask']),
      marketCode: _s(json['market_code']),
      market: _s(json['market']),
      typeCode: _s(json['type_code']),
      type: _s(json['type']),
      sectorCode: _s(json['sector_code']),
      sector: _s(json['sector']),
      unit: _s(json['unit']) ?? 'IRR',
      cached: json['cached'] == true,
    );
  }

  /// Short text for a queue badge, or null when there is no queue.
  String? get queueLabel => queueLabelOf(queueRaw);

  /// True when this quote carries a price the UI may show as "current".
  bool get hasPrice => price != null && price! > 0;

  /// ETF NAV bubble percentage: `(price - nav) / nav * 100`.
  /// Positive means trading at a premium above NAV; negative means discount below NAV.
  double? get navBubblePct {
    final p = price;
    final n = nav;
    if (p == null || p <= 0 || n == null || n <= 0) return null;
    final pct = (p - n) / n * 100.0;
    return (pct.isNaN || pct.isInfinite) ? null : pct;
  }

  /// Close price percent change vs yesterday's close, when both are positive.
  double? get closeChangePct {
    final c = close;
    final prev = prevClose;
    if (c == null || c <= 0 || prev == null || prev <= 0) return null;
    final pct = (c - prev) / prev * 100.0;
    return (pct.isNaN || pct.isInfinite) ? null : pct;
  }

  String? get typeLabel => type ?? typeCode;
  String? get marketLabel => market ?? marketCode;

  @override
  String toString() => 'BourseQuote($symbol, $state, $price)';
}

String? _s(Object? v) => v == null ? null : (v is String ? v : v.toString());

num? _n(Object? v) => v is num ? v : null;
