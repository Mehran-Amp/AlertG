import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/alert_engine/widgets/alert_row.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_draft.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';
import 'package:bitcoin_checker/features/settings/models/app_settings.dart';
import 'package:bitcoin_checker/features/settings/services/settings_service.dart';
import 'package:bitcoin_checker/features/watchlist/pages/watchlist_page.dart';

class _FakeSettingsService extends SettingsService {
  AppSettings _fakeSettings;

  _FakeSettingsService({String language = 'en'})
      : _fakeSettings = AppSettings(language: language),
        super('');

  @override
  AppSettings get settings => _fakeSettings;

  @override
  Future<void> updateSettings(AppSettings newSettings) async {
    _fakeSettings = newSettings;
    notifyListeners();
  }
}

AlertRule _makeVolumeAboveRule({
  double targetVolume = 10000000,
  double? currentVolume,
  double? lastCheckedPrice = 5000,
  double? basePrice = 4900,
}) {
  return AlertRule(
    uuid: 'vol-rule-p25',
    baseCurrency: 'توریل',
    counterCurrency: 'IRR',
    marketSymbol: '35425587644337450',
    exchangeId: bourseExchangeId,
    checkIntervalSeconds: 180,
    conditionType: AlertConditionType.volumeAbove,
    direction: AlertDirection.above,
    triggerMode: TriggerMode.oneShot,
    targetPrice: targetVolume,
    basePrice: basePrice,
    lastCheckedPrice: lastCheckedPrice,
    currentVolume: currentVolume,
    createdAt: DateTime(2026, 11, 28, 10, 0),
  );
}

Widget _wrapAlertRow(AlertRule rule, {String language = 'en'}) {
  return ChangeNotifierProvider<SettingsService>.value(
    value: _FakeSettingsService(language: language),
    child: MaterialApp(
      home: Scaffold(
        body: AlertRow(
          rule: rule,
          onToggle: (_) {},
          onSwipeDelete: () {},
          onRearm: () {},
          onDuplicate: () {},
          onEdit: () {},
          onExport: () {},
        ),
      ),
    ),
  );
}

void main() {
  group('Phase 25b — volumeAbove real currentVolume / targetVolume progress', () {
    test('AlertRule JSON parses currentVolume and snake_case current_volume', () {
      final rule = _makeVolumeAboveRule(currentVolume: 3500000);
      final roundTrip = AlertRule.fromJson(rule.toJson());
      expect(roundTrip.currentVolume, 3500000.0);

      final fromServerMap = Map<String, dynamic>.from(rule.toJson())
        ..remove('currentVolume')
        ..['current_volume'] = 6400000;
      final parsedSnake = AlertRule.fromJson(fromServerMap);
      expect(parsedSnake.currentVolume, 6400000.0);
    });

    test('BourseAlertDraft.fromQuote seeds currentVolume for volumeAbove rules', () {
      const quote = BourseQuote(
        symbol: '35425587644337450',
        ticker: 'توریل',
        name: 'توکاریل',
        state: BourseState.live,
        price: 5200,
        prevClose: 5000,
        upperLimit: 5150,
        lowerLimit: 4850,
        volume: 4200000,
        tradedToday: true,
      );

      final draft = BourseAlertDraft.fromQuote(
        quote,
        kind: BourseAlertKind.volumeAbove,
        direction: AlertDirection.above,
        amount: 10000000,
      );
      final rule = draft.toRule();
      expect(rule.conditionType, AlertConditionType.volumeAbove);
      expect(rule.targetPrice, 10000000.0);
      expect(rule.currentVolume, 4200000.0);
    });

    test('computeTargetProgressState computes real volumeAbove ratio and handles null/clamp', () {
      final mid = _makeVolumeAboveRule(
        targetVolume: 10000000,
        currentVolume: 3500000,
        lastCheckedPrice: null,
        basePrice: null,
      );
      final midState = computeTargetProgressState(mid);
      expect(midState.progressFactor, closeTo(0.35, 1e-6));
      expect(midState.percentageInt, 35);
      expect(midState.color, isNotNull);

      final exceeded = _makeVolumeAboveRule(
        targetVolume: 10000000,
        currentVolume: 14000000,
      );
      final exceededState = computeTargetProgressState(exceeded);
      expect(exceededState.progressFactor, 1.0);
      expect(exceededState.percentageInt, 100);

      final missingVol = _makeVolumeAboveRule(
        targetVolume: 10000000,
        currentVolume: null,
      );
      final missingState = computeTargetProgressState(missingVol);
      expect(missingState.progressFactor, 0.0);
      expect(missingState.percentageInt, 0);
      expect(missingState.color, isNull);
    });

    testWidgets('AlertRow renders real currentVolume / targetVolume progress bar for volumeAbove', (t) async {
      final rule = _makeVolumeAboveRule(
        targetVolume: 10000000,
        currentVolume: 3500000,
        lastCheckedPrice: 5000,
      );

      await t.pumpWidget(_wrapAlertRow(rule, language: 'en'));

      final barFinder = find.byKey(const Key('alert_row_volume_progress'));
      expect(barFinder, findsOneWidget);
      final indicator = t.widget<LinearProgressIndicator>(barFinder);
      expect(indicator.value, closeTo(0.35, 1e-6));

      expect(find.text('35%'), findsOneWidget);
      final ratioFinder = find.byKey(const Key('alert_row_volume_ratio'));
      expect(ratioFinder, findsOneWidget);
      expect(t.widget<Text>(ratioFinder).data, '3,500,000 / 10,000,000 shares');
    });

    testWidgets('AlertRow hides progress bar when volumeAbove has no currentVolume instead of dividing price', (t) async {
      final rule = _makeVolumeAboveRule(
        targetVolume: 10000000,
        currentVolume: null,
        lastCheckedPrice: 5000000, // Would falsely show 50% if price/target were used
      );

      await t.pumpWidget(_wrapAlertRow(rule, language: 'en'));

      expect(find.byKey(const Key('alert_row_volume_progress')), findsNothing);
      expect(find.byKey(const Key('alert_row_volume_ratio')), findsNothing);
      expect(find.text('50%'), findsNothing);
    });
  });
}
