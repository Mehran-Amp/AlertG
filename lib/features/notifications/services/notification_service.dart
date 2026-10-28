import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:path_provider/path_provider.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import '../models/alert_dispatch_result.dart';
import '../../../core/services/tts_service.dart';
import '../../../core/services/service_logger.dart';
import 'notification_service_interface.dart';
import '../../settings/services/sound_manager.dart';


/// Reads persisted master settings (settings.json). Shared by every isolate.
Future<Map<String, dynamic>> loadMasterSettingsFromDisk() async {
  try {
    final dir = await getApplicationDocumentsDirectory();
    final file = File('${dir.path}/settings.json');
    if (await file.exists()) {
      final content = await file.readAsString();
      if (content.trim().isNotEmpty) {
        return jsonDecode(content) as Map<String, dynamic>;
      }
    }
  } catch (e) {
    debugPrint('⚠️ [NotificationService] settings.json read failed: $e');
  }
  return {};
}

/// Cross-isolate de-duplication.
/// The main isolate, the foreground-service isolate and the FCM background
/// isolate cannot share memory, so the claim is an atomic exclusive file
/// create (`dedup/<key>.lock`). Only one isolate can win a given key per window.
class AlertDedup {
  static const Duration window = Duration(seconds: 20);
  static const Duration deliveryIdWindow = Duration(minutes: 10);
  @visibleForTesting
  static Directory? baseDirOverride;
  static Directory? _dir;

  static Future<Directory> _lockDir() async {
    if (baseDirOverride != null) {
      final d = Directory('${baseDirOverride!.path}/dedup');
      if (!d.existsSync()) d.createSync(recursive: true);
      return d;
    }
    if (_dir != null) return _dir!;
    final docs = await getApplicationDocumentsDirectory();
    final d = Directory('${docs.path}/dedup');
    if (!d.existsSync()) d.createSync(recursive: true);
    return _dir = d;
  }

  static String _safe(String key) {
    final s = key.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');
    return s.length > 80 ? s.substring(0, 80) : s;
  }

  static bool _isDeliveryId(String key) {
    final clean = key.trim();
    return RegExp(r'^[a-fA-F0-9]{32}$').hasMatch(clean) ||
        RegExp(r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$').hasMatch(clean);
  }

  @visibleForTesting
  static String safe(String key) => _safe(key);

  /// true = this caller owns the alert and must show it.
  static Future<bool> claim(String key, {Duration? window}) async {
    final effectiveWindow = window ?? (_isDeliveryId(key) ? deliveryIdWindow : AlertDedup.window);
    try {
      final d = await _lockDir();
      final f = File('${d.path}/${_safe(key)}.lock');
      if (f.existsSync()) {
        if (DateTime.now().difference(f.lastModifiedSync()) < effectiveWindow) {
          return false;
        }
        f.deleteSync(); // stale lock from an earlier trigger
      }
      f.createSync(exclusive: true); // atomic: throws if another isolate won
      _cleanupOld(d);
      return true;
    } on FileSystemException {
      return false; // lost the race to another isolate
    } catch (e) {
      debugPrint('⚠️ [AlertDedup] claim failed, allowing alert: $e');
      return true; // never lose an alert because dedup broke
    }
  }

  /// Give the claim back when the banner could not be shown.
  static Future<void> release(String key) async {
    try {
      final d = await _lockDir();
      final f = File('${d.path}/${_safe(key)}.lock');
      if (f.existsSync()) f.deleteSync();
    } catch (_) {}
  }

  static void _cleanupOld(Directory d) {
    try {
      final cutoff = DateTime.now().subtract(const Duration(minutes: 30));
      for (final e in d.listSync()) {
        if (e is File && e.lastModifiedSync().isBefore(cutoff)) e.deleteSync();
      }
    } catch (_) {}
  }
}

/// Dispatches mission-critical alerts.
/// Design rules:
///  * The banner (`show()`) is ALWAYS the first thing that happens.
///  * Every alert gets its own banner immediately (no queue in front of it).
///  * Only voice (TTS) is serialized, with a hard cap.
///  * In the FCM background isolate sound/haptics come from the OS channel only.
class NotificationService implements NotificationServiceInterface {
  // Singleton: one queue / one plugin per isolate.
  static final NotificationService _instance = NotificationService._internal();
  factory NotificationService() => _instance;
  NotificationService._internal();

