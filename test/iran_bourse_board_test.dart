import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/iran_bourse/models/bourse_board.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/iran_bourse_service.dart';

/// IB-16b: browse-list models and the service call, against a fake server (no network).
const String ayarId = '34144395039913458';
const String maeyarId = '50580753680043015';

http.Response jsonOk(Object body, [int status = 200]) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

Map<String, dynamic> row(String id, String ticker, {Object? price = 668761, String group = 'funds', num? change = -0.4}) => {
      'id': id,
      'ticker': ticker,
      'name': 'نام $ticker',
      'price': price,
      'price_source': 'last',
      'last': price,
      'close': 668554,
      'yesterday': 668554,
      'change_pct': change,
      'volume': 1500,
      'value': 1000000000,
      'traded': true,
      'group': group,
      'market_code': '1',
      'type_code': '315',
      'type': 'صندوق کالایی',
      'sector_code': '68',
      'sector': 'صندوق سرمایه‌گذاری قابل معامله',
      'update_time': '12:22:16',
    };

Map<String, dynamic> page({List<Object?>? items, int total = 2445, int offset = 0, String session = 'OPEN'}) => {
      'unit': 'IRR',
      'session': session,
      'stale': false,
      'as_of': 1794726798,
      'total': total,
      'offset': offset,
      'limit': 50,
      'sort': 'value',
      'order': 'desc',
      'groups': {'stocks': 1209, 'funds': 412, 'bonds': 703, 'rights': 13, 'derivatives': 1381, 'other': 46},
      'other_types': {'?': 33},
      'items': items ?? [row(ayarId, 'عیار'), row(maeyarId, 'معیار', price: 2623, group: 'funds')],
    };

IranBourseService make(MockClient c, {Duration timeout = const Duration(seconds: 10)}) =>
    IranBourseService(client: c, baseUrl: () => 'https://srv.test/', apiKey: () => 'k-test', timeout: timeout);

