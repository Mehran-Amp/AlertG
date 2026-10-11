import 'package:equatable/equatable.dart';

/// Represents a standardized trading pair on any financial exchange.
class CurrencyPair extends Equatable {
  /// Base asset currency symbol (e.g. "BTC", "ETH", "SOL")
  final String baseCurrency;

  /// Quote / counter asset currency symbol (e.g. "USDT", "USD", "EUR")
  final String counterCurrency;

  /// Raw symbol formatted as expected by the specific exchange API (e.g. "BTCUSDT", "BTC-USD")
  final String marketSymbol;

  const CurrencyPair({
    required this.baseCurrency,
    required this.counterCurrency,
    required this.marketSymbol,
  });

  /// Human-readable display label (e.g. "BTC / USDT")
  String get displayName => '$baseCurrency / $counterCurrency';

  @override
  List<Object?> get props => [baseCurrency, counterCurrency, marketSymbol];

  Map<String, dynamic> toJson() => {
    'baseCurrency': baseCurrency,
    'counterCurrency': counterCurrency,
    'marketSymbol': marketSymbol,
  };

  factory CurrencyPair.fromJson(Map<String, dynamic> json) => CurrencyPair(
    baseCurrency: json['baseCurrency'] as String,
    counterCurrency: json['counterCurrency'] as String,
    marketSymbol: json['marketSymbol'] as String,
  );
}
