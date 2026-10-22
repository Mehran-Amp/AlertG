import 'dart:async';
import 'dart:io';
import 'dart:ui';
import 'package:flutter/foundation.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:path_provider/path_provider.dart';

import '../../../core/services/delivery_ack_service.dart';
import '../../../core/services/fcm_notification_service.dart';
import '../../../core/services/server_alert_service.dart';
import '../../../core/services/service_logger.dart';
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

  /// Updates foreground persistent notification text with current price source.
  static void updatePriceSource({required bool isFromServer, String? lang}) {
    _lastPriceFromServer = isFromServer;
    try {
      final service = FlutterBackgroundService();
      service.invoke('updatePriceSource', {
        'source': isFromServer ? 'fcm' : 'local',
        'lang': lang ?? 'fa',
      });
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

    void setNotificationText(bool isServer, [String lang = 'fa']) {
      if (service is AndroidServiceInstance) {
        final isFa = lang == 'fa' || lang == 'ar' || lang == 'ckb';
        final sourceText = isServer
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
        } catch (e, st) {
          ServiceLogger.logError('setNotificationText', e, st).ignore();
        }
      }
    }

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
          setNotificationText(isServer, lang);
        }
      });

      try {
        service.setAsForegroundService();
        setNotificationText(false, 'fa');
      } catch (e, st) {
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

    service.on('stopService').listen((event) {
      ServiceLogger.log('service', 'stopService received').ignore();
      service.stopSelf();
    });
  }
}