  @visibleForTesting
  static Future<void> Function({
    required int id,
    required String title,
    required String body,
    String? payload,
  })? showBannerOverride;

  @visibleForTesting
  static bool? areNotificationsEnabledOverride;

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  // Kept for old callers; points at a channel that really exists.
  static const String channelId = 'alarmer_channel_sound_vibrate_v5';
  static const String channelName = 'Price Alerts (Sound & Vibration)';
  static const String channelDescription =
      'High-priority urgent alerts when crypto or market price targets and percentage changes occur.';

  // Channel ids (must match AndroidManifest default_notification_channel_id).
  static const String chSoundVibrate = 'alarmer_channel_sound_vibrate_v5';
  static const String chSoundOnly = 'alarmer_channel_sound_only_v5';
  static const String chVibrateOnly = 'alarmer_channel_vibrate_only_v5';
  static const String chSilentVoice = 'alarmer_channel_silent_voice_v5';

  /// Emits the payload (alert id) of a tapped notification.
  static final StreamController<String?> tapStream =
      StreamController<String?>.broadcast();

  bool _initialized = false;

  /// Plugin + channels only. Safe in ANY isolate (FCM background handler,
  /// foreground-service isolate). Never touches permissions or notification 777.
  Future<void> initializeLight() async {
    if (_initialized) return;
    const initSettings = InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
      iOS: DarwinInitializationSettings(
        requestAlertPermission: false,
        requestBadgePermission: false,
        requestSoundPermission: false,
        requestCriticalPermission: false,
      ),
    );
    await _plugin.initialize(
      initSettings,
      onDidReceiveNotificationResponse: (d) => tapStream.add(d.payload),
    );
    await _createChannels();
    _initialized = true;
  }

  /// Full init for the UI (main) isolate: light init + runtime permission.
  /// The persistent service notification (id 777) belongs to
  /// BackgroundServiceManager only and is no longer created here.
  Future<void> initialize() async {
    await initializeLight();
    await requestPermissions();
  }

  /// Payload of the notification that cold-started the app (null if none).
  Future<String?> getLaunchPayload() async {
    try {
      final d = await _plugin.getNotificationAppLaunchDetails();
      if (d?.didNotificationLaunchApp ?? false) {
        return d?.notificationResponse?.payload;
      }
    } catch (_) {}
    return null;
  }

  Future<void> _createChannels() async {
    const rawSound = RawResourceAndroidNotificationSound('alarm_siren');
    final channels = <AndroidNotificationChannel>[
      AndroidNotificationChannel(
        chSoundVibrate,
        'Price Alerts (Sound & Vibration)',
        description: 'High-priority price alerts with audible ringtone and vibration.',
        importance: Importance.max,
        playSound: true,
        sound: rawSound,
        enableVibration: true,
        vibrationPattern: Int64List.fromList([0, 500, 200, 500, 200, 500]),
        showBadge: true,
        enableLights: true,
        ledColor: const Color.fromARGB(255, 255, 0, 0),
        audioAttributesUsage: AudioAttributesUsage.alarm,
      ),
      AndroidNotificationChannel(
        chSoundOnly,
        'Price Alerts (Sound Only)',
        description: 'High-priority price alerts with audible chime and zero vibration.',
        importance: Importance.max,
        playSound: true,
        sound: rawSound,
        enableVibration: false,
        showBadge: true,
        enableLights: true,
        audioAttributesUsage: AudioAttributesUsage.alarm,
      ),
      AndroidNotificationChannel(
        chVibrateOnly,
        'Price Alerts (Vibration Only)',
        description: 'High-priority price alerts with vibration only.',
        importance: Importance.max,
        playSound: false,
        enableVibration: true,
        vibrationPattern: Int64List.fromList([0, 500, 200, 500, 200, 500]),
        showBadge: true,
        enableLights: true,
        audioAttributesUsage: AudioAttributesUsage.notification,
      ),
      AndroidNotificationChannel(
        chSilentVoice,
        'Price Alerts (Silent & Voice Only)',
        description: 'High-priority price alerts for voice announcements with zero vibration.',
        importance: Importance.high,
        playSound: false,
        enableVibration: false,
        showBadge: true,
        enableLights: false,
        audioAttributesUsage: AudioAttributesUsage.notification,
      ),
    ];
    final android = _plugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();

    // Delete legacy/cached channels so Android applies updated audio & vibration settings
    const oldChannelIds = [
      'alarmer_channel_sound_vibrate_v4',
      'alarmer_channel_sound_only_v4',
      'alarmer_channel_vibrate_only_v4',
      'alarmer_channel_silent_voice_v4',
      'alarmer_critical_price_alerts',
    ];
    for (final oldId in oldChannelIds) {
      try {
        await android?.deleteNotificationChannel(oldId);
      } catch (_) {}
    }

    for (final c in channels) {
      try {
        await android?.createNotificationChannel(c);
      } catch (e) {
        debugPrint('⚠️ [NotificationService] channel ${c.id} failed: $e');
      }
    }
  }

