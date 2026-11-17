import 'bourse_instrument.dart';

/// Category tabs of the Bourse browse list (IB-16). Keys match the server's `group` values.
enum BourseGroup {
  stocks('stocks'),
  funds('funds'),
  bonds('bonds'),
  rights('rights'),
  derivatives('derivatives'),
  other('other');

  final String key;
  const BourseGroup(this.key);

  /// Unknown or missing keys become [other], so a new server group never breaks the list.
  static BourseGroup fromKey(Object? key) {
    for (final g in BourseGroup.values) {
      if (g.key == key) return g;
    }
    return BourseGroup.other;
  }
}

/// Sort orders the server supports. Keys match the server's `sort` values.
enum BourseSort {
  value('value'),
  volume('volume'),
  change('change'),
  price('price'),
  name('name');

  final String key;
  const BourseSort(this.key);
}

/// Whether the displayed prices are live (market open) or the last known ones.
enum BourseSession {
  open,
  closed,
  stale,
  unknown;

  static BourseSession fromServer(Object? value) {
    switch (value) {
      case 'OPEN':
        return BourseSession.open;
      case 'CLOSED':
        return BourseSession.closed;
      case 'STALE':
        return BourseSession.stale;
      default:
        return BourseSession.unknown;
    }
  }

  /// True when the list shows live prices. Everything else is "last known price".
  bool get isLive => this == BourseSession.open;
}

/// Which trade the row's price comes from.
enum BoursePriceSource {
  last,
  close,
  yesterday,
  none;

  static BoursePriceSource fromServer(Object? value) {
    switch (value) {
      case 'last':
        return BoursePriceSource.last;
      case 'close':
        return BoursePriceSource.close;
      case 'yesterday':
        return BoursePriceSource.yesterday;
      default:
        return BoursePriceSource.none;
    }
  }
}

/// One row of `GET /api/iran-bourse/board`. All prices are Rial (IRR); the id is a String (N6).
class BourseBoardItem {
  final String id;
  final String ticker;
  final String name;

  /// The price to show: last trade, else closing price, else yesterday's. Null when unknown.
  final num? price;
  final BoursePriceSource priceSource;

  /// Percent change of the last price versus yesterday (e.g. -2.85 means -2.85 %).
  final double? changePct;
  final num? volume;
  final num? value;
  final bool traded;
  final BourseGroup group;
  final String? marketCode;
  final String? typeCode;
  final String? type;
  final String? sectorCode;
  final String? sector;
  final String? updateTime;

  const BourseBoardItem({
    required this.id,
    required this.ticker,
    required this.name,
    this.price,
    this.priceSource = BoursePriceSource.none,
    this.changePct,
    this.volume,
    this.value,
    this.traded = false,
    this.group = BourseGroup.other,
    this.marketCode,
    this.typeCode,
    this.type,
    this.sectorCode,
    this.sector,
    this.updateTime,
  });

  /// Shown name: the ticker, or the full name when the ticker is empty.
  String get displayTicker => ticker.isNotEmpty ? ticker : name;

  /// Returns `null` for an unusable row (no string id of 12-20 digits). Never throws.
  static BourseBoardItem? tryParse(Object? json) {
    if (json is! Map) return null;
    final rawId = json['id'];
    if (rawId is! String || !BourseInstrument.isValidId(rawId)) return null;
    return BourseBoardItem(
      id: rawId,
      ticker: _str(json['ticker']) ?? '',
      name: _str(json['name']) ?? '',
      price: _num(json['price']),
      priceSource: BoursePriceSource.fromServer(json['price_source']),
      changePct: _num(json['change_pct'])?.toDouble(),
      volume: _num(json['volume']),
      value: _num(json['value']),
      traded: json['traded'] == true,
      group: BourseGroup.fromKey(json['group']),
      marketCode: _str(json['market_code']),
      typeCode: _str(json['type_code']),
      type: _str(json['type']),
      sectorCode: _str(json['sector_code']),
      sector: _str(json['sector']),
      updateTime: _str(json['update_time']),
    );
  }
}

/// One page of the board, with the counts the category tabs need.
class BourseBoardPage {
  final List<BourseBoardItem> items;
  final int total;
  final int offset;
  final int limit;
  final BourseSession session;

  /// True when the server's market data is old (feed down or slow).
  final bool stale;

  /// Unix seconds of the data, or null.
  final int? asOf;
  final String sort;
  final bool descending;

  /// Number of instruments per group over the whole market (not just this page).
  final Map<BourseGroup, int> groupCounts;

  const BourseBoardPage({
    required this.items,
    required this.total,
    required this.offset,
    required this.limit,
    required this.session,
    required this.stale,
    required this.asOf,
    required this.sort,
    required this.descending,
    required this.groupCounts,
  });

  /// More rows exist after this page.
  bool get hasMore => offset + items.length < total;

  /// Offset to request for the next page.
  int get nextOffset => offset + items.length;

  /// Returns `null` when the body is not a board answer. Unusable rows are skipped.
  static BourseBoardPage? tryParse(Object? json) {
    if (json is! Map) return null;
    final rawItems = json['items'];
    final total = json['total'];
    if (rawItems is! List || total is! int) return null;
    final items = <BourseBoardItem>[];
    for (final row in rawItems) {
      final item = BourseBoardItem.tryParse(row);
      if (item != null) items.add(item);
    }
    final counts = <BourseGroup, int>{};
    final rawCounts = json['groups'];
    if (rawCounts is Map) {
      for (final g in BourseGroup.values) {
        final c = rawCounts[g.key];
        if (c is int) counts[g] = c;
      }
    }
    return BourseBoardPage(
      items: items,
      total: total,
      offset: json['offset'] is int ? json['offset'] as int : 0,
      limit: json['limit'] is int ? json['limit'] as int : items.length,
      session: BourseSession.fromServer(json['session']),
      stale: json['stale'] == true,
      asOf: json['as_of'] is int ? json['as_of'] as int : null,
      sort: json['sort'] is String ? json['sort'] as String : 'value',
      descending: json['order'] != 'asc',
      groupCounts: counts,
    );
  }
}

String? _str(Object? v) {
  if (v is! String) return null;
  final t = v.trim();
  return t.isEmpty ? null : t;
}

num? _num(Object? v) => (v is num && !v.isNaN && !v.isInfinite) ? v : null;
