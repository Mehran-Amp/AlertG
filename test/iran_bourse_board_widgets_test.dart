import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_board.dart';
import 'package:bitcoin_checker/features/iran_bourse/widgets/bourse_board_row.dart';
import 'package:bitcoin_checker/features/iran_bourse/widgets/bourse_session_banner.dart';

/// IB-16c-1: list row and the "last price, not live" banner.
const String ayarId = '34144395039913458';

BourseBoardItem item({num? price = 668761, double? change = -0.4, bool traded = true, String ticker = 'عیار'}) =>
    BourseBoardItem(
      id: ayarId,
      ticker: ticker,
      name: 'صندوق طلای عیار مفید',
      price: price,
      priceSource: BoursePriceSource.last,
      changePct: change,
      traded: traded,
      group: BourseGroup.funds,
      type: 'صندوق کالایی',
    );

Widget host(Widget child) => MaterialApp(home: Directionality(textDirection: TextDirection.rtl, child: Scaffold(body: child)));

void main() {
  group('BourseSessionBanner.messageFor', () {
    test('live and fresh shows nothing', () {
      expect(BourseSessionBanner.messageFor(BourseSession.open), isNull);
    });

    test('closed explains last price and that alerts still work', () {
      final m = BourseSessionBanner.messageFor(BourseSession.closed)!;
      expect(m, BourseStrings.bannerClosed);
      expect(m, contains('آخرین قیمت'));
      expect(m, contains('هشدار'));
    });

    test('stale feed wins unless the market is simply closed', () {
      expect(BourseSessionBanner.messageFor(BourseSession.stale), BourseStrings.bannerStale);
      expect(BourseSessionBanner.messageFor(BourseSession.open, stale: true), BourseStrings.bannerStale);
      expect(BourseSessionBanner.messageFor(BourseSession.closed, stale: true), BourseStrings.bannerClosed);
      expect(BourseSessionBanner.messageFor(BourseSession.unknown), BourseStrings.bannerUnknown);
    });
  });

  group('BourseBoardRow.tagFor', () {
    test('closed market: every priced row is a last price', () {
      expect(BourseBoardRow.tagFor(item(), BourseSession.closed), BourseStrings.tagLastPrice);
      expect(BourseBoardRow.tagFor(item(traded: false), BourseSession.closed), BourseStrings.tagLastPrice);
      expect(BourseBoardRow.tagFor(item(), BourseSession.stale), BourseStrings.tagLastPrice);
    });

    test('open market: live rows have no tag, untraded ones say so', () {
      expect(BourseBoardRow.tagFor(item(), BourseSession.open), isNull);
      expect(BourseBoardRow.tagFor(item(traded: false), BourseSession.open), BourseStrings.tagNotTradedToday);
    });

    test('no price, no tag', () {
      expect(BourseBoardRow.tagFor(item(price: null), BourseSession.closed), isNull);
    });
  });

  group('widgets', () {
    testWidgets('banner is invisible while live and visible when closed', (t) async {
      await t.pumpWidget(host(const BourseSessionBanner(session: BourseSession.open)));
      expect(find.byKey(const Key('bourse_session_banner')), findsNothing);
      await t.pumpWidget(host(const BourseSessionBanner(session: BourseSession.closed)));
      expect(find.byKey(const Key('bourse_session_banner')), findsOneWidget);
      expect(find.text(BourseStrings.bannerClosed), findsOneWidget);
    });

    testWidgets('row shows ticker, name, Rial price, red change and the tag when closed', (t) async {
      await t.pumpWidget(host(BourseBoardRow(item: item(), session: BourseSession.closed)));
      expect(find.text('عیار'), findsOneWidget);
      expect(find.textContaining('صندوق طلای عیار مفید'), findsOneWidget);
      expect(find.text('668,761 ریال'), findsOneWidget);
      final pct = t.widget<Text>(find.text('-0.40%'));
      expect(pct.style?.color, const Color(0xFFF43F5E));
      expect(find.byKey(const Key('bourse_row_tag')), findsOneWidget);
      expect(find.text(BourseStrings.tagLastPrice), findsOneWidget);
    });

    testWidgets('green for gains, no tag while live, dash without a price', (t) async {
      await t.pumpWidget(host(BourseBoardRow(item: item(change: 2.5), session: BourseSession.open)));
      final pct = t.widget<Text>(find.text('+2.50%'));
      expect(pct.style?.color, const Color(0xFF10B981));
      expect(find.byKey(const Key('bourse_row_tag')), findsNothing);

      await t.pumpWidget(host(BourseBoardRow(item: item(price: null, change: null), session: BourseSession.closed)));
      expect(find.text('—'), findsWidgets);
      expect(find.byKey(const Key('bourse_row_tag')), findsNothing);
    });

    testWidgets('an empty ticker shows the name once, and tapping calls back', (t) async {
      var taps = 0;
      await t.pumpWidget(host(BourseBoardRow(item: item(ticker: ''), session: BourseSession.open, onTap: () => taps++)));
      expect(find.text('صندوق طلای عیار مفید'), findsOneWidget);   // title only, not repeated as subtitle
      await t.tap(find.byKey(const ValueKey('bourse_board_row_$ayarId')));
      expect(taps, 1);
    });
  });
}
