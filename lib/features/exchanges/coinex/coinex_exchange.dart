import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// CoinEx REST Exchange Adapter (Unrestricted access to all 700+ crypto pairs)
class CoinExExchange implements Exchange {
  final Dio _dio;

  CoinExExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.coinex.com',
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 10),
            ));

  @override
  String get id => 'coinex';

  @override
  String get name => 'CoinEx';

  @override
  ExchangeCategory get category => ExchangeCategory.middleEast;

  @override
  String get countryBadge => '🌐 Global / Middle East';

  @override
  String get defaultCounterCurrency => 'USDT';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/v1/market/list');
      final list = response.data?['data'] as List?;
      if (list != null && list.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final item in list) {
          final symbol = item.toString().toUpperCase();
          if (symbol.endsWith('USDT') || symbol.endsWith('USDC') || symbol.endsWith('BTC')) {
            String quote = 'USDT';
            if (symbol.endsWith('USDC')) quote = 'USDC';
            if (symbol.endsWith('BTC')) quote = 'BTC';

            final base = symbol.substring(0, symbol.length - quote.length);
            if (base.isNotEmpty) {
              pairs.add(CurrencyPair(
                baseCurrency: base,
                counterCurrency: quote,
                marketSymbol: symbol,
              ));
            }
          }
        }
        if (pairs.isNotEmpty) return pairs;
      }
    } catch (_) {}

    return CryptoCatalogData.buildPairs(quoteCurrencies: ['USDT', 'USDC']);
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
    final market = '${pair.baseCurrency}${pair.counterCurrency}'.toUpperCase();
    try {
      final response = await _dio.get(
        '/v1/market/ticker',
        queryParameters: {'market': market},
      );

      final tickerData = response.data?['data']?['ticker'] as Map<String, dynamic>?;
      if (tickerData == null) {
        throw Exception('Ticker not found on CoinEx for $market');
      }

      final price = double.tryParse(tickerData['last']?.toString() ?? '0') ?? 0.0;
      final vol = double.tryParse(tickerData['vol']?.toString() ?? '0') ?? 0.0;
      final high = double.tryParse(tickerData['high']?.toString() ?? '0') ?? price;
      final low = double.tryParse(tickerData['low']?.toString() ?? '0') ?? price;

      if (price <= 0) {
        throw Exception('Invalid price received from CoinEx ($price)');
      }

      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: price,
        volume24h: vol,
        high24h: high,
        low24h: low,
        timestamp: DateTime.now(),
      );
    } catch (e) {
      throw Exception('CoinEx Live Connection Error for ${pair.displayName}: $e');
    }
  }
}
