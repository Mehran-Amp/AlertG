import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/core/services/fcm_notification_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DEV-4c: onBackgroundMessage registration', () {
    tearDown(() {
      FCMNotificationService.onBackgroundMessageRegisterOverride = null;
      FCMNotificationService.forceFirebaseInitializedForTesting = false;
    });

    test('UI isolate (registerBackgroundHandler=true) registers handler exactly once', () async {
      int callCount = 0;
      FCMNotificationService.onBackgroundMessageRegisterOverride = (handler) async {
        callCount++;
      };
      FCMNotificationService.forceFirebaseInitializedForTesting = true;
      try {
        await FCMNotificationService.initialize(
          storageDirectoryPath: '/tmp/test_dev4c',
          requestPermission: false,
          registerBackgroundHandler: true,
        );
      } finally {
        FCMNotificationService.forceFirebaseInitializedForTesting = false;
      }
      expect(callCount, equals(1),
          reason: 'onBackgroundMessage must be called exactly once in UI isolate');
    });

    test('service isolate (registerBackgroundHandler=false) never registers handler', () async {
      int callCount = 0;
      FCMNotificationService.onBackgroundMessageRegisterOverride = (handler) async {
        callCount++;
      };
      FCMNotificationService.forceFirebaseInitializedForTesting = true;
      try {
        await FCMNotificationService.initialize(
          storageDirectoryPath: '/tmp/test_dev4c',
          requestPermission: false,
          registerBackgroundHandler: false,
        );
      } finally {
        FCMNotificationService.forceFirebaseInitializedForTesting = false;
      }
      expect(callCount, equals(0),
          reason: 'onBackgroundMessage must NOT be called in service isolate');
    });
  });
}