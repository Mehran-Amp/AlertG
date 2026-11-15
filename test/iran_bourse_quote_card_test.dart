import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';
import 'package:bitcoin_checker/features/iran_bourse/widgets/bourse_quote_card.dart';
import 'package:bitcoin_checker/features/iran_bourse/widgets/bourse_state_badge.dart';

/// IB-11c: the quote card and the state badge (real capture values, Ayar gold fund).
const String ayarId = '34144395039913458';

BourseQuote quote({
  BourseState state = BourseState.closed,
  num? price = 668761,
  double? changePct = 0.03,
  num? nav = 670622,
  Object? queue,
  String? market,
  String? marketCode = '7',
  String? type = 'صندوق کالایی',
  String? sector = 'صندوق سرمایه‌گذاری قابل معامله',
  DateTime? asOf,
}) {
  return BourseQuote(
    symbol: ayarId,
    ticker: 'عیار',
    name: 'صندوق طلای عیار مفید',
    state: state,
    price: price,
    changePct: changePct,
    prevClose: 668554,
    close: 673142,
    high: 677950,
    low: 668545,
    volume: 65135046,
    upperLimit: 735409,
    lowerLimit: 601699,
    nav: nav,
    queueRaw: queue,
    lastTradeTime: '17:59:59',
    asOf: asOf ?? DateTime.utc(2026, 11, 15, 5, 0, 0),
    marketCode: marketCode,
    market: market,
    type: type,
    sector: sector,
  );
}

Future<void> pumpCard(WidgetTester tester, BourseQuote q, {bool persianDigits = false}) {
  return tester.pumpWidget(MaterialApp(
    home: Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        body: SingleChildScrollView(
          child: BourseQuoteCard(quote: q, persianDigits: persianDigits),
        ),
      ),
    ),
  ));
}

String textOf(WidgetTester tester, Key key) => tester.widget<Text>(find.byKey(key)).data!;

void main() {
  group('BourseQuoteCard', () {
    testWidgets('shows price in Rial, change, state and the main rows', (tester) async {
      await pumpCard(tester, quote());
      expect(textOf(tester, const Key('bourse_price')), '668,761 ریال');
      expect(textOf(tester, const Key('bourse_change_pct')), '+0.03%');
      expect(find.text('عیار'), findsOneWidget);
      expect(find.text('صندوق طلای عیار مفید'), findsOneWidget);
      expect(find.text(BourseStrings.stateLabel(BourseState.closed)), findsOneWidget);
      expect(find.text(BourseStrings.stateDescription(BourseState.closed)), findsOneWidget);
      expect(find.text('668,554 ریال'), findsOneWidget); // yesterday
      expect(find.text('673,142 ریال'), findsOneWidget); // close
      expect(find.text('668,545 تا 677,950'), findsOneWidget); // day range
      expect(find.text('735,409 ریال'), findsOneWidget); // upper limit
      expect(find.text('601,699 ریال'), findsOneWidget); // lower limit
      expect(find.text('65,135,046'), findsOneWidget); // volume
      expect(find.text('17:59:59'), findsOneWidget); // last trade
      expect(find.text('08:30:00'), findsOneWidget); // asOf shown in Tehran time
      expect(find.text(BourseStrings.unitNote), findsOneWidget);
    });

    testWidgets('optional rows appear only when the server has the data', (tester) async {
      await pumpCard(tester, quote(nav: null, queue: null, type: null, sector: null, marketCode: null));
      expect(find.byKey(const Key('bourse_row_nav')), findsNothing);
      expect(find.byKey(const Key('bourse_row_queue')), findsNothing);
      expect(find.byKey(const Key('bourse_row_type')), findsNothing);
      expect(find.byKey(const Key('bourse_row_sector')), findsNothing);
      expect(find.byKey(const Key('bourse_row_market')), findsNothing);

      await pumpCard(tester, quote(queue: 'صف خرید'));
      expect(find.byKey(const Key('bourse_row_nav')), findsOneWidget);
      expect(find.text('670,622 ریال'), findsOneWidget);
      expect(find.byKey(const Key('bourse_row_queue')), findsOneWidget);
      expect(find.text('صف خرید'), findsOneWidget);
      expect(find.byKey(const Key('bourse_row_type')), findsOneWidget);
      expect(find.byKey(const Key('bourse_row_market')), findsOneWidget); // falls back to the code
      expect(find.text('7'), findsOneWidget);
    });

    testWidgets('a null or zero price shows a dash, never "0 ریال"', (tester) async {
      await pumpCard(tester, quote(price: null));
      expect(textOf(tester, const Key('bourse_price')), '—');
      await pumpCard(tester, quote(price: 0));
      expect(textOf(tester, const Key('bourse_price')), '—');
    });

    testWidgets('missing change and times show dashes', (tester) async {
      final q = BourseQuote(symbol: ayarId, ticker: 'X', name: 'X', state: BourseState.unknown);
      await pumpCard(tester, q);
      expect(textOf(tester, const Key('bourse_change_pct')), '—');
      expect(find.text('—'), findsWidgets);
    });

    testWidgets('change colour follows the sign', (tester) async {
      Color colorOf(WidgetTester t) => t.widget<Text>(find.byKey(const Key('bourse_change_pct'))).style!.color!;
      await pumpCard(tester, quote(changePct: 1.5));
      final up = colorOf(tester);
      await pumpCard(tester, quote(changePct: -1.5));
      final down = colorOf(tester);
      await pumpCard(tester, quote(changePct: 0));
      final flat = colorOf(tester);
      expect(up, isNot(down));
      expect(flat, isNot(up));
      expect(flat, isNot(down));
    });

    testWidgets('Persian digits on request', (tester) async {
      await pumpCard(tester, quote(), persianDigits: true);
      expect(textOf(tester, const Key('bourse_price')), '۶۶۸٬۷۶۱ ریال');
      expect(find.text('۱۷:۵۹:۵۹'), findsOneWidget);
    });

    testWidgets('each state gets its own description', (tester) async {
      for (final s in BourseState.values) {
        await pumpCard(tester, quote(state: s));
        expect(find.text(BourseStrings.stateDescription(s)), findsOneWidget, reason: '$s');
      }
    });
  });

  group('BourseStateBadge', () {
    testWidgets('shows the Persian label of the state', (tester) async {
      for (final s in BourseState.values) {
        await tester.pumpWidget(MaterialApp(home: Scaffold(body: BourseStateBadge(state: s))));
        expect(find.text(BourseStrings.stateLabel(s)), findsOneWidget, reason: '$s');
      }
    });

    test('live is green, stale is amber, the others are neutral', () {
      final live = BourseStateBadge.colorOf(BourseState.live);
      final stale = BourseStateBadge.colorOf(BourseState.stale);
      final closed = BourseStateBadge.colorOf(BourseState.closed);
      expect(live, isNot(stale));
      expect(live, isNot(closed));
      expect(stale, isNot(closed));
      expect(BourseStateBadge.colorOf(BourseState.noTradeToday), closed);
      expect(BourseStateBadge.colorOf(BourseState.unknown), closed);
    });
  });
}
