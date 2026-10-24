import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/core/services/device_health_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DeviceHealthService', () {
    setUp(() {
      DeviceHealthService.postOverride = null;
      DeviceHealthService.getOverride = null;
    });

    tearDown(() {
      DeviceHealthService.postOverride = null;
      DeviceHealthService.getOverride = null;
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

    test('getDeviceHealth returns map when user health exists', () async {
      DeviceHealthService.getOverride = (uid) async {
        return {
          'status': 'ok',
          'data': {
            'user_id': uid,
            'fcm_token_tail': 'abcdef',
            'battery_unrestricted': true,
          },
          'age_seconds': 120,
        };
      };

      final res = await DeviceHealthService.getDeviceHealth(userId: 'trader_test_1');
      expect(res, isNotNull);
      expect(res!['status'], 'ok');
      expect(res['age_seconds'], 120);
      expect(res['data']['fcm_token_tail'], 'abcdef');
    });

    test('getDeviceHealth returns null for blank userId without calling network', () async {
      var called = false;
      DeviceHealthService.getOverride = (uid) async {
        called = true;
        return {'status': 'ok'};
      };

      final res = await DeviceHealthService.getDeviceHealth(userId: '   ');
      expect(res, isNull);
      expect(called, isFalse);
    });

    test('isSilent flags devices with heartbeat older than 45 minutes', () {
      expect(DeviceHealthService.isSilent(null), isFalse);
      expect(DeviceHealthService.isSilent(0), isFalse);
      expect(DeviceHealthService.isSilent(2699), isFalse); // 44m 59s
      expect(DeviceHealthService.isSilent(2700), isFalse); // exactly 45m
      expect(DeviceHealthService.isSilent(2701), isTrue);  // 45m 1s -> silent!
      expect(DeviceHealthService.isSilent(3600), isTrue);  // 60m -> silent!
    });
  });
}
