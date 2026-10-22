import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
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
}
