import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_api.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_form_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';
import 'package:bitcoin_checker/features/iran_bourse/pages/bourse_symbol_workspace_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/iran_bourse_service.dart';
import 'package:bitcoin_checker/features/iran_bourse/utils/bourse_format.dart';
import 'package:bitcoin_checker/features/settings/models/app_settings.dart';

const String _ayarId = '34144395039913458';

Map<String, dynamic> _richQuoteJson({
  num price = 672000,
  num? nav = 665000,
  num? volume = 12500000,
  String state = 'LIVE',
  Object? queue,
  Map<String, dynamic>? bestBid,
  Map<String, dynamic>? bestAsk,
}) =>
    {
      'symbol': _ayarId,
      'ticker': 'عیار',
      'name': 'صندوق طلای عیار مفید',
      'price': price,
      'state': state,
      'alert_eligible': state == 'LIVE',
      'asOf': 1795000000,
      'last_trade_time': '12:25:10',
      'prev_close': 668500,
      'close': 670500,
      'change_pct': 0.52,
      'high': 674000,
      'low': 666000,
      'volume': volume,
      'traded_today': true,
      'upper_limit': 678000,
      'lower_limit': 659000,
      'nav': nav,
      'queue': queue,
      'best_bid': bestBid ?? {'price': 671500, 'volume': 450000, 'orders': 12},
      'best_ask': bestAsk ?? {'price': 672500, 'volume': 180000, 'orders': 5},
      'market': 'بورس تهران',
      'type': 'صندوق کالایی',
      'sector': 'صندوق سرمایه‌گذاری قابل معامله',
      'unit': 'IRR',
    };

http.Response _jsonOk(Object body, [int status = 200]) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

double _contrast(Color a, Color b) {
  final l1 = a.computeLuminance(), l2 = b.computeLuminance();
  final hi = l1 > l2 ? l1 : l2, lo = l1 > l2 ? l2 : l1;
  return (hi + 0.05) / (lo + 0.05);
}

void _expectReadable(WidgetTester t, String label) {
  final skip = <Element>{
    for (final f in [
      find.byWidgetPredicate((w) => w is ButtonStyleButton),
      find.byWidgetPredicate((w) => w is ChoiceChip),
      find.byWidgetPredicate((w) => w is SegmentedButton),
    ])
      ...find.descendant(of: f, matching: find.byType(Text)).evaluate(),
  };
  final problems = <String>[];
  for (final e in find.byType(Text).evaluate()) {
    if (skip.contains(e)) continue;
    final w = e.widget as Text;
    final theme = Theme.of(e);
    final style = DefaultTextStyle.of(e).style.merge(w.style);
    final color = style.color;
    if (color == null) continue;
    for (final bg in [theme.scaffoldBackgroundColor, theme.colorScheme.surface]) {
      final shown = Color.alphaBlend(color, bg);
      final ratio = _contrast(shown, bg);
      if (ratio < 2.0) {
        problems.add('"${w.data ?? w.textSpan}" = ${ratio.toStringAsFixed(2)}');
      }
    }
  }
  expect(problems, isEmpty, reason: '$label\n${problems.join('\n')}');
}

