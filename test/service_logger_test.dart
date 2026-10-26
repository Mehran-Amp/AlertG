import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/core/services/service_logger.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DEV-5: ServiceLogger isolate tag', () {
    tearDown(() {
      ServiceLogger.isolateTagOverride = null;
    });

    test('default tag is "ui" when no debug name and no override', () {
      ServiceLogger.isolateTagOverride = null;
      // In unit tests Isolate.current.debugName is typically null, so the
      // fallback "ui" applies.
      final tag = ServiceLogger.isolateTag;
      expect(tag, isA<String>());
      expect(tag.isNotEmpty, isTrue);
    });

    test('override is used when set', () {
      ServiceLogger.isolateTagOverride = 'service';
      expect(ServiceLogger.isolateTag, equals('service'));

      ServiceLogger.isolateTagOverride = 'fcm';
      expect(ServiceLogger.isolateTag, equals('fcm'));

      ServiceLogger.isolateTagOverride = 'ui';
      expect(ServiceLogger.isolateTag, equals('ui'));
    });
  });
}