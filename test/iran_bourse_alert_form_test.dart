import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_api.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_form_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/iran_bourse_service.dart';

/// IB-11d-3: the alert form, against a fake server (no network).
const String ayarId = '34144395039913458';

BourseQuote quote() => BourseQuote.tryParse({
      'price': 668761,
      'state': 'LIVE',
      'alert_eligible': true,
      'asOf': 1794726798,
      'symbol': ayarId,
      'ticker': 'عیار',
      'name': 'صندوق طلای عیار مفید',
      'prev_close': 668554,
      'upper_limit': 677950,
      'lower_limit': 659000,
      'unit': 'IRR',
    })!;

http.Response reply(int status, [Object? body]) => http.Response.bytes(
      utf8.encode(jsonEncode(body ?? {})),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

class Harness {
  final List<http.Request> requests = [];
  final List<AlertRule> saved = [];
  Future<http.Response> Function(http.Request) server = (r) async => reply(200);
  bool saveFails = false;

  BourseAlertApi get api => BourseAlertApi(
        client: MockClient((r) async {
          requests.add(r);
          return server(r);
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
        userId: () async => 'u1',
        fcmToken: () async => 'tok',
      );

  Widget page() => MaterialApp(
        home: BourseAlertFormPage(
          quote: quote(),
          api: api,
          onCreated: (rule) async {
            if (saveFails) throw StateError('disk full');
            saved.add(rule);
          },
        ),
      );

  Map<String, dynamic> get lastBody => jsonDecode(utf8.decode(requests.last.bodyBytes)) as Map<String, dynamic>;
}

Future<void> enter(WidgetTester t, String text) async {
  await t.enterText(find.byKey(const Key('bourse_form_amount')), text);
  await t.pump();
}

Future<void> submit(WidgetTester t) async {
  final btn = find.byKey(const Key('bourse_form_submit'));
  await t.ensureVisible(btn);
  await t.tap(btn);
  await t.pumpAndSettle();
}

void main() {
  group('parseBourseAmount', () {
    test('plain, grouped, Persian and Arabic digits', () {
      expect(parseBourseAmount('700000'), 700000);
      expect(parseBourseAmount('700,000'), 700000);
      expect(parseBourseAmount('۷۰۰٬۰۰۰'), 700000);
      expect(parseBourseAmount('٧٠٠٠٠٠'), 700000);
      expect(parseBourseAmount('2.5'), 2.5);
      expect(parseBourseAmount('۲٫۵'), 2.5);
    });

    test('rubbish is null', () {
      expect(parseBourseAmount(''), isNull);
      expect(parseBourseAmount('abc'), isNull);
      expect(parseBourseAmount('1.2.3'), isNull);
      expect(parseBourseAmount('   '), isNull);
    });
  });

  group('form', () {
    testWidgets('shows the last price and starts without errors', (t) async {
      final h = Harness();
      await t.pumpWidget(h.page());
      expect(find.byKey(const Key('bourse_form_last_price')), findsOneWidget);
      expect(find.text('${BourseStrings.lastPrice}: 668,761 ریال'), findsOneWidget);
      expect(find.byKey(const Key('bourse_form_error')), findsNothing);
      expect(find.byKey(const Key('bourse_form_warning')), findsNothing);
    });

    testWidgets('an empty amount is explained and nothing is sent', (t) async {
      final h = Harness();
      await t.pumpWidget(h.page());
      await submit(t);
      expect(find.text(BourseStrings.alertProblem(BourseAlertProblem.amountMissing)), findsOneWidget);
      expect(h.requests, isEmpty);
      expect(h.saved, isEmpty);
    });

    testWidgets('zero is refused', (t) async {
      final h = Harness();
      await t.pumpWidget(h.page());
      await enter(t, '0');
      await submit(t);
      expect(find.text(BourseStrings.alertProblem(BourseAlertProblem.amountNotPositive)), findsOneWidget);
      expect(h.requests, isEmpty);
    });

    testWidgets('a price alert is created on the server, then saved on the phone', (t) async {
      final h = Harness();
      await t.pumpWidget(h.page());
      await enter(t, '۷۰۰٬۰۰۰');
      expect(find.byKey(const Key('bourse_form_preview')), findsOneWidget);
      expect(find.text('700,000 ریال'), findsOneWidget);

      await submit(t);
      expect(h.requests.length, 1);
      expect(h.requests.single.method, 'POST');
      expect(h.lastBody['exchange'], 'tsetmc');
      expect(h.lastBody['symbol'], ayarId);
      expect(h.lastBody['condition'], 'ABOVE');
      expect(h.lastBody['target_price'], 700000);
      expect(h.saved.length, 1);
      expect(h.saved.single.uuid, h.lastBody['id']);
      expect(h.saved.single.marketSymbol, ayarId);
      expect(find.byKey(const Key('bourse_form_error')), findsNothing);
    });

    testWidgets('direction below and recurring are sent', (t) async {
      final h = Harness();
      await t.pumpWidget(h.page());
      await t.tap(find.text(BourseStrings.directionBelow));
      await t.pump();
      final sw = find.byKey(const Key('bourse_form_recurring'));
      await t.ensureVisible(sw);
      await t.tap(sw);
      await t.pump();
      await enter(t, '600000');
      await submit(t);
      expect(h.lastBody['condition'], 'BELOW');
      expect(h.lastBody['trigger_mode'], 'recurring');
    });

    testWidgets('the note is sent', (t) async {
      final h = Harness();
      await t.pumpWidget(h.page());
      await enter(t, '700000');
      final note = find.byKey(const Key('bourse_form_note'));
      await t.ensureVisible(note);
      await t.enterText(note, 'هدف اول');
      await submit(t);
      expect(h.lastBody['note'], 'هدف اول');
    });

    testWidgets('a percent alert shows the price it needs and sends percent + base', (t) async {
      final h = Harness();
      await t.pumpWidget(h.page());
      await t.tap(find.byKey(const Key('bourse_kind_percentChange')));
      await t.pump();
      await enter(t, '3');
      // 668554 * 1.03 = 688,610.6 -> 688,611
      expect(find.byKey(const Key('bourse_form_target')), findsOneWidget);
      expect(find.text('≈ 688,611 ریال'), findsOneWidget);

      await submit(t);
      expect(h.lastBody['condition_type'], 'percentChange');
      expect(h.lastBody['percent'], 3.0);
      expect(h.lastBody['base_price'], 668554.0);
    });

    testWidgets('a Rial-change alert sends delta_absolute', (t) async {
      final h = Harness();
      await t.pumpWidget(h.page());
      await t.tap(find.byKey(const Key('bourse_kind_absoluteChange')));
      await t.pump();
      await enter(t, '5000');
      await submit(t);
      expect(h.lastBody['condition_type'], 'absolutePriceChange');
      expect(h.lastBody['delta_absolute'], 5000.0);
    });

    testWidgets('outside the daily band shows a warning but can still be created', (t) async {
      final h = Harness();
      await t.pumpWidget(h.page());
      await enter(t, '700000'); // upper limit is 677,950
      expect(find.text(BourseStrings.alertWarning(BourseAlertWarning.unreachableToday)), findsOneWidget);
      await submit(t);
      expect(h.requests.length, 1);
    });

    testWidgets('a condition that is already true shows the immediate-fire warning', (t) async {
      final h = Harness();
      await t.pumpWidget(h.page());
      await enter(t, '600000'); // last price 668,761 is already above
      expect(find.text(BourseStrings.alertWarning(BourseAlertWarning.alreadyReached)), findsOneWidget);
    });

    testWidgets('a normal target shows no warning', (t) async {
      final h = Harness();
      await t.pumpWidget(h.page());
      await enter(t, '675000');
      expect(find.byKey(const Key('bourse_form_warning')), findsNothing);
    });
  });

  group('refusals and failures', () {
    testWidgets('user not on the rollout list: message shown, nothing saved', (t) async {
      final h = Harness()
        ..server = (r) async => reply(403, {'detail': 'Iranian Bourse alerts are not available for this user yet.'});
      await t.pumpWidget(h.page());
      await enter(t, '700000');
      await submit(t);
      expect(find.text(BourseStrings.failureMessage(BourseFailure.notAllowed)), findsOneWidget);
      expect(h.saved, isEmpty);
      expect(h.requests.length, 1); // no undo call: the server never had it
    });

    testWidgets('no network: message shown, can retry', (t) async {
      final h = Harness()..server = (r) async => throw http.ClientException('down');
      await t.pumpWidget(h.page());
      await enter(t, '700000');
      await submit(t);
      expect(find.text(BourseStrings.failureMessage(BourseFailure.network)), findsOneWidget);
      expect(h.saved, isEmpty);

      h.server = (r) async => reply(200);
      await submit(t);
      expect(h.saved.length, 1);
      expect(find.byKey(const Key('bourse_form_error')), findsNothing);
    });

    testWidgets('typing again clears the old error', (t) async {
      final h = Harness()..server = (r) async => reply(500);
      await t.pumpWidget(h.page());
      await enter(t, '700000');
      await submit(t);
      expect(find.byKey(const Key('bourse_form_error')), findsOneWidget);
      await enter(t, '690000');
      expect(find.byKey(const Key('bourse_form_error')), findsNothing);
    });

    testWidgets('when saving on the phone fails the server copy is removed', (t) async {
      final h = Harness()..saveFails = true;
      await t.pumpWidget(h.page());
      await enter(t, '700000');
      await submit(t);

      expect(h.requests.map((r) => r.method).toList(), ['POST', 'DELETE']);
      final posted = jsonDecode(utf8.decode(h.requests.first.bodyBytes)) as Map<String, dynamic>;
      expect(h.requests.last.url.path, '/api/alerts/${posted['id']}');
      expect(find.text(BourseStrings.alertSaveFailed), findsOneWidget);
      expect(h.saved, isEmpty);
    });
  });
}
