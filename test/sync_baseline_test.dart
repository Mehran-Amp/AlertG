import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider/path_provider.dart';
import 'package:bitcoin_checker/core/services/server_alert_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

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
  });
}