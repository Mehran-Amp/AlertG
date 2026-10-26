import 'dart:async';
import 'dart:io';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

import '../../features/notifications/services/notification_service.dart';
import '../../features/notifications/background/background_service_manager.dart';
import '../../features/notifications/models/alert_dispatch_result.dart';
import 'delivery_ack_service.dart';
import 'service_logger.dart';
import 'tts_service.dart';

/// Stable Android notification id derived from the server alert id, so a
/// repeated push for the same rule REPLACES its banner instead of stacking.
/// Never collides with the foreground-service notification (777).
// ignore: unused_element
int _notificationIdFor(RemoteMessage m, String alertId) {
  final seed = alertId.isNotEmpty ? alertId : (m.messageId ?? m.hashCode.toString());
  final id = seed.hashCode & 0x7FFFFFFF;
  return id == 777 ? 778 : id;
}

/// Shared central alert handling pipeline for both FCM push and WebSocket alerts.
/// Enforces cross-channel deduplication via [delivery_id] (Phase 4B-2).
Future<void> handleAlertDataMap(
    Map<String, dynamic> d, {
      String? title,
      String? body,
      required bool inApp,
      String source = 'fcm',
    }) async {
  final symbol = (d['symbol'] as String?) ?? '';
  final priceStr = (d['price'] as String?) ?? '';
  final alertId = (d['alert_id'] as String?) ?? '';
  final effectiveTitle = title ?? (d['title'] as String?) ?? '';
  final effectiveBody = body ?? (d['body'] as String?) ?? '';
  final note = (d['note'] as String?) ?? '';
  final deliveryId = ((d['delivery_id'] as String?) ?? '').trim();

  await ServiceLogger.log(
    'alert.handle',
    'enter source=$source inApp=$inApp alert_id=$alertId delivery_id=$deliveryId symbol=$symbol tts_enabled=${d['tts_enabled']} sound_enabled=${d['sound_enabled']} vibration_enabled=${d['vibration_enabled']}',
  );

  // Reject ghost / empty pushes without real alert data.
  if (effectiveTitle.isEmpty && symbol.isEmpty && alertId.isEmpty) {
    debugPrint('ℹ️ [$source] Suppressed ghost alert without payload.');
    await ServiceLogger.log('alert.handle', 'suppressed ghost alert (no title/symbol/alert_id)');
    return;
  }

  // DEV-2: only update the FGS notification text when running in the UI
  // isolate (inApp=true). In the FCM background isolate `inApp` is false and
  // `FlutterBackgroundService()` is unavailable, so the call is skipped and
  // the FGS notification text is left as-is.
  if (inApp) {
    BackgroundServiceManager.updatePriceSource(isFromServer: true);
  }

  final double? parsedPrice = double.tryParse(priceStr);
  final String speechText;
  if (symbol.isNotEmpty && parsedPrice != null && parsedPrice > 0) {
    speechText = TtsService.buildAlertSpeech(
      symbol: symbol,
      price: parsedPrice,
      customNote: note.isNotEmpty ? note : null,
    );
  } else {
    speechText = effectiveBody.isNotEmpty
        ? effectiveBody
        : (effectiveTitle.isNotEmpty ? effectiveTitle : 'هشدار قیمت دریافتی از سرور');
  }

  final ns = NotificationService();
  final dispatch = await ns.enqueueCriticalAlert(
    // Use alert_id (stable per rule) for the notification id so repeated
    // pushes for the same alert REPLACE the banner instead of stacking.
    // delivery_id changes on every resend; using it would stack banners.
    id: alertId.isNotEmpty
        ? alertId.hashCode.abs()
        : (deliveryId.isNotEmpty ? deliveryId.hashCode.abs() : 7777),
    title: effectiveTitle.isNotEmpty ? effectiveTitle : '🚨 Price Alert',
    body: effectiveBody,
    payload: alertId.isNotEmpty ? alertId : null,
    dedupeKey: deliveryId.isNotEmpty ? deliveryId : null,
    soundName: d['sound'] as String?,
    soundEnabled: d['sound_enabled'] != 'false',
    vibrationEnabled: d['vibration_enabled'] != 'false',
    ttsEnabled: d['tts_enabled'] != 'false',
    speechText: speechText,
    inAppFeedback: inApp,
    waitForSpeech: !inApp, // keep the background isolate alive while speaking
  );

  await ServiceLogger.log(
    'alert.handle',
    'enqueueCriticalAlert done source=$source alert_id=$alertId delivery_id=$deliveryId result=$dispatch speechText="${speechText.length > 60 ? '${speechText.substring(0, 60)}...' : speechText}"',
  );

  // Phase 2 / 4: ack the server only after the banner is really shown (or a
  // duplicate confirms it was already shown by another channel/isolate).
  if ((dispatch == AlertDispatchResult.shown || dispatch == AlertDispatchResult.duplicate) &&
      deliveryId.isNotEmpty) {
    try {
      await DeliveryAckService.enqueueAck(deliveryId);
      await DeliveryAckService.flush()
          .timeout(const Duration(seconds: 5), onTimeout: () {});
      await ServiceLogger.log('alert.ack', 'acked delivery_id=$deliveryId source=$source');
    } catch (e, st) {
      await ServiceLogger.logError('alert.ack', e, st);
    }
  }
}

