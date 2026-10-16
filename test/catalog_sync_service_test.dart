import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/core/services/catalog_sync_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('CatalogSyncService Tests', () {
    late CatalogSyncService service;

    setUp(() {
      service = CatalogSyncService.instance;
    });

    test('1. Empty cache starts with version 0 and sync requests since_version=0', () async {
      service.resetForTesting(version: 0, items: []);

      expect(service.localVersion, equals(0));
      expect(service.items.isEmpty, isTrue);

      final requestedUrls = <Uri>[];
      final mockClient = MockClient((request) async {
        requestedUrls.add(request.url);
        if (request.url.queryParameters['since_version'] == '0') {
          return http.Response(
            jsonEncode({
              'status': 'success',
              'catalog_version': 2,
              'total_count': 2,
              'symbols': [
                {
                  'id': 'AAPL',
                  'symbol': 'AAPL',
                  'name': 'Apple Inc.',
                  'category': 'stock',
                  'market': 'US Stock',
                  'is_active': true,
                },
                {
                  'id': 'BTCUSDT',
                  'symbol': 'BTCUSDT',
                  'name': 'Bitcoin',
                  'category': 'crypto',
                  'market': 'Binance',
                  'is_active': true,
                },
              ],
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }
        return http.Response('Not Found', 404);
      });

      service.client = mockClient;

      final success = await service.syncDelta();

      expect(success, isTrue);
      expect(requestedUrls.length, equals(1));
      expect(requestedUrls.first.queryParameters['since_version'], equals('0'));
      expect(service.localVersion, equals(2));
      expect(service.items.length, equals(2));
      expect(service.items.map((e) => e.symbol), containsAll(['AAPL', 'BTCUSDT']));
    });

    test('2. Offline fallback cache (<=20 items) forces localVersion to 0', () {
      final fallbackItems = List.generate(
        15,
        (i) => CatalogItem(
          id: 'SYM_$i',
          symbol: 'SYM_$i',
          nameEn: 'Symbol $i',
          nameFa: 'نماد $i',
          category: 'stock',
        ),
      );

      service.resetForTesting(version: 3, items: fallbackItems);

      expect(service.items.length, equals(15));
      expect(service.localVersion, equals(0));
    });

    test('3. Self-healing on up_to_date when local count mismatches total_count', () async {
      final existingItems = List.generate(
        25,
        (i) => CatalogItem(
          id: 'EXISTING_$i',
          symbol: 'EXISTING_$i',
          nameEn: 'Existing $i',
          nameFa: 'نماد موجود $i',
          category: 'stock',
        ),
      );

      service.resetForTesting(version: 2, items: existingItems);
      expect(service.localVersion, equals(2));
      expect(service.items.length, equals(25));

      final requestedUrls = <Uri>[];
      final mockClient = MockClient((request) async {
        requestedUrls.add(request.url);
        final sinceVersion = request.url.queryParameters['since_version'];

        if (sinceVersion == '2') {
          // Server says up to date, but total_count is 100 (while local is only 25)
          return http.Response(
            jsonEncode({
              'status': 'up_to_date',
              'catalog_version': 2,
              'total_count': 100,
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        } else if (sinceVersion == '0') {
          // Full catalog self-healing response
          final fullSymbols = List.generate(
            100,
            (i) => {
              'id': 'FULL_$i',
              'symbol': 'FULL_$i',
              'name': 'Full Symbol $i',
              'category': 'stock',
              'market': 'US Stock',
              'is_active': true,
            },
          );

          return http.Response(
            jsonEncode({
              'status': 'success',
              'catalog_version': 2,
              'total_count': 100,
              'symbols': fullSymbols,
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }

        return http.Response('Bad request', 400);
      });

      service.client = mockClient;

      final success = await service.syncDelta();

      expect(success, isTrue);
      expect(requestedUrls.length, equals(2));
      expect(requestedUrls[0].queryParameters['since_version'], equals('2'));
      expect(requestedUrls[1].queryParameters['since_version'], equals('0'));
      expect(service.items.length, equals(100));
      expect(service.items.first.symbol, equals('FULL_0'));
    });

    test('4. Self-healing on delta_success when applied delta count mismatches total_count', () async {
      final existingItems = List.generate(
        25,
        (i) => CatalogItem(
          id: 'ITEM_$i',
          symbol: 'ITEM_$i',
          nameEn: 'Item $i',
          nameFa: 'نماد $i',
          category: 'stock',
        ),
      );

      service.resetForTesting(version: 1, items: existingItems);
      expect(service.localVersion, equals(1));
      expect(service.items.length, equals(25));

      final requestedUrls = <Uri>[];
      final mockClient = MockClient((request) async {
        requestedUrls.add(request.url);
        final sinceVersion = request.url.queryParameters['since_version'];

        if (sinceVersion == '1') {
          // Server returns delta with 1 added item, but server total_count is 80
          return http.Response(
            jsonEncode({
              'status': 'delta_success',
              'is_delta': true,
              'catalog_version': 2,
              'total_count': 80,
              'added': [
                {
                  'id': 'NEW_1',
                  'symbol': 'NEW_1',
                  'name': 'New Symbol 1',
                  'category': 'stock',
                  'market': 'US Stock',
                  'is_active': true,
                }
              ],
              'updated': [],
              'delisted': [],
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        } else if (sinceVersion == '0') {
          // Self-healing full resync response
          final fullSymbols = List.generate(
            80,
            (i) => {
              'id': 'RECOVERED_$i',
              'symbol': 'RECOVERED_$i',
              'name': 'Recovered $i',
              'category': 'stock',
              'market': 'US Stock',
              'is_active': true,
            },
          );

          return http.Response(
            jsonEncode({
              'status': 'success',
              'catalog_version': 2,
              'total_count': 80,
              'symbols': fullSymbols,
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }

        return http.Response('Bad request', 400);
      });

      service.client = mockClient;

      final success = await service.syncDelta();

      expect(success, isTrue);
      expect(requestedUrls.length, equals(2));
      expect(requestedUrls[0].queryParameters['since_version'], equals('1'));
      expect(requestedUrls[1].queryParameters['since_version'], equals('0'));
      expect(service.items.length, equals(80));
      expect(service.items.first.symbol, equals('RECOVERED_0'));
    });
  });
}
