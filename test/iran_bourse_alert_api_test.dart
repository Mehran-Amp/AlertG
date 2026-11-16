import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_api.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_draft.dart';
import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/iran_bourse_service.dart';

/// IB-11d-2: creating / removing Bourse alerts on the server and explaining refusals.
const String ayarId = '34144395039913458';

AlertRule priceRule({String? note}) => BourseAlertDraft(
      instrumentId: ayarId,
      ticker: 'عیار',
      name: 'صندوق طلای عیار مفید',
      kind: BourseAlertKind.price,
      direction: AlertDirection.above,
      amount: 700000,
      prevClose: 668554,
      lastPrice: 668761,
      note: note,
    ).toRule();

AlertRule changeRule(BourseAlertKind kind, double amount) => BourseAlertDraft(
      instrumentId: ayarId,
      ticker: 'عیار',
      name: 'x',
      kind: kind,
      direction: AlertDirection.below,
      amount: amount,
      prevClose: 668554,
      lastPrice: 668761,
    ).toRule();

http.Response reply(int status, [Object? body]) => http.Response.bytes(
      utf8.encode(jsonEncode(body ?? {})),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

BourseAlertApi api(
  Future<http.Response> Function(http.Request) handler, {
  String userId = 'me@example.com',
  Future<String> Function()? fcm,
  Duration timeout = const Duration(seconds: 5),
}) {
  return BourseAlertApi(
    client: MockClient(handler),
    baseUrl: () => 'https://srv.test/',
    apiKey: () => 'k-test',
    userId: () async => userId,
    fcmToken: fcm ?? () async => 'real-fcm-token',
    timeout: timeout,
  );
}

void main() {
  group('create: what is sent', () {
    test('a price alert goes to POST /api/alerts with the key and the String id', () async {
      late http.Request seen;
      final rule = priceRule(note: 'هدف اول');
      final r = await api((req) async {
        seen = req;
        return reply(200, {'id': rule.uuid});
      }).create(rule);

      expect(r.isOk, isTrue);
      expect(r.data, isTrue);
      expect(seen.method, 'POST');
      expect(seen.url.toString(), 'https://srv.test/api/alerts'); // trailing slash handled
      expect(seen.headers['X-API-Key'], 'k-test');
      expect(seen.headers['Content-Type'], contains('application/json'));

      final b = jsonDecode(utf8.decode(seen.bodyBytes)) as Map<String, dynamic>;
      expect(b['id'], rule.uuid);
      expect(b['user_id'], 'me@example.com');
      expect(b['exchange'], 'tsetmc');
      expect(b['symbol'], ayarId);
      expect(b['symbol'], isA<String>());
      expect(b['target_price'], 700000);
      expect(b['condition'], 'ABOVE');
      expect(b['condition_type'], 'priceThreshold');
      expect(b['direction'], 'above');
      expect(b['base_currency'], 'عیار');
      expect(b['counter_currency'], 'IRR');
      expect(b['market_symbol'], ayarId);
      expect(b['trigger_mode'], 'oneShot');
      expect(b['prefer_server_proxy'], isTrue);
      expect(b['fcm_token'], 'real-fcm-token');
      expect(b['note'], 'هدف اول');
      expect(b.containsKey('percent'), isFalse);
      expect(b.containsKey('delta_absolute'), isFalse);
      final raw = b['raw_rule'] as Map<String, dynamic>;
      expect(raw['marketSymbol'], ayarId);
      expect(raw['exchangeId'], 'tsetmc');
      expect(utf8.decode(seen.bodyBytes), contains('"symbol":"$ayarId"'));
    });

    test('percent and Rial-change alerts carry their own fields and the daily base', () async {
      late Map<String, dynamic> body;
      final a = api((req) async {
        body = jsonDecode(utf8.decode(req.bodyBytes)) as Map<String, dynamic>;
        return reply(200);
      });

      await a.create(changeRule(BourseAlertKind.percentChange, 3));
      expect(body['condition_type'], 'percentChange');
      expect(body['percent'], 3.0);
      expect(body['base_price'], 668554.0);
      expect(body['condition'], 'BELOW');
      expect(body.containsKey('delta_absolute'), isFalse);

      await a.create(changeRule(BourseAlertKind.absoluteChange, 10000));
      expect(body['condition_type'], 'absolutePriceChange');
      expect(body['delta_absolute'], 10000.0);
      expect(body['base_price'], 668554.0);
      expect(body['trigger_mode'], 'oneShot');
    });

    test('no note means no note key', () async {
      late Map<String, dynamic> body;
      await api((req) async {
        body = jsonDecode(utf8.decode(req.bodyBytes)) as Map<String, dynamic>;
        return reply(200);
      }).create(priceRule());
      expect(body.containsKey('note'), isFalse);
    });

    test('a blank user id falls back to the guest bucket', () async {
      late Map<String, dynamic> body;
      await api((req) async {
        body = jsonDecode(utf8.decode(req.bodyBytes)) as Map<String, dynamic>;
        return reply(200);
      }, userId: '   ')
          .create(priceRule());
      expect(body['user_id'], 'user_default');
    });

    test('a missing push token does not stop the alert', () async {
      final tokens = <String>[];
      final fails = api((req) async {
        tokens.add((jsonDecode(utf8.decode(req.bodyBytes)) as Map)['fcm_token'] as String);
        return reply(200);
      }, fcm: () async => throw StateError('no firebase'));
      expect((await fails.create(priceRule())).isOk, isTrue);

      final empty = api((req) async {
        tokens.add((jsonDecode(utf8.decode(req.bodyBytes)) as Map)['fcm_token'] as String);
        return reply(200);
      }, fcm: () async => '');
      expect((await empty.create(priceRule())).isOk, isTrue);
      expect(tokens, ['device_token_pending', 'device_token_pending']);
    });

    test('201 also counts as created', () async {
      final r = await api((req) async => reply(201)).create(priceRule());
      expect(r.isOk, isTrue);
    });

    test('a rule of another exchange is refused without any request', () async {
      var calls = 0;
      final other = priceRule().copyWith(exchangeId: 'binance');
      final r = await api((req) async {
        calls++;
        return reply(200);
      }).create(other);
      expect(r.failure, BourseFailure.badRequest);
      expect(calls, 0);
    });
  });

  group('create: why the server said no', () {
    Future<BourseFailure?> failureFor(int status, [Object? body]) async {
      final r = await api((req) async => reply(status, body)).create(priceRule());
      expect(r.isOk, isFalse);
      return r.failure;
    }

    test('Bourse switched off', () async {
      expect(await failureFor(503, {'detail': 'Iranian Bourse alerts are not enabled on this server.'}),
          BourseFailure.disabled);
    });

    test('gateway down', () async {
      expect(
          await failureFor(503, {'detail': 'Iranian Bourse gateway unavailable (BourseTimeout); try again shortly.'}),
          BourseFailure.unavailable);
    });

    test('user not on the rollout list', () async {
      expect(await failureFor(403, {'detail': 'Iranian Bourse alerts are not available for this user yet.'}),
          BourseFailure.notAllowed);
    });

    test('wrong API key', () async {
      expect(await failureFor(403, {'detail': 'Invalid or missing API key.'}), BourseFailure.unauthorized);
      expect(await failureFor(401, {'detail': 'Invalid or missing API key.'}), BourseFailure.unauthorized);
    });

    test('unknown instrument', () async {
      expect(await failureFor(400, {'detail': 'Unknown Bourse instrument id 34144395039913458.'}),
          BourseFailure.notFound);
    });

    test('no previous close for a change alert', () async {
      expect(
          await failureFor(
              400, {'detail': 'This instrument has no previous close yet; use a price-level alert.'}),
          BourseFailure.noPreviousClose);
    });

    test('any other 400 is a plain refusal', () async {
      expect(await failureFor(400, {'detail': 'percent must be a positive number.'}), BourseFailure.rejected);
      expect(await failureFor(400, {'detail': 'Alert limit reached for this user.'}), BourseFailure.rejected);
      expect(await failureFor(400), BourseFailure.rejected);
    });

    test('other statuses', () async {
      expect(await failureFor(422, {'detail': []}), BourseFailure.badRequest);
      expect(await failureFor(500), BourseFailure.unavailable);
      expect(await failureFor(502), BourseFailure.unavailable);
      expect(await failureFor(418), BourseFailure.rejected);
    });

    test('a non-JSON error body still maps by status', () async {
      final r = await api((req) async => http.Response('<html>bad gateway</html>', 502)).create(priceRule());
      expect(r.failure, BourseFailure.unavailable);
      expect(r.httpStatus, 502);
    });

    test('the server detail is kept for logs, and the status is reported', () async {
      final r = await api((req) async => reply(403, {'detail': 'Iranian Bourse alerts are not available for this user yet.'}))
          .create(priceRule());
      expect(r.message, contains('not available for this user'));
      expect(r.httpStatus, 403);
    });

    test('a connection error is a network failure and never throws', () async {
      final r = await api((req) async => throw http.ClientException('socket closed')).create(priceRule());
      expect(r.failure, BourseFailure.network);
    });

    test('a timeout is a network failure', () async {
      final r = await api((req) async {
        await Future<void>.delayed(const Duration(milliseconds: 200));
        return reply(200);
      }, timeout: const Duration(milliseconds: 20))
          .create(priceRule());
      expect(r.failure, BourseFailure.network);
      expect(r.message, 'timeout');
    });

    test('every new failure has its own Persian text', () {
      final persian = RegExp(r'[؀-ۿ]');
      for (final f in [BourseFailure.notAllowed, BourseFailure.noPreviousClose, BourseFailure.rejected]) {
        expect(persian.hasMatch(BourseStrings.failureMessage(f)), isTrue, reason: '$f');
      }
    });
  });

  group('remove', () {
    test('DELETE /api/alerts/{id} with the key', () async {
      late http.Request seen;
      final r = await api((req) async {
        seen = req;
        return reply(200, {'status': 'deleted'});
      }).remove('abc-123');
      expect(r.isOk, isTrue);
      expect(seen.method, 'DELETE');
      expect(seen.url.path, '/api/alerts/abc-123');
      expect(seen.headers['X-API-Key'], 'k-test');
    });

    test('the id is URL-encoded', () async {
      late Uri seen;
      await api((req) async {
        seen = req.url;
        return reply(200);
      }).remove('a b/c');
      expect(seen.path, '/api/alerts/a%20b%2Fc');
    });

    test('an empty id sends nothing', () async {
      var calls = 0;
      final r = await api((req) async {
        calls++;
        return reply(200);
      }).remove('  ');
      expect(r.failure, BourseFailure.badRequest);
      expect(calls, 0);
    });

    test('server and network errors are reported, not thrown', () async {
      expect((await api((req) async => reply(500)).remove('x')).failure, BourseFailure.unavailable);
      expect((await api((req) async => throw http.ClientException('down')).remove('x')).failure,
          BourseFailure.network);
    });
  });
}
