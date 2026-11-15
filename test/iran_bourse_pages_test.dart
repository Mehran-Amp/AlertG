import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_instrument.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';
import 'package:bitcoin_checker/features/iran_bourse/pages/bourse_search_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/pages/bourse_symbol_detail_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/iran_bourse_service.dart';
import 'package:bitcoin_checker/features/iran_bourse/widgets/bourse_quote_card.dart';

/// IB-11c: search page and detail page against a fake server (no network).
const String ayarId = '34144395039913458';
const String idA = '11111111111111';
const String idB = '22222222222222';
const Duration quick = Duration(milliseconds: 10);

http.Response jsonOk(Object body, [int status = 200]) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

Map<String, dynamic> row(String id, String ticker, String name, {num last = 671609, double pct = 0.46}) => {
      'id': id,
      'ticker': ticker,
      'name': name,
      'last': last,
      'last_change_pct': pct,
      'type': 'صندوق کالایی',
    };

Map<String, dynamic> quoteJson({String state = 'CLOSED', Object? nav = 670622}) => {
      'price': 668761,
      'state': state,
      'alert_eligible': state == 'LIVE',
      'asOf': 1794726798,
      'symbol': ayarId,
      'ticker': 'عیار',
      'name': 'صندوق طلای عیار مفید',
      'prev_close': 668554,
      'close': 673142,
      'change_pct': 0.03,
      'nav': nav,
      'unit': 'IRR',
    };

final Map<String, dynamic> classificationBody = {
  'stale': false,
  'classification': {
    'codes': {
      'markets': {
        '1': {'name_fa': 'بورس'},
        '2': {'name_fa': 'فرابورس'},
      },
      'types': {
        '380': {'name_fa': 'صندوق کالایی'},
      },
    },
    'observed': {
      'markets': [
        {'code': '2', 'count': 776, 'label': null},
        {'code': '1', 'count': 500, 'label': null},
      ],
      'types': [
        {'code': '380', 'count': 40, 'label': null},
      ],
    },
  },
};

/// A fake server. [onSymbols] / [onQuote] may be replaced inside a test.
class FakeServer {
  final List<Uri> symbolRequests = [];
  final List<Uri> allRequests = [];

  Future<http.Response> Function(Uri uri) onSymbols = (uri) async => jsonOk({
        'query': uri.queryParameters['q'],
        'count': 1,
        'stale': false,
        'items': [row(ayarId, 'عیار', 'صندوق طلای عیار مفید')],
      });

  Future<http.Response> Function(Uri uri) onQuote = (uri) async => jsonOk(quoteJson());

