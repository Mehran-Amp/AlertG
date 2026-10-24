import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:permission_handler/permission_handler.dart';

import 'fcm_notification_service.dart';
import 'server_alert_service.dart';
import 'service_logger.dart';

/// Periodic device health indicators reporter (Phase 3A-2).
/// Runs from the service isolate and reports notification, battery,
/// and foreground service state to the server every 15 minutes.
class DeviceHealthService {
  @visibleForTesting
  static Future<bool> Function(Map<String, dynamic> payload)? postOverride;

  static const String appVersion = '3.6.1';

  /// Sends a single heartbeat with current device indicators.
  /// If an indicator cannot be determined, it sends null (do not guess).
  static Future<bool> sendHeartbeat({String? userId}) async {
    try {
      final uid = (userId ?? '').trim();
      if (uid.isEmpty) {
        return false;
      }

      String? fcmTail;
      try {
        final token = FCMNotificationService.fcmToken;
        if (token != null && token.trim().isNotEmpty) {
          final trimmed = token.trim();
          fcmTail = trimmed.length > 6 ? trimmed.substring(trimmed.length - 6) : trimmed;
        }
      } catch (e, st) {
        await ServiceLogger.logError('health.fcmTail', e, st);
      }

      bool? notificationsEnabled;
      try {
        if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
          notificationsEnabled = await Permission.notification.status.isGranted;
        }
      } catch (e, st) {
        await ServiceLogger.logError('health.notificationsPermission', e, st);
      }

      bool? batteryUnrestricted;
      try {
        if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
          batteryUnrestricted = await Permission.ignoreBatteryOptimizations.status.isGranted;
        }
      } catch (e, st) {
        await ServiceLogger.logError('health.batteryPermission', e, st);
      }

      bool? fgsRunning;
      try {
        if (!kIsWeb) {
          fgsRunning = await FlutterBackgroundService().isRunning();
        }
      } catch (e, st) {
        await ServiceLogger.logError('health.fgsRunning', e, st);
      }

      final payload = <String, dynamic>{
        'user_id': uid,
        'fcm_token_tail': fcmTail,
        'app_version': appVersion,
        'notifications_enabled': notificationsEnabled,
        'battery_unrestricted': batteryUnrestricted,
        'fgs_running': fgsRunning,
        'ts_ms': DateTime.now().millisecondsSinceEpoch,
      };

      final override = postOverride;
      if (override != null) {
        return await override(payload);
      }

      final res = await ServerAlertService.post('/api/device/heartbeat', body: payload);
      final ok = res.statusCode == 200;
      if (ok) {
        await ServiceLogger.log('health', 'heartbeat OK');
      } else {
        await ServiceLogger.log('health', 'heartbeat returned ${res.statusCode}');
      }
      return ok;
    } catch (e, st) {
      await ServiceLogger.logError('health.sendHeartbeat', e, st);
      return false;
    }
  }
}
