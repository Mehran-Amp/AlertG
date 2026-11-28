import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/iran_bourse/models/bourse_board.dart';
import 'package:bitcoin_checker/features/iran_bourse/pages/bourse_browse_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/bourse_catalog_cache.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/iran_bourse_service.dart';

String _idOf(int n) => '20000000000${n.toString().padLeft(6, '0')}';

Map<String, dynamic> _row(
  int n, {
  required String ticker,
  required String name,
  required String group,
  num? price = 1000,
  num? volume = 100,
  num? value = 500,
  num? changePct = 1.0,
  bool traded = true,
}) =>
    {
      'id': _idOf(n),
      'ticker': ticker,
      'name': name,
      'price': price,
      'price_source': price == null ? 'none' : 'last',
      'change_pct': changePct,
      'volume': volume,
      'value': value,
      'traded': traded,
      'group': group,
      'type': group == 'funds' ? 'صندوق' : (group == 'derivatives' ? 'اختیار معامله' : 'سهام'),
    };

Map<String, dynamic> _catalogJson(List<Map<String, dynamic>> items, {String session = 'CLOSED'}) => {
      'unit': 'IRR',
      'session': session,
      'stale': false,
      'as_of': 1795000000,
      'total': items.length,
      'groups': {
        'stocks': items.where((e) => e['group'] == 'stocks').length,
        'funds': items.where((e) => e['group'] == 'funds').length,
        'derivatives': items.where((e) => e['group'] == 'derivatives').length,
      },
      'items': items,
    };