void main() {
  group('BourseQuote order book & NAV bubble', () {
    test('parses best_bid, best_ask, navBubblePct and closeChangePct', () {
      final q = BourseQuote.tryParse(_richQuoteJson())!;
      expect(q.bestBid, isNotNull);
      expect(q.bestBid!.price, 671500);
      expect(q.bestBid!.volume, 450000);
      expect(q.bestBid!.orders, 12);

      expect(q.bestAsk, isNotNull);
      expect(q.bestAsk!.price, 672500);
      expect(q.bestAsk!.volume, 180000);
      expect(q.bestAsk!.orders, 5);

      // (672000 - 665000) / 665000 * 100 = +1.0526...%
      expect(q.navBubblePct, closeTo(1.0526, 0.001));
      // (670500 - 668500) / 668500 * 100 = +0.2991...%
      expect(q.closeChangePct, closeTo(0.299, 0.001));
    });

    test('compactVolume formats shares cleanly', () {
      expect(BourseFormat.compactVolume(12500000), '12.5 میلیون');
      expect(BourseFormat.compactVolume(450000), '450 هزار');
      expect(BourseFormat.compactVolume(1200000000), '1.2 میلیارد');
      expect(BourseFormat.compactVolume(8500), '8,500');
    });
  });

  group('Unified Symbol + Alert Workspace UX', () {
    testWidgets('shows sticky daily band gauge, Quick Board, order book, NAV bubble, and tap-to-fill', (t) async {
      final quote = BourseQuote.tryParse(_richQuoteJson())!;
      final saved = <AlertRule>[];
      final api = BourseAlertApi(
        client: MockClient((_) async => _jsonOk({'status': 'ok'})),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
        userId: () async => 'u1',
        fcmToken: () async => 'tok',
      );

      await t.pumpWidget(MaterialApp(
        theme: AppSettings(themePalette: AppThemePalette.darkSapphire).buildThemeData(),
        home: BourseAlertFormPage(
          quote: quote,
          api: api,
          onCreated: (r) async => saved.add(r),
        ),
      ));

      // Sticky price strip + visual daily band gauge
      expect(find.byKey(const Key('bourse_workspace_sticky_header')), findsOneWidget);
      expect(find.byKey(const Key('bourse_form_daily_band')), findsOneWidget);
      expect(find.byKey(const Key('bourse_band_last_marker')), findsOneWidget);
      expect(find.byKey(const Key('bourse_band_target_marker')), findsNothing);

      // Quick Board tiles: close, prevClose, volume, NAV + bubble, and best_bid/best_ask
      expect(find.byKey(const Key('bourse_quick_board')), findsOneWidget);
      expect(find.byKey(const Key('bourse_quick_close')), findsOneWidget);
      expect(find.byKey(const Key('bourse_quick_nav')), findsOneWidget);
      expect(find.byKey(const Key('bourse_quick_order_book')), findsOneWidget);
      expect(find.textContaining('حباب +1.05%'), findsOneWidget);

      // Secondary details collapsed by default, expands on tap
      expect(find.byKey(const Key('bourse_quick_board_details')), findsNothing);
      await t.tap(find.byKey(const Key('bourse_quick_board_more_toggle')));
      await t.pumpAndSettle();
      expect(find.byKey(const Key('bourse_quick_board_details')), findsOneWidget);
      expect(find.text('12:25:10'), findsOneWidget);
      // Collapse back so workspace stays compact
      await t.tap(find.byKey(const Key('bourse_quick_board_more_toggle')));
      await t.pumpAndSettle();

      // Tap best_ask (672,500 > last 672,000) -> populates amount, sets ABOVE, shows live target pin & live summary
      await t.tap(find.byKey(const Key('bourse_quick_best_ask')));
      await t.pumpAndSettle();
      final amountField = t.widget<TextField>(find.byKey(const Key('bourse_form_amount')));
      expect(amountField.controller!.text, '672500');
      expect(find.byKey(const Key('bourse_band_target_marker')), findsOneWidget);
      expect(find.byKey(const Key('bourse_form_live_summary')), findsOneWidget);

      // Tap NAV (665,000 < last 672,000) -> populates 665000 & auto-selects BELOW
      await t.tap(find.byKey(const Key('bourse_quick_nav')));
      await t.pumpAndSettle();
      expect(amountField.controller!.text, '665000');

      // Submit via sticky bottom button
      await t.tap(find.byKey(const Key('bourse_form_submit')));
      await t.pumpAndSettle();
      expect(saved, hasLength(1));
      expect(saved.single.targetPrice, 665000.0);
      expect(saved.single.direction, AlertDirection.below);
    });

    testWidgets('volumeAbove shows quick multiplier chips that fill scaled share threshold', (t) async {
      final quote = BourseQuote.tryParse(_richQuoteJson(volume: 10000000))!;
      await t.pumpWidget(MaterialApp(
        home: BourseAlertFormPage(quote: quote, onCreated: (_) async {}),
      ));

      await t.ensureVisible(find.byKey(const Key('bourse_kind_volumeAbove')));
      await t.tap(find.byKey(const Key('bourse_kind_volumeAbove')));
      await t.pumpAndSettle();

      expect(find.byKey(const Key('bourse_volume_multipliers')), findsOneWidget);
      await t.ensureVisible(find.byKey(const Key('bourse_vol_mult_20')));
      await t.tap(find.byKey(const Key('bourse_vol_mult_20')));
      await t.pumpAndSettle();

      final field = t.widget<TextField>(find.byKey(const Key('bourse_form_amount')));
      expect(field.controller!.text, '20000000');
    });

    testWidgets('BourseSymbolWorkspacePage loads quote, retries on error, and refreshes in place without clearing form',
        (t) async {
      var calls = 0;
      var failFirst = true;
      final service = IranBourseService(
        client: MockClient((req) async {
          calls++;
          if (failFirst) {
            failFirst = false;
            return _jsonOk({'detail': 'down'}, 503);
          }
          return _jsonOk(_richQuoteJson(price: calls == 2 ? 672000 : 675500));
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
      );

      await t.pumpWidget(MaterialApp(
        home: BourseSymbolWorkspacePage(
          instrumentId: _ayarId,
          title: 'عیار',
          service: service,
          onCreated: (_) async {},
        ),
      ));
      await t.pumpAndSettle();

      // First call failed -> shows retry
      expect(find.byKey(const Key('bourse_failure_text')), findsOneWidget);
      await t.tap(find.byKey(const Key('bourse_retry')));
      await t.pumpAndSettle();

      // Loaded at 672,000
      expect(find.textContaining('672,000'), findsWidgets);

      // Type a custom target price
      await t.ensureVisible(find.byKey(const Key('bourse_form_amount')));
      await t.enterText(find.byKey(const Key('bourse_form_amount')), '677000');
      await t.pump();

      // Tap AppBar refresh -> live price updates to 675,500 while typed 677000 stays intact!
      await t.tap(find.byKey(const Key('bourse_workspace_refresh')));
      await t.pumpAndSettle();
      expect(find.textContaining('675,500'), findsWidgets);
      final field = t.widget<TextField>(find.byKey(const Key('bourse_form_amount')));
      expect(field.controller!.text, '677000');
    });

    testWidgets('all 10 palettes maintain readable contrast on rich unified workspace', (t) async {
      final quote = BourseQuote.tryParse(_richQuoteJson(queue: 'BUY'))!;
      for (final palette in AppThemePalette.values) {
        await t.pumpWidget(MaterialApp(
          theme: AppSettings(themePalette: palette).buildThemeData(),
          home: BourseAlertFormPage(quote: quote, onCreated: (_) async {}),
        ));
        await t.pumpAndSettle();
        _expectReadable(t, 'workspace ${palette.name}');
      }
    });
  });
}
