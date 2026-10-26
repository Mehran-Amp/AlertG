import 'dart:async';
import 'dart:io';
import 'dart:ui';
import 'package:flutter/foundation.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:path_provider/path_provider.dart';

import '../../../core/services/delivery_ack_service.dart';
import '../../../core/services/device_health_service.dart';
import '../../../core/services/fcm_notification_service.dart';
import '../../../core/services/server_alert_service.dart';
import '../../../core/services/service_logger.dart';
import '../../../core/services/websocket_client_service.dart';
import '../../alert_engine/repositories/json_alert_rule_repository.dart';
import '../../alert_engine/scheduler/scheduler_service.dart';
import '../../exchanges/registry/exchange_catalog.dart';
import '../../exchanges/registry/exchange_registry.dart';
import '../../notifications/repositories/notification_repository.dart';
import '../../notifications/services/notification_service.dart';
import '../../settings/services/settings_service.dart';

/// Configures Android 14+ Foreground Service
/// using a persistent background task to keep market monitoring alive 24/7
/// even when the app UI is closed by the user.
@pragma('vm:entry-point')
class BackgroundServiceManager {
  static const String notificationChannelId = 'alarmer_foreground_service';
  static const int notificationId = 777;
  static bool _lastPriceFromServer = false;
  static ServiceInstance? _currentServiceInstance;

  /// Applies foreground persistent notification text with current price source (777).
  static void _applyNotificationInfo({required bool isFromServer, String lang = 'fa'}) {
    final service = _currentServiceInstance;
    if (service is AndroidServiceInstance) {
      final isFa = lang == 'fa' || lang == 'ar' || lang == 'ckb';
      final sourceText = isFromServer
          ? (isFa ? 'سرور ابری (FCM)' : 'Cloud Server (FCM)')
          : (isFa ? 'پایش محلی دستگاه' : 'Local Device Engine');
      final contentText = isFa
          ? 'سرویس پایش ۲۴/۷ بازار فعال است • منبع: $sourceText'
          : '24/7 Market Monitor Active • Source: $sourceText';
      try {
        service.setForegroundNotificationInfo(
          title: 'SignalAlert',
          content: contentText,
        );
        ServiceLogger.log(
          'bg.notification',
          'notification 777 text applied: isFromServer=$isFromServer, text="$contentText"',
        ).ignore();
      } catch (e, st) {
        ServiceLogger.logError('applyNotificationInfo', e, st).ignore();
      }
    }
  }

  /// Public helper to update foreground persistent notification text.
  static void setNotificationText(bool isFromServer, [String lang = 'fa']) {
    _applyNotificationInfo(isFromServer: isFromServer, lang: lang);
  }

  /// Updates foreground persistent notification text with current price source.
  static void updatePriceSource({required bool isFromServer, String? lang}) {
    _lastPriceFromServer = isFromServer;
    final effectiveLang = lang ?? 'fa';

    // 1. Direct application if running inside the background service isolate
    if (_currentServiceInstance != null) {
      _applyNotificationInfo(isFromServer: isFromServer, lang: effectiveLang);
      return;
    }

    // 2. Inter-isolate event dispatch if called from main UI isolate
    try {
      final service = FlutterBackgroundService();
      service.invoke('updatePriceSource', {
        'source': isFromServer ? 'fcm' : 'local',
        'lang': effectiveLang,
      });
      ServiceLogger.log(
        'bg.notification',
        'updatePriceSource dispatched from UI isolate: isServer=$isFromServer',
      ).ignore();
    } catch (e, st) {
      ServiceLogger.logError('updatePriceSource', e, st).ignore();
    }
  }

  static Future<void> initializeService() async {
    if (kIsWeb) return;

    try {
      final service = FlutterBackgroundService();

      const AndroidNotificationChannel channel = AndroidNotificationChannel(
        notificationChannelId,
        'Alarmer Service',
        description: 'Permanent background monitoring',
        importance: Importance.low,
        playSound: false,
        enableVibration: false,
        showBadge: false,
      );

      final FlutterLocalNotificationsPlugin flutterLocalNotificationsPlugin =
          FlutterLocalNotificationsPlugin();

      try {
        await flutterLocalNotificationsPlugin
            .resolvePlatformSpecificImplementation<
                AndroidFlutterLocalNotificationsPlugin>()
            ?.createNotificationChannel(channel);
      } catch (e, st) {
        await ServiceLogger.logError('initializeService.createChannel', e, st);
      }

      try {
        await service.configure(
          androidConfiguration: AndroidConfiguration(
            onStart: onBackgroundServiceStart,
            autoStart: true,
            autoStartOnBoot: true,
            isForegroundMode: true,
            notificationChannelId: notificationChannelId,
            initialNotificationTitle: 'SignalAlert',
            initialNotificationContent:
                'سرویس پایش ۲۴/۷ بازار فعال است • منبع: پایش محلی دستگاه',
            foregroundServiceNotificationId: notificationId,
          ),
          iosConfiguration: IosConfiguration(
            autoStart: true,
            onForeground: onBackgroundServiceStart,
            onBackground: onIosBackground,
          ),
        );
      } catch (e, st) {
        await ServiceLogger.logError('initializeService.configure', e, st);
        return;
      }

      try {
        final isRunning = await service.isRunning();
        if (!isRunning) {
          await service.startService();
          await ServiceLogger.log('initializeService', 'service.startService() called');
        }
      } catch (e, st) {
        await ServiceLogger.logError('initializeService.startService', e, st);
      }
    } catch (e, st) {
      await ServiceLogger.logError('initializeService.outer', e, st);
    }
  }

  @pragma('vm:entry-point')
  static Future<bool> onIosBackground(ServiceInstance service) async {
    DartPluginRegistrant.ensureInitialized();
    return true;
  }

  @pragma('vm:entry-point')
  static void onBackgroundServiceStart(ServiceInstance service) async {
    DartPluginRegistrant.ensureInitialized();
    _currentServiceInstance = service;
    final serviceStartTime = DateTime.now();
    // FIX-6b: no disk I/O before setAsForegroundService(). The lifecycle log
    // is written after startForeground succeeds, without await.

    if (service is AndroidServiceInstance) {
      service.on('setAsForeground').listen((event) {
        try {
          service.setAsForegroundService();
        } catch (e, st) {
          ServiceLogger.logError('setAsForeground', e, st).ignore();
        }
      });

      service.on('setAsBackground').listen((event) {
        try {
          service.setAsBackgroundService();
        } catch (e, st) {
          ServiceLogger.logError('setAsBackground', e, st).ignore();
        }
      });

      service.on('updatePriceSource').listen((event) {
        if (event != null) {
          final isServer = event['source'] == 'fcm';
          final lang = event['lang'] as String? ?? 'fa';
          _lastPriceFromServer = isServer;
          _applyNotificationInfo(isFromServer: isServer, lang: lang);
        }
      });

      try {
        service.setAsForegroundService();
        _applyNotificationInfo(isFromServer: false, lang: 'fa');
        // FIX-6b: log fgs.lifecycle (started + foreground OK) AFTER
        // startForeground succeeds, without await, so no disk I/O blocks
        // the Android FGS deadline.
        ServiceLogger.log(
          'fgs.lifecycle',
          'service started + setAsForegroundService OK '
              '(type: dataSync, started_at: ${serviceStartTime.toIso8601String()})',
        ).ignore();
      } catch (e, st) {
        ServiceLogger.log(
          'fgs.lifecycle',
          'setAsForegroundService() FAILED: $e',
        ).ignore();
        ServiceLogger.logError('onBackgroundServiceStart.foreground', e, st).ignore();
      }
      
    }

    // Each init step has its own try/catch and its own log line.
    // The scheduler MUST start even if FCM or ServerAlertService fail.
    final notificationService = NotificationService();
    try {
      await notificationService.initializeLight();
      await ServiceLogger.log('init', 'notificationService.initializeLight OK');
    } catch (e, st) {
      await ServiceLogger.logError('init.notificationService', e, st);
    }

    Directory? dir;
    try {
      dir = await getApplicationDocumentsDirectory();
      await ServiceLogger.log('init', 'documents dir: ${dir.path}');
    } catch (e, st) {
      await ServiceLogger.logError('init.documentsDir', e, st);
      return;
    }

    final alertRuleRepository = JsonAlertRuleRepository(dir.path);
    try {
      await alertRuleRepository.load();
      await ServiceLogger.log(
          'init', 'alertRuleRepository.load OK (${alertRuleRepository.allRules.length} rules)');
    } catch (e, st) {
      await ServiceLogger.logError('init.alertRuleRepository', e, st);
    }

    final notificationRepository = NotificationRepository(dir.path);
    try {
      await notificationRepository.load();
      await ServiceLogger.log('init', 'notificationRepository.load OK');
    } catch (e, st) {
      await ServiceLogger.logError('init.notificationRepository', e, st);
    }

    final settingsService = SettingsService(dir.path);
    try {
      await settingsService.load();
      await ServiceLogger.log('init', 'settingsService.load OK');
    } catch (e, st) {
      await ServiceLogger.logError('init.settingsService', e, st);
    }

    try {
      await ServerAlertService.initialize();
      await ServiceLogger.log('init', 'ServerAlertService.initialize OK');
    } catch (e, st) {
      await ServiceLogger.logError('init.serverAlertService', e, st);
    }

    try {
      FCMNotificationService.onTokenChanged = (newToken) {
        ServerAlertService.syncAllRulesToServer(
          alertRuleRepository.allRules,
          userId: settingsService.settings.userEmail,
        );
      };
    } catch (e, st) {
      await ServiceLogger.logError('init.fcmOnTokenChanged', e, st);
    }

    try {
      await FCMNotificationService.initialize(
        storageDirectoryPath: dir.path,
        requestPermission: false,
      );
      await ServiceLogger.log('init', 'FCMNotificationService.initialize OK');
    } catch (e, st) {
      await ServiceLogger.logError('init.fcmNotificationService', e, st);
    }

    // Scheduler: ALWAYS started, even if everything above failed.
    try {
      final exchangeRegistry = ExchangeRegistry();
      for (final ex in ExchangeCatalog.buildAllExchanges()) {
        exchangeRegistry.register(ex);
      }

      final schedulerService = SchedulerService(
        alertRuleRepository: alertRuleRepository,
        exchangeRegistry: exchangeRegistry,
        notificationService: notificationService,
        notificationRepository: notificationRepository,
        settingsService: settingsService,
      );

      schedulerService.start();
      await ServiceLogger.log('init', 'schedulerService.start() called');
    } catch (e, st) {
      await ServiceLogger.logError('init.schedulerService', e, st);
    }

    Timer.periodic(const Duration(seconds: 10), (timer) async {
      try {
        await alertRuleRepository.load();
        if (service is AndroidServiceInstance) {
          final hasActiveServer = ServerAlertService.isServerAvailable &&
              FCMNotificationService.isRealFCMActive;
          setNotificationText(
              _lastPriceFromServer || hasActiveServer, settingsService.settings.language);
        }
      } catch (e, st) {
        await ServiceLogger.logError('tick.reload', e, st);
      }
    });

    
    // Periodic ack flush and server sync every 60s from the service isolate.
    Timer.periodic(const Duration(seconds: 60), (timer) async {
      try {
        await DeliveryAckService.flush();
      } catch (e, st) {
        await ServiceLogger.logError('ack.periodicFlush', e, st);
      }

      try {
        final pending = await ServerAlertService.refreshSyncPending();
        if (!pending) return;
        final provider = ServerAlertService.rulesProvider;
        if (provider == null) return;
        final ok = await ServerAlertService.syncAllRulesToServer(provider());
        await ServiceLogger.log(
          'sync',
          ok ? 'periodic sync OK' : 'periodic sync failed',
        );
      } catch (e, st) {
        await ServiceLogger.logError('sync.periodic', e, st);
      }
    });

    await ServiceLogger.log('service', 'service started');

    // Initial device health heartbeat upon startup (Phase 3A-2)
    try {
      final uid = settingsService.settings.userEmail ?? '';
      if (uid.isNotEmpty) {
        DeviceHealthService.sendHeartbeat(userId: uid, fgsRunning: true).ignore();
      }
    } catch (e, st) {
      ServiceLogger.logError('init.heartbeat', e, st).ignore();
    }

    // Periodic device health heartbeat every 15 minutes (Phase 3A-2)
    Timer.periodic(const Duration(minutes: 15), (timer) async {
      try {
        final uid = settingsService.settings.userEmail ?? '';
        if (uid.isNotEmpty) {
          await DeviceHealthService.sendHeartbeat(userId: uid, fgsRunning: true);
        }
      } catch (e, st) {
        await ServiceLogger.logError('health.periodicHeartbeat', e, st);
      }
    });

    // Periodic FGS lifecycle diagnostics log (Phase 3B-1)
    Timer.periodic(const Duration(minutes: 30), (timer) async {
      try {
        final uptime = DateTime.now().difference(serviceStartTime).inMinutes;
        await ServiceLogger.log(
          'fgs.lifecycle',
          'service running heartbeat (uptime: ${uptime}m, type: dataSync)',
        );
      } catch (e, st) {
        await ServiceLogger.logError('fgs.lifecycle.timer', e, st);
      }
    });

    // WebSocket Client in Background Service Isolate (Phase 4B-1)
    try {
      final uid = settingsService.settings.userEmail ?? '';
      WebSocketClientService.start(userId: uid);
      await ServiceLogger.log('init', 'WebSocketClientService.start called (uid: "$uid")');
    } catch (e, st) {
      await ServiceLogger.logError('init.webSocketClient', e, st);
    }

    service.on('stopService').listen((event) async {
      final uptime = DateTime.now().difference(serviceStartTime).inMinutes;
      await ServiceLogger.log(
        'fgs.lifecycle',
        'service stop requested (reason: stopService event, uptime: ${uptime}m, payload: $event)',
      );
      try {
        WebSocketClientService.stop();
      } catch (e, st) {
        ServiceLogger.logError('stopService.webSocket', e, st).ignore();
      }
      service.stopSelf();
    });
  }
}