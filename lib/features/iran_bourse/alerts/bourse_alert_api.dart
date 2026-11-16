import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../../core/services/fcm_notification_service.dart';
import '../../../core/services/server_alert_service.dart';
import '../../alert_engine/models/alert_rule.dart';
import '../services/iran_bourse_service.dart';
import 'bourse_alert_draft.dart';

/// Creates and removes Bourse alerts on the AlertG server, and says *why* when it refuses.
///
/// Why this exists: the app's normal "create alert" call ignores the server's answer. For the
/// Bourse the server can legitimately say no (not enabled, user not on the rollout list,
/// unknown instrument, no previous close), and the user must be told before the alert is
/// saved on the phone. Calls never throw.
class BourseAlertApi {
  final http.Client? _client;
  final String Function() _baseUrl;
  final String Function() _apiKey;
  final Future<String> Function() _userId;
  final Future<String> Function() _fcmToken;
  final Duration timeout;

  /// All parameters exist for tests; the defaults use the app's own server settings.
  BourseAlertApi({
    http.Client? client,
    String Function()? baseUrl,
    String Function()? apiKey,
    Future<String> Function()? userId,
    Future<String> Function()? fcmToken,
    this.timeout = const Duration(seconds: 30),
  })  : _client = client,
        _baseUrl = baseUrl ?? (() => ServerAlertService.effectiveBaseUrl),
        _apiKey = apiKey ?? (() => ServerAlertService.apiKey),
        _userId = userId ?? ServerAlertService.getEffectiveUserId,
        _fcmToken = fcmToken ?? FCMNotificationService.getFCMToken;

  /// Sends [rule] to the server. [rule] must be a Bourse rule (exchange `tsetmc`).
  /// Success carries `true`; creating the same rule id again just updates it on the server.
  Future<BourseResult<bool>> create(AlertRule rule) async {
    if (rule.exchangeId.toLowerCase() != bourseExchangeId) {
      return const BourseResult<bool>.fail(BourseFailure.badRequest, message: 'not a Bourse rule');
    }
    try {
      final userId = (await _userId()).trim();
      var token = '';
      try {
        token = (await _fcmToken()).trim();
      } catch (_) {
        token = ''; // a missing push token must not stop the alert; the server accepts a placeholder
      }
      final body = jsonEncode(_payload(rule, userId.isEmpty ? 'user_default' : userId, token));
      final response = await _post('/api/alerts', body);
      return _interpret(response);
    } on TimeoutException {
      return const BourseResult<bool>.fail(BourseFailure.network, message: 'timeout');
    } catch (e) {
      return BourseResult<bool>.fail(BourseFailure.network, message: '$e');
    }
  }

  /// Removes an alert by its rule id (used to undo [create] when saving on the phone failed).
  Future<BourseResult<bool>> remove(String ruleId) async {
    final id = ruleId.trim();
    if (id.isEmpty) {
      return const BourseResult<bool>.fail(BourseFailure.badRequest, message: 'empty rule id');
    }
    try {
      final uri = _uri('/api/alerts/${Uri.encodeComponent(id)}');
      final headers = _headers();
      final c = _client;
      final response = await (c != null ? c.delete(uri, headers: headers) : http.delete(uri, headers: headers))
          .timeout(timeout);
      return _interpret(response);
    } on TimeoutException {
      return const BourseResult<bool>.fail(BourseFailure.network, message: 'timeout');
    } catch (e) {
      return BourseResult<bool>.fail(BourseFailure.network, message: '$e');
    }
  }

  // ---- internals ------------------------------------------------------------------------

  Map<String, dynamic> _payload(AlertRule rule, String userId, String fcmToken) {
    final effectiveTarget = rule.targetPrice ?? rule.upperTargetPrice ?? rule.lowerTargetPrice ?? 0.0;
    final condition = rule.direction == AlertDirection.below
        ? 'BELOW'
        : (rule.direction == AlertDirection.bothSides ? 'BOTHSIDES' : 'ABOVE');
    final note = rule.customNote;
    return {
      'id': rule.uuid,
      'user_id': userId,
      'exchange': bourseExchangeId,
      'symbol': rule.marketSymbol, // the instrument id, always a String (rule N6)
      'target_price': effectiveTarget,
      'condition': condition,
      'condition_type': rule.conditionType.name,
      'direction': rule.direction.name,
      'both_way_behavior': rule.bothWayBehavior.name,
      if (rule.percent != null) 'percent': rule.percent,
      if (rule.deltaAbsolute != null) 'delta_absolute': rule.deltaAbsolute,
      if (rule.basePrice != null) 'base_price': rule.basePrice,
      'base_currency': rule.baseCurrency,
      'counter_currency': rule.counterCurrency,
      'market_symbol': rule.marketSymbol, // the server replaces this with the ticker
      'language': rule.language ?? 'fa',
      'prefer_server_proxy': rule.preferServerProxy,
      'raw_rule': rule.toJson(),
      'fcm_token': fcmToken.isNotEmpty ? fcmToken : 'device_token_pending',
      'check_interval_seconds': rule.checkIntervalSeconds,
      'trigger_mode': rule.triggerMode == TriggerMode.recurring ? 'recurring' : 'oneShot',
      'sound_enabled': rule.soundEnabled,
      'vibration_enabled': rule.vibrationEnabled,
      'flash_enabled': rule.flashEnabled,
      'tts_enabled': rule.ttsEnabled,
      'sound': rule.customSound ?? 'alarm_siren',
      if (note != null && note.isNotEmpty) 'note': note,
    };
  }

  Uri _uri(String path) {
    var base = _baseUrl().trim();
    while (base.endsWith('/')) {
      base = base.substring(0, base.length - 1);
    }
    return Uri.parse('$base$path');
  }

  Map<String, String> _headers() {
    final headers = <String, String>{'Content-Type': 'application/json', 'Accept': 'application/json'};
    final key = _apiKey();
    if (key.isNotEmpty) headers['X-API-Key'] = key;
    return headers;
  }

  Future<http.Response> _post(String path, String body) {
    final uri = _uri(path);
    final headers = _headers();
    final c = _client;
    return (c != null ? c.post(uri, headers: headers, body: body) : http.post(uri, headers: headers, body: body))
        .timeout(timeout);
  }

  BourseResult<bool> _interpret(http.Response response) {
    final status = response.statusCode;
    if (status == 200 || status == 201) return const BourseResult<bool>.ok(true);

    String? detail;
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map && decoded['detail'] is String) detail = decoded['detail'] as String;
    } catch (_) {
      detail = null;
    }
    final d = (detail ?? '').toLowerCase();

    final BourseFailure failure;
    if (status == 503) {
      failure = d.contains('not enabled') ? BourseFailure.disabled : BourseFailure.unavailable;
    } else if (status == 403) {
      failure = d.contains('not available for this user') ? BourseFailure.notAllowed : BourseFailure.unauthorized;
    } else if (status == 401) {
      failure = BourseFailure.unauthorized;
    } else if (status == 400) {
      if (d.contains('unknown bourse instrument')) {
        failure = BourseFailure.notFound;
      } else if (d.contains('no previous close')) {
        failure = BourseFailure.noPreviousClose;
      } else {
        failure = BourseFailure.rejected;
      }
    } else if (status == 422) {
      failure = BourseFailure.badRequest;
    } else if (status >= 500) {
      failure = BourseFailure.unavailable;
    } else {
      failure = BourseFailure.rejected;
    }
    return BourseResult<bool>.fail(failure, message: detail ?? 'http $status', httpStatus: status);
  }
}
