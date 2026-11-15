import 'package:flutter_test/flutter_test.dart';

import 'package:bitcoin_checker/features/iran_bourse/models/bourse_instrument.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';

/// IB-11a: models. Values come from the real gateway capture of 2026-11-14 (Ayar gold fund).
const String ayarId = '34144395039913458'; // > 2^53: must never become a number

Map<String, dynamic> ayarRow() => {
      'id': ayarId,
      'isin': 'IRTKMOFD0001',
      'ticker': 'عیار',
      'name': 'صندوق طلای عیار مفید',
      'last': 671609,
      'close': 668554,
      'yesterday': 668554,
      'last_change_pct': 0.46,
      'close_change_pct': 0.0,
      'high': 677950,
      'low': 668545,
      'volume': 65135046,
      'traded': true,
      'upper_limit': 735409,
      'lower_limit': 601699,
      'queue': null,
      'market_code': '7',
      'market': null,
      'board_code': 'QS',
      'board': null,
      'type_code': '380',
      'type': 'صندوق کالایی',
      'sector_code': '68',
      'sector': 'صندوق سرمایه‌گذاری قابل معامله',
      'nav': 678232,
      'update_time': '17:59:59',
    };

Map<String, dynamic> ayarQuote() => {
      'price': 668761,
      'currency': 'IRR',
      'asOf': 1794726798,
      'state': 'CLOSED',
      'source': 'tsetmc-gateway',
      'price_field': 'last',
      'last_trade_time': '17:59:59',
      'prev_close': 668554,
      'close': 673142,
      'change_pct': 0.03,
      'high': 677950,
      'low': 668545,
      'volume': 65135046,
      'ticker': 'عیار',
      'name': 'صندوق طلای عیار مفید',
      'symbol': ayarId,
      'traded_today': true,
      'is_stale': false,
      'upper_limit': 735409,
      'lower_limit': 601699,
      'queue': null,
      'nav': 670622,
      'market_code': '7',
      'market': null,
      'type_code': '380',
      'type': 'صندوق کالایی',
      'sector_code': '68',
      'sector': 'صندوق سرمایه‌گذاری قابل معامله',
      'alert_eligible': false,
      'unit': 'IRR',
      'cached': false,
    };

void main() {
  group('BourseInstrument', () {
    test('parses a real row and keeps the id a String', () {
      final i = BourseInstrument.tryParse(ayarRow())!;
      expect(i.id, ayarId);
      expect(i.id, isA<String>());
      expect(i.ticker, 'عیار');
      expect(i.name, 'صندوق طلای عیار مفید');
      expect(i.last, 671609);
      expect(i.upperLimit, 735409);
      expect(i.lowerLimit, 601699);
      expect(i.lastChangePct, 0.46);
      expect(i.nav, 678232);
      expect(i.traded, isTrue);
      expect(i.updateTime, '17:59:59');
    });

    test('null labels are tolerated and fall back to codes', () {
      final i = BourseInstrument.tryParse(ayarRow())!;
      expect(i.market, isNull);
      expect(i.board, isNull);
      expect(i.marketLabel, '7'); // name missing -> code
      expect(i.typeLabel, 'صندوق کالایی'); // name present -> name
      expect(i.queueLabel, isNull);
    });

    test('missing optional fields do not crash', () {
      final i = BourseInstrument.tryParse({'id': ayarId, 'ticker': 'X'})!;
      expect(i.name, '');
      expect(i.last, isNull);
      expect(i.nav, isNull);
      expect(i.traded, isFalse);
      expect(i.displayTicker, 'X');
    });

    test('a numeric id is rejected, never rounded (rule N6)', () {
      final row = ayarRow()..['id'] = 34144395039913458;
      expect(BourseInstrument.tryParse(row), isNull);
    });

    test('ids of the wrong shape are rejected', () {
      for (final bad in ['', '123', 'abc', '12345678901', '1' * 21, '3414439503991345x']) {
        expect(BourseInstrument.tryParse({'id': bad}), isNull, reason: bad);
      }
      expect(BourseInstrument.tryParse({'id': '1' * 12}), isNotNull);
      expect(BourseInstrument.tryParse({'id': '1' * 20}), isNotNull);
    });

    test('non-object input returns null', () {
      expect(BourseInstrument.tryParse(null), isNull);
      expect(BourseInstrument.tryParse('x'), isNull);
      expect(BourseInstrument.tryParse(<int>[1]), isNull);
    });

    test('queue label handles string, map and empty', () {
      expect(queueLabelOf(null), isNull);
      expect(queueLabelOf('  '), isNull);
      expect(queueLabelOf('صف خرید'), 'صف خرید');
      expect(queueLabelOf({'side': 'buy'}), 'buy');
      expect(queueLabelOf({'type': 'sell'}), 'sell');
      expect(queueLabelOf({}), isNull);
    });

    test('equality is by id', () {
      final a = BourseInstrument.tryParse(ayarRow())!;
      final b = BourseInstrument.tryParse({'id': ayarId, 'ticker': 'other'})!;
      expect(a == b, isTrue);
    });
  });

  group('BourseQuote', () {
    test('parses a real quote', () {
      final q = BourseQuote.tryParse(ayarQuote())!;
      expect(q.symbol, ayarId);
      expect(q.symbol, isA<String>());
      expect(q.price, 668761);
      expect(q.state, BourseState.closed);
      expect(q.alertEligible, isFalse);
      expect(q.hasPrice, isTrue);
      expect(q.unit, 'IRR');
      expect(q.prevClose, 668554);
      expect(q.changePct, 0.03);
      expect(q.lastTradeTime, '17:59:59');
      expect(q.cached, isFalse);
    });

    test('asOf is UTC epoch seconds converted to DateTime', () {
      final q = BourseQuote.tryParse(ayarQuote())!;
      expect(q.asOf, isNotNull);
      expect(q.asOf!.isUtc, isTrue);
      expect(q.asOf!.millisecondsSinceEpoch, 1794726798 * 1000);
    });

    test('state parsing, including unknown future values', () {
      expect(BourseState.parse('LIVE'), BourseState.live);
      expect(BourseState.parse('live'), BourseState.live);
      expect(BourseState.parse('CLOSED'), BourseState.closed);
      expect(BourseState.parse('NO_TRADE_TODAY'), BourseState.noTradeToday);
      expect(BourseState.parse('STALE'), BourseState.stale);
      expect(BourseState.parse('SOMETHING_NEW'), BourseState.unknown);
      expect(BourseState.parse(null), BourseState.unknown);
      expect(BourseState.parse(5), BourseState.unknown);
    });

    test('null price and missing asOf are tolerated', () {
      final m = ayarQuote()
        ..['price'] = null
        ..['asOf'] = null;
      final q = BourseQuote.tryParse(m)!;
      expect(q.price, isNull);
      expect(q.hasPrice, isFalse);
      expect(q.asOf, isNull);
    });

    test('zero or negative price does not count as a price', () {
      final q = BourseQuote.tryParse(ayarQuote()..['price'] = 0)!;
      expect(q.hasPrice, isFalse);
    });

    test('a numeric or malformed symbol is rejected', () {
      expect(BourseQuote.tryParse(ayarQuote()..['symbol'] = 34144395039913458), isNull);
      expect(BourseQuote.tryParse(ayarQuote()..['symbol'] = '12'), isNull);
      expect(BourseQuote.tryParse(ayarQuote()..remove('symbol')), isNull);
      expect(BourseQuote.tryParse(null), isNull);
    });

    test('LIVE and alert eligible are carried through', () {
      final q = BourseQuote.tryParse(ayarQuote()
        ..['state'] = 'LIVE'
        ..['alert_eligible'] = true)!;
      expect(q.state, BourseState.live);
      expect(q.alertEligible, isTrue);
    });
  });
}