  /// Deprecated: the foreground-service notification is owned by
  /// flutter_background_service (id 777). Kept as a no-op for old callers.
  @Deprecated('Owned by BackgroundServiceManager')
  /// Cross-platform check: are notifications allowed at the OS level?
  /// Uses FirebaseMessaging because it returns a unified AuthorizationStatus
  /// on both Android (13+ POST_NOTIFICATIONS) and iOS (UNUserNotificationCenter).
  Future<bool> _areNotificationsEnabled() async {
    if (areNotificationsEnabledOverride != null) {
      return areNotificationsEnabledOverride!;
    }
    try {
      final settings = await FirebaseMessaging.instance.getNotificationSettings();
      switch (settings.authorizationStatus) {
        case AuthorizationStatus.authorized:
        case AuthorizationStatus.provisional:
          return true;
        case AuthorizationStatus.denied:
          return false;
        case AuthorizationStatus.notDetermined:
          return true;
      }
    } catch (e) {
      debugPrint('⚠️ [NotificationService] getNotificationSettings failed: $e');
      return true;
    }
  }

  Future<void> showPersistentServiceNotification() async {}

  /// Runtime notification permission (UI isolate only).
  Future<bool> requestPermissions() async {
    try {
      final android = _plugin
          .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
      final androidGranted = await android?.requestNotificationsPermission() ?? true;

      final ios = _plugin
          .resolvePlatformSpecificImplementation<IOSFlutterLocalNotificationsPlugin>();
      final iosGranted =
          await ios?.requestPermissions(alert: true, badge: true, sound: true) ?? true;
      return androidGranted && iosGranted;
    } catch (_) {
      return false;
    }
  }

  /// Cancels an active or scheduled notification by its integer ID
  Future<void> cancelNotification(int id) async {
    try {
      await _plugin.cancel(id);
    } catch (_) {}
  }

  FlutterLocalNotificationsPlugin get plugin => _plugin;

  // ---------------------------------------------------------------------------
  // Voice queue: only TTS is serialized. Capped so a burst cannot pile up.
  // ---------------------------------------------------------------------------
  static const int _maxPendingSpeech = 5;
  Future<void> _speechChain = Future.value();
  int _pendingSpeech = 0;

  Future<void> _enqueueSpeech(String text) {
    if (_pendingSpeech >= _maxPendingSpeech) {
      debugPrint('🔇 [NotificationService] speech queue full, skipping voice');
      return Future.value();
    }
    _pendingSpeech++;
    ServiceLogger.log('tts.start',
        'text="${text.length > 60 ? '${text.substring(0, 60)}...' : text}"').ignore();
    _speechChain = _speechChain.then((_) async {
      try {
        await TtsService.instance.speak(text: text);
        await ServiceLogger.log('tts.end', 'speak OK');
        final words = text.split(RegExp(r'\s+')).length;
        final ms = (words * 280 + 2000).clamp(2800, 15000);
        await Future.delayed(Duration(milliseconds: ms));
      } catch (e, st) {
        debugPrint('⚠️ [NotificationService] TTS failed: $e');
        await ServiceLogger.logError('tts.error', e, st);
      } finally {
        _pendingSpeech--;
      }
    });
    return _speechChain;
  }