/// Shared by the background handler and the foreground listener.
/// [inApp] = true when the UI/service isolate is alive (extra sound/haptics ok).
Future<void> _handleIncomingAlert(RemoteMessage message, {required bool inApp}) async {
  await handleAlertDataMap(
    message.data,
    title: message.notification?.title,
    body: message.notification?.body,
    inApp: inApp,
    source: 'fcm',
  );
}

/// Top-level FCM background handler (runs in its own short-lived isolate).
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  debugPrint('⚡ [FCM Background] ${message.messageId}');
  await ServiceLogger.log('fcm.bg', 'handler entered messageId=${message.messageId}');
  try {
    await Firebase.initializeApp();
    await ServiceLogger.log('fcm.bg', 'Firebase.initializeApp OK');
  } catch (e) {
    await ServiceLogger.log('fcm.bg', 'Firebase.initializeApp note: $e');
  }
  try {
    // Plugin + channels only. NO permissions, NO persistent notification 777.
    await NotificationService().initializeLight();
    await ServiceLogger.log('fcm.bg', 'initializeLight OK');
    await _handleIncomingAlert(message, inApp: false);
  } catch (e, st) {
    debugPrint('⚠️ [FCM Background] handler error: $e');
    await ServiceLogger.logError('fcm.bg.handler', e, st);
  }
}

/// FCMNotificationService handles Firebase Cloud Messaging & device token.
class FCMNotificationService {
  static String? _cachedToken;
  static String? _storageDir;
  static bool _firebaseInitialized = false;
  static bool _handlersRegistered = false;
  static Timer? _retryTimer;
  static int _retryAttempts = 0;

  /// Returns true if the token is a genuine Google FCM token
  static bool isRealFCMToken(String? token) {
    if (token == null || token.trim().isEmpty) return false;
    final clean = token.trim();
    if (clean.startsWith('dev_') || clean.startsWith('device_token_')) return false;
    return clean.length >= 40;
  }

  /// Whether a verified Google FCM push token is actively available
  static bool get isRealFCMActive => isRealFCMToken(_cachedToken);

  /// Current cached token value (FCM or fallback)
  static String? get currentToken => _cachedToken;
  static String? get fcmToken => _cachedToken;

  /// Called whenever Google rotates or discovers a new token. Wire this to your alert sync so
  /// the server never keeps pushing to a dead token.
  static void Function(String token)? onTokenChanged;

  /// [requestPermission] must be false in the foreground-service isolate
  /// (no Activity there, and onBackgroundMessage cannot be called on background isolates).
  static Future<void> initialize({
    String? storageDirectoryPath,
    bool requestPermission = true,
    bool registerBackgroundHandler = true,
  }) async {
    _storageDir = storageDirectoryPath;
    if (_storageDir == null) {
      try {
        _storageDir = (await getApplicationDocumentsDirectory()).path;
      } catch (e, st) {
        await ServiceLogger.logError('fcm.initStorageDir', e, st);
      }
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

      try {
        await fcm.setAutoInitEnabled(true);
      } catch (e, st) {
        await ServiceLogger.logError('fcm.setAutoInitEnabled', e, st);
      }

      // 1. Listeners FIRST:
      // Note: onBackgroundMessage can ONLY be called on root isolate with an Activity!
      // DEV-4b: onBackgroundMessage must be registered in the UI isolate
      // (where it is allowed) even when requestPermission is false. Only the
      // service isolate (which runs without an Activity) must not register it.
      if (registerBackgroundHandler) {
        try {
          FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
        } catch (e) {
          debugPrint('⚠️ FCM onBackgroundMessage registration note: $e');
        }
      }

      try {
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
          _stopBackgroundTokenRetry();
          onTokenChanged?.call(t);
          debugPrint('🔄 FCM token refreshed / discovered: ...${t.length > 6 ? t.substring(t.length - 6) : t}');
        });
      } catch (e) {
        debugPrint('⚠️ FCM listener registration error: $e');
      }

      // 2. Permission (UI isolate only)
      if (requestPermission) {
        try {
          await fcm.requestPermission(alert: true, badge: true, sound: true);
        } catch (e) {
          debugPrint('⚠️ FCM requestPermission error: $e');
        }
      }

      // 3. Token
      try {
        final token = await fcm.getToken().timeout(const Duration(seconds: 8));
        if (token != null && token.isNotEmpty) {
          _cachedToken = token;
          await _saveTokenToDisk(token);
          _stopBackgroundTokenRetry();
          onTokenChanged?.call(token);
          debugPrint('✅ FCM Token successfully resolved: ...${token.length > 6 ? token.substring(token.length - 6) : token}');
          return;
        }
      } catch (e) {
        debugPrint('⚠️ Initial FCM token fetch failed, starting background retry: $e');
      }
    }

    // Fallback: cached token from disk or persistent device id
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

    // If still on a fallback ID, keep retrying in the background until Google services respond!
    if (!isRealFCMToken(_cachedToken) && _firebaseInitialized) {
      _startBackgroundTokenRetry();
    }
  }

  /// Active retry loop to fetch real FCM token when Google Play Services reconnects
  static void _startBackgroundTokenRetry() {
    if (_retryTimer != null && _retryTimer!.isActive) return;
    _retryAttempts = 0;
    _retryTimer = Timer.periodic(const Duration(seconds: 12), (timer) async {
      _retryAttempts++;
      if (_retryAttempts > 25) {
        timer.cancel();
        return;
      }
      try {
        if (_firebaseInitialized) {
          final token = await FirebaseMessaging.instance
              .getToken()
              .timeout(const Duration(seconds: 6));
          if (token != null && token.isNotEmpty && isRealFCMToken(token)) {
            _cachedToken = token;
            await _saveTokenToDisk(token);
            timer.cancel();
            onTokenChanged?.call(token);
            debugPrint('🎯 [FCM Retry] Real token obtained after retry #$_retryAttempts: ...${token.substring(token.length - 6)}');
          }
        }
      } catch (e, st) {
        await ServiceLogger.logError('fcm.retryToken', e, st);
      }
    });
  }

  static void _stopBackgroundTokenRetry() {
    _retryTimer?.cancel();
    _retryTimer = null;
  }

  static Future<void> _saveTokenToDisk(String token) async {
    try {
      if (_storageDir != null) {
        await File('$_storageDir/device_token.txt').writeAsString(token, flush: true);
      }
    } catch (e, st) {
      await ServiceLogger.logError('fcm.saveTokenToDisk', e, st);
    }
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
    } catch (e, st) {
      await ServiceLogger.logError('fcm.loadTokenFromDisk', e, st);
    }
    return null;
  }

  /// Set or update real device FCM token manually.
  static Future<void> setCustomToken(String token) async {
    if (token.isNotEmpty) {
      _cachedToken = token.trim();
      await _saveTokenToDisk(_cachedToken!);
      if (isRealFCMToken(_cachedToken)) {
        _stopBackgroundTokenRetry();
        onTokenChanged?.call(_cachedToken!);
      }
    }
  }

  /// Current token (upgrades from `dev_` fallback to the real Google token).
  static Future<String> getFCMToken() async {
    if (isRealFCMToken(_cachedToken)) {
      return _cachedToken!;
    }
    try {
      if (_firebaseInitialized) {
        final token = await FirebaseMessaging.instance
            .getToken()
            .timeout(const Duration(seconds: 4));
        if (token != null && token.isNotEmpty && isRealFCMToken(token)) {
          _cachedToken = token;
          await _saveTokenToDisk(token);
          _stopBackgroundTokenRetry();
          onTokenChanged?.call(token);
          return token;
        }
      }
    } catch (e, st) {
      await ServiceLogger.logError('fcm.getFCMToken', e, st);
    }

    if (_cachedToken != null && _cachedToken!.isNotEmpty) return _cachedToken!;

    await initialize();
    return _cachedToken ?? 'dev_${DateTime.now().millisecondsSinceEpoch}';
  }
}