import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/core/services/delivery_ack_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DeliveryAckService', () {
    late Directory tmp;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('ack_test_');
      DeliveryAckService.baseDirOverride = tmp;
      DeliveryAckService.postOverride = null;
    });

    tearDown(() {
      try { tmp.deleteSync(recursive: true); } catch (_) {}
      DeliveryAckService.baseDirOverride = null;
      DeliveryAckService.postOverride = null;
    });

    test('enqueueAck writes one file per deliveryId', () async {
      await DeliveryAckService.enqueueAck('abc-123');
      final f = File('${tmp.path}/acks/abc-123.json');
      expect(f.existsSync(), isTrue);
      final parsed = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      expect(parsed['delivery_id'], 'abc-123');
      expect(parsed['shown'], isTrue);
    });

    test('flush removes file on successful POST', () async {
      var called = 0;
      DeliveryAckService.postOverride = (id) async { called++; return true; };
      await DeliveryAckService.enqueueAck('abc-1');
      await DeliveryAckService.enqueueAck('abc-2');
      await DeliveryAckService.flush();
      expect(called, 2);
      expect(File('${tmp.path}/acks/abc-1.json').existsSync(), isFalse);
      expect(File('${tmp.path}/acks/abc-2.json').existsSync(), isFalse);
    });

    test('flush keeps file on failed POST', () async {
      DeliveryAckService.postOverride = (id) async => false;
      await DeliveryAckService.enqueueAck('abc-3');
      await DeliveryAckService.flush();
      expect(File('${tmp.path}/acks/abc-3.json').existsSync(), isTrue);
    });

    test('flush is single-flight', () async {
      var concurrent = 0;
      var maxConcurrent = 0;
      DeliveryAckService.postOverride = (id) async {
        concurrent++;
        if (concurrent > maxConcurrent) maxConcurrent = concurrent;
        await Future.delayed(const Duration(milliseconds: 20));
        concurrent--;
        return true;
      };
      await DeliveryAckService.enqueueAck('abc-sf');
      final f1 = DeliveryAckService.flush();
      final f2 = DeliveryAckService.flush();
      await Future.wait([f1, f2]);
      expect(maxConcurrent, 1, reason: 'flush must be single-flight');
    });

    test('flush gracefully handles unexpected post exceptions', () async {
      DeliveryAckService.postOverride = (id) async => throw Exception('network down');
      await DeliveryAckService.enqueueAck('abc-err');
      expect(() async => await DeliveryAckService.flush(), returnsNormally);
      expect(File('${tmp.path}/acks/abc-err.json').existsSync(), isTrue);
    });
  });
}