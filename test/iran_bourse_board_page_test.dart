import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_board.dart';
import 'package:bitcoin_checker/features/iran_bourse/pages/bourse_board_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/iran_bourse_service.dart';

/// IB-16c-2: the browse list page against a fake server (no network).
String idOf(int n) => '10000000000${n.toString().padLeft(6, '0')}';

http.Response jsonOk(Object body, [int status = 200]) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

Map<String, dynamic> row(int n, {num? change = 1.5, bool traded = true}) => {
      'id': idOf(n),
      'ticker': 'نماد$n',
      'name': 'شرکت $n',
      'price': 1000 + n,
      'price_source': 'last',
      'change_pct': change,
      'volume': 10,
      'value': 100,
      'traded': traded,
      'group': 'stocks',
      'type': 'سهام',
    };

Map<String, dynamic> pageJson(List<Map<String, dynamic>> items,
        {int total = 0, int offset = 0, String session = 'OPEN'}) =>
    {
      'unit': 'IRR',
      'session': session,
      'stale': false,
      'as_of': 1794726798,
      'total': total == 0 ? items.length : total,
      'offset': offset,
      'limit': 50,
      'sort': 'value',
      'order': 'desc',
      'groups': {'stocks': 1209, 'funds': 412, 'bonds': 703, 'rights': 13, 'derivatives': 1381, 'other': 46},
      'other_types': {},
      'items': items,
    };

class Fake {
  final List<Uri> calls = [];
  Future<http.Response> Function(Uri) handler = (u) async => jsonOk(pageJson([row(1), row(2)]));

  IranBourseService get service => IranBourseService(
        client: MockClient((r) async {
          calls.add(r.url);
          return handler(r.url);
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
      );
}

Widget host(Fake f, {void Function(BourseBoardItem)? onSelected, int pageSize = 50}) =>
    MaterialApp(home: BourseBoardPage(service: f.service, onSelected: onSelected, debounce: Duration.zero, pageSize: pageSize));

void main() {
  testWidgets('loads the first page and shows rows, tabs with counts', (t) async {
    final f = Fake();
    await t.pumpWidget(host(f));
    await t.pumpAndSettle();
    expect(find.byKey(ValueKey('bourse_board_row_${idOf(1)}')), findsOneWidget);
    expect(find.byKey(ValueKey('bourse_board_row_${idOf(2)}')), findsOneWidget);
    expect(find.textContaining('1,209'), findsOneWidget); // stocks tab count
    expect(find.byKey(const Key('bourse_session_banner')), findsNothing);
    expect(f.calls.single.queryParameters['sort'], 'value');
    expect(f.calls.single.queryParameters.containsKey('group'), isFalse);
  });

  testWidgets('closed market: banner and last-price tags', (t) async {
    final f = Fake()..handler = (u) async => jsonOk(pageJson([row(1)], session: 'CLOSED'));
    await t.pumpWidget(host(f));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('bourse_session_banner')), findsOneWidget);
    expect(find.text(BourseStrings.tagLastPrice), findsOneWidget);
  });

  testWidgets('choosing a tab asks for that group', (t) async {
    final f = Fake();
    await t.pumpWidget(host(f));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('bourse_tab_funds')));
    await t.pumpAndSettle();
    expect(f.calls.last.queryParameters['group'], 'funds');
    await t.tap(find.byKey(const Key('bourse_tab_derivatives')));
    await t.pumpAndSettle();
    expect(f.calls.last.queryParameters['group'], 'derivatives');
  });

  testWidgets('sort menu sends the sort key', (t) async {
    final f = Fake();
    await t.pumpWidget(host(f));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('bourse_sort_menu')));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('bourse_sort_volume')));
    await t.pumpAndSettle();
    expect(f.calls.last.queryParameters['sort'], 'volume');
  });

  testWidgets('traded-only switch sends traded=true', (t) async {
    final f = Fake();
    await t.pumpWidget(host(f));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('bourse_traded_only')));
    await t.pumpAndSettle();
    expect(f.calls.last.queryParameters['traded'], 'true');
  });

  testWidgets('search sends q inside the current tab', (t) async {
    final f = Fake();
    await t.pumpWidget(host(f));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('bourse_tab_funds')));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const Key('bourse_board_search')), 'عیار');
    await t.pumpAndSettle();
    expect(f.calls.last.queryParameters['q'], 'عیار');
    expect(f.calls.last.queryParameters['group'], 'funds');
  });

  testWidgets('scrolling to the end loads the next page by offset', (t) async {
    final f = Fake();
    f.handler = (u) async {
      final off = int.parse(u.queryParameters['offset'] ?? '0');
      final items = [for (var i = off; i < off + 20; i++) row(i + 1)];
      return jsonOk(pageJson(items, total: 40, offset: off));
    };
    await t.pumpWidget(host(f, pageSize: 20));
    await t.pumpAndSettle();
    expect(f.calls.length, 1);
    await t.drag(find.byKey(const Key('bourse_board_list')), const Offset(0, -3000));
    await t.pumpAndSettle();
    expect(f.calls.length, 2);
    expect(f.calls.last.queryParameters['offset'], '20');
    await t.drag(find.byKey(const Key('bourse_board_list')), const Offset(0, -3000));
    await t.pumpAndSettle();
    expect(f.calls.length, 2); // everything loaded: no third request
    expect(find.byKey(ValueKey('bourse_board_row_${idOf(40)}')), findsOneWidget);
  });

  testWidgets('empty tab says so', (t) async {
    final f = Fake()..handler = (u) async => jsonOk(pageJson([]));
    await t.pumpWidget(host(f));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('bourse_board_empty')), findsOneWidget);
  });

  testWidgets('error shows a message and retry works', (t) async {
    final f = Fake()..handler = (u) async => throw http.ClientException('down');
    await t.pumpWidget(host(f));
    await t.pumpAndSettle();
    expect(find.text(BourseStrings.failureMessage(BourseFailure.network)), findsOneWidget);
    f.handler = (u) async => jsonOk(pageJson([row(1)]));
    await t.tap(find.byKey(const Key('bourse_retry')));
    await t.pumpAndSettle();
    expect(find.byKey(ValueKey('bourse_board_row_${idOf(1)}')), findsOneWidget);
    expect(find.byKey(const Key('bourse_failure_text')), findsNothing);
  });

  testWidgets('tapping a row reports the item', (t) async {
    final f = Fake();
    BourseBoardItem? picked;
    await t.pumpWidget(host(f, onSelected: (i) => picked = i));
    await t.pumpAndSettle();
    await t.tap(find.byKey(ValueKey('bourse_board_row_${idOf(2)}')));
    expect(picked?.id, idOf(2));
  });
}