  /// Shows the alert banner immediately, then sound/haptics/voice.
  /// Completes after the banner is shown (and, if [waitForSpeech], after voice,
  /// bounded by [maxWait] so a background isolate is never held hostage).
  ///
  /// [inAppFeedback]: false in the FCM background isolate (OS channel plays the
  /// sound; HapticFeedback/SoundManager have no Activity there).
  @override
  Future<AlertDispatchResult> enqueueCriticalAlert({
    required int id,
    required String title,
    required String body,
    String? payload,
    String? dedupeKey,
    String? soundName,
    double volume = 1.0,
    bool soundEnabled = true,
    bool vibrationEnabled = true,
    bool flashEnabled = false,
    bool ttsEnabled = false,
    String? speechText,
    bool inAppFeedback = true,
    bool waitForSpeech = false,
    Duration maxWait = const Duration(seconds: 12),
  }) async {
    final hasDedupeKey = dedupeKey != null && dedupeKey.trim().isNotEmpty;
    final List<String> claimedKeys = [];

    // 1. Cross-isolate dedup.
    // When dedupeKey (delivery_id) is provided:
    //  a) First claim dedupeKey with 10-minute window (deliveryIdWindow).
    //  b) Then if payload (alert_id) is non-empty, claim payload with 20-second window (window).
    //  c) If either claim fails, return duplicate (keeping earlier claims).
    // When dedupeKey is NOT provided (local scheduler):
    //  Claim payload ?? '$id:$title' with 20-second window.
    if (hasDedupeKey) {
      final dKey = dedupeKey.trim();
      if (!await AlertDedup.claim(dKey, window: AlertDedup.deliveryIdWindow)) {
        debugPrint('🔇 [NotificationService] duplicate delivery_id suppressed: $dKey');
        return AlertDispatchResult.duplicate;
      }
      claimedKeys.add(dKey);

      if (payload != null && payload.trim().isNotEmpty) {
        final pKey = payload.trim();
        if (!await AlertDedup.claim(pKey, window: AlertDedup.window)) {
          debugPrint('🔇 [NotificationService] duplicate alert_id suppressed: $pKey');
          // Keep the first claim (delivery_id) and return duplicate
          return AlertDispatchResult.duplicate;
        }
        claimedKeys.add(pKey);
      }
    } else {
      final localKey = (payload != null && payload.trim().isNotEmpty) ? payload.trim() : '$id:$title';
      if (!await AlertDedup.claim(localKey, window: AlertDedup.window)) {
        debugPrint('🔇 [NotificationService] duplicate local alert suppressed: $localKey');
        return AlertDispatchResult.duplicate;
      }
      claimedKeys.add(localKey);
    }

    Future<void> releaseAllClaims() async {
      for (final key in claimedKeys) {
        await AlertDedup.release(key);
      }
    }

    // 2. OS-level permission check. If notifications are disabled, do not
    //    pretend the banner was shown: release the dedup locks and report failure
    //    so the scheduler retries on the next interval.
    if (!await _areNotificationsEnabled()) {
      debugPrint('🔕 [NotificationService] notifications disabled at OS level; releasing dedup');
      await releaseAllClaims();
      return AlertDispatchResult.failed;
    }

    final master = await loadMasterSettingsFromDisk();
    final effSound = (master['soundEnabled'] as bool? ?? true) && soundEnabled;
    final effVibration =
        (master['vibrationEnabled'] as bool? ?? true) && vibrationEnabled;
    final effTts = (master['ttsEnabled'] as bool? ?? true) && ttsEnabled;
    final vol = (master['alarmVolume'] as num?)?.toDouble() ?? volume;
    final sound = soundName ?? master['soundName'] as String? ?? 'alarm_siren';

    try {
      // 3. Banner FIRST.
      if (showBannerOverride != null) {
        await showBannerOverride!(
          id: id,
          title: title,
          body: body,
          payload: payload,
        );
      } else {
        await showCriticalAlert(
          id: id,
          title: title,
          body: body,
          payload: payload,
          soundName: sound,
          volume: vol,
          soundEnabled: effSound,
          vibrationEnabled: effVibration,
          flashEnabled: flashEnabled,
          inAppFeedback: inAppFeedback,
          master: master,
        );
      }
    } catch (e) {
      debugPrint('❌ [NotificationService] banner failed: $e');
      await releaseAllClaims(); // let a retry/redelivery through
      return AlertDispatchResult.failed;
    }

    // 4. Voice (serialized, capped).
    if (effTts && speechText != null && speechText.trim().isNotEmpty) {
      final f = _enqueueSpeech(speechText);
      if (waitForSpeech) {
        await f.timeout(maxWait, onTimeout: () {});
      }
    }

    return AlertDispatchResult.shown;
  }

