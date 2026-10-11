import 'package:equatable/equatable.dart';
import '../currency_pair.dart';

/// Standardized financial market tick payload emitted across all exchanges.
class MarketTicker extends Equatable {
  final String? exchangeId;
  final CurrencyPair? pair;

  /// Latest traded price
  final double lastPrice;

  /// Total trading volume in counter currency over the last 24 hours
  final double volume24h;

  /// Highest traded price in the last 24 hours
  final double high24h;

  /// Lowest traded price in the last 24 hours
  final double low24h;

  /// Best current buy order price (bid)
  final double? bid;

  /// Best current sell order price (ask)
  final double? ask;

  /// Timestamp when the tick was emitted
  final DateTime timestamp;

  /// True source timestamp when the price was produced at source exchange/feed
  final DateTime? asOf;

  /// Market state: 'live', 'delayed', 'closed', 'stale'
  final String? state;

  /// Explicit quote/currency unit: e.g. 'USD', '%', 'pts', 'EUR', 'CNY'
  final String? quoteUnit;

  /// Originating price provider or upstream exchange: e.g. 'YahooFinance', 'CoinGecko'
  final String? source;

  const MarketTicker({
    this.exchangeId,
    this.pair,
    required this.lastPrice,
    required this.volume24h,
    double? high24h,
    double? low24h,
    this.bid,
    this.ask,
    required this.timestamp,
    this.asOf,
    this.state,
    this.quoteUnit,
    this.source,
  })  : high24h = high24h ?? lastPrice,
        low24h = low24h ?? lastPrice;

  @override
  List<Object?> get props => [
    exchangeId,
    pair,
    lastPrice,
    volume24h,
    high24h,
    low24h,
    bid,
    ask,
    timestamp,
    asOf,
    state,
    quoteUnit,
    source,
  ];

  Map<String, dynamic> toJson() => {
    if (exchangeId != null) 'exchangeId': exchangeId,
    'lastPrice': lastPrice,
    'volume24h': volume24h,
    'high24h': high24h,
    'low24h': low24h,
    'bid': bid,
    'ask': ask,
    'timestamp': timestamp.toIso8601String(),
    if (asOf != null) 'asOf': asOf!.toIso8601String(),
    if (state != null) 'state': state,
    if (quoteUnit != null) 'quoteUnit': quoteUnit,
    if (source != null) 'source': source,
  };

  factory MarketTicker.fromJson(Map<String, dynamic> json) => MarketTicker(
    exchangeId: json['exchangeId'] as String?,
    lastPrice: (json['lastPrice'] as num).toDouble(),
    volume24h: (json['volume24h'] as num).toDouble(),
    high24h: (json['high24h'] as num?)?.toDouble() ?? (json['lastPrice'] as num).toDouble(),
    low24h: (json['low24h'] as num?)?.toDouble() ?? (json['lastPrice'] as num).toDouble(),
    bid: (json['bid'] as num?)?.toDouble(),
    ask: (json['ask'] as num?)?.toDouble(),
    timestamp: DateTime.parse(json['timestamp'] as String),
    asOf: json['asOf'] != null ? DateTime.parse(json['asOf'] as String) : null,
    state: json['state'] as String?,
    quoteUnit: json['quoteUnit'] as String?,
    source: json['source'] as String?,
  );
}
