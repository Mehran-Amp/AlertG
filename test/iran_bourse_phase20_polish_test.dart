import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_form_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_board.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';
import 'package:bitcoin_checker/features/iran_bourse/pages/bourse_browse_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/iran_bourse_service.dart';
import 'package:bitcoin_checker/features/iran_bourse/widgets/bourse_board_row.dart';

const String _ayarId = '34144395039913458';
const String _fooladId = '46348559193224090';

http.Response _jsonOk(Object body) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      200,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

BourseQuote _quote(String state) => BourseQuote.tryParse({
      'price': 668761,
      'state': state,
      'alert_eligible': state == 'LIVE',
      'asOf': 1794726798,
      'symbol': _ayarId,
      'ticker': 'عیار',
      'name': 'صندوق طلای عیار مفید',
      'prev_close': 668554,
      'unit': 'IRR',
    })!;

void main() {
  group('Phase 20 — Bourse UI polish', () {
    testWidgets('BourseBoardRow shows alert badge only when alertCount > 0', (t) async {
      const item = BourseBoardItem(
        id: _ayarId,
        ticker: 'عیار',
        name: 'صندوق طلای عیار مفید',
        price: 668761,
        priceSource: BoursePriceSource.last,
        changePct: 1.25,
        traded: true,
        group: BourseGroup.funds,
        type: 'صندوق کالایی',
      );

      await t.pumpWidget(
        const MaterialApp(
          home: Directionality(
            textDirection: TextDirection.rtl,
            child: Scaffold(
              body: BourseBoardRow(item: item, session: BourseSession.open),
            ),
          ),
        ),
      );
      expect(find.byKey(const Key('bourse_row_alert_badge')), findsNothing);

      await t.pumpWidget(
        const MaterialApp(
          home: Directionality(
            textDirection: TextDirection.rtl,
            child: Scaffold(
              body: BourseBoardRow(
                item: item,
                session: BourseSession.open,
                alertCount: 2,
              ),
            ),
          ),
        ),
      );
      expect(find.byKey(const Key('bourse_row_alert_badge')), findsOneWidget);
      expect(find.text('2 هشدار'), findsOneWidget);
    });

    testWidgets('BourseBrowsePage Top Movers tab sorts by change and shows row alert badges', (t) async {
      final calls = <Uri>[];
      final service = IranBourseService(
        client: MockClient((req) async {
          calls.add(req.url);
          return _jsonOk({
            'unit': 'IRR',
            'session': 'OPEN',
            'stale': false,
            'as_of': 1794726798,
            'total': 2,
            'offset': 0,
            'limit': 50,
            'sort': req.url.queryParameters['sort'] ?? 'value',
            'order': 'desc',
            'groups': {'stocks': 1, 'funds': 1, 'bonds': 0, 'rights': 0, 'derivatives': 0, 'other': 0},
            'other_types': {},
            'items': [
              {
                'id': _ayarId,
                'ticker': 'عیار',
                'name': 'صندوق طلای عیار مفید',
                'price': 668761,
                'price_source': 'last',
                'change_pct': 2.5,
                'traded': true,
                'group': 'funds',
                'type': 'صندوق کالایی',
              },
              {
                'id': _fooladId,
                'ticker': 'فولاد',
                'name': 'فولاد مبارکه اصفهان',
                'price': 4820,
                'price_source': 'last',
                'change_pct': -1.1,
                'traded': true,
                'group': 'stocks',
                'type': 'سهام',
              },
            ],
          });
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
      );

      await t.pumpWidget(
        MaterialApp(
          home: BourseBrowsePage(
            service: service,
            debounce: Duration.zero,
            alertCounts: const {_ayarId: 1},
          ),
        ),
      );
      await t.pumpAndSettle();

      // Only Ayar has an active alert badge.
      expect(find.byKey(const Key('bourse_row_alert_badge')), findsOneWidget);
      expect(find.text('1 هشدار'), findsOneWidget);
      expect(calls.last.queryParameters['sort'], 'value');

      // Tap Top Movers -> sends sort=change without a group filter.
      await t.tap(find.byKey(const Key('bourse_tab_top_movers')));
      await t.pumpAndSettle();
      expect(calls.last.queryParameters['sort'], 'change');
      expect(calls.last.queryParameters.containsKey('group'), isFalse);

      // Tap All -> restores previous non-movers sort ('value').
      await t.tap(find.byKey(const Key('bourse_tab_all')));
      await t.pumpAndSettle();
      expect(calls.last.queryParameters['sort'], 'value');
    });

    testWidgets('BourseAlertFormPage hides redundant alertOnlyLiveNote when market is closed', (t) async {
      await t.pumpWidget(
        MaterialApp(
          home: BourseAlertFormPage(quote: _quote('LIVE'), onCreated: (_) async {}),
        ),
      );
      expect(find.byKey(const Key('bourse_form_closed_note')), findsNothing);
      expect(find.byKey(const Key('bourse_form_only_live_note')), findsOneWidget);
      expect(find.text(BourseStrings.alertOnlyLiveNote), findsOneWidget);

      await t.pumpWidget(
        MaterialApp(
          home: BourseAlertFormPage(quote: _quote('CLOSED'), onCreated: (_) async {}),
        ),
      );
      expect(find.byKey(const Key('bourse_form_closed_note')), findsOneWidget);
      expect(find.byKey(const Key('bourse_form_only_live_note')), findsNothing);
      expect(find.text(BourseStrings.alertOnlyLiveNote), findsNothing);
    });

    testWidgets('BourseBoardRow shows queue badge only when traded and queued', (t) async {
      const queuedBuy = BourseBoardItem(
        id: _fooladId,
        ticker: 'فولاد',
        name: 'فولاد مبارکه اصفهان',
        price: 4820,
        priceSource: BoursePriceSource.last,
        changePct: 3.0,
        traded: true,
        group: BourseGroup.stocks,
        queueRaw: 'buy',
      );
      await t.pumpWidget(
        const MaterialApp(
          home: Directionality(
            textDirection: TextDirection.rtl,
            child: Scaffold(
              body: BourseBoardRow(item: queuedBuy, session: BourseSession.open),
            ),
          ),
        ),
      );
      expect(find.byKey(const Key('bourse_row_queue_badge')), findsOneWidget);
      expect(find.text('صف خرید'), findsOneWidget);

      // Untraded symbol with stale queue flag must NOT show a queue badge
      const untradedQueued = BourseBoardItem(
        id: _fooladId,
        ticker: 'ضسپا8090',
        name: 'اختیار خرید',
        price: 1,
        priceSource: BoursePriceSource.last,
        traded: false,
        group: BourseGroup.derivatives,
        queueRaw: 'sell',
      );
      await t.pumpWidget(
        const MaterialApp(
          home: Directionality(
            textDirection: TextDirection.rtl,
            child: Scaffold(
              body: BourseBoardRow(item: untradedQueued, session: BourseSession.open),
            ),
          ),
        ),
      );
      expect(find.byKey(const Key('bourse_row_queue_badge')), findsNothing);
    });

    testWidgets('BourseBrowsePage exposes commodities tab and requests group=commodities', (t) async {
      t.view.physicalSize = const Size(2400, 1200);
      t.view.devicePixelRatio = 1.0;
      addTearDown(t.view.resetPhysicalSize);
      addTearDown(t.view.resetDevicePixelRatio);

      final calls = <Uri>[];
      final service = IranBourseService(
        client: MockClient((req) async {
          calls.add(req.url);
          return _jsonOk({
            'unit': 'IRR',
            'session': 'OPEN',
            'stale': false,
            'as_of': 1794726798,
            'total': 1,
            'offset': 0,
            'limit': 50,
            'sort': 'value',
            'order': 'desc',
            'groups': {
              'stocks': 0,
              'funds': 0,
              'bonds': 0,
              'rights': 0,
              'commodities': 13,
              'derivatives': 0,
              'other': 0,
            },
            'other_types': {},
            'items': [
              {
                'id': _ayarId,
                'ticker': 'زعف0510پ19',
                'name': 'زعفران نگین قاینات',
                'price': 910000,
                'price_source': 'last',
                'change_pct': 1.5,
                'traded': true,
                'group': 'commodities',
                'type': 'زعفران (کالا)',
              },
            ],
          });
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
      );

      await t.pumpWidget(
        MaterialApp(
          home: BourseBrowsePage(service: service, debounce: Duration.zero),
        ),
      );
      await t.pumpAndSettle();

      expect(find.byKey(const Key('bourse_tab_commodities')), findsOneWidget);
      await t.tap(find.byKey(const Key('bourse_tab_commodities')));
      await t.pumpAndSettle();
      expect(calls.last.queryParameters['group'], 'commodities');
    });
  });
}
