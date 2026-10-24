import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/core/services/device_health_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DeviceHealthService', () {
    setUp(() {
      DeviceHealthService.postOverride = null;
    });

    tearDown(() {
      DeviceHealthService.postOverride = null;
    });

    test('sendHeartbeat constructs and sends device health payload', () async {
      Map<String, dynamic>? capturedPayload;

      DeviceHealthService.postOverride = (payload) async {
        capturedPayload = payload;
        return true;
      };

      final ok = await DeviceHealthService.sendHeartbeat(userId: 'trader_test_1');
      expect(ok, isTrue);
      expect(capturedPayload, isNotNull);
      expect(capturedPayload!['user_id'], 'trader_test_1');
      expect(capturedPayload!['app_version'], '3.6.1');
      expect(capturedPayload!.containsKey('ts_ms'), isTrue);
      expect(capturedPayload!.containsKey('notifications_enabled'), isTrue);
      expect(capturedPayload!.containsKey('battery_unrestricted'), isTrue);
      expect(capturedPayload!.containsKey('fgs_running'), isTrue);
    });

    test('sendHeartbeat returns false without calling network when userId is blank', () async {
      var called = false;
      DeviceHealthService.postOverride = (payload) async {
        called = true;
        return true;
      };

      final ok = await DeviceHealthService.sendHeartbeat(userId: '   ');
      expect(ok, isFalse);
      expect(called, isFalse);
    });
  });
}
