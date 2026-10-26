import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'fcm_notification_service.dart';
import 'server_alert_service.dart';
import 'service_logger.dart';

/// Phase 4B-1: WebSocket Client in Background Service Isolate.
/// Connects to /ws with backoff reconnection (2, 5, 15, 60 seconds),
/// handles ping/pong, receives real-time alerts, and routes through
/// the deduplicated alert handler with delivery ACK.
class WebSocketClientService {
  static const List<int> _reconnectBackoffSeconds = [2, 5, 15, 60];
  static int _backoffIndex = 0;
  static bool _running = false;
  static WebSocket? _socket;
  static Timer? _reconnectTimer;
  static String? _currentUserId;

  static bool get isConnected => _socket != null;
  static int get currentBackoffSeconds => _reconnectBackoffSeconds[_backoffIndex];
  static List<int> get reconnectBackoffSchedule => List.unmodifiable(_reconnectBackoffSeconds);
  static int get backoffIndex => _backoffIndex;
  static bool get isRunning => _running;
  static String? get currentUserId => _currentUserId;

  /// Optional hook for unit tests to capture outgoing frames (pong, ack).
  static void Function(String message)? onOutgoingMessageForTest;

  /// Reset state for test isolation.
  static void resetForTesting() {
    stop();
    _backoffIndex = 0;
    _currentUserId = null;
    onOutgoingMessageForTest = null;
  }

  /// Direct message handler invocation for unit testing.
  static void handleMessageForTesting(dynamic rawData) => _onMessage(rawData);

  /// Trigger backoff increment for unit testing.
  static void advanceBackoffForTesting() => _scheduleReconnect();

  /// Starts the persistent WebSocket client loop with backoff reconnection.
  static void start({required String userId}) {
    _currentUserId = userId.isNotEmpty ? userId : 'anonymous';
    if (_running) return;
    _running = true;
    _backoffIndex = 0;
    _connect();
  }

  /// Stops the client and cancels all active reconnection timers.
  static void stop() {
    _running = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    try {
      _socket?.close();
    } catch (e, st) {
      ServiceLogger.logError('ws.client.stopClose', e, st).ignore();
    }
    _socket = null;
    ServiceLogger.log('ws.client', 'WebSocket client stopped').ignore();
  }

  static Future<void> _connect() async {
    if (!_running) return;

    final baseUrl = ServerAlertService.baseUrl;
    final apiKey = ServerAlertService.apiKey;
    final userId = _currentUserId ?? 'anonymous';

    String wsUrl;
    try {
      final uri = Uri.parse(baseUrl);
      final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
      final portPart = uri.hasPort ? ':${uri.port}' : '';
      // Security: API key is sent only via X-API-Key header (below), never in
      // the query string, so it does not leak into access logs / proxies.
      wsUrl = '$scheme://${uri.host}$portPart/ws?user_id=${Uri.encodeComponent(userId)}';
    } catch (e) {
      wsUrl = 'wss://aisocialfeed.com/ws?user_id=${Uri.encodeComponent(userId)}';
    }

    await ServiceLogger.log(
      'ws.client',
      'connecting to $wsUrl (backoff step: $_backoffIndex, delay: ${_reconnectBackoffSeconds[_backoffIndex]}s)',
    );

    try {
      final socket = await WebSocket.connect(
        wsUrl,
        headers: apiKey.isNotEmpty ? {'X-API-Key': apiKey} : null,
      ).timeout(const Duration(seconds: 8));

      _socket = socket;
      _backoffIndex = 0; // Reset backoff on successful connection
      await ServiceLogger.log('ws.client', 'connected successfully to server WebSocket');

      socket.listen(
        (data) => _onMessage(data),
        onError: (e) async {
          await ServiceLogger.logError('ws.client.onError', e);
          _scheduleReconnect();
        },
        onDone: () async {
          await ServiceLogger.log('ws.client', 'socket closed by remote server');
          _scheduleReconnect();
        },
        cancelOnError: true,
      );
    } catch (e, st) {
      await ServiceLogger.logError('ws.client.connectFailed', e, st);
      _scheduleReconnect();
    }
  }

  static void _scheduleReconnect() {
    _socket = null;
    if (!_running) return;

    final delaySeconds = _reconnectBackoffSeconds[_backoffIndex];
    if (_backoffIndex < _reconnectBackoffSeconds.length - 1) {
      _backoffIndex++;
    }

    ServiceLogger.log(
      'ws.client',
      'reconnecting in ${delaySeconds}s (next backoff step: $_backoffIndex)',
    ).ignore();

    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(Duration(seconds: delaySeconds), () {
      _connect();
    });
  }

  static void _onMessage(dynamic rawData) {
    if (rawData == null) return;
    try {
      final text = rawData.toString();
      final decoded = jsonDecode(text);
      if (decoded is! Map<String, dynamic>) return;

      final type = (decoded['type'] as String?)?.toLowerCase();

      if (type == 'ping') {
        final pong = jsonEncode({'type': 'pong', 'ts': DateTime.now().millisecondsSinceEpoch});
        _socket?.add(pong);
        onOutgoingMessageForTest?.call(pong);
      } else if (type == 'alert') {
        final deliveryId = (decoded['delivery_id'] as String?) ?? '';
        final title = decoded['title'] as String?;
        final body = decoded['body'] as String?;
        final data = Map<String, dynamic>.from((decoded['data'] as Map?) ?? {});

        if (deliveryId.isNotEmpty && !data.containsKey('delivery_id')) {
          data['delivery_id'] = deliveryId;
        }

        // Send instant ACK back over the socket
        if (deliveryId.isNotEmpty) {
          final ack = jsonEncode({'action': 'ack', 'delivery_id': deliveryId});
          _socket?.add(ack);
          onOutgoingMessageForTest?.call(ack);
        }

        // Route through central deduplicated alert handler (Phase 4B-2)
        handleAlertDataMap(
          data,
          title: title,
          body: body,
          inApp: true,
          source: 'ws',
        ).ignore();
      }
    } catch (e, st) {
      ServiceLogger.logError('ws.client.onMessage', e, st).ignore();
    }
  }
}