  /// Posts the banner. Sound/haptics beyond the OS channel are fire-and-forget
  /// and happen AFTER show().
  Future<void> showCriticalAlert({
    required int id,
    required String title,
    required String body,
    String? payload,
    String soundName = 'alarm_siren',
    double volume = 1.0,
    bool soundEnabled = true,
    bool vibrationEnabled = true,
    bool flashEnabled = false,
    bool inAppFeedback = true,
    Map<String, dynamic>? master,
  }) async {
    final m = master ?? await loadMasterSettingsFromDisk();
    final effSound = (m['soundEnabled'] as bool? ?? true) && soundEnabled;
    final effVibration =
        (m['vibrationEnabled'] as bool? ?? true) && vibrationEnabled;

    // 3C-2: always use the silent channel. playAlarm handles sound + vibration.
    final String channelId = chSilentVoice;
    final String channelName = 'Price Alerts (Silent & Voice Only)';

    final cleanSound = (soundName.isNotEmpty ? soundName : 'alarm_siren')
        .replaceAll('.wav', '')
        .replaceAll('.mp3', '')
        .toLowerCase()
        .trim();



    final androidDetails = AndroidNotificationDetails(
      channelId,
      channelName,
      channelDescription: channelDescription,
      importance: (effSound || effVibration) ? Importance.max : Importance.high,
      priority: Priority.max,
      ticker: '⚡ Price Alert Triggered',
      enableVibration: false,          // 3C-2: vibration played by playAlarm, not the OS channel
      vibrationPattern: null,          // 3C-2
      playSound: false,                // 3C-2: sound played by playAlarm
      sound: null,                     // 3C-2
      category: AndroidNotificationCategory.alarm,
      audioAttributesUsage: AudioAttributesUsage.notification,
      visibility: NotificationVisibility.public,
      showWhen: true,
      when: DateTime.now().millisecondsSinceEpoch,
      enableLights: true,
      ledColor: const Color.fromARGB(255, 255, 0, 0),
      ledOnMs: 1000,
      ledOffMs: 500,
      color: const Color(0xFF0284C7),
      colorized: true,
      styleInformation: BigTextStyleInformation(
        body,
        contentTitle: title,
        summaryText: 'SignalAlert',
      ),
    );

    const darwinDetails = DarwinNotificationDetails(
      presentAlert: true,
      presentBadge: true,
      presentSound: true,
      interruptionLevel: InterruptionLevel.timeSensitive,
    );

    final details =
        NotificationDetails(android: androidDetails, iOS: darwinDetails);

    // 1. Banner first, one retry on transient plugin failure.
    try {
      await _plugin.show(id, title, body, details, payload: payload);
    } catch (e) {
      debugPrint('⚠️ [NotificationService] show() failed, retrying: $e');
      await Future.delayed(const Duration(milliseconds: 300));
      await _plugin.show(id, title, body, details, payload: payload);
    }

    // 2. Audible alarm & physical vibration via native engine (works in both foreground & background)
    if (effSound || effVibration) {
      unawaited(() async {
        try {
          const mChannel = MethodChannel('com.example.bitcoin_checker/app_lifecycle');
          await mChannel.invokeMethod('playAlarm', {
            'sound': cleanSound,
            'vibrate': effVibration,
            'soundEnabled': effSound,
            'volume': volume,
          });
          await ServiceLogger.log('alarm.play', 'playAlarm OK sound=$cleanSound vibrate=$effVibration');

          // FLASH-1: SOS flash pattern (only if user enabled it for this alert)
          if (flashEnabled) {
            try {
              await mChannel.invokeMethod('startFlashSOS');
              await ServiceLogger.log('flash.start', 'startFlashSOS OK');
            } catch (e) {
              debugPrint('⚠️ [NotificationService] startFlashSOS note: $e');
            }
          }
                } catch (e, st) {
          debugPrint('⚠️ [NotificationService] native playAlarm note: $e');
          await ServiceLogger.logError('alarm.play.error', e, st);
          if (inAppFeedback && effVibration) {
            try {
              await HapticFeedback.heavyImpact();
            } catch (_) {}
          }
        }
      }());
    }
  }

  /// FLASH-1: stop the SOS flash pattern (call when notification is dismissed).
  static Future<void> stopFlash() async {
    try {
      const mChannel = MethodChannel('com.example.bitcoin_checker/app_lifecycle');
      await mChannel.invokeMethod('stopFlashSOS');
    } catch (e) {
      debugPrint('⚠️ [NotificationService] stopFlashSOS note: $e');
    }
  }
}