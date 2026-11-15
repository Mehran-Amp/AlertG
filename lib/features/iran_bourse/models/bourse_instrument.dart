/// Iranian Bourse (TSETMC) instrument, as returned by `GET /api/iran-bourse/symbols`.
///
/// Rules (IB plan):
///  * N6  - the instrument id is a **String** everywhere. Ids are 12-20 digits and exceed
///          2^53, so a JSON *number* id is rejected instead of being silently rounded.
///  * D1  - every price is in **Rial** (IRR). No unit conversion anywhere in the app.
///  * Labels (`market`, `board`, `type`, `sector`) and `nav`, `queue`, ... may be `null`.
class BourseInstrument {
  /// TSETMC instrument id, digits only, always a String.
  final String id;
  final String? isin;
  final String ticker;
  final String name;

  /// Last trade price, closing price and yesterday's close (Rial). Null when absent.
  final num? last;
  final num? close;
  final num? yesterday;

  /// Percent change of the last price versus yesterday (e.g. 0.46 means +0.46 %).
  final double? lastChangePct;
  final double? closeChangePct;

  final num? high;
  final num? low;
  final num? volume;
  final bool traded;

  /// Daily price limits (Rial).
  final num? upperLimit;
  final num? lowerLimit;

  /// Net asset value (funds only). Null for other instruments.
  final num? nav;

  /// Buy/sell queue info, kept raw because its shape is not guaranteed. See [queueLabel].
  final Object? queueRaw;

  /// Time of the last update on the exchange, `HH:mm:ss` (Tehran), or null.
  final String? updateTime;

  final String? marketCode;
  final String? market;
  final String? boardCode;
  final String? board;
  final String? typeCode;
  final String? type;
  final String? sectorCode;
  final String? sector;

  const BourseInstrument({
    required this.id,
    required this.ticker,
    required this.name,
    this.isin,
    this.last,
    this.close,
    this.yesterday,
    this.lastChangePct,
    this.closeChangePct,
    this.high,
    this.low,
    this.volume,
    this.traded = false,
    this.upperLimit,
    this.lowerLimit,
    this.nav,
    this.queueRaw,
    this.updateTime,
    this.marketCode,
    this.market,
    this.boardCode,
    this.board,
    this.typeCode,
    this.type,
    this.sectorCode,
    this.sector,
  });

  /// True when the id has the shape the server accepts (12-20 digits).
  static bool isValidId(String id) => RegExp(r'^[0-9]{12,20}$').hasMatch(id);

  /// Parses one gateway/server row. Returns `null` when the row is unusable
  /// (no string id, or an id that is not 12-20 digits). Never throws.
  static BourseInstrument? tryParse(Object? json) {
    if (json is! Map) return null;
    final rawId = json['id'];
    if (rawId is! String || !isValidId(rawId)) return null; // N6: never accept a numeric id
    return BourseInstrument(
      id: rawId,
      isin: _str(json['isin']),
      ticker: _str(json['ticker']) ?? '',
      name: _str(json['name']) ?? '',
      last: _num(json['last']),
      close: _num(json['close']),
      yesterday: _num(json['yesterday']),
      lastChangePct: _num(json['last_change_pct'])?.toDouble(),
      closeChangePct: _num(json['close_change_pct'])?.toDouble(),
      high: _num(json['high']),
      low: _num(json['low']),
      volume: _num(json['volume']),
      traded: json['traded'] == true,
      upperLimit: _num(json['upper_limit']),
      lowerLimit: _num(json['lower_limit']),
      nav: _num(json['nav']),
      queueRaw: json['queue'],
      updateTime: _str(json['update_time']),
      marketCode: _str(json['market_code']),
      market: _str(json['market']),
      boardCode: _str(json['board_code']),
      board: _str(json['board']),
      typeCode: _str(json['type_code']),
      type: _str(json['type']),
      sectorCode: _str(json['sector_code']),
      sector: _str(json['sector']),
    );
  }

  /// Short text for a queue badge, or null when there is no queue.
  /// A String is shown as is; a Map is shown through its `side`/`type` field if present.
  String? get queueLabel => queueLabelOf(queueRaw);

  /// Name to show in lists: the ticker, falling back to the full name.
  String get displayTicker => ticker.isNotEmpty ? ticker : name;

  /// Best available label for the instrument type (name first, then code).
  String? get typeLabel => type ?? typeCode;

  /// Best available label for the market (name first, then code).
  String? get marketLabel => market ?? marketCode;

  @override
  bool operator ==(Object other) => other is BourseInstrument && other.id == id;

  @override
  int get hashCode => id.hashCode;

  @override
  String toString() => 'BourseInstrument($id, $ticker)';
}

String? queueLabelOf(Object? raw) {
  if (raw == null) return null;
  if (raw is String) return raw.trim().isEmpty ? null : raw.trim();
  if (raw is Map) {
    final v = raw['side'] ?? raw['type'];
    if (v is String && v.trim().isNotEmpty) return v.trim();
    return raw.isEmpty ? null : raw.toString();
  }
  return raw.toString();
}

String? _str(Object? v) {
  if (v == null) return null;
  if (v is String) return v;
  return v.toString();
}

num? _num(Object? v) {
  if (v is num) return v;
  return null;
}
