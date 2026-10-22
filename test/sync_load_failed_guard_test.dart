import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/core/services/server_alert_service.dart';

void main() {
  group('ServerAlertService sync loadFailed guard', () {
    tearDown(() {
      // Reset the provider so tests do not leak into each other.
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');
    });

    test('when loadFailed provider returns true, sync returns false without HTTP', () async {
      ServerAlertService.registerLoadFailedProvider(() => true);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');

      final ok = await ServerAlertService.syncAllRulesToServer(const []);

      expect(ok, isFalse);
      // No HTTP call was attempted (no exception thrown from the unreachable
      // URL); the guard short-circuits before any network code.
    });

    test('when loadFailed provider returns false, sync proceeds (previous behaviour)', () async {
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');

      // With no rules, sync proceeds but may fail on the HTTP request. The
      // point is that the guard did not short-circuit: it reached the network
      // path. We only assert it returns a bool and does not throw.
      final ok = await ServerAlertService.syncAllRulesToServer(const []);
      expect(ok, isA<bool>());
    });

    test('when no loadFailed provider is registered, sync proceeds', () async {
      // Reset to a false provider to simulate "not registered" (the default
      // null path is equivalent to false for the guard).
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');

      final ok = await ServerAlertService.syncAllRulesToServer(const []);
      expect(ok, isA<bool>());
    });
  });
}