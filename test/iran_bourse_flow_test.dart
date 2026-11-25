import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_api.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_flow.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/iran_bourse_service.dart';

/// IB-11e / IB-16e: the whole Bourse flow (browse list -> detail -> form -> save) against a fake server.
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
  bool boardFails = false;
  int boardCalls = 0;
  bool? result;
  bool finished = false;

  IranBourseService get service => IranBourseService(
        client: MockClient((req) async {
          final path = req.url.path;
          if (path == '/api/iran-bourse/board') {
            boardCalls++;
            if (boardFails) return jsonOk({'detail': 'down'}, 503);
            return jsonOk({
              'unit': 'IRR',
              'session': 'OPEN',
              'stale': false,
              'as_of': 1794726798,
              'total': 1,
              'offset': 0,
              'limit': 50,
              'sort': 'value',
              'order': 'desc',
              'groups': {'stocks': 0, 'funds': 1, 'bonds': 0, 'rights': 0, 'derivatives': 0, 'other': 0},
              'other_types': {},
              'items': [
                {
                  'id': ayarId,
                  'ticker': 'عیار',
                  'name': 'صندوق طلای عیار مفید',
                  'price': 668761,
                  'price_source': 'last',
                  'change_pct': -0.4,
                  'traded': true,
                  'group': 'funds',
                  'type': 'صندوق کالایی',
                },
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
  // Tapping a symbol in the browse list opens the unified Symbol + Alert workspace directly.
  await t.tap(find.byKey(const ValueKey('bourse_board_row_$ayarId')));
  await t.pumpAndSettle();
}

void main() {
  testWidgets('list, pick, create: alert is saved and the whole flow closes with true', (t) async {
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
    expect(find.byKey(const Key('bourse_board_search')), findsNothing);
    expect(find.byKey(const Key('bourse_form_amount')), findsNothing);
    expect(find.byKey(const Key('open_flow')), findsOneWidget);
  });

  testWidgets('the browse list opens first and shows the symbol without any search', (t) async {
    final rig = Rig();
    await t.pumpWidget(rig.app());
    await t.tap(find.byKey(const Key('open_flow')));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('bourse_board_search')), findsOneWidget);
    expect(find.byKey(const ValueKey('bourse_board_row_$ayarId')), findsOneWidget);
    expect(rig.boardCalls, 1);
  });

  testWidgets('if the list fails to load the user sees a message and can retry into the flow', (t) async {
    final rig = Rig()..boardFails = true;
    await t.pumpWidget(rig.app());
    await t.tap(find.byKey(const Key('open_flow')));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('bourse_failure_text')), findsOneWidget);
    expect(find.byKey(const Key('bourse_retry')), findsOneWidget);

    rig.boardFails = false;
    await t.tap(find.byKey(const Key('bourse_retry')));
    await t.pumpAndSettle();
    expect(find.byKey(const ValueKey('bourse_board_row_$ayarId')), findsOneWidget);
    await t.tap(find.byKey(const ValueKey('bourse_board_row_$ayarId')));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('bourse_form_amount')), findsOneWidget);
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
    // Unified flow has 2 routes: workspace -> browse -> caller.
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
