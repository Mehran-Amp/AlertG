import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/core/services/device_health_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DEV-1: sendHeartbeat fgsRunning', () {
    tearDown(() {
      DeviceHealthService.postOverride = null;
    });

    test('explicit fgsRunning=true is passed to the payload', () async {
      Map<String, dynamic>? captured;
      DeviceHealthService.postOverride = (payload) async {
        captured = payload;
        return true;
      };
      await DeviceHealthService.sendHeartbeat(
        userId: 'u1',
        fgsRunning: true,
      );
      expect(captured, isNotNull);
      expect(captured!['fgs_running'], isTrue);
    });

    test('explicit fgsRunning=false is passed to the payload', () async {
      Map<String, dynamic>? captured;
      DeviceHealthService.postOverride = (payload) async {
        captured = payload;
        return true;
      };
      await DeviceHealthService.sendHeartbeat(
        userId: 'u1',
        fgsRunning: false,
      );
      expect(captured, isNotNull);
      expect(captured!['fgs_running'], isFalse);
    });
  });
}