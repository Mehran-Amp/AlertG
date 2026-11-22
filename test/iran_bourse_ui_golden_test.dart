import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:bitcoin_checker/core/localization/app_strings.dart';
import 'package:bitcoin_checker/features/alert_engine/repositories/json_alert_rule_repository.dart';
import 'package:bitcoin_checker/features/exchanges/registry/exchange_registry.dart';
import 'package:bitcoin_checker/features/settings/models/app_settings.dart';
import 'package:bitcoin_checker/features/settings/services/settings_service.dart';
import 'package:bitcoin_checker/features/watchlist/pages/create_alert_flow.dart';

/// Phase 22f visual regression guard:
/// Locks the unified Market Chooser (3 cards) and Iranian Hub (Model 1 two-tab switcher)
/// in both dark and light palettes so unintended layout/theme regressions fail in `flutter test`.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const audioChannel = MethodChannel('xyz.luan/audioplayers');
  const audioGlobalChannel = MethodChannel('xyz.luan/audioplayers.global');

  late Directory tempDir;

  setUpAll(() {
    tempDir = Directory.systemTemp.createTempSync('iran_bourse_22f_golden_');
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

  Future<Directory> pumpThemedFlow(
    WidgetTester tester, {
    required AppThemePalette palette,
  }) async {
    // Fixed mobile phone viewport (390x844 logical @ 2x DPR) for deterministic golden snapshots.
    tester.view.physicalSize = const Size(780, 1688);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final runDir = tempDir.createTempSync('golden_case_');
    final registry = ExchangeRegistry();
    final repo = JsonAlertRuleRepository(runDir.path);
    final settings = SettingsService(runDir.path);

    await tester.pumpWidget(
      ChangeNotifierProvider<SettingsService>.value(
        value: settings,
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: AppSettings(themePalette: palette).buildThemeData(),
          home: CreateAlertFlow(
            registry: registry,
            repository: repo,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    return runDir;
  }

  Future<void> openIranHub(WidgetTester tester) async {
    final iranCta = find.text(AppStrings.get('iran_market_cta', 'en'));
    await tester.ensureVisible(iranCta);
    await tester.pumpAndSettle();
    await tester.tap(iranCta);
    await tester.pumpAndSettle();
  }

  group('Phase 22f — Unified UI golden tests', () {
    testWidgets('market chooser (dark palette)', (WidgetTester tester) async {
      final runDir = await pumpThemedFlow(tester, palette: AppThemePalette.darkGreen);
      try {
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/market_chooser_dark.png'),
        );
      } finally {
        if (runDir.existsSync()) runDir.deleteSync(recursive: true);
      }
    });

    testWidgets('market chooser (light palette)', (WidgetTester tester) async {
      final runDir = await pumpThemedFlow(tester, palette: AppThemePalette.lightGreen);
      try {
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/market_chooser_light.png'),
        );
      } finally {
        if (runDir.existsSync()) runDir.deleteSync(recursive: true);
      }
    });

    testWidgets('Iranian hub (dark palette)', (WidgetTester tester) async {
      final runDir = await pumpThemedFlow(tester, palette: AppThemePalette.darkGreen);
      try {
        await openIranHub(tester);
        expect(find.byKey(const Key('iran_hub_tab_domestic')), findsOneWidget);
        expect(find.byKey(const Key('iran_hub_tab_bourse')), findsOneWidget);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/iran_hub_dark.png'),
        );
      } finally {
        if (runDir.existsSync()) runDir.deleteSync(recursive: true);
      }
    });

    testWidgets('Iranian hub (light palette)', (WidgetTester tester) async {
      final runDir = await pumpThemedFlow(tester, palette: AppThemePalette.lightGreen);
      try {
        await openIranHub(tester);
        expect(find.byKey(const Key('iran_hub_tab_domestic')), findsOneWidget);
        expect(find.byKey(const Key('iran_hub_tab_bourse')), findsOneWidget);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/iran_hub_light.png'),
        );
      } finally {
        if (runDir.existsSync()) runDir.deleteSync(recursive: true);
      }
    });
  });
}