void main() {
  late Directory tempDir;

  setUp(() {
    tempDir = Directory.systemTemp.createTempSync('bourse_catalog_cache_test_');
  });

  tearDown(() {
    if (tempDir.existsSync()) {
      tempDir.deleteSync(recursive: true);
    }
  });

  group('BourseCatalogCache — schedule & disk persistence', () {
    test('latestTehranCloseUtc follows 19:00 Tehran (15:30 UTC)', () {
      // 2026-11-26 15:29 UTC == 18:59 Tehran -> latest close is previous day 15:30 UTC
      final beforeClose = DateTime.utc(2026, 11, 26, 15, 29);
      expect(
        BourseCatalogCache.latestTehranCloseUtc(beforeClose),
        DateTime.utc(2026, 11, 25, 15, 30),
      );

      // 2026-11-26 15:30 UTC == 19:00 Tehran -> latest close is today 15:30 UTC
      final atClose = DateTime.utc(2026, 11, 26, 15, 30);
      expect(
        BourseCatalogCache.latestTehranCloseUtc(atClose),
        DateTime.utc(2026, 11, 26, 15, 30),
      );

      // 2026-11-26 17:00 UTC == 20:30 Tehran -> latest close is today 15:30 UTC
      final afterClose = DateTime.utc(2026, 11, 26, 17, 0);
      expect(
        BourseCatalogCache.latestTehranCloseUtc(afterClose),
        DateTime.utc(2026, 11, 26, 15, 30),
      );
    });

    test('persists catalog to disk and reuses without network until next 19:00 Tehran', () async {
      DateTime clock = DateTime.utc(2026, 11, 26, 16, 0); // 19:30 Tehran (just after close)
      int calls = 0;

      final payload = _catalogJson([
        _row(1, ticker: 'فولاد', name: 'فولاد مبارکه اصفهان', group: 'stocks', value: 900),
        _row(2, ticker: 'عیار', name: 'صندوق طلای عیار مفید', group: 'funds', value: 700),
      ]);

      final service = IranBourseService(
        client: MockClient((r) async {
          calls++;
          expect(r.url.path, '/api/iran-bourse/catalog');
          return http.Response.bytes(
            utf8.encode(jsonEncode(payload)),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
      );

      final cache1 = BourseCatalogCache(directoryProvider: () async => tempDir, nowUtc: () => clock);
      final res1 = await cache1.ensureLoaded(service: service);
      expect(res1.isOk, isTrue);
      expect(calls, 1);
      expect(cache1.items, hasLength(2));
      expect(cache1.isFresh(), isTrue);

      // Next morning (09:00 Tehran = 05:30 UTC on Nov 27): still fresh -> 0 calls on new cache instance from disk
      clock = DateTime.utc(2026, 11, 27, 5, 30);
      final cache2 = BourseCatalogCache(directoryProvider: () async => tempDir, nowUtc: () => clock);
      final res2 = await cache2.ensureLoaded(service: service);
      expect(res2.isOk, isTrue);
      expect(calls, 1); // loaded purely from disk!
      expect(cache2.items, hasLength(2));

      // After next day 19:00 Tehran (19:05 Tehran = 15:35 UTC on Nov 27): stale -> triggers 1 refresh
      clock = DateTime.utc(2026, 11, 27, 15, 35);
      expect(cache2.isFresh(), isFalse);
      final res3 = await cache2.ensureLoaded(service: service);
      expect(res3.isOk, isTrue);
      expect(calls, 2);
      expect(cache2.isFresh(), isTrue);
    });

    test('local query matches backend filtering, Arabic normalization, sorting with nulls last, and paging', () async {
      final payload = _catalogJson([
        _row(1, ticker: 'فولاد', name: 'فولاد مبارکه', group: 'stocks', value: 500, volume: 20, changePct: 1.5, price: 2000),
        _row(2, ticker: 'عیار', name: 'صندوق طلای عیار', group: 'funds', value: 900, volume: 100, changePct: 4.5, price: 660000),
        _row(3, ticker: 'کیمیا', name: 'کیمیا تجارت', group: 'stocks', value: null, volume: 5, changePct: -2.0, price: 500, traded: false),
        _row(4, ticker: 'ضفلا1', name: 'اختیار فولاد', group: 'derivatives', value: 1000, volume: 500, changePct: 10.0, price: 300),
      ]);

      final service = IranBourseService(
        client: MockClient((_) async => http.Response.bytes(utf8.encode(jsonEncode(payload)), 200)),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
      );
      final cache = BourseCatalogCache(
        directoryProvider: () async => tempDir,
        nowUtc: () => DateTime.utc(2026, 11, 26, 16, 0),
      );
      await cache.ensureLoaded(service: service);

      // Default list excludes derivatives and puts null `value` last
      final allPage = cache.query(sort: BourseSort.value);
      expect(allPage.total, 3);
      expect(allPage.items.map((e) => e.id).toList(), [_idOf(2), _idOf(1), _idOf(3)]);
      expect(allPage.groupCounts[BourseGroup.derivatives], 1);

      // Derivatives tab explicitly includes options/futures
      final derivPage = cache.query(group: BourseGroup.derivatives);
      expect(derivPage.items.single.id, _idOf(4));

      // Traded-only filter excludes id 3
      final tradedPage = cache.query(traded: true);
      expect(tradedPage.total, 2);

      // Arabic Yeh & Kaf normalize cleanly to Persian
      final arabicSearch = cache.query(q: 'كيميا');
      expect(arabicSearch.total, 1);
      expect(arabicSearch.items.single.ticker, 'کیمیا');

      // Sort by change descending
      final movers = cache.query(sort: BourseSort.change);
      expect(movers.items.map((e) => e.id).toList(), [_idOf(2), _idOf(1), _idOf(3)]);

      // Paging works locally
      final p1 = cache.query(limit: 2, offset: 0);
      expect(p1.hasMore, isTrue);
      expect(p1.nextOffset, 2);
      final p2 = cache.query(limit: 2, offset: p1.nextOffset);
      expect(p2.hasMore, isFalse);
      expect(p2.items, hasLength(1));
    });
  });

  group('BourseBrowsePage with useCatalogCache', () {
    testWidgets('loads catalog once and runs tab, sort, traded, and search locally without extra requests; pull-to-refresh reloads', (t) async {
      t.view.physicalSize = const Size(2400, 1200);
      t.view.devicePixelRatio = 1.0;
      addTearDown(t.view.resetPhysicalSize);
      addTearDown(t.view.resetDevicePixelRatio);

      final calls = <Uri>[];
      final payload = _catalogJson([
        _row(1, ticker: 'فولاد', name: 'فولاد مبارکه', group: 'stocks', value: 500, changePct: 1.0),
        _row(2, ticker: 'عیار', name: 'صندوق طلای عیار', group: 'funds', value: 900, changePct: 4.0),
        _row(3, ticker: 'خساپا', name: 'سایپا', group: 'stocks', value: 100, changePct: -1.0, traded: false),
      ]);

      final service = IranBourseService(
        client: MockClient((r) async {
          calls.add(r.url);
          return http.Response.bytes(
            utf8.encode(jsonEncode(payload)),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
      );
      final cache = BourseCatalogCache(
        // Avoid real dart:io file calls inside Flutter's FakeAsync testWidgets zone;
        // disk persistence is verified in the real-async unit tests above.
        directoryProvider: () async => throw UnsupportedError('memory-only in widget test'),
        nowUtc: () => DateTime.utc(2026, 11, 26, 16, 0),
      );

      await t.pumpWidget(MaterialApp(
        home: BourseBrowsePage(
          service: service,
          catalogCache: cache,
          useCatalogCache: true,
          debounce: Duration.zero,
        ),
      ));
      await t.pumpAndSettle();

      // 1 single catalog request on mount
      expect(calls, hasLength(1));
      expect(calls.single.path, '/api/iran-bourse/catalog');
      expect(find.byKey(ValueKey('bourse_board_row_${_idOf(1)}')), findsOneWidget);
      expect(find.byKey(ValueKey('bourse_board_row_${_idOf(2)}')), findsOneWidget);

      // Switching tabs, sorting, traded-only, and searching must make ZERO HTTP requests
      await t.tap(find.byKey(const Key('bourse_tab_funds')));
      await t.pumpAndSettle();
      expect(find.byKey(ValueKey('bourse_board_row_${_idOf(2)}')), findsOneWidget);
      expect(find.byKey(ValueKey('bourse_board_row_${_idOf(1)}')), findsNothing);
      expect(calls, hasLength(1));

      await t.tap(find.byKey(const Key('bourse_tab_top_movers')));
      await t.pumpAndSettle();
      expect(find.byKey(ValueKey('bourse_board_row_${_idOf(1)}')), findsOneWidget);
      expect(calls, hasLength(1));

      await t.tap(find.byKey(const Key('bourse_traded_only')));
      await t.pumpAndSettle();
      expect(find.byKey(ValueKey('bourse_board_row_${_idOf(3)}')), findsNothing);
      expect(calls, hasLength(1));

      await t.enterText(find.byKey(const Key('bourse_board_search')), 'عيار'); // Arabic Yeh
      await t.pumpAndSettle();
      expect(find.byKey(ValueKey('bourse_board_row_${_idOf(2)}')), findsOneWidget);
      expect(find.byKey(ValueKey('bourse_board_row_${_idOf(1)}')), findsNothing);
      expect(calls, hasLength(1));

      // Clear search and pull-to-refresh -> triggers a forced catalog reload
      await t.enterText(find.byKey(const Key('bourse_board_search')), '');
      await t.pumpAndSettle();
      await t.fling(find.byKey(ValueKey('bourse_board_row_${_idOf(2)}')), const Offset(0, 500), 1000);
      await t.pumpAndSettle();
      expect(calls, hasLength(2));
    });
  });
}
