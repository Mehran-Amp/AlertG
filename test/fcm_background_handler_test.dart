import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/core/services/fcm_notification_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DEV-4b: onBackgroundMessage registration', () {
    test('UI isolate (registerBackgroundHandler=true) registers handler', () async {
      expect(
        () => FCMNotificationService.initialize(
          storageDirectoryPath: '/tmp/test',
          requestPermission: false,
          registerBackgroundHandler: true,
        ),
        returnsNormally,
      );
    });

    test('service isolate (registerBackgroundHandler=false) does not crash', () async {
      expect(
        () => FCMNotificationService.initialize(
          storageDirectoryPath: '/tmp/test',
          requestPermission: false,
          registerBackgroundHandler: false,
        ),
        returnsNormally,
      );
    });
  });
}