import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/iran_bourse_service.dart';

/// IB-11a: the Bourse service against a fake server (no network).
const String ayarId = '34144395039913458';

http.Response jsonOk(Object body, [int status = 200]) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

Map<String, dynamic> ayarRow() => {
      'id': ayarId,
      'ticker': 'عیار',
      'name': 'صندوق طلای عیار مفید',
      'last': 671609,
      'upper_limit': 735409,
      'lower_limit': 601699,
      'market': null,
      'type': 'صندوق کالایی',
      'nav': 678232,
    };

Map<String, dynamic> ayarQuote() => {
      'price': 668761,
      'state': 'LIVE',
      'alert_eligible': true,
      'asOf': 1794726798,
      'symbol': ayarId,
      'ticker': 'عیار',
      'name': 'صندوق طلای عیار مفید',
      'unit': 'IRR',
      'cached': false,
    };

IranBourseService make(MockClient client, {String key = 'k-test', String base = 'https://srv.test'}) =>
    IranBourseService(client: client, baseUrl: () => base, apiKey: () => key);

void main() {
  group('search', () {
    test('sends q, limit and the API key, and keeps Persian text', () async {
      late http.Request seen;
      final svc = make(MockClient((req) async {
        seen = req;
        return jsonOk({
          'query': 'عیار',
          'count': 1,
          'limit': 20,
          'unit': 'IRR',
          'stale': false,
          'items': [ayarRow()],
        });
      }));

      final r = await svc.search('  عیار  ');
      expect(r.isOk, isTrue);
      expect(seen.url.path, '/api/iran-bourse/symbols');
      expect(seen.url.queryParameters['q'], 'عیار');
      expect(seen.url.queryParameters['limit'], '20');
      expect(seen.headers['X-API-Key'], 'k-test');
      expect(r.data!.items, hasLength(1));
      expect(r.data!.items.first.id, ayarId);
      expect(r.data!.items.first.market, isNull);
      expect(r.data!.stale, isFalse);
    });

    test('empty query makes no request', () async {
      var calls = 0;
      final svc = make(MockClient((req) async {
        calls++;
        return jsonOk({});
      }));
      final r = await svc.search('   ');
      expect(r.isOk, isTrue);
      expect(r.data!.items, isEmpty);
      expect(calls, 0);
    });

    test('filters are sent only when set; limit is clamped to 1..50', () async {
      final urls = <Uri>[];
      final svc = make(MockClient((req) async {
        urls.add(req.url);
        return jsonOk({'query': 'x', 'items': <dynamic>[], 'stale': false});
      }));

      await svc.search('x', market: ' 7 ', type: '', sector: null, traded: true, limit: 500);
      await svc.search('x', limit: 0);
      expect(urls[0].queryParameters['market'], '7');
      expect(urls[0].queryParameters.containsKey('type'), isFalse);
      expect(urls[0].queryParameters.containsKey('sector'), isFalse);
      expect(urls[0].queryParameters['traded'], 'true');
      expect(urls[0].queryParameters['limit'], '50');
      expect(urls[1].queryParameters['limit'], '1');
      expect(urls[1].queryParameters.containsKey('traded'), isFalse);
    });

    test('a very long query is cut to 64 characters', () async {
      late Uri seen;
      final svc = make(MockClient((req) async {
        seen = req.url;
        return jsonOk({'items': <dynamic>[]});
      }));
      await svc.search('a' * 200);
      expect(seen.queryParameters['q'], hasLength(64));
    });

    test('rows without a valid string id are skipped, not fatal', () async {
      final svc = make(MockClient((req) async => jsonOk({
            'items': [
              ayarRow(),
              {'id': 34144395039913458, 'ticker': 'numeric id'},
              {'ticker': 'no id'},
              'garbage',
            ],
          })));
      final r = await svc.search('x');
      expect(r.isOk, isTrue);
      expect(r.data!.items.map((e) => e.id), [ayarId]);
    });

    test('items that is not a list is a bad response', () async {
      final svc = make(MockClient((req) async => jsonOk({'items': 'nope'})));
      final r = await svc.search('x');
      expect(r.failure, BourseFailure.badResponse);
    });

    test('no API key configured means no key header', () async {
      late http.Request seen;
      final svc = make(MockClient((req) async {
        seen = req;
        return jsonOk({'items': <dynamic>[]});
      }), key: '');
      await svc.search('x');
      expect(seen.headers.containsKey('X-API-Key'), isFalse);
    });

    test('a trailing slash on the base URL is handled', () async {
      late Uri seen;
      final svc = make(MockClient((req) async {
        seen = req.url;
        return jsonOk({'items': <dynamic>[]});
      }), base: 'https://srv.test///');
      await svc.search('x');
      expect(seen.toString(), startsWith('https://srv.test/api/iran-bourse/symbols?'));
    });
  });

  group('quote', () {
    test('returns a parsed quote and calls the right path', () async {
      late Uri seen;
      final svc = make(MockClient((req) async {
        seen = req.url;
        return jsonOk(ayarQuote());
      }));
      final r = await svc.quote(ayarId);
      expect(seen.path, '/api/iran-bourse/quote/$ayarId');
      expect(r.isOk, isTrue);
      expect(r.data!.state, BourseState.live);
      expect(r.data!.alertEligible, isTrue);
      expect(r.data!.price, 668761);
      expect(r.data!.symbol, isA<String>());
    });

    test('an invalid id never reaches the network', () async {
      var calls = 0;
      final svc = make(MockClient((req) async {
        calls++;
        return jsonOk(ayarQuote());
      }));
      for (final bad in ['', 'abc', '123', '../etc', '1' * 21]) {
        final r = await svc.quote(bad);
        expect(r.failure, BourseFailure.badRequest, reason: bad);
      }
      expect(calls, 0);
    });

    test('a quote without a string symbol is a bad response', () async {
      final svc = make(MockClient((req) async => jsonOk(ayarQuote()..['symbol'] = 34144395039913458)));
      final r = await svc.quote(ayarId);
      expect(r.failure, BourseFailure.badResponse);
    });
  });

  group('classification', () {
    test('returns the raw classification object', () async {
      final svc = make(MockClient((req) async => jsonOk({
            'stale': false,
            'classification': {
              'codes': {'markets': {}},
              'observed': {'markets': []},
            },
          })));
      final r = await svc.classification();
      expect(r.isOk, isTrue);
      expect(r.data!.keys, containsAll(['codes', 'observed']));
    });

    test('a missing classification is a bad response', () async {
      final svc = make(MockClient((req) async => jsonOk({'stale': false})));
      expect((await svc.classification()).failure, BourseFailure.badResponse);
    });
  });

  group('failures', () {
    Future<BourseResult<BourseQuote>> quoteWith(http.Response Function() make_) {
      final svc = make(MockClient((req) async => make_()));
      return svc.quote(ayarId);
    }

    test('503 "not enabled" means the Bourse is disabled', () async {
      final r = await quoteWith(() => jsonOk({'detail': 'Iranian Bourse is not enabled on this server.'}, 503));
      expect(r.failure, BourseFailure.disabled);
      expect(r.httpStatus, 503);
    });

    test('other 503 means unavailable', () async {
      final r = await quoteWith(() => jsonOk(
          {'detail': 'Iranian Bourse data source unavailable (BourseTimeout); try again shortly.'}, 503));
      expect(r.failure, BourseFailure.unavailable);
    });

    test('404 is notFound, 400/422 badRequest, 401/403 unauthorized', () async {
      expect((await quoteWith(() => jsonOk({'detail': 'Unknown'}, 404))).failure, BourseFailure.notFound);
      expect((await quoteWith(() => jsonOk({'detail': 'bad'}, 400))).failure, BourseFailure.badRequest);
      expect((await quoteWith(() => jsonOk({'detail': 'bad'}, 422))).failure, BourseFailure.badRequest);
      expect((await quoteWith(() => jsonOk({'detail': 'no'}, 401))).failure, BourseFailure.unauthorized);
      expect((await quoteWith(() => jsonOk({'detail': 'no'}, 403))).failure, BourseFailure.unauthorized);
    });

    test('500 is unavailable even with a non-JSON body', () async {
      final r = await quoteWith(() => http.Response('<html>oops</html>', 502));
      expect(r.failure, BourseFailure.unavailable);
    });

    test('a 200 with a non-JSON body is a bad response', () async {
      final r = await quoteWith(() => http.Response('not json', 200));
      expect(r.failure, BourseFailure.badResponse);
    });

    test('a 200 with a JSON array is a bad response', () async {
      final r = await quoteWith(() => jsonOk([1, 2, 3]));
      expect(r.failure, BourseFailure.badResponse);
    });

    test('a transport error is a network failure and never throws', () async {
      final svc = make(MockClient((req) async => throw http.ClientException('socket closed')));
      final r = await svc.quote(ayarId);
      expect(r.failure, BourseFailure.network);
      expect(r.isOk, isFalse);
    });

    test('a timeout is a network failure', () async {
      final svc = IranBourseService(
        client: MockClient((req) async {
          await Future<void>.delayed(const Duration(milliseconds: 200));
          return jsonOk(ayarQuote());
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
        timeout: const Duration(milliseconds: 20),
      );
      final r = await svc.quote(ayarId);
      expect(r.failure, BourseFailure.network);
      expect(r.message, 'timeout');
    });
  });
}
