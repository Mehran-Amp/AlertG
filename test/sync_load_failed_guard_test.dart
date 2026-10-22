import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/core/services/server_alert_service.dart';
import 'package:http/http.dart' as http;

/// Simple counting HTTP client that records how many requests were made and
/// returns a canned response.
class _CountingClient extends http.BaseClient {
  int requestCount = 0;
  http.Response Function(http.BaseRequest) responder;

  _CountingClient(this.responder);

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requestCount++;
    final response = responder(request);
    return http.StreamedResponse(
      Stream.value(response.bodyBytes),
      response.statusCode,
      headers: response.headers,
    );
  }
}
void main() {
  group('ServerAlertService sync loadFailed guard', () {
    tearDown(() {
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');
      ServerAlertService.httpClientForTesting = null;
    });

    test('when loadFailed provider returns true, zero HTTP requests are made', () async {
      ServerAlertService.registerLoadFailedProvider(() => true);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');
      final client = _CountingClient((_) => http.Response('{}', 200));
      ServerAlertService.httpClientForTesting = client;

      final ok = await ServerAlertService.syncAllRulesToServer(const []);

      expect(ok, isFalse);
      expect(client.requestCount, 0);
    });

    test('when loadFailed provider returns false, exactly one HTTP request is made', () async {
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');
      final client = _CountingClient((_) => http.Response('{}', 200));
      ServerAlertService.httpClientForTesting = client;

      final ok = await ServerAlertService.syncAllRulesToServer(const []);

      expect(ok, isTrue);
      expect(client.requestCount, 1);
    });
  });
}