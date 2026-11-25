import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_api.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_draft.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_form_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_text.dart';
import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';
import 'package:bitcoin_checker/features/settings/models/app_settings.dart';

const String _ayarId = '34144395039913458';

BourseQuote _quote({String state = 'LIVE'}) => BourseQuote.tryParse({
      'price': 668761,
      'state': state,
      'alert_eligible': state == 'LIVE',
      'asOf': 1794726798,
      'symbol': _ayarId,
      'ticker': 'عیار',
      'name': 'صندوق طلای عیار مفید',
      'prev_close': 668554,
      'upper_limit': 677950,
      'lower_limit': 659000,
      'unit': 'IRR',
    })!;

http.Response _ok() => http.Response.bytes(
      utf8.encode(jsonEncode({'status': 'ok'})),
      200,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

class _Harness {
  final List<http.Request> requests = [];
  final List<AlertRule> saved = [];

  BourseAlertApi get api => BourseAlertApi(
        client: MockClient((r) async {
          requests.add(r);
          return _ok();
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
        userId: () async => 'u1',
        fcmToken: () async => 'tok',
      );

  Widget page({AppThemePalette palette = AppThemePalette.darkSapphire}) => MaterialApp(
        theme: AppSettings(themePalette: palette).buildThemeData(),
        home: BourseAlertFormPage(
          quote: _quote(),
          api: api,
          onCreated: (rule) async => saved.add(rule),
        ),
      );

  Map<String, dynamic> get lastBody => jsonDecode(utf8.decode(requests.last.bodyBytes)) as Map<String, dynamic>;
}

Future<void> _tapVisible(WidgetTester t, Finder finder) async {
  await t.ensureVisible(finder);
  await t.tap(finder);
  await t.pumpAndSettle();
}

void main() {
  group('Unified Bourse alert form — two-way, price basis & notification options', () {
    testWidgets('two-way percent change with quick chip shows both bounds and sends BOTHSIDES', (t) async {
      final h = _Harness();
      await t.pumpWidget(h.page());

      await _tapVisible(t, find.byKey(const Key('bourse_kind_percentChange')));
      await _tapVisible(t, find.text(BourseStrings.directionBothSides));
      await _tapVisible(t, find.byKey(const Key('bourse_quick_pct_3')));

      expect(find.byKey(const Key('bourse_form_both_targets')), findsOneWidget);
      expect(find.textContaining('688,611'), findsOneWidget); // 668554 * 1.03
      expect(find.textContaining('648,497'), findsOneWidget); // 668554 * 0.97

      await _tapVisible(t, find.byKey(const Key('bourse_form_submit')));
      expect(h.requests, hasLength(1));
      expect(h.lastBody['condition'], 'BOTHSIDES');
      expect(h.lastBody['direction'], 'bothSides');
      expect(h.lastBody['condition_type'], 'percentChange');
      expect(h.lastBody['percent'], 3.0);
      expect(h.lastBody['base_price'], 668554.0);
      expect(h.saved.single.direction, AlertDirection.bothSides);
    });

    testWidgets('two-way price channel with daily limit shortcuts, notes and dualActive', (t) async {
      final h = _Harness();
      await t.pumpWidget(h.page());

      await _tapVisible(t, find.text(BourseStrings.directionBothSides));
      expect(find.byKey(const Key('bourse_form_two_way_price')), findsOneWidget);

      // Use Tehran Bourse daily limit shortcuts to populate upper and lower bounds.
      await _tapVisible(t, find.byKey(const Key('bourse_shortcut_upper_limit')));
      await _tapVisible(t, find.byKey(const Key('bourse_shortcut_lower_limit')));

      await t.ensureVisible(find.byKey(const Key('bourse_form_upper_note')));
      await t.enterText(find.byKey(const Key('bourse_form_upper_note')), 'مقاومت');
      await t.ensureVisible(find.byKey(const Key('bourse_form_lower_note')));
      await t.enterText(find.byKey(const Key('bourse_form_lower_note')), 'حمایت');

      await _tapVisible(t, find.text(BourseStrings.bothWayDualTitle));
      await _tapVisible(t, find.byKey(const Key('bourse_form_submit')));

      expect(h.requests, hasLength(1));
      expect(h.lastBody['condition'], 'BOTHSIDES');
      expect(h.lastBody['condition_type'], 'priceThreshold');
      expect(h.lastBody['upper_target_price'], 677950.0);
      expect(h.lastBody['lower_target_price'], 659000.0);
      expect(h.lastBody['upper_note'], 'مقاومت');
      expect(h.lastBody['lower_note'], 'حمایت');
      expect(h.lastBody['both_way_behavior'], 'dualActive');
      expect(h.lastBody['trigger_mode'], 'recurring');
    });

    testWidgets('two-way price refuses invalid range where upper <= lower', (t) async {
      final h = _Harness();
      await t.pumpWidget(h.page());

      await _tapVisible(t, find.text(BourseStrings.directionBothSides));
      await t.enterText(find.byKey(const Key('bourse_form_upper_amount')), '650000');
      await t.enterText(find.byKey(const Key('bourse_form_lower_amount')), '660000');
      await _tapVisible(t, find.byKey(const Key('bourse_form_submit')));

      expect(find.text(BourseStrings.alertProblem(BourseAlertProblem.invalidRange)), findsOneWidget);
      expect(h.requests, isEmpty);
    });

    testWidgets('price basis close sends raw_rule.price_field = close', (t) async {
      final h = _Harness();
      await t.pumpWidget(h.page());

      await t.enterText(find.byKey(const Key('bourse_form_amount')), '675000');
      await _tapVisible(t, find.byKey(const Key('bourse_price_field_close')));
      await _tapVisible(t, find.byKey(const Key('bourse_form_submit')));

      final raw = h.lastBody['raw_rule'] as Map<String, dynamic>;
      expect(raw['price_field'], 'close');
      expect(h.saved.single.priceField, 'close');
    });

    testWidgets('notification quick presets and manual toggles are sent in payload', (t) async {
      final h = _Harness();
      await t.pumpWidget(h.page());

      await t.enterText(find.byKey(const Key('bourse_form_amount')), '675000');

      // Expand the collapsed-by-default notification options card first
      await _tapVisible(t, find.byKey(const Key('bourse_notif_expand')));

      // Apply "vibrate only" preset -> sound=false, vibration=true
      await _tapVisible(t, find.byKey(const Key('bourse_notif_preset_vibrateOnly')));
      // Also enable flash SOS and TTS manually
      await _tapVisible(t, find.byKey(const Key('bourse_form_flash_enabled')));
      await _tapVisible(t, find.byKey(const Key('bourse_form_tts_enabled')));
      expect(find.byKey(const Key('bourse_form_tts_test')), findsOneWidget);

      await _tapVisible(t, find.byKey(const Key('bourse_form_submit')));

      expect(h.lastBody['sound_enabled'], isFalse);
      expect(h.lastBody['vibration_enabled'], isTrue);
      expect(h.lastBody['flash_enabled'], isTrue);
      expect(h.lastBody['tts_enabled'], isTrue);
      expect(h.lastBody['sound'], 'alarm_siren');
    });

    test('bourseAlertDescription formats bothSides rules cleanly in Persian', () {
      final pctRule = BourseAlertDraft(
        instrumentId: _ayarId,
        ticker: 'عیار',
        name: 'عیار',
        kind: BourseAlertKind.percentChange,
        direction: AlertDirection.bothSides,
        amount: 3,
        prevClose: 668554,
      ).toRule();
      expect(bourseAlertDescription(pctRule, persianDigits: false), 'تغییر قیمت ±3٪ نسبت به قیمت دیروز');

      final channelRule = BourseAlertDraft(
        instrumentId: _ayarId,
        ticker: 'عیار',
        name: 'عیار',
        kind: BourseAlertKind.price,
        direction: AlertDirection.bothSides,
        amount: null,
        upperAmount: 677950,
        lowerAmount: 659000,
        lastPrice: 668761,
      ).toRule();
      expect(
        bourseAlertDescription(channelRule, persianDigits: false),
        'کانال قیمت: پایین‌تر از 659,000 ریال یا بالاتر از 677,950 ریال',
      );
    });
  });
}
