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

/// Phase 22f / 24e visual regression guard:
/// Locks the unified Market Chooser (3 cards) and Iranian Hub (Model 1 two-tab switcher)
/// in both dark and light palettes so unintended layout/theme regressions fail in `flutter test`.
///
/// Uses a bounded 3% pixel-diff threshold so minor OS-level font/icon anti-aliasing
/// differences between Windows and Linux CI do not cause false positives while real
/// layout, palette, or widget regressions still fail.
class _TolerantGoldenFileComparator extends LocalFileComparator {
  final double maxDiffRatio;

  _TolerantGoldenFileComparator(super.testFile, {required this.maxDiffRatio});

  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async {
    final ComparisonResult result = await GoldenFileComparator.compareLists(
      imageBytes,
      await getGoldenBytes(golden),
    );
    final bool passed = result.passed || result.diffPercent <= maxDiffRatio;
    if (passed) {
      result.dispose();
      return true;
    }
    final String error = await generateFailureOutput(result, golden, basedir);
    result.dispose();
    throw FlutterError(error);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const audioChannel = MethodChannel('xyz.luan/audioplayers');
  const audioGlobalChannel = MethodChannel('xyz.luan/audioplayers.global');

  late Directory tempDir;
  late GoldenFileComparator previousComparator;

  setUpAll(() {
    final prev = goldenFileComparator;
    previousComparator = prev;
    if (prev is LocalFileComparator) {
      goldenFileComparator = _TolerantGoldenFileComparator(
        prev.basedir.resolve('iran_bourse_ui_golden_test.dart'),
        maxDiffRatio: 0.03,
      );
    }
    tempDir = Directory.systemTemp.createTempSync('iran_bourse_22f_golden_');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(audioChannel, (_) async => null);
    messenger.setMockMethodCallHandler(audioGlobalChannel, (_) async => null);
  });

  tearDownAll(() {
    goldenFileComparator = previousComparator;
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
    // Fixed deterministic viewport (540x1100 logical @ 2x DPR) wide enough for Flutter's Ahem test font.
    tester.view.physicalSize = const Size(1080, 2200);
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