void main() {
  group('parsing', () {
    test('a full page', () {
      final p = BourseBoardPage.tryParse(page())!;
      expect(p.items.length, 2);
      expect(p.total, 2445);
      expect(p.session, BourseSession.open);
      expect(p.session.isLive, isTrue);
      expect(p.stale, isFalse);
      expect(p.asOf, 1794726798);
      expect(p.descending, isTrue);
      expect(p.groupCounts[BourseGroup.stocks], 1209);
      expect(p.groupCounts[BourseGroup.derivatives], 1381);
      expect(p.hasMore, isTrue);
      expect(p.nextOffset, 2);

      final a = p.items.first;
      expect(a.id, ayarId);
      expect(a.id, isA<String>());
      expect(a.displayTicker, 'عیار');
      expect(a.price, 668761);
      expect(a.priceSource, BoursePriceSource.last);
      expect(a.changePct, -0.4);
      expect(a.group, BourseGroup.funds);
      expect(a.traded, isTrue);
      expect(a.updateTime, '12:22:16');
    });

    test('hasMore is false on the last page', () {
      final p = BourseBoardPage.tryParse(page(total: 2, items: [row(ayarId, 'عیار'), row(maeyarId, 'معیار')]))!;
      expect(p.hasMore, isFalse);
    });

    test('rows with a numeric, short or missing id are skipped, the rest are kept', () {
      final p = BourseBoardPage.tryParse(page(items: [
        row(ayarId, 'عیار'),
        {...row(ayarId, 'x'), 'id': 34144395039913458},   // JSON number: rejected (N6)
        {...row(ayarId, 'y'), 'id': '123'},
        {'ticker': 'z'},
        'not a map',
        null,
      ]))!;
      expect(p.items.map((i) => i.ticker), ['عیار']);
    });

    test('unknown group and price source fall back instead of failing', () {
      final it = BourseBoardItem.tryParse({...row(ayarId, 'عیار'), 'group': 'newgroup', 'price_source': 'weird'})!;
      expect(it.group, BourseGroup.other);
      expect(it.priceSource, BoursePriceSource.none);
    });

    test('missing and odd numbers become null', () {
      final it = BourseBoardItem.tryParse({
        ...row(ayarId, 'عیار'),
        'price': null,
        'change_pct': 'x',
        'volume': double.nan,
      })!;
      expect(it.price, isNull);
      expect(it.changePct, isNull);
      expect(it.volume, isNull);
    });

    test('an empty ticker shows the name', () {
      final it = BourseBoardItem.tryParse({...row(ayarId, ''), 'ticker': ''})!;
      expect(it.displayTicker, it.name);
    });

    test('session values', () {
      expect(BourseSession.fromServer('OPEN'), BourseSession.open);
      expect(BourseSession.fromServer('CLOSED'), BourseSession.closed);
      expect(BourseSession.fromServer('STALE'), BourseSession.stale);
      expect(BourseSession.fromServer(null), BourseSession.unknown);
      expect(BourseSession.closed.isLive, isFalse);
      expect(BourseSession.stale.isLive, isFalse);
      expect(BourseSession.unknown.isLive, isFalse);
    });

    test('not a board answer', () {
      expect(BourseBoardPage.tryParse(null), isNull);
      expect(BourseBoardPage.tryParse([]), isNull);
      expect(BourseBoardPage.tryParse({'items': [], 'total': 'x'}), isNull);
      expect(BourseBoardPage.tryParse({'total': 3}), isNull);
    });
  });

  group('service.board request', () {
    test('defaults: sorted by value, 50 rows, key sent, no filters', () async {
      late http.Request seen;
      final r = await make(MockClient((req) async {
        seen = req;
        return jsonOk(page());
      })).board();
      expect(r.isOk, isTrue);
      expect(r.data!.items.length, 2);
      expect(seen.url.path, '/api/iran-bourse/board');
      expect(seen.headers['X-API-Key'], 'k-test');
      expect(seen.url.queryParameters, {'sort': 'value', 'limit': '50', 'offset': '0'});
    });

    test('every filter is sent, Persian text survives', () async {
      late Uri seen;
      await make(MockClient((req) async {
        seen = req.url;
        return jsonOk(page());
      })).board(
        group: BourseGroup.derivatives,
        market: '1',
        sector: '68',
        type: '315',
        traded: true,
        q: '  فولاد  ',
        sort: BourseSort.change,
        ascending: true,
        offset: 100,
        limit: 25,
      );
      expect(seen.queryParameters, {
        'sort': 'change',
        'limit': '25',
        'offset': '100',
        'group': 'derivatives',
        'market': '1',
        'sector': '68',
        'type': '315',
        'traded': 'true',
        'q': 'فولاد',
        'order': 'asc',
      });
    });

    test('traded false and descending are explicit', () async {
      late Uri seen;
      await make(MockClient((req) async {
        seen = req.url;
        return jsonOk(page());
      })).board(traded: false, ascending: false);
      expect(seen.queryParameters['traded'], 'false');
      expect(seen.queryParameters['order'], 'desc');
    });

    test('blank filters are left out; limit and offset are clamped', () async {
      late Uri seen;
      final svc = make(MockClient((req) async {
        seen = req.url;
        return jsonOk(page());
      }));
      await svc.board(market: '  ', q: '', limit: 5000, offset: -3);
      expect(seen.queryParameters, {'sort': 'value', 'limit': '100', 'offset': '0'});
      await svc.board(limit: 0, offset: 999999);
      expect(seen.queryParameters['limit'], '1');
      expect(seen.queryParameters['offset'], '100000');
    });

    test('a very long query is cut to 64 characters', () async {
      late Uri seen;
      await make(MockClient((req) async {
        seen = req.url;
        return jsonOk(page());
      })).board(q: 'ا' * 200);
      expect(seen.queryParameters['q']!.length, 64);
    });
  });

  group('service.board failures', () {
    Future<BourseFailure?> failureFor(http.Response Function() reply) async {
      final r = await make(MockClient((req) async => reply())).board();
      expect(r.isOk, isFalse);
      return r.failure;
    }

    test('Bourse switched off', () async {
      expect(await failureFor(() => jsonOk({'detail': 'Iranian Bourse alerts are not enabled on this server.'}, 503)),
          BourseFailure.disabled);
    });

    test('feed unavailable', () async {
      expect(await failureFor(() => jsonOk({'detail': 'Iranian Bourse gateway unavailable (BourseTimeout); try again shortly.'}, 503)),
          BourseFailure.unavailable);
      expect(await failureFor(() => jsonOk({}, 500)), BourseFailure.unavailable);
    });

    test('bad key, bad parameters, bad body', () async {
      expect(await failureFor(() => jsonOk({'detail': 'Invalid or missing API key.'}, 401)), BourseFailure.unauthorized);
      expect(await failureFor(() => jsonOk({'detail': 'group must be one of x.'}, 400)), BourseFailure.badRequest);
      expect(await failureFor(() => jsonOk({'hello': 'world'})), BourseFailure.badResponse);
      expect(await failureFor(() => http.Response('<html>', 200)), BourseFailure.badResponse);
    });

    test('a transport error never throws', () async {
      final r = await make(MockClient((req) async => throw http.ClientException('down'))).board();
      expect(r.failure, BourseFailure.network);
    });

    test('the first (slow) call is allowed more time than a search', () async {
      Future<http.Response> slow(http.Request req) async {
        await Future<void>.delayed(const Duration(milliseconds: 150));
        return jsonOk(page());
      }

      final svc = make(MockClient(slow), timeout: const Duration(milliseconds: 20));
      final board = await svc.board();
      expect(board.isOk, isTrue);                                  // default board timeout is 30 s
      final tight = await svc.board(boardTimeout: const Duration(milliseconds: 20));
      expect(tight.failure, BourseFailure.network);
      expect(tight.message, 'timeout');
    });
  });
}