  IranBourseService get service => IranBourseService(
        client: MockClient((req) async {
          allRequests.add(req.url);
          final path = req.url.path;
          if (path == '/api/iran-bourse/symbols') {
            symbolRequests.add(req.url);
            return onSymbols(req.url);
          }
          if (path == '/api/iran-bourse/classification') return jsonOk(classificationBody);
          if (path.startsWith('/api/iran-bourse/quote/')) return onQuote(req.url);
          return jsonOk({'detail': 'not found'}, 404);
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
      );
}

Future<void> pumpApp(WidgetTester tester, Widget home) => tester.pumpWidget(MaterialApp(home: home));

Future<void> typeQuery(WidgetTester tester, String text) async {
  await tester.enterText(find.byKey(const Key('bourse_search_field')), text);
  await tester.pump(const Duration(milliseconds: 50)); // debounce fires, request is sent
  await tester.pumpAndSettle();
}

void main() {
  group('BourseSearchPage', () {
    testWidgets('starts with a prompt and sends no search', (tester) async {
      final server = FakeServer();
      await pumpApp(tester, BourseSearchPage(service: server.service, debounce: quick));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('bourse_prompt')), findsOneWidget);
      expect(server.symbolRequests, isEmpty);
    });

    testWidgets('typing searches and lists price and change in Rial', (tester) async {
      final server = FakeServer();
      await pumpApp(tester, BourseSearchPage(service: server.service, debounce: quick));
      await typeQuery(tester, 'عیار');

      expect(server.symbolRequests, hasLength(1));
      expect(server.symbolRequests.single.queryParameters['q'], 'عیار');
      expect(find.byKey(ValueKey('bourse_item_$ayarId')), findsOneWidget);
      expect(find.text('671,609 ریال'), findsOneWidget);
      expect(find.text('+0.46%'), findsOneWidget);
      expect(find.byKey(const Key('bourse_prompt')), findsNothing);
    });

    testWidgets('an empty result shows the no-results text', (tester) async {
      final server = FakeServer()
        ..onSymbols = (uri) async => jsonOk({'query': 'zzz', 'items': <dynamic>[], 'stale': false});
      await pumpApp(tester, BourseSearchPage(service: server.service, debounce: quick));
      await typeQuery(tester, 'zzz');
      expect(find.byKey(const Key('bourse_no_results')), findsOneWidget);
    });

    testWidgets('a stale instrument list is announced', (tester) async {
      final server = FakeServer()
        ..onSymbols = (uri) async => jsonOk({
              'query': 'x',
              'stale': true,
              'items': [row(ayarId, 'عیار', 'n')],
            });
      await pumpApp(tester, BourseSearchPage(service: server.service, debounce: quick));
      await typeQuery(tester, 'x');
      expect(find.byKey(const Key('bourse_stale_note')), findsOneWidget);
    });

    testWidgets('a disabled Bourse shows its message, and retry works', (tester) async {
      var enabled = false;
      final server = FakeServer()
        ..onSymbols = (uri) async => enabled
            ? jsonOk({
                'query': 'x',
                'stale': false,
                'items': [row(ayarId, 'عیار', 'n')],
              })
            : jsonOk({'detail': 'Iranian Bourse is not enabled on this server.'}, 503);
      await pumpApp(tester, BourseSearchPage(service: server.service, debounce: quick));
      await typeQuery(tester, 'x');

      expect(find.text(BourseStrings.failureMessage(BourseFailure.disabled)), findsOneWidget);
      expect(find.byKey(const Key('bourse_retry')), findsOneWidget);

      enabled = true;
      await tester.tap(find.byKey(const Key('bourse_retry')));
      await tester.pumpAndSettle();
      expect(find.byKey(ValueKey('bourse_item_$ayarId')), findsOneWidget);
      expect(find.byKey(const Key('bourse_failure_text')), findsNothing);
    });

    testWidgets('a network failure shows the network message', (tester) async {
      final server = FakeServer()..onSymbols = (uri) async => throw http.ClientException('down');
      await pumpApp(tester, BourseSearchPage(service: server.service, debounce: quick));
      await typeQuery(tester, 'x');
      expect(find.text(BourseStrings.failureMessage(BourseFailure.network)), findsOneWidget);
    });

    testWidgets('tapping a result calls onSelected with the String id', (tester) async {
      final server = FakeServer();
      BourseInstrument? picked;
      await pumpApp(
        tester,
        BourseSearchPage(service: server.service, debounce: quick, onSelected: (i) => picked = i),
      );
      await typeQuery(tester, 'عیار');
      await tester.tap(find.byKey(ValueKey('bourse_item_$ayarId')));
      await tester.pumpAndSettle();

      expect(picked, isNotNull);
      expect(picked!.id, ayarId);
      expect(picked!.id, isA<String>());
      expect(find.byType(BourseSymbolDetailPage), findsNothing);
    });

    testWidgets('without onSelected, tapping a result opens the detail page', (tester) async {
      final server = FakeServer();
      await pumpApp(tester, BourseSearchPage(service: server.service, debounce: quick));
      await typeQuery(tester, 'عیار');
      await tester.tap(find.byKey(ValueKey('bourse_item_$ayarId')));
      await tester.pumpAndSettle();

      expect(find.byType(BourseSymbolDetailPage), findsOneWidget);
      expect(find.byType(BourseQuoteCard), findsOneWidget);
      expect(server.allRequests.any((u) => u.path == '/api/iran-bourse/quote/$ayarId'), isTrue);
    });

    testWidgets('the traded-only switch re-runs the search with traded=true', (tester) async {
      final server = FakeServer();
      await pumpApp(tester, BourseSearchPage(service: server.service, debounce: quick));
      await typeQuery(tester, 'عیار');
      expect(server.symbolRequests.last.queryParameters.containsKey('traded'), isFalse);

      await tester.tap(find.byKey(const Key('bourse_traded_switch')));
      await tester.pumpAndSettle();
      expect(server.symbolRequests, hasLength(2));
      expect(server.symbolRequests.last.queryParameters['traded'], 'true');
    });

    testWidgets('choosing a market filter sends its code', (tester) async {
      final server = FakeServer();
      await pumpApp(tester, BourseSearchPage(service: server.service, debounce: quick));
      await tester.pumpAndSettle(); // classification loaded
      await typeQuery(tester, 'عیار');

      await tester.tap(find.byKey(const Key('bourse_market_filter')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('فرابورس').last);
      await tester.pumpAndSettle();

      expect(server.symbolRequests.last.queryParameters['market'], '2');
    });

    testWidgets('clearing the box clears the results without another request', (tester) async {
      final server = FakeServer();
      await pumpApp(tester, BourseSearchPage(service: server.service, debounce: quick));
      await typeQuery(tester, 'عیار');
      final before = server.symbolRequests.length;

      await tester.enterText(find.byKey(const Key('bourse_search_field')), '');
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('bourse_prompt')), findsOneWidget);
      expect(find.byKey(ValueKey('bourse_item_$ayarId')), findsNothing);
      expect(server.symbolRequests.length, before);
    });

    testWidgets('an older, slower answer never replaces the newest one', (tester) async {
      final server = FakeServer()
        ..onSymbols = (uri) async {
          final q = uri.queryParameters['q'];
          if (q == 'slow') {
            await Future<void>.delayed(const Duration(milliseconds: 400));
            return jsonOk({
              'query': q,
              'stale': false,
              'items': [row(idA, 'SLOWROW', 'old')],
            });
          }
          return jsonOk({
            'query': q,
            'stale': false,
            'items': [row(idB, 'FASTROW', 'new')],
          });
        };
      await pumpApp(tester, BourseSearchPage(service: server.service, debounce: quick));

      await tester.enterText(find.byKey(const Key('bourse_search_field')), 'slow');
      await tester.pump(const Duration(milliseconds: 50)); // slow request is in flight
      await tester.enterText(find.byKey(const Key('bourse_search_field')), 'fast');
      await tester.pump(const Duration(milliseconds: 50)); // fast request answers
      await tester.pump(const Duration(milliseconds: 600)); // slow answer arrives late
      await tester.pumpAndSettle();

      expect(find.text('FASTROW'), findsOneWidget);
      expect(find.text('SLOWROW'), findsNothing);
    });
  });

  group('BourseSymbolDetailPage', () {
    testWidgets('shows a spinner, then the quote card', (tester) async {
      final server = FakeServer();
      await pumpApp(tester, BourseSymbolDetailPage(instrumentId: ayarId, service: server.service));
      expect(find.byKey(const Key('bourse_loading')), findsOneWidget);
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('bourse_loading')), findsNothing);
      expect(find.byType(BourseQuoteCard), findsOneWidget);
      expect(find.byKey(const Key('bourse_create_alert')), findsNothing); // no callback given
    });

    testWidgets('an unknown instrument shows a message; retry loads it', (tester) async {
      var known = false;
      final server = FakeServer()
        ..onQuote = (uri) async => known ? jsonOk(quoteJson()) : jsonOk({'detail': 'Unknown'}, 404);
      await pumpApp(tester, BourseSymbolDetailPage(instrumentId: ayarId, service: server.service));
      await tester.pumpAndSettle();
      expect(find.text(BourseStrings.failureMessage(BourseFailure.notFound)), findsOneWidget);

      known = true;
      await tester.tap(find.byKey(const Key('bourse_retry')));
      await tester.pumpAndSettle();
      expect(find.byType(BourseQuoteCard), findsOneWidget);
    });

    testWidgets('create-alert button passes the loaded quote to the callback', (tester) async {
      final server = FakeServer();
      BourseQuote? got;
      await pumpApp(
        tester,
        BourseSymbolDetailPage(instrumentId: ayarId, service: server.service, onCreateAlert: (q) => got = q),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byKey(const Key('bourse_create_alert'))); // below the long card
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('bourse_create_alert')));
      await tester.pump();
      expect(got, isNotNull);
      expect(got!.symbol, ayarId);
      expect(got!.price, 668761);
    });

    testWidgets('NAV row follows the data', (tester) async {
      final server = FakeServer()..onQuote = (uri) async => jsonOk(quoteJson(nav: null));
      await pumpApp(tester, BourseSymbolDetailPage(instrumentId: ayarId, service: server.service));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('bourse_row_nav')), findsNothing);
    });

    testWidgets('a LIVE quote shows the live badge', (tester) async {
      final server = FakeServer()..onQuote = (uri) async => jsonOk(quoteJson(state: 'LIVE'));
      await pumpApp(tester, BourseSymbolDetailPage(instrumentId: ayarId, service: server.service));
      await tester.pumpAndSettle();
      expect(find.text(BourseStrings.stateLabel(BourseState.live)), findsOneWidget);
    });

    testWidgets('a failed refresh keeps the last quote and warns', (tester) async {
      var fail = false;
      final server = FakeServer()
        ..onQuote = (uri) async => fail ? jsonOk({'detail': 'gone'}, 503) : jsonOk(quoteJson());
      await pumpApp(
        tester,
        BourseSymbolDetailPage(
          instrumentId: ayarId,
          service: server.service,
          autoRefresh: const Duration(seconds: 30),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(BourseQuoteCard), findsOneWidget);

      fail = true;
      await tester.pump(const Duration(seconds: 31)); // timer fires, request fails
      await tester.pump();
      expect(find.byType(BourseQuoteCard), findsOneWidget);
      expect(find.byKey(const Key('bourse_refresh_failure')), findsOneWidget);

      fail = false;
      await tester.pump(const Duration(seconds: 31));
      await tester.pump();
      expect(find.byKey(const Key('bourse_refresh_failure')), findsNothing);

      await tester.pumpWidget(const SizedBox()); // dispose the page: cancels its timer
    });
  });
}
