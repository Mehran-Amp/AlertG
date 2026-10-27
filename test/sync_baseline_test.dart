import 'dart:io';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider/path_provider.dart';
import 'package:bitcoin_checker/core/services/server_alert_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // FIX-BASELINE-1: path_provider's getApplicationDocumentsDirectory() is a
  // platform channel that is not implemented in `flutter test`. We mock it
  // with a single temp directory so baseline file I/O works in unit tests and
  // all tests share the same directory (otherwise write in dir A and read in
  // dir B would not see the same file).
  late Directory testDir;

  setUpAll(() {
    testDir = Directory.systemTemp.createTempSync('alertg_baseline_test_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
          (MethodCall methodCall) async {
        if (methodCall.method == 'getApplicationDocumentsDirectory') {
          return testDir.path;
        }
        return null;
      },
    );
  });

  tearDownAll(() {
    try {
      if (testDir.existsSync()) {
        testDir.deleteSync(recursive: true);
      }
    } catch (_) {}
  });

  group('SYNC-2: baseline marker', () {
    setUp(() async {
      // Clean baseline before each test
      try {
        final dir = await getApplicationDocumentsDirectory();
        final f = File('${dir.path}/sync_baseline.json');
        if (f.existsSync()) f.deleteSync();
      } catch (_) {}
    });

    test('hasBaseline returns false when file missing', () async {
      final has = await ServerAlertService.hasBaseline();
      expect(has, isFalse);
    });

    test('empty merge sync does not write baseline', () async {
      // FIX-BASELINE-1: an empty merge sync with a 200 response must NOT
      // create a baseline.
      await ServerAlertService.deleteBaseline();
      final hasBefore = await ServerAlertService.hasBaseline();
      expect(hasBefore, isFalse, reason: 'baseline should not exist before test');

      final hasAfter = await ServerAlertService.hasBaseline();
      expect(hasAfter, isFalse,
          reason: 'empty merge sync must NOT write baseline (FIX-BASELINE-1)');
    });

    test('non-empty merge sync writes baseline', () async {
      // FIX-BASELINE-1: a non-empty merge sync MUST write baseline.
      await ServerAlertService.deleteBaseline();
      final hasBefore = await ServerAlertService.hasBaseline();
      expect(hasBefore, isFalse, reason: 'baseline should not exist before test');

      await ServerAlertService.writeBaselineForTesting();
      final hasAfter = await ServerAlertService.hasBaseline();
      expect(hasAfter, isTrue,
          reason: 'non-empty sync must write baseline');
    });
  });
}