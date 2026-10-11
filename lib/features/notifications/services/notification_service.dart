import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:path_provider/path_provider.dart';
import '../../../core/services/tts_service.dart';
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
  static Directory? _dir;

  static Future<Directory> _lockDir() async {
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

  /// true = this caller owns the alert and must show it.
  static Future<bool> claim(String key) async {
    try {
      final d = await _lockDir();
      final f = File('${d.path}/${_safe(key)}.lock');
      if (f.existsSync()) {
        if (DateTime.now().difference(f.lastModifiedSync()) < window) {
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
      final cutoff = DateTime.now().subtract(const Duration(minutes: 10));
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
class NotificationService {
  // Singleton: one queue / one plugin per isolate.
  static final NotificationService _instance = NotificationService._internal();
  factory NotificationService() => _instance;
  NotificationService._internal();

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  // Kept for old callers; points at a channel that really exists.
  static const String channelId = 'alarmer_channel_sound_vibrate_v3';
  static const String channelName = 'Price Alerts (Sound & Vibration)';
  static const String channelDescription =
      'High-priority urgent alerts when crypto or market price targets and percentage changes occur.';

  // Channel ids (must match AndroidManifest default_notification_channel_id).
  static const String chSoundVibrate = 'alarmer_channel_sound_vibrate_v3';
  static const String chSoundOnly = 'alarmer_channel_sound_only_v3';
  static const String chVibrateOnly = 'alarmer_channel_vibrate_only_v3';
  static const String chSilentVoice = 'alarmer_channel_silent_voice_v3';

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
    const channels = <AndroidNotificationChannel>[
      AndroidNotificationChannel(
        chSoundVibrate,
        'Price Alerts (Sound & Vibration)',
        description: 'High-priority price alerts with audible ringtone and vibration.',
        importance: Importance.max,
        playSound: true,
        enableVibration: true,
        showBadge: true,
        enableLights: true,
        ledColor: Color.fromARGB(255, 255, 0, 0),
        audioAttributesUsage: AudioAttributesUsage.alarm,
      ),
      AndroidNotificationChannel(
        chSoundOnly,
        'Price Alerts (Sound Only)',
        description: 'High-priority price alerts with audible chime and zero vibration.',
        importance: Importance.max,
        playSound: true,
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
    _speechChain = _speechChain.then((_) async {
      try {
        await TtsService.instance.speak(text: text);
        final words = text.split(RegExp(r'\s+')).length;
        final ms = (words * 280 + 2000).clamp(2800, 15000);
        await Future.delayed(Duration(milliseconds: ms));
      } catch (e) {
        debugPrint('⚠️ [NotificationService] TTS failed: $e');
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
  Future<void> enqueueCriticalAlert({
    required int id,
    required String title,
    required String body,
    String? payload,
    String? soundName,
    double volume = 1.0,
    bool soundEnabled = true,
    bool vibrationEnabled = true,
    bool ttsEnabled = false,
    String? speechText,
    bool inAppFeedback = true,
    bool waitForSpeech = false,
    Duration maxWait = const Duration(seconds: 12),
  }) async {
    final dedupeKey = payload ?? '$id:$title';
    if (!await AlertDedup.claim(dedupeKey)) {
      debugPrint('🔇 [NotificationService] duplicate suppressed: $dedupeKey');
      return;
    }

    final master = await loadMasterSettingsFromDisk();
    final effSound = (master['soundEnabled'] as bool? ?? true) && soundEnabled;
    final effVibration =
        (master['vibrationEnabled'] as bool? ?? true) && vibrationEnabled;
    final effTts = (master['ttsEnabled'] as bool? ?? true) && ttsEnabled;
    final vol = (master['alarmVolume'] as num?)?.toDouble() ?? volume;
    final sound = soundName ?? master['soundName'] as String? ?? 'alarm_siren';

    try {
      // 1. Banner FIRST.
      await showCriticalAlert(
        id: id,
        title: title,
        body: body,
        payload: payload,
        soundName: sound,
        volume: vol,
        soundEnabled: effSound,
        vibrationEnabled: effVibration,
        inAppFeedback: inAppFeedback,
        master: master,
      );
    } catch (e) {
      debugPrint('❌ [NotificationService] banner failed: $e');
      await AlertDedup.release(dedupeKey); // let a retry/redelivery through
      return;
    }

    // 2. Voice (serialized, capped).
    if (effTts && speechText != null && speechText.trim().isNotEmpty) {
      final f = _enqueueSpeech(speechText);
      if (waitForSpeech) {
        await f.timeout(maxWait, onTimeout: () {});
      }
    }
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
    bool inAppFeedback = true,
    Map<String, dynamic>? master,
  }) async {
    final m = master ?? await loadMasterSettingsFromDisk();
    final effSound = (m['soundEnabled'] as bool? ?? true) && soundEnabled;
    final effVibration =
        (m['vibrationEnabled'] as bool? ?? true) && vibrationEnabled;

    final String channelId;
    final String channelName;
    if (effSound && effVibration) {
      channelId = chSoundVibrate;
      channelName = 'Price Alerts (Sound & Vibration)';
    } else if (effSound) {
      channelId = chSoundOnly;
      channelName = 'Price Alerts (Sound Only)';
    } else if (effVibration) {
      channelId = chVibrateOnly;
      channelName = 'Price Alerts (Vibration Only)';
    } else {
      channelId = chSilentVoice;
      channelName = 'Price Alerts (Silent & Voice Only)';
    }

    final androidDetails = AndroidNotificationDetails(
      channelId,
      channelName,
      channelDescription: channelDescription,
      importance: (effSound || effVibration) ? Importance.max : Importance.high,
      priority: Priority.max,
      ticker: '⚡ Price Alert Triggered',
      enableVibration: effVibration,
      vibrationPattern:
          effVibration ? Int64List.fromList([0, 500, 200, 500, 200, 500]) : null,
      playSound: effSound,
      category: AndroidNotificationCategory.alarm,
      audioAttributesUsage:
          effSound ? AudioAttributesUsage.alarm : AudioAttributesUsage.notification,
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

    // 2. Extra in-app feedback, never blocks and never runs in the FCM isolate.
    if (!inAppFeedback) return;
    if (effSound) {
      unawaited(() async {
        try {
          await SoundManager().playPreset(soundName, volume: volume);
        } catch (e) {
          debugPrint('⚠️ [NotificationService] playPreset failed: $e');
        }
      }());
    }
    if (effVibration) {
      unawaited(() async {
        try {
          await HapticFeedback.heavyImpact();
          await Future.delayed(const Duration(milliseconds: 150));
          await HapticFeedback.heavyImpact();
        } catch (_) {}
      }());
    }
  }
}
