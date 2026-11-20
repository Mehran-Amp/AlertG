import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:bitcoin_checker/core/localization/app_strings.dart';
import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/alert_engine/repositories/json_alert_rule_repository.dart';
import 'package:bitcoin_checker/features/exchanges/registry/exchange_registry.dart';
import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/settings/services/settings_service.dart';
import 'package:bitcoin_checker/features/watchlist/pages/create_alert_flow.dart';

/// Phase 22c safety net: verifies the unified Iranian entry (Option A) and backward compatibility.
///
/// 1. Market chooser renders 3 cards (Crypto, Macro, Iran Domestic) with no standalone 4th Bourse card.
/// 2. Iranian hub shows the prominent 'بورس تهران' tile and hides the 4 legacy TSE chips & rows.
/// 3. Editing a saved rule with `exchangeId == 'iran_market'` and a `TopStocks` asset still opens
///    step 2 directly with that asset resolved.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const audioChannel = MethodChannel('xyz.luan/audioplayers');
  const audioGlobalChannel = MethodChannel('xyz.luan/audioplayers.global');

  late Directory tempDir;

  setUpAll(() {
    tempDir = Directory.systemTemp.createTempSync('iran_bourse_22b_');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(audioChannel, (_) async => null);
    messenger.setMockMethodCallHandler(audioGlobalChannel, (_) async => null);
  });

  tearDownAll(() {
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(audioChannel, null);
    messenger.setMockMethodCallHandler(audioGlobalChannel, null);
    if (tempDir.existsSync()) {
      tempDir.deleteSync(recursive: true);
    }
  });

  Future<Directory> pumpCreateAlertFlow(
    WidgetTester tester, {
    AlertRule? initialRule,
  }) async {
    // Tall logical viewport (540x1600) so all chooser cards and step-2 form controls render cleanly.
    tester.view.physicalSize = const Size(1080, 3200);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final runDir = tempDir.createTempSync('case_');
    final registry = ExchangeRegistry();
    final repo = JsonAlertRuleRepository(runDir.path);
    final settings = SettingsService(runDir.path);

    await tester.pumpWidget(
      ChangeNotifierProvider<SettingsService>.value(
        value: settings,
        child: MaterialApp(
          home: CreateAlertFlow(
            registry: registry,
            repository: repo,
            initialRule: initialRule,
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    return runDir;
  }

  group('Phase 22c — Unified Iranian entry & saved-rule safety net', () {
    testWidgets('market chooser renders 3 cards (Crypto, Macro, Iran Domestic) without standalone Bourse card',
        (WidgetTester tester) async {
      final runDir = await pumpCreateAlertFlow(tester);
      try {
        // Default SettingsService language is 'en'.
        expect(find.text(AppStrings.get('crypto_market_title', 'en')), findsOneWidget);
        expect(find.text(AppStrings.get('macro_market_title', 'en')), findsOneWidget);
        expect(find.text(AppStrings.get('iran_market_title', 'en')), findsOneWidget);
        expect(find.text(BourseStrings.marketCardTitle), findsNothing);

        expect(find.text(AppStrings.get('crypto_market_cta', 'en')), findsOneWidget);
        expect(find.text(AppStrings.get('macro_market_cta', 'en')), findsOneWidget);
        expect(find.text(AppStrings.get('iran_market_cta', 'en')), findsOneWidget);
        expect(find.text(BourseStrings.marketCardCta), findsNothing);
      } finally {
        if (runDir.existsSync()) runDir.deleteSync(recursive: true);
      }
    });

    testWidgets('Iranian hub shows 2-tab segmented switcher (Gold/FX & Tehran Bourse) and hides legacy TSE chips',
        (WidgetTester tester) async {
      final runDir = await pumpCreateAlertFlow(tester);
      try {
        final iranCta = find.text(AppStrings.get('iran_market_cta', 'en'));
        await tester.ensureVisible(iranCta);
        await tester.tap(iranCta);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        // Model 1 segmented switcher with both tabs visible.
        expect(find.byKey(const Key('iran_hub_tab_domestic')), findsOneWidget);
        expect(find.byKey(const Key('iran_hub_tab_bourse')), findsOneWidget);
        expect(find.text('طلا و ارز'), findsOneWidget);
        expect(find.text('بورس تهران'), findsOneWidget);

        // Kept non-TSE domestic chips (Iran hub is always pure Persian 'fa').
        expect(find.text(AppStrings.get('iran_cat_all', 'fa')), findsOneWidget);
        expect(find.text(AppStrings.get('iran_cat_gold', 'fa')), findsOneWidget);
        expect(find.text(AppStrings.get('iran_cat_coins', 'fa')), findsOneWidget);
        expect(find.text(AppStrings.get('iran_cat_currencies', 'fa')), findsOneWidget);
        expect(find.text(AppStrings.get('iran_cat_tether', 'fa')), findsOneWidget);
        expect(find.text(AppStrings.get('iran_cat_digital_gold', 'fa')), findsOneWidget);

        // Legacy TSE chips must be hidden.
        expect(find.text(AppStrings.get('iran_cat_gold_funds', 'fa')), findsNothing);
        expect(find.text(AppStrings.get('iran_cat_leveraged', 'fa')), findsNothing);
        expect(find.text(AppStrings.get('iran_cat_top_stocks', 'fa')), findsNothing);
        expect(find.text(AppStrings.get('iran_cat_bourse', 'fa')), findsNothing);

        // Legacy TSE rows must not duplicate Bourse entries in the 'all' list either.
        expect(find.text('فولاد مبارکه اصفهان (فولاد)'), findsNothing);

        // Switching to the Tehran Bourse tab mounts the embedded BourseBrowsePage.
        await tester.tap(find.byKey(const Key('iran_hub_tab_bourse')));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));
        expect(find.byKey(const Key('bourse_board_search')), findsOneWidget);
        expect(find.byKey(const Key('bourse_sort_menu')), findsOneWidget);
        expect(find.text(AppStrings.get('iran_cat_gold', 'fa')), findsNothing);
      } finally {
        if (runDir.existsSync()) runDir.deleteSync(recursive: true);
      }
    });

    testWidgets(
        'editing a saved rule with exchangeId == iran_market and a TopStocks asset opens step 2 directly',
        (WidgetTester tester) async {
      final legacyTopStockRule = AlertRule(
        uuid: 'legacy-iran-topstock-foolad',
        baseCurrency: 'FOOLAD',
        counterCurrency: 'تومان',
        marketSymbol: 'FOOLAD',
        exchangeId: 'iran_market',
        checkIntervalSeconds: 300,
        conditionType: AlertConditionType.priceThreshold,
        direction: AlertDirection.above,
        triggerMode: TriggerMode.oneShot,
        targetPrice: 650.0,
        lastCheckedPrice: 585.0,
        createdAt: DateTime(2026, 11, 1),
      );

      final runDir = await pumpCreateAlertFlow(tester, initialRule: legacyTopStockRule);
      try {
        // Edit mode header (uses SettingsService language = 'en')
        expect(find.text(AppStrings.get('edit_alert_title', 'en')), findsOneWidget);

        // Step 2 (condition & frequency form in pure Persian 'fa') opened directly with FOOLAD resolved
        expect(find.text('فولاد مبارکه اصفهان (فولاد)'), findsOneWidget);
        expect(find.text(AppStrings.get('auto_check_schedule', 'fa')), findsOneWidget);
        expect(find.text(AppStrings.get('condition_type', 'fa')), findsOneWidget);
        expect(find.text(AppStrings.get('save_changes_cta', 'fa')), findsOneWidget);

        // Neither chooser nor step-1 hub chips are shown
        expect(find.text(AppStrings.get('choose_market_title', 'en')), findsNothing);
        expect(find.text(AppStrings.get('iran_cat_top_stocks', 'fa')), findsNothing);
      } finally {
        if (runDir.existsSync()) runDir.deleteSync(recursive: true);
      }
    });
  });
}
