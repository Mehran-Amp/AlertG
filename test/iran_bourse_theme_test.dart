import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_form_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_board.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';
import 'package:bitcoin_checker/features/iran_bourse/widgets/bourse_board_row.dart';
import 'package:bitcoin_checker/features/iran_bourse/widgets/bourse_quote_card.dart';
import 'package:bitcoin_checker/features/iran_bourse/widgets/bourse_session_banner.dart';
import 'package:bitcoin_checker/features/settings/models/app_settings.dart';

/// Every text on the Bourse screens must be readable on every app theme (light and dark):
/// text colour against the page and card background. Catches "white text on white" bugs.
const String ayarId = '34144395039913458';

BourseQuote quote(String state) => BourseQuote.tryParse({
      'price': 668761,
      'state': state,
      'alert_eligible': state == 'LIVE',
      'asOf': 1794726798,
      'symbol': ayarId,
      'ticker': 'عیار',
      'name': 'صندوق طلای عیار مفید',
      'prev_close': 668554,
      'close': 668000,
      'upper_limit': 677950,
      'lower_limit': 659000,
      'volume': 1500,
      'change_pct': -0.4,
      'nav': 668000,
      'unit': 'IRR',
    })!;

double luminance(Color c) => c.computeLuminance();

double contrast(Color a, Color b) {
  final l1 = luminance(a), l2 = luminance(b);
  final hi = l1 > l2 ? l1 : l2, lo = l1 > l2 ? l2 : l1;
  return (hi + 0.05) / (lo + 0.05);
}

/// Below this the text is practically invisible. Signal colours (green / red / amber) pass.
const double minContrast = 2.0;

void expectReadable(WidgetTester t, String label) {
  // Text inside buttons / chips has its own colours (on the button background): not checked here.
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
      final ratio = contrast(shown, bg);
      if (ratio < minContrast) {
        problems.add('"${w.data ?? w.textSpan}" colour ${color.toARGB32().toRadixString(16)} on ${bg.toARGB32().toRadixString(16)} = ${ratio.toStringAsFixed(2)}');
      }
    }
  }
  expect(problems, isEmpty, reason: '$label\n${problems.join('\n')}');
}

Widget host(AppThemePalette p, Widget child) => MaterialApp(
      theme: AppSettings(themePalette: p).buildThemeData(),
      home: Directionality(textDirection: TextDirection.rtl, child: Scaffold(body: SingleChildScrollView(child: child))),
    );

void main() {
  for (final palette in AppThemePalette.values) {
    group(palette.name, () {
      for (final state in ['LIVE', 'CLOSED', 'NO_TRADE_TODAY', 'STALE']) {
        testWidgets('quote card ($state)', (t) async {
          await t.pumpWidget(host(palette, BourseQuoteCard(quote: quote(state))));
          expect(find.byType(Text), findsWidgets);
          expectReadable(t, 'quote card $state');
        });
      }

      testWidgets('list row and banners', (t) async {
        final item = BourseBoardItem(
          id: ayarId,
          ticker: 'عیار',
          name: 'صندوق طلای عیار مفید',
          price: 668761,
          priceSource: BoursePriceSource.last,
          changePct: 0,
          traded: true,
          group: BourseGroup.funds,
          type: 'صندوق کالایی',
        );
        await t.pumpWidget(host(
          palette,
          Column(children: [
            BourseBoardRow(item: item, session: BourseSession.closed),
            BourseBoardRow(item: item, session: BourseSession.open),
            const BourseSessionBanner(session: BourseSession.closed),
            const BourseSessionBanner(session: BourseSession.stale),
          ]),
        ));
        expectReadable(t, 'row and banners');
      });

      testWidgets('alert form (closed market, with warning and distance)', (t) async {
        await t.pumpWidget(MaterialApp(
          theme: AppSettings(themePalette: palette).buildThemeData(),
          home: BourseAlertFormPage(quote: quote('CLOSED'), onCreated: (_) async {}),
        ));
        await t.enterText(find.byKey(const Key('bourse_form_amount')), '700000');
        await t.pump();
        expectReadable(t, 'alert form');
      });
    });
  }
}
