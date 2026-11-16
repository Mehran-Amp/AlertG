import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_api.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_flow.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/iran_bourse_service.dart';

/// IB-11e: the whole Bourse flow (search -> detail -> form -> save) against a fake server.
const String ayarId = '34144395039913458';

http.Response jsonOk(Object body, [int status = 200]) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

class Rig {
  final List<http.Request> alertRequests = [];
  final List<AlertRule> saved = [];
  bool serverRefuses = false;
  bool? result;
  bool finished = false;

  IranBourseService get service => IranBourseService(
        client: MockClient((req) async {
          final path = req.url.path;
          if (path == '/api/iran-bourse/symbols') {
            return jsonOk({
              'query': 'ayar',
              'count': 1,
              'stale': false,
              'items': [
                {'id': ayarId, 'ticker': 'عیار', 'name': 'صندوق طلای عیار مفید', 'last': 668761, 'type': 'صندوق کالایی'},
              ],
            });
          }
          if (path == '/api/iran-bourse/classification') {
            return jsonOk({'stale': false, 'classification': {'codes': {}, 'observed': {}}});
          }
          if (path.startsWith('/api/iran-bourse/quote/')) {
            return jsonOk({
              'price': 668761,
              'state': 'LIVE',
              'alert_eligible': true,
              'asOf': 1794726798,
              'symbol': ayarId,
              'ticker': 'عیار',
              'name': 'صندوق طلای عیار مفید',
              'prev_close': 668554,
              'unit': 'IRR',
            });
          }
          return jsonOk({'detail': 'not found'}, 404);
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
      );

  BourseAlertApi get api => BourseAlertApi(
        client: MockClient((req) async {
          alertRequests.add(req);
          return serverRefuses
              ? jsonOk({'detail': 'Iranian Bourse alerts are not available for this user yet.'}, 403)
              : jsonOk({});
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
        userId: () async => 'u1',
        fcmToken: () async => 'tok',
      );

  Widget app() => MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                key: const Key('open_flow'),
                onPressed: () async {
                  result = await BourseAlertFlow.open(
                    context,
                    saveRule: (r) async => saved.add(r),
                    service: service,
                    api: api,
                  );
                  finished = true;
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
}

Future<void> goToForm(WidgetTester t, Rig rig) async {
  await t.pumpWidget(rig.app());
  await t.tap(find.byKey(const Key('open_flow')));
  await t.pumpAndSettle();
  await t.enterText(find.byKey(const Key('bourse_search_field')), 'عیار');
  await t.pumpAndSettle(const Duration(milliseconds: 500));
  await t.tap(find.text('عیار').last);
  await t.pumpAndSettle();
  await t.tap(find.byKey(const Key('bourse_create_alert')));
  await t.pumpAndSettle();
}

void main() {
  testWidgets('search, pick, create: alert is saved and the whole flow closes with true', (t) async {
    final rig = Rig();
    await goToForm(t, rig);
    expect(find.byKey(const Key('bourse_form_amount')), findsOneWidget);

    await t.enterText(find.byKey(const Key('bourse_form_amount')), '700000');
    final submit = find.byKey(const Key('bourse_form_submit'));
    await t.ensureVisible(submit);
    await t.tap(submit);
    await t.pumpAndSettle();

    expect(rig.alertRequests.length, 1);
    expect(rig.saved.length, 1);
    expect(rig.saved.single.exchangeId, 'tsetmc');
    expect(rig.saved.single.marketSymbol, ayarId);
    expect(rig.finished, isTrue);
    expect(rig.result, isTrue);
    expect(find.byKey(const Key('bourse_search_field')), findsNothing);
    expect(find.byKey(const Key('bourse_form_amount')), findsNothing);
    expect(find.byKey(const Key('open_flow')), findsOneWidget);
  });

  testWidgets('a server refusal keeps the user on the form and saves nothing', (t) async {
    final rig = Rig()..serverRefuses = true;
    await goToForm(t, rig);
    await t.enterText(find.byKey(const Key('bourse_form_amount')), '700000');
    final submit = find.byKey(const Key('bourse_form_submit'));
    await t.ensureVisible(submit);
    await t.tap(submit);
    await t.pumpAndSettle();

    expect(rig.saved, isEmpty);
    expect(rig.finished, isFalse);
    expect(find.byKey(const Key('bourse_form_error')), findsOneWidget);
  });

  testWidgets('backing out of the flow returns null and saves nothing', (t) async {
    final rig = Rig();
    await goToForm(t, rig);
    await t.pageBack();
    await t.pumpAndSettle();
    await t.pageBack();
    await t.pumpAndSettle();
    await t.pageBack();
    await t.pumpAndSettle();
    expect(rig.saved, isEmpty);
    expect(rig.alertRequests, isEmpty);
    expect(rig.result, isNull);
    expect(rig.finished, isTrue);
  });
}
