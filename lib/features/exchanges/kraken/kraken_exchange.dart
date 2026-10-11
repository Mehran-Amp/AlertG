import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Kraken REST Exchange Adapter (Unrestricted access to all Kraken pairs)
class KrakenExchange implements Exchange {
  final Dio _dio;

  KrakenExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.kraken.com',
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 10),
            ));

  @override
  String get id => 'kraken';

  @override
  String get name => 'Kraken';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🇺🇸 USA / EU (700+ Pairs)';

  @override
  String get defaultCounterCurrency => 'USD';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/0/public/AssetPairs');
      final result = response.data?['result'] as Map<String, dynamic>?;
      if (result != null && result.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final entry in result.entries) {
          final val = entry.value as Map<String, dynamic>?;
          final wsname = val?['wsname']?.toString(); // e.g. "XBT/USD", "ETH/USD"
          final status = val?['status']?.toString();

          if (status != 'cancel_only' && status != 'delisted') {
            if (wsname != null && wsname.contains('/')) {
              final parts = wsname.split('/');
              pairs.add(CurrencyPair(
                baseCurrency: parts[0].replaceAll('XBT', 'BTC'),
                counterCurrency: parts[1],
                marketSymbol: entry.key,
              ));
            } else {
              final base = (val?['base']?.toString() ?? '').replaceAll('XXBT', 'BTC').replaceAll('XETH', 'ETH').replaceAll('ZUSD', 'USD');
              final quote = (val?['quote']?.toString() ?? '').replaceAll('ZUSD', 'USD').replaceAll('ZEUR', 'EUR');
              if (base.isNotEmpty && quote.isNotEmpty) {
                pairs.add(CurrencyPair(
                  baseCurrency: base,
                  counterCurrency: quote,
                  marketSymbol: entry.key,
                ));
              }
            }
          }
        }
        if (pairs.isNotEmpty) return pairs;
      }
    } catch (_) {}

    return CryptoCatalogData.buildPairs(
      quoteCurrencies: ['USD', 'EUR', 'USDT'],
    );
  }

  @override
  Future<PriceSnapshot> fetchSnapshot(CurrencyPair pair) async {
    final ticker = await fetchTicker(pair);
    return PriceSnapshot(
      price: ticker.lastPrice,
      volume: ticker.volume24h,
      fetchedAt: ticker.timestamp,
    );
  }

  @override
  Future<MarketTicker> fetchTicker(CurrencyPair pair) async {
    final symbol = pair.marketSymbol;
    try {
      final response = await _dio.get(
        '/0/public/Ticker',
        queryParameters: {'pair': symbol},
      );

      final result = response.data?['result'] as Map<String, dynamic>?;
      final pairData = result?.values.firstOrNull as Map<String, dynamic>?;

      if (pairData == null) {
        throw Exception('Ticker not found on Kraken for $symbol');
      }

      final c = pairData['c'] as List?;
      final price = double.tryParse(c?.firstOrNull?.toString() ?? '0') ?? 0.0;
      final v = pairData['v'] as List?;
      final vol = double.tryParse(v?.lastOrNull?.toString() ?? '0') ?? 0.0;

      if (price <= 0) {
        throw Exception('Invalid price received from Kraken ($price)');
      }

      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: price,
        volume24h: vol,
        timestamp: DateTime.now(),
      );
    } catch (e) {
      throw Exception('Kraken Live Connection Error for ${pair.displayName}: $e');
    }
  }
}
