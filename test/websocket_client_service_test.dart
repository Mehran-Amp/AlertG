import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/core/services/websocket_client_service.dart';
import 'package:bitcoin_checker/features/notifications/models/alert_dispatch_result.dart';
import 'package:bitcoin_checker/features/notifications/services/notification_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('WebSocketClientService Tests (Phase 4B)', () {
    late Directory tmp;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('ws_client_test_');
      AlertDedup.baseDirOverride = tmp;
      NotificationService.showBannerOverride = ({
        required id,
        required title,
        required body,
        payload,
      }) async {};
      NotificationService.areNotificationsEnabledOverride = true;
      WebSocketClientService.resetForTesting();
    });

    tearDown(() {
      WebSocketClientService.resetForTesting();
      NotificationService.showBannerOverride = null;
      NotificationService.areNotificationsEnabledOverride = null;
      try {
        tmp.deleteSync(recursive: true);
      } catch (_) {}
      AlertDedup.baseDirOverride = null;
    });

    // Test 1: Backoff schedule adheres to [2, 5, 15, 60] and progresses appropriately
    test('1. reconnect backoff schedule adheres to [2, 5, 15, 60] and caps at 60s', () {
      expect(
        WebSocketClientService.reconnectBackoffSchedule,
        equals([2, 5, 15, 60]),
        reason: 'Backoff schedule must match architecture requirement [2, 5, 15, 60]',
      );

      // Start client
      WebSocketClientService.wsEnabled = true;
      WebSocketClientService.start(userId: 'user_test_backoff');
      expect(WebSocketClientService.backoffIndex, equals(0));
      expect(WebSocketClientService.currentBackoffSeconds, equals(2));

      // Advance 1: from 2s to 5s
      WebSocketClientService.advanceBackoffForTesting();
      expect(WebSocketClientService.backoffIndex, equals(1));
      expect(WebSocketClientService.currentBackoffSeconds, equals(5));

      // Advance 2: from 5s to 15s
      WebSocketClientService.advanceBackoffForTesting();
      expect(WebSocketClientService.backoffIndex, equals(2));
      expect(WebSocketClientService.currentBackoffSeconds, equals(15));

      // Advance 3: from 15s to 60s
      WebSocketClientService.advanceBackoffForTesting();
      expect(WebSocketClientService.backoffIndex, equals(3));
      expect(WebSocketClientService.currentBackoffSeconds, equals(60));

      // Advance 4: caps at 60s
      WebSocketClientService.advanceBackoffForTesting();
      expect(WebSocketClientService.backoffIndex, equals(3));
      expect(WebSocketClientService.currentBackoffSeconds, equals(60));

      // Reset for testing restores initial state
      WebSocketClientService.resetForTesting();
      expect(WebSocketClientService.backoffIndex, equals(0));
      expect(WebSocketClientService.isRunning, isFalse);
    });

    // Test 2: Ping frame generates immediate Pong response with valid timestamp
    test('2. incoming ping frame produces immediate pong response frame', () {
      final List<String> capturedFrames = [];
      WebSocketClientService.onOutgoingMessageForTest = (msg) {
        capturedFrames.add(msg);
      };

      final pingPayload = jsonEncode({
        'type': 'ping',
        'ts': DateTime.now().millisecondsSinceEpoch,
      });

      WebSocketClientService.handleMessageForTesting(pingPayload);

      expect(capturedFrames.length, equals(1), reason: 'One pong frame must be emitted');
      final decodedPong = jsonDecode(capturedFrames.first) as Map<String, dynamic>;
      expect(decodedPong['type'], equals('pong'));
      expect(decodedPong['ts'], isA<int>());
    });


    test('WS-OFF-1: start() does nothing when wsEnabled=false', () {
      WebSocketClientService.resetForTesting();
      WebSocketClientService.wsEnabled = false;
      WebSocketClientService.start(userId: 'u1');
      expect(WebSocketClientService.isRunning, isFalse);
      expect(WebSocketClientService.isConnected, isFalse);
    });

    // Test 3: Alert frame triggers immediate ACK and deduplication across channels
    test('3. incoming alert frame triggers immediate socket ACK and claims dedupe lock', () async {
      final List<String> capturedFrames = [];
      WebSocketClientService.onOutgoingMessageForTest = (msg) {
        capturedFrames.add(msg);
      };

      const testDeliveryId = 'deliv_ws_test_8888444422221111';
      final alertPayload = jsonEncode({
        'type': 'alert',
        'delivery_id': testDeliveryId,
        'title': 'BTC/USDT Target Alert',
        'body': 'Price crossed 75000',
        'data': {
          'alert_id': 'rule_btc_75k',
          'symbol': 'BTCUSDT',
          'price': '75100',
          'delivery_id': testDeliveryId,
          'sound_enabled': 'false',
          'tts_enabled': 'false',
        },
      });

      WebSocketClientService.handleMessageForTesting(alertPayload);

      // Verify immediate ACK frame was dispatched over socket
      expect(capturedFrames.length, equals(1), reason: 'One ACK frame must be emitted for the alert');
      final decodedAck = jsonDecode(capturedFrames.first) as Map<String, dynamic>;
      expect(decodedAck['action'], equals('ack'));
      expect(decodedAck['delivery_id'], equals(testDeliveryId));

      // Allow async alert handling to complete
      await Future.delayed(const Duration(milliseconds: 100));

      // The deliveryId should now be locked in AlertDedup
      final isFreshClaim = await AlertDedup.claim(testDeliveryId);
      expect(
        isFreshClaim,
        isFalse,
        reason: 'delivery_id must be claimed in dedup lock so duplicate deliveries are suppressed',
      );

      // Verify that subsequent duplicate alert returns AlertDispatchResult.duplicate
      final notificationService = NotificationService();
      final duplicateResult = await notificationService.enqueueCriticalAlert(
        id: 999,
        title: 'BTC/USDT Duplicate',
        body: 'Already received',
        dedupeKey: testDeliveryId,
      );
      expect(duplicateResult, equals(AlertDispatchResult.duplicate));
    }, skip: 'DEV-2 pending: updatePriceSource must not be called from FCM isolate');
  });
}