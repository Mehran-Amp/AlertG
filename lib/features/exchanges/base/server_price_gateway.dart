import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../../../core/services/server_alert_service.dart';
import 'currency_pair.dart';
import 'models/price_snapshot.dart';

/// Gateway service for server-first price resolution for cryptocurrency pairs.
///
/// Bypasses filtered direct mobile connections by delegating price fetching
/// to the Python server proxy with structured logging and error tolerance.
class ServerPriceGateway {
  /// Fetches a price snapshot via the server proxy for a given exchange and currency pair.
  ///
  /// - `symbol`: uses `pair.marketSymbol` if non-empty, otherwise falls back to `baseCurrency + counterCurrency`.
  /// - Calls `ServerAlertService.fetchPriceViaServerDetailed`.
  /// - Logs exactly ONE line with `debugPrint`:
  ///   `[CryptoPrice] ex=<id> sym=<s> source=server http=<code|none> ms=<n> reason=<r|none>`
  /// - Returns `PriceSnapshot` on success, or `null` on failure.
  /// - Never throws an exception.
  static Future<PriceSnapshot?> fetch(
    String exchangeId,
    CurrencyPair pair, {
    http.Client? client,
  }) async {
    try {
      final symbol = pair.marketSymbol.trim().isNotEmpty
          ? pair.marketSymbol
          : '${pair.baseCurrency}${pair.counterCurrency}';

      final res = await ServerAlertService.fetchPriceViaServerDetailed(
        exchangeId,
        symbol,
        client: client,
      );

      final httpStatus = res['httpStatus'];
      final httpStr = httpStatus != null ? '$httpStatus' : 'none';
      final ms = res['ms'] ?? 0;
      final reason = res['reason'];
      final reasonStr = reason != null ? '$reason' : 'none';

      debugPrint('[CryptoPrice] ex=$exchangeId sym=$symbol source=server http=$httpStr ms=$ms reason=$reasonStr');

      final rawPrice = res['price'];
      if (rawPrice is num && rawPrice > 0) {
        DateTime? asOf;
        final asOfRaw = res['asOf'];
        if (asOfRaw is int) {
          asOf = DateTime.fromMillisecondsSinceEpoch(asOfRaw * 1000, isUtc: true);
        } else if (asOfRaw is num) {
          asOf = DateTime.fromMillisecondsSinceEpoch(asOfRaw.toInt() * 1000, isUtc: true);
        }

        return PriceSnapshot(
          price: rawPrice.toDouble(),
          volume: null,
          fetchedAt: DateTime.now(),
          asOf: asOf,
          state: res['state'] as String?,
          source: res['source'] as String?,
        );
      }

      return null;
    } catch (_) {
      return null;
    }
  }
}
