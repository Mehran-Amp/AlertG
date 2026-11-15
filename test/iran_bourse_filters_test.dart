import 'package:flutter_test/flutter_test.dart';

import 'package:bitcoin_checker/features/iran_bourse/models/bourse_filters.dart';
import 'package:bitcoin_checker/features/iran_bourse/utils/bourse_format.dart';

/// IB-11c: filter options built from the classification, and the Tehran time helper.
Map<String, dynamic> classification() => {
      'codes': {
        'markets': {
          '1': {'name_fa': 'بورس', 'name_en': 'Bourse'},
          '2': {'name_fa': 'فرابورس', 'name_en': 'Fara Bourse'},
          '7': {'name_fa': 'صندوق‌ها', 'name_en': 'Funds'},
        },
        'types': {
          '300': {'name_fa': 'سهام'},
          '303': {'name_fa': 'سهام'},
          '380': {'name_fa': 'صندوق کالایی'},
        },
      },
      'observed': {
        'markets': [
          {'code': '3', 'count': 1673, 'label': null},
          {'code': '2', 'count': 776, 'label': null},
          {'code': '1', 'count': 500, 'label': 'بورس تهران'},
        ],
        'types': [
          {'code': '380', 'count': 40, 'label': null},
          {'code': '311', 'count': 592, 'label': 'اختیار خرید'},
          {'code': '300', 'count': 400, 'label': null},
        ],
      },
    };

void main() {
  group('BourseFilterOptions.fromClassification', () {
    test('orders by how many instruments use the code', () {
      final o = BourseFilterOptions.fromClassification(classification());
      expect(o.markets.map((e) => e.code).toList().take(3), ['3', '2', '1']);
      expect(o.types.first.code, '311');
    });

    test('label priority: observed label, then Persian code-table name, then the code', () {
      final o = BourseFilterOptions.fromClassification(classification());
      String label(List<BourseFilterOption> l, String code) => l.firstWhere((e) => e.code == code).label;
      expect(label(o.markets, '1'), 'بورس تهران'); // observed label wins
      expect(label(o.markets, '2'), 'فرابورس'); // from the code table
      expect(label(o.markets, '3'), '3'); // nothing known: the code itself
    });

    test('codes known only from the table are still offered, after the observed ones', () {
      final o = BourseFilterOptions.fromClassification(classification());
      expect(o.markets.last.code, '7');
      expect(o.markets.last.label, 'صندوق‌ها');
      expect(o.markets.last.count, 0);
    });

    test('codes are Strings', () {
      final o = BourseFilterOptions.fromClassification(classification());
      for (final e in [...o.markets, ...o.types]) {
        expect(e.code, isA<String>());
        expect(e.code, isNotEmpty);
      }
    });

    test('labels shared by several codes get the code added', () {
      final o = BourseFilterOptions.fromClassification(classification());
      final labels = o.types.map((e) => e.label).toList();
      expect(labels, contains('سهام (300)'));
      expect(labels, contains('سهام (303)'));
      expect(labels, contains('صندوق کالایی'));
      expect(labels.toSet().length, labels.length); // all distinct
    });

    test('null, empty and malformed input never throws', () {
      expect(BourseFilterOptions.fromClassification(null).markets, isEmpty);
      expect(BourseFilterOptions.fromClassification({}).types, isEmpty);
      final weird = BourseFilterOptions.fromClassification({
        'codes': 'nope',
        'observed': {
          'markets': [
            1,
            null,
            {'code': 5},
            {'code': '', 'count': 3},
            {'code': '9', 'count': 'many'},
          ],
          'types': 'nope',
        },
      });
      expect(weird.markets.map((e) => e.code), ['9']);
      expect(weird.markets.single.count, 0);
      expect(weird.types, isEmpty);
    });
  });

  group('BourseFormat.tehranTime', () {
    test('adds 3h30 to UTC', () {
      expect(BourseFormat.tehranTime(DateTime.utc(2026, 11, 14, 20, 41, 25)), '00:11:25');
      expect(BourseFormat.tehranTime(DateTime.utc(2026, 11, 15, 5, 0, 0)), '08:30:00');
      expect(BourseFormat.tehranTime(DateTime.utc(2026, 11, 15, 15, 29, 59)), '18:59:59');
    });

    test('wraps past midnight and pads with zeros', () {
      expect(BourseFormat.tehranTime(DateTime.utc(2026, 1, 1, 20, 30, 5)), '00:00:05');
      expect(BourseFormat.tehranTime(DateTime.utc(2026, 1, 1, 0, 0, 0)), '03:30:00');
    });

    test('null gives a dash and Persian digits are optional', () {
      expect(BourseFormat.tehranTime(null), BourseFormat.dash);
      expect(BourseFormat.tehranTime(DateTime.utc(2026, 11, 15, 5, 0, 0), persianDigits: true), '۰۸:۳۰:۰۰');
    });

    test('a non-UTC input is converted correctly', () {
      final local = DateTime.utc(2026, 11, 15, 5, 0, 0).toLocal();
      expect(BourseFormat.tehranTime(local), '08:30:00');
    });
  });
}
