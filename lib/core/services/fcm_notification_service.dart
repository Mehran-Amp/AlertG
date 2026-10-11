import 'dart:io';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

import '../../features/notifications/services/notification_service.dart';
import 'tts_service.dart';

/// Stable Android notification id derived from the server alert id, so a
/// repeated push for the same rule REPLACES its banner instead of stacking.
/// Never collides with the foreground-service notification (777).
int _notificationIdFor(RemoteMessage m, String alertId) {
  final seed = alertId.isNotEmpty ? alertId : (m.messageId ?? m.hashCode.toString());
  final id = seed.hashCode & 0x7FFFFFFF;
  return id == 777 ? 778 : id;
}

/// Shared by the background handler and the foreground listener.
/// [inApp] = true when the UI/service isolate is alive (extra sound/haptics ok).
Future<void> _handleIncomingAlert(RemoteMessage message, {required bool inApp}) async {
  final d = message.data;
  final symbol = d['symbol'] ?? '';
  final priceStr = d['price'] ?? '';
  final alertId = d['alert_id'] ?? '';
  final title = d['title'] ?? message.notification?.title ?? '';
  final body = d['body'] ?? message.notification?.body ?? '';
  final note = d['note'] ?? '';

  // Reject ghost / empty pushes without real alert data.
  if (title.isEmpty && symbol.isEmpty && alertId.isEmpty) {
    debugPrint('ℹ️ [FCM] Suppressed ghost push without alert payload.');
    return;
  }

  final speechText = TtsService.buildAlertSpeech(
    symbol: symbol.isNotEmpty ? symbol : 'Price Alert',
    price: double.tryParse(priceStr) ?? 0.0,
    customNote: note.isNotEmpty ? note : null,
  );

  final ns = NotificationService();
  // Banner first. Master toggles / volume / sound name are resolved once,
  // inside enqueueCriticalAlert, from settings.json.
  await ns.enqueueCriticalAlert(
    id: _notificationIdFor(message, alertId),
    title: title.isNotEmpty ? title : '🚨 Price Alert',
    body: body,
    payload: alertId.isNotEmpty ? alertId : null,
    soundName: d['sound'],
    soundEnabled: d['sound_enabled'] != 'false',
    vibrationEnabled: d['vibration_enabled'] != 'false',
    ttsEnabled: d['tts_enabled'] != 'false',
    speechText: speechText,
    inAppFeedback: inApp,
    waitForSpeech: !inApp, // keep the background isolate alive while speaking
  );
}

/// Top-level FCM background handler (runs in its own short-lived isolate).
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  debugPrint('⚡ [FCM Background] ${message.messageId}');
  try {
    await Firebase.initializeApp();
  } catch (_) {}
  try {
    // Plugin + channels only. NO permissions, NO persistent notification 777.
    await NotificationService().initializeLight();
    await _handleIncomingAlert(message, inApp: false);
  } catch (e) {
    debugPrint('⚠️ [FCM Background] handler error: $e');
  }
}

/// FCMNotificationService handles Firebase Cloud Messaging & device token.
class FCMNotificationService {
  static String? _cachedToken;
  static String? _storageDir;
  static bool _firebaseInitialized = false;
  static bool _handlersRegistered = false;

  /// Called whenever Google rotates the token. Wire this to your alert sync so
  /// the server never keeps pushing to a dead token.
  static void Function(String token)? onTokenChanged;

  /// [requestPermission] must be false in the foreground-service isolate
  /// (no Activity there).
  static Future<void> initialize({
    String? storageDirectoryPath,
    bool requestPermission = true,
  }) async {
    _storageDir = storageDirectoryPath;
    if (_storageDir == null) {
      try {
        _storageDir = (await getApplicationDocumentsDirectory()).path;
      } catch (_) {}
    }

    try {
      await Firebase.initializeApp();
      _firebaseInitialized = true;
    } catch (e) {
      // "already initialized" lands here too; treat as initialized.
      _firebaseInitialized = Firebase.apps.isNotEmpty;
      debugPrint('ℹ️ Firebase Core init note: $e');
    }

    if (_firebaseInitialized && !_handlersRegistered) {
      _handlersRegistered = true;
      final fcm = FirebaseMessaging.instance;

      // 1. Listeners FIRST: a pending permission dialog must never delay them.
      try {
        FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
        FirebaseMessaging.onMessage.listen((m) async {
          try {
            await _handleIncomingAlert(m, inApp: true);
          } catch (e) {
            debugPrint('⚠️ [FCM Foreground] handler error: $e');
          }
        });
        fcm.onTokenRefresh.listen((t) {
          _cachedToken = t;
          _saveTokenToDisk(t);
          onTokenChanged?.call(t);
          debugPrint('🔄 FCM token refreshed');
        });
      } catch (e) {
        debugPrint('⚠️ FCM listener registration error: $e');
      }

      // 2. Permission (UI isolate only), isolated from token retrieval.
      if (requestPermission) {
        try {
          await fcm.requestPermission(alert: true, badge: true, sound: true);
        } catch (e) {
          debugPrint('⚠️ FCM requestPermission error: $e');
        }
      }

      // 3. Token.
      try {
        final token = await fcm.getToken().timeout(const Duration(seconds: 10));
        if (token != null && token.isNotEmpty) {
          _cachedToken = token;
          await _saveTokenToDisk(token);
          return;
        }
      } catch (e) {
        debugPrint('⚠️ Error retrieving FCM token: $e');
      }
    }

    // Fallback: cached token or persistent device id.
    if (_cachedToken == null) {
      final saved = await _loadTokenFromDisk();
      if (saved != null && saved.isNotEmpty) {
        _cachedToken = saved;
      } else {
        final newId = 'dev_${const Uuid().v4().replaceAll('-', '').substring(0, 16)}';
        _cachedToken = newId;
        await _saveTokenToDisk(newId);
      }
    }
  }

  static Future<void> _saveTokenToDisk(String token) async {
    try {
      if (_storageDir != null) {
        await File('$_storageDir/device_token.txt').writeAsString(token, flush: true);
      }
    } catch (_) {}
  }

  static Future<String?> _loadTokenFromDisk() async {
    try {
      if (_storageDir != null) {
        final file = File('$_storageDir/device_token.txt');
        if (await file.exists()) {
          final content = (await file.readAsString()).trim();
          if (content.isNotEmpty) return content;
        }
      }
    } catch (_) {}
    return null;
  }

  /// Set or update real device FCM token manually.
  static Future<void> setCustomToken(String token) async {
    if (token.isNotEmpty) {
      _cachedToken = token.trim();
      await _saveTokenToDisk(_cachedToken!);
    }
  }

  /// Current token (upgrades from `dev_` fallback to the real Google token).
  static Future<String> getFCMToken() async {
    if (_cachedToken != null && _cachedToken!.isNotEmpty && !_cachedToken!.startsWith('dev_')) {
      return _cachedToken!;
    }
    try {
      if (_firebaseInitialized) {
        final token = await FirebaseMessaging.instance.getToken().timeout(const Duration(seconds: 4));
        if (token != null && token.isNotEmpty) {
          _cachedToken = token;
          await _saveTokenToDisk(token);
          return token;
        }
      }
    } catch (_) {}

    if (_cachedToken != null && _cachedToken!.isNotEmpty) return _cachedToken!;

    await initialize();
    return _cachedToken ?? 'dev_${DateTime.now().millisecondsSinceEpoch}';
  }
}
