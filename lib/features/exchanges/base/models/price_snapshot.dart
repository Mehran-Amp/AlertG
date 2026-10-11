import 'package:equatable/equatable.dart';

/// Lightweight price and volume snapshot for rule evaluation without full ticker metadata.
class PriceSnapshot extends Equatable {
  final double price;
  final double? volume;
  final DateTime fetchedAt;

  /// True source timestamp when the price was produced at source exchange/feed
  final DateTime? asOf;

  /// Market state: 'live', 'delayed', 'closed', 'stale'
  final String? state;

  /// Explicit quote/currency unit: e.g. 'USD', '%', 'pts', 'EUR', 'CNY'
  final String? quoteUnit;

  /// Originating price provider or upstream exchange: e.g. 'YahooFinance', 'CoinGecko'
  final String? source;

  const PriceSnapshot({
    required this.price,
    this.volume,
    required this.fetchedAt,
    this.asOf,
    this.state,
    this.quoteUnit,
    this.source,
  });

  @override
  List<Object?> get props => [
    price,
    volume,
    fetchedAt,
    asOf,
    state,
    quoteUnit,
    source,
  ];

  @override
  String toString() =>
      'PriceSnapshot(price: $price, volume: $volume, fetchedAt: $fetchedAt, asOf: $asOf, state: $state, quoteUnit: $quoteUnit, source: $source)';
}
