import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:bitcoin_checker/core/services/server_alert_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ServerAlertService.claimGuestAlerts Unit Tests', () {
    const testUserId = 'test_user@example.com';
    const testToken = 'fcm_mock_device_token_12345';
    const testApiKey = 'test_secret_mobile_api_key';

    setUp(() {
      ServerAlertService.setApiKeyForTesting(testApiKey);
      ServerAlertService.setBaseUrlForTesting('https://test.aisocialfeed.com');
    });

    test('1. Successful claim sends POST to /api/alerts/claim with user_id, fcm_token and X-API-Key', () async {
      http.Request? capturedRequest;
      final mockClient = MockClient((request) async {
        capturedRequest = request as http.Request;
        if (request.url.path.endsWith('/api/alerts/claim') && request.method == 'POST') {
          return http.Response(
            jsonEncode({'status': 'success', 'claimed_count': 3}),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }
        return http.Response('Not Found', 404);
      });

      final result = await ServerAlertService.claimGuestAlerts(
        userId: testUserId,
        fcmToken: testToken,
        apiKey: testApiKey,
        client: mockClient,
      );

      expect(result, equals(3));
      expect(capturedRequest, isNotNull);
      expect(capturedRequest!.method, equals('POST'));
      expect(capturedRequest!.url.path, endsWith('/api/alerts/claim'));
      expect(capturedRequest!.headers['x-api-key'], equals(testApiKey));
      expect(capturedRequest!.headers['content-type'], contains('application/json'));
      final decodedBody = jsonDecode(capturedRequest!.body);
      expect(decodedBody['user_id'], equals(testUserId));
      expect(decodedBody['fcm_token'], equals(testToken));
    });

    test('2. Server error (500) returns 0 and does not disrupt execution', () async {
      final mockClient = MockClient((request) async {
        return http.Response('{"detail": "Internal Server Error"}', 500);
      });

      final result = await ServerAlertService.claimGuestAlerts(
        userId: testUserId,
        fcmToken: testToken,
        client: mockClient,
      );

      expect(result, equals(0));
    });

    test('3. Network / Socket exception does not throw and returns 0', () async {
      final mockClient = MockClient((request) async {
        throw http.ClientException('Network unreachable');
      });

      final result = await ServerAlertService.claimGuestAlerts(
        userId: testUserId,
        fcmToken: testToken,
        client: mockClient,
      );

      expect(result, equals(0));
    });

    test('4. Empty userId or user_default returns 0 without HTTP call', () async {
      bool called = false;
      final mockClient = MockClient((request) async {
        called = true;
        return http.Response('{}', 200);
      });

      final res1 = await ServerAlertService.claimGuestAlerts(
        userId: '',
        fcmToken: testToken,
        client: mockClient,
      );
      final res2 = await ServerAlertService.claimGuestAlerts(
        userId: 'user_default',
        fcmToken: testToken,
        client: mockClient,
      );

      expect(res1, equals(0));
      expect(res2, equals(0));
      expect(called, isFalse);
    });

    test('5. Empty fcmToken returns 0 without HTTP call', () async {
      bool called = false;
      final mockClient = MockClient((request) async {
        called = true;
        return http.Response('{}', 200);
      });

      final res = await ServerAlertService.claimGuestAlerts(
        userId: testUserId,
        fcmToken: '',
        client: mockClient,
      );

      expect(res, equals(0));
      expect(called, isFalse);
    });
  });
}
