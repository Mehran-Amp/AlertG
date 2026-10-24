import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/features/notifications/models/alert_dispatch_result.dart';
import 'package:bitcoin_checker/features/notifications/services/notification_service.dart';

void main() {
  group('AlertDedup', () {
    late Directory tmp;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('alert_dedup_test_');
      AlertDedup.baseDirOverride = tmp;
    });

    tearDown(() {
      try {
        tmp.deleteSync(recursive: true);
      } catch (_) {}
      AlertDedup.baseDirOverride = null;
    });

    test('claim returns false on duplicate in window and true after release', () async {
      final first = await AlertDedup.claim('alert_test_uuid');
      expect(first, isTrue, reason: 'First claim must succeed');

      final second = await AlertDedup.claim('alert_test_uuid');
      expect(second, isFalse, reason: 'Second claim within window must return false');

      await AlertDedup.release('alert_test_uuid');

      final third = await AlertDedup.claim('alert_test_uuid');
      expect(third, isTrue, reason: 'Claim after release must return true');
    });

    test('claim honors deliveryIdWindow for delivery_id keys', () async {
      const deliveryId = 'a1b2c3d4e5f60718293a4b5c6d7e8f90';

      final first = await AlertDedup.claim(deliveryId, window: AlertDedup.deliveryIdWindow);
      expect(first, isTrue, reason: 'First claim with deliveryIdWindow must succeed');

      final second = await AlertDedup.claim(deliveryId, window: AlertDedup.deliveryIdWindow);
      expect(second, isFalse, reason: 'Duplicate within 10-minute window must return false');

      await AlertDedup.release(deliveryId);

      final third = await AlertDedup.claim(deliveryId, window: AlertDedup.deliveryIdWindow);
      expect(third, isTrue, reason: 'Claim after release must succeed again');
    });
  });

  group('NotificationService dual-key dedup (FIX-3)', () {
    late Directory tmp;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('notif_dedup_test_');
      AlertDedup.baseDirOverride = tmp;
      NotificationService.showBannerOverride = ({required id, required title, required body, payload}) async {};
      NotificationService.areNotificationsEnabledOverride = true;
    });

    tearDown(() {
      NotificationService.showBannerOverride = null;
      NotificationService.areNotificationsEnabledOverride = null;
      try {
        tmp.deleteSync(recursive: true);
      } catch (_) {}
      AlertDedup.baseDirOverride = null;
    });

    test('1. local alert with alert_id, then FCM with same alert_id and new delivery_id within 20s returns duplicate', () async {
      final service = NotificationService();

      // Local alert with alert_id in payload
      final localRes = await service.enqueueCriticalAlert(
        id: 101,
        title: 'BTC High Alert',
        body: 'BTC is above 70000',
        payload: 'rule-btc-70k',
      );
      expect(localRes, equals(AlertDispatchResult.shown));

      // FCM arrives within 20s with same alert_id in payload and a new delivery_id
      final fcmRes = await service.enqueueCriticalAlert(
        id: 101,
        title: 'BTC High Alert',
        body: 'BTC is above 70000',
        payload: 'rule-btc-70k',
        dedupeKey: 'deliv-fcm-hex-000000000000000001',
      );
      expect(fcmRes, equals(AlertDispatchResult.duplicate));
    });

    test('2. FCM resend with same delivery_id after 30s returns duplicate (10m window)', () async {
      final service = NotificationService();

      final res1 = await service.enqueueCriticalAlert(
        id: 202,
        title: 'ETH Alert',
        body: 'ETH > 3500',
        payload: 'rule-eth-3500',
        dedupeKey: 'deliv-fcm-hex-000000000000000002',
      );
      expect(res1, equals(AlertDispatchResult.shown));

      // Age both lock files by 30 seconds
      final dFile = File('${tmp.path}/dedup/${AlertDedup.safe('deliv-fcm-hex-000000000000000002')}.lock');
      final pFile = File('${tmp.path}/dedup/${AlertDedup.safe('rule-eth-3500')}.lock');
      expect(dFile.existsSync(), isTrue);
      expect(pFile.existsSync(), isTrue);

      final thirtySecAgo = DateTime.now().subtract(const Duration(seconds: 30));
      dFile.setLastModifiedSync(thirtySecAgo);
      pFile.setLastModifiedSync(thirtySecAgo);

      // Resending with same delivery_id after 30s must be suppressed because deliveryIdWindow is 10m
      final res2 = await service.enqueueCriticalAlert(
        id: 202,
        title: 'ETH Alert',
        body: 'ETH > 3500',
        payload: 'rule-eth-3500',
        dedupeKey: 'deliv-fcm-hex-000000000000000002',
      );
      expect(res2, equals(AlertDispatchResult.duplicate));
    });

    test('3. new delivery_id for same alert_id after 30s returns shown (20s window expired)', () async {
      final service = NotificationService();

      final res1 = await service.enqueueCriticalAlert(
        id: 303,
        title: 'SOL Alert',
        body: 'SOL < 150',
        payload: 'rule-sol-150',
        dedupeKey: 'deliv-fcm-hex-000000000000000003',
      );
      expect(res1, equals(AlertDispatchResult.shown));

      // Age locks by 30 seconds (20s window expires, while old delivery_id lock remains)
      final dFile = File('${tmp.path}/dedup/${AlertDedup.safe('deliv-fcm-hex-000000000000000003')}.lock');
      final pFile = File('${tmp.path}/dedup/${AlertDedup.safe('rule-sol-150')}.lock');
      expect(dFile.existsSync(), isTrue);
      expect(pFile.existsSync(), isTrue);

      final thirtySecAgo = DateTime.now().subtract(const Duration(seconds: 30));
      dFile.setLastModifiedSync(thirtySecAgo);
      pFile.setLastModifiedSync(thirtySecAgo);

      // A fresh FCM push (new delivery_id) after 30s for the same alert_id must show
      final res2 = await service.enqueueCriticalAlert(
        id: 303,
        title: 'SOL Alert',
        body: 'SOL < 150',
        payload: 'rule-sol-150',
        dedupeKey: 'deliv-fcm-hex-000000000000000004',
      );
      expect(res2, equals(AlertDispatchResult.shown));
    });
  });
}

