import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import '../../features/alert_engine/models/alert_rule.dart';
import '../../features/alert_engine/repositories/json_alert_rule_repository.dart';
import '../../features/exchanges/base/currency_pair.dart';
import '../../features/watchlist/pages/create_alert_flow.dart' show CheckUnit;
import 'fcm_notification_service.dart';

/// ServerAlertService handles communication with the Python Alert Engine backend
class ServerAlertService {
  // Configurable base URL for the Python server
  static String _baseUrl = const String.fromEnvironment('SERVER_URL', defaultValue: 'https://aisocialfeed.com');
  static String _apiKey = const String.fromEnvironment('API_KEY');
  static bool _initialized = false;
  static DateTime? _circuitBreakerUntil;

  /// Centralized headers builder for internal Python server endpoints
  static Map<String, String> _buildHeaders({Map<String, String>? extra}) {
    final map = <String, String>{
      'Content-Type': 'application/json',
    };
    if (_apiKey.isNotEmpty) {
      map['X-API-Key'] = _apiKey;
    }
    if (extra != null) {
      map.addAll(extra);
    }
    return map;
  }

  /// Resolves the actual effective base URL (supports web origin, local server, or configured URL)
  static String get effectiveBaseUrl {
    if (_baseUrl.trim().isNotEmpty) return _baseUrl.trim();
    if (kIsWeb) {
      try {
        final origin = Uri.base.origin;
        if (origin.isNotEmpty && origin != 'null') return origin;
      } catch (_) {}
    }
    return 'https://aisocialfeed.com';
  }

  /// Whether server calls should be attempted
  static bool get isServerAvailable {
    if (_circuitBreakerUntil != null && DateTime.now().isBefore(_circuitBreakerUntil!)) {
      return false;
    }
    return true;
  }

  /// Load persisted server URL and API key from disk on startup
  static Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;
    try {
      final dir = await getApplicationDocumentsDirectory();
      
      // Load saved server URL
      final file = File('${dir.path}/server_url.txt');
      if (await file.exists()) {
        final saved = (await file.readAsString()).trim();
        if (saved.isNotEmpty) {
          _baseUrl = saved.endsWith('/') ? saved.substring(0, saved.length - 1) : saved;
          debugPrint('🌐 Loaded persisted Server Base URL: $_baseUrl');
        }
      }

      // Load saved API key if modified dynamically
      final kFile = File('${dir.path}/api_key.txt');
      if (await kFile.exists()) {
        final savedKey = (await kFile.readAsString()).trim();
        if (savedKey.isNotEmpty) {
          _apiKey = savedKey;
          debugPrint('🔑 Loaded persisted API Key.');
        }
      }
    } catch (_) {}
  }

  /// Set or update the server base URL dynamically and persist to disk
  static Future<void> setBaseUrl(String url) async {
    if (url.trim().isNotEmpty) {
      final cleanUrl = url.trim().endsWith('/') ? url.trim().substring(0, url.trim().length - 1) : url.trim();
      _baseUrl = cleanUrl;
      _circuitBreakerUntil = null; // Reset circuit breaker
      debugPrint('🌐 ServerAlertService Base URL updated to: $_baseUrl');
      try {
        final dir = await getApplicationDocumentsDirectory();
        final file = File('${dir.path}/server_url.txt');
        await file.writeAsString(cleanUrl);
      } catch (_) {}
    }
  }

  /// Set or update the API Key dynamically and persist to disk
  static Future<void> setApiKey(String key) async {
    final cleanKey = key.trim();
    _apiKey = cleanKey;
    debugPrint('🔑 ServerAlertService API Key updated.');
    try {
      final dir = await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/api_key.txt');
      await file.writeAsString(cleanKey);
    } catch (_) {}
  }

  /// Get current base URL
  static String get baseUrl => _baseUrl;

  /// Get current API key
  static String get apiKey => _apiKey;

  /// Helper to handle response status codes with friendly Iranian error messages
  static String _parseErrorMessage(http.Response response) {
    if (response.statusCode == 401) {
      return 'کلید دسترسی API نامعتبر است (401)';
    } else if (response.statusCode == 503) {
      return 'سرویس سرور آلارم تنظیم نشده است (503)';
    } else if (response.statusCode == 400) {
      return 'پارامترهای درخواستی با فرمت سرور تطابق ندارد (400)';
    }
    return 'خطای پاسخ سرور (کد ${response.statusCode})';
  }

  /// Returns the effective user identifier (e.g. userEmail from settings or Google auth)
  static Future<String> getEffectiveUserId() async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      final sFile = File('${dir.path}/settings.json');
      if (await sFile.exists()) {
        final sData = jsonDecode(await sFile.readAsString());
        final savedEmail = sData['userEmail'] as String?;
        if (savedEmail != null && savedEmail.trim().isNotEmpty) {
          return savedEmail.trim().toLowerCase();
        }
        final deviceId = sData['deviceId'] as String?;
        if (deviceId != null && deviceId.trim().isNotEmpty) {
          return deviceId.trim();
        }
      }
    } catch (e) {
      debugPrint('Error getting effective user id: $e');
    }
    return 'Mehran.Aminpoor@gmail.com';
  }

  /// Bulk sync all local alert rules to Python server with real FCM Token
  static Future<bool> syncAllRulesToServer(List<AlertRule> rules, {String? userId}) async {
    if (!isServerAvailable) return false;
    try {
      final fcmToken = await FCMNotificationService.getFCMToken();
      final activeRules = rules.where((r) => r.isActive && r.exchangeId.toLowerCase() != 'timer' && r.exchangeId.toLowerCase() != 'local').toList();

      // Retrieve userEmail & telegram_chat_id from settings.json
      String effectiveUserId = userId ?? 'user_default';
      String? telegramChatId;
      try {
        final dir = await getApplicationDocumentsDirectory();
        final sFile = File('${dir.path}/settings.json');
        if (await sFile.exists()) {
          final sData = jsonDecode(await sFile.readAsString());
          telegramChatId = sData['telegramChatId'] as String?;
          final savedEmail = sData['userEmail'] as String?;
          if (savedEmail != null && savedEmail.trim().isNotEmpty) {
            effectiveUserId = savedEmail.trim().toLowerCase();
          }
        }
      } catch (_) {}
      
      final alertsPayload = activeRules.map((rule) {
        final effectiveTarget = rule.targetPrice ?? rule.upperTargetPrice ?? rule.lowerTargetPrice ?? 0.0;
        final conditionStr = (rule.direction == AlertDirection.below)
            ? 'BELOW'
            : (rule.direction == AlertDirection.bothSides ? 'BOTHSIDES' : 'ABOVE');
        final trigMode = (rule.triggerMode == TriggerMode.recurring) ? 'recurring' : 'oneShot';
        return {
          'id': rule.uuid,
          'exchange': rule.exchangeId.toLowerCase(),
          'symbol': rule.marketSymbol.toUpperCase(),
          'target_price': effectiveTarget,
          'condition': conditionStr,
          'condition_type': rule.conditionType.name,
          'direction': rule.direction.name,
          'both_way_behavior': rule.bothWayBehavior.name,
          'percent': rule.percent,
          'upper_target_price': rule.upperTargetPrice,
          'upper_note': rule.upperNote,
          'lower_target_price': rule.lowerTargetPrice,
          'lower_note': rule.lowerNote,
          'delta_absolute': rule.deltaAbsolute,
          'volume_percent': rule.volumePercent,
          'base_price': rule.basePrice,
          'base_volume': rule.baseVolume,
          'base_currency': rule.baseCurrency,
          'counter_currency': rule.counterCurrency,
          'market_symbol': rule.marketSymbol,
          'check_interval_seconds': rule.checkIntervalSeconds,
          'note': rule.customNote ?? rule.upperNote ?? rule.lowerNote,
          'trigger_mode': trigMode,
          'sound_enabled': rule.soundEnabled,
          'vibration_enabled': rule.vibrationEnabled,
          'tts_enabled': rule.ttsEnabled,
          'sound': rule.customSound ?? 'alarm_siren',
          'language': rule.language ?? 'fa',
          'prefer_server_proxy': rule.preferServerProxy,
          'is_active': rule.isActive,
          'fcm_token': fcmToken,
          'raw_rule': rule.toJson(),
          if (telegramChatId != null && telegramChatId.isNotEmpty) 'telegram_chat_id': telegramChatId,
        };
      }).toList();

      final url = Uri.parse('$effectiveBaseUrl/api/alerts/sync');
      final payload = {
        'user_id': effectiveUserId,
        'fcm_token': fcmToken,
        'alerts': alertsPayload,
      };

      final response = await http.post(
        url,
        headers: _buildHeaders(),
        body: jsonEncode(payload),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        _circuitBreakerUntil = null;
        debugPrint('✅ All alerts successfully synced to Python server for user $effectiveUserId');
        return true;
      } else {
        debugPrint('❌ Sync error: ${_parseErrorMessage(response)}');
      }
    } catch (e) {
      debugPrint('⚠️ Network/Sync Exception: $e');
    }
    return false;
  }

  /// Helper to sync all rules in context repository to server
  static Future<bool> syncWithServer(BuildContext context) async {
    try {
      final repo = context.read<JsonAlertRuleRepository>();
      return await syncAllRulesToServer(repo.allRules);
    } catch (e) {
      debugPrint('Sync with server error: $e');
      return false;
    }
  }

  /// Restores user alerts from cloud server when signing in or reinstalling app
  static Future<int> restoreUserAlertsFromCloud({
    BuildContext? context,
    JsonAlertRuleRepository? repository,
    required String userEmail,
  }) async {
    if (userEmail.trim().isEmpty) return 0;
    try {
      final fcmToken = await FCMNotificationService.getFCMToken();
      final cleanUser = userEmail.trim().toLowerCase();
      final url = Uri.parse('$effectiveBaseUrl/api/alerts/$cleanUser').replace(
        queryParameters: {
          if (fcmToken.isNotEmpty) 'fcm_token': fcmToken,
        },
      );
      final response = await http.get(url, headers: _buildHeaders()).timeout(const Duration(seconds: 8));

      if (response.statusCode == 200) {
        final dynamic decoded = jsonDecode(utf8.decode(response.bodyBytes));
        if (decoded is List && decoded.isNotEmpty) {
          JsonAlertRuleRepository? repo = repository;
          if (repo == null && context != null) {
            try {
              repo = context.read<JsonAlertRuleRepository>();
            } catch (_) {}
          }
          if (repo == null) {
            final dir = await getApplicationDocumentsDirectory();
            repo = JsonAlertRuleRepository(dir.path);
            await repo.load();
          }

          int imported = 0;
          for (final item in decoded) {
            if (item is Map<String, dynamic>) {
              try {
                if (item['raw_rule'] is Map) {
                  final rawMap = Map<String, dynamic>.from(item['raw_rule'] as Map);
                  final rule = AlertRule.fromJson(rawMap);
                  await repo.saveRule(rule, syncToServer: false);
                  imported++;
                  continue;
                }

                final symbol = item['symbol'] as String? ?? 'BTCUSDT';
                final exchange = item['exchange'] as String? ?? 'binance';
                final target = (item['target_price'] as num?)?.toDouble() ?? 0.0;
                final condition = item['condition'] as String? ?? 'ABOVE';
                final note = item['note'] as String?;
                final interval = item['check_interval_seconds'] as int? ?? 180;
                final ruleId = item['id'] as String? ?? DateTime.now().microsecondsSinceEpoch.toString();
                final sound = item['sound'] as String? ?? 'alarm_siren';
                final soundEnabled = item['sound_enabled'] as bool? ?? true;
                final vibEnabled = item['vibration_enabled'] as bool? ?? true;
                final ttsEnabled = item['tts_enabled'] as bool? ?? false;
                final isActive = item['is_active'] as bool? ?? true;

                final condTypeStr = item['condition_type'] as String? ?? 'priceThreshold';
                final condType = AlertConditionType.values.firstWhere(
                  (c) => c.name == condTypeStr,
                  orElse: () => AlertConditionType.priceThreshold,
                );

                final dirStr = item['direction'] as String? ?? (condition.toUpperCase() == 'BELOW' ? 'below' : (condition.toUpperCase() == 'BOTHSIDES' ? 'bothSides' : 'above'));
                final direction = AlertDirection.values.firstWhere(
                  (d) => d.name == dirStr,
                  orElse: () => (condition.toUpperCase() == 'BELOW' ? AlertDirection.below : AlertDirection.above),
                );

                final bothWayStr = item['both_way_behavior'] as String? ?? 'oco';
                final bothWay = BothWayBehavior.values.firstWhere(
                  (b) => b.name == bothWayStr,
                  orElse: () => BothWayBehavior.oco,
                );

                final trigModeStr = item['trigger_mode'] as String? ?? 'oneShot';
                final trigMode = TriggerMode.values.firstWhere(
                  (t) => t.name == trigModeStr,
                  orElse: () => TriggerMode.oneShot,
                );

                String base = item['base_currency'] as String? ?? 'BTC';
                String counter = item['counter_currency'] as String? ?? 'USDT';
                if (item['base_currency'] == null) {
                  if (symbol.contains('/')) {
                    final parts = symbol.split('/');
                    base = parts[0];
                    counter = parts.length > 1 ? parts[1] : 'USDT';
                  } else {
                    for (final q in ['USDT', 'USDC', 'BUSD', 'FDUSD', 'EUR', 'USD', 'TMN', 'IRT', 'BTC', 'ETH']) {
                      if (symbol.endsWith(q) && symbol.length > q.length) {
                        base = symbol.substring(0, symbol.length - q.length);
                        counter = q;
                        break;
                      }
                    }
                  }
                }

                final rule = AlertRule(
                  uuid: ruleId,
                  baseCurrency: base,
                  counterCurrency: counter,
                  marketSymbol: symbol,
                  exchangeId: exchange,
                  checkIntervalSeconds: interval,
                  conditionType: condType,
                  direction: direction,
                  bothWayBehavior: bothWay,
                  triggerMode: trigMode,
                  targetPrice: target > 0 ? target : null,
                  upperTargetPrice: (item['upper_target_price'] as num?)?.toDouble(),
                  upperNote: item['upper_note'] as String?,
                  lowerTargetPrice: (item['lower_target_price'] as num?)?.toDouble(),
                  lowerNote: item['lower_note'] as String?,
                  percent: (item['percent'] as num?)?.toDouble(),
                  deltaAbsolute: (item['delta_absolute'] as num?)?.toDouble(),
                  volumePercent: (item['volume_percent'] as num?)?.toDouble(),
                  basePrice: (item['base_price'] as num?)?.toDouble(),
                  baseVolume: (item['base_volume'] as num?)?.toDouble(),
                  customNote: note,
                  customSound: sound,
                  language: item['language'] as String? ?? 'fa',
                  soundEnabled: soundEnabled,
                  vibrationEnabled: vibEnabled,
                  ttsEnabled: ttsEnabled,
                  preferServerProxy: item['prefer_server_proxy'] as bool? ?? false,
                  isActive: isActive,
                  createdAt: DateTime.now(),
                );

                await repo.saveRule(rule, syncToServer: false);
                imported++;
              } catch (e) {
                debugPrint('⚠️ Error parsing cloud alert: $e');
              }
            }
          }
          // Extract any active Telegram Chat ID from restored alerts to maintain connection
          String? cloudChatId;
          for (final item in decoded) {
            if (item is Map && item['telegram_chat_id'] != null) {
              final c = item['telegram_chat_id'].toString().trim();
              if (c.isNotEmpty) {
                cloudChatId = c;
                break;
              }
            }
          }
          if (cloudChatId != null && cloudChatId.isNotEmpty) {
            try {
              final dir = await getApplicationDocumentsDirectory();
              final lastTgFile = File('${dir.path}/last_telegram_chat.txt');
              await lastTgFile.writeAsString(cloudChatId);

              final profFile = File('${dir.path}/account_profile_${cleanUser}.json');
              await profFile.writeAsString(jsonEncode({
                'email': cleanUser,
                'telegram_chat_id': cloudChatId,
                'is_connected': true,
                'last_updated': DateTime.now().toIso8601String(),
              }));
            } catch (_) {}
          }

          if (imported > 0) {
            await repo.load();
          }
          debugPrint('☁️ Successfully restored $imported alert(s) from cloud for $cleanUser (Telegram Chat ID: $cloudChatId)');
          return imported;
        }
      } else {
        debugPrint('⚠️ Restore alerts error: ${_parseErrorMessage(response)}');
      }
    } catch (e) {
      debugPrint('⚠️ Error restoring alerts from cloud: $e');
    }
    return 0;
  }

  /// Completely purge all alerts stored on the Python server
  static Future<bool> purgeAllServerAlerts() async {
    try {
      final url = Uri.parse('$effectiveBaseUrl/api/alerts');
      final response = await http.delete(url, headers: _buildHeaders()).timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Helper method to convert (unitValue, CheckUnit) into total seconds
  static int calculateIntervalInSeconds(int unitValue, CheckUnit unit) {
    final val = unitValue <= 0 ? 10 : unitValue;
    switch (unit) {
      case CheckUnit.seconds:
        return val;
      case CheckUnit.minutes:
        return val * 60;
      case CheckUnit.hours:
        return val * 3600;
      default:
        return val * 60;
    }
  }

  /// Create and register a new alert on the Python server
  static Future<bool> createAlertOnServer({
    String? ruleId,
    required String userId,
    required String exchange,
    required String symbol,
    required double targetPrice,
    required String condition, // 'ABOVE' or 'BELOW' or 'BOTHSIDES'
    required int checkIntervalSeconds,
    String? note,
    String triggerMode = 'oneShot',
    String? conditionType,
    String? direction,
    String? bothWayBehavior,
    double? percent,
    double? upperTargetPrice,
    String? upperNote,
    double? lowerTargetPrice,
    String? lowerNote,
    double? deltaAbsolute,
    double? volumePercent,
    double? basePrice,
    double? baseVolume,
    String? baseCurrency,
    String? counterCurrency,
    String? marketSymbol,
    String? language,
    bool preferServerProxy = false,
    Map<String, dynamic>? rawRule,
    bool soundEnabled = true,
    bool vibrationEnabled = true,
    bool ttsEnabled = false,
    String sound = 'alarm_siren',
  }) async {
    try {
      // Get the device's FCM token
      final fcmToken = await FCMNotificationService.getFCMToken();
      if (fcmToken.isEmpty) {
        debugPrint('⚠️ FCM Token not available yet. Using fallback token for registration.');
      }

      // Retrieve telegram_chat_id if saved in settings.json
      String? telegramChatId;
      try {
        final dir = await getApplicationDocumentsDirectory();
        final sFile = File('${dir.path}/settings.json');
        if (await sFile.exists()) {
          final sData = jsonDecode(await sFile.readAsString());
          telegramChatId = sData['telegramChatId'] as String?;
        }
      } catch (_) {}

      final url = Uri.parse('$effectiveBaseUrl/api/alerts');
      final payload = {
        if (ruleId != null && ruleId.isNotEmpty) 'id': ruleId,
        'user_id': userId,
        'exchange': exchange.toLowerCase(),
        'symbol': symbol.toUpperCase(),
        'target_price': targetPrice,
        'condition': condition.toUpperCase(),
        if (conditionType != null) 'condition_type': conditionType,
        if (direction != null) 'direction': direction,
        if (bothWayBehavior != null) 'both_way_behavior': bothWayBehavior,
        if (percent != null) 'percent': percent,
        if (upperTargetPrice != null) 'upper_target_price': upperTargetPrice,
        if (upperNote != null) 'upper_note': upperNote,
        if (lowerTargetPrice != null) 'lower_target_price': lowerTargetPrice,
        if (lowerNote != null) 'lower_note': lowerNote,
        if (deltaAbsolute != null) 'delta_absolute': deltaAbsolute,
        if (volumePercent != null) 'volume_percent': volumePercent,
        if (basePrice != null) 'base_price': basePrice,
        if (baseVolume != null) 'base_volume': baseVolume,
        if (baseCurrency != null) 'base_currency': baseCurrency,
        if (counterCurrency != null) 'counter_currency': counterCurrency,
        if (marketSymbol != null) 'market_symbol': marketSymbol,
        if (language != null) 'language': language,
        'prefer_server_proxy': preferServerProxy,
        if (rawRule != null) 'raw_rule': rawRule,
        'fcm_token': fcmToken.isNotEmpty ? fcmToken : 'device_token_pending',
        'check_interval_seconds': checkIntervalSeconds,
        'trigger_mode': triggerMode,
        'sound_enabled': soundEnabled,
        'vibration_enabled': vibrationEnabled,
        'tts_enabled': ttsEnabled,
        'sound': sound,
        if (note != null && note.isNotEmpty) 'note': note,
        if (telegramChatId != null && telegramChatId.isNotEmpty) 'telegram_chat_id': telegramChatId,
      };

      debugPrint('📤 Sending alert to Python server: $payload');

      final response = await http.post(
        url,
        headers: _buildHeaders(),
        body: jsonEncode(payload),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200 || response.statusCode == 201) {
        debugPrint('✅ Alert successfully created on Python server: ${utf8.decode(response.bodyBytes)}');
        return true;
      } else {
        debugPrint('❌ Failed to create alert on server: ${_parseErrorMessage(response)}');
      }
    } catch (e) {
      debugPrint('❌ Error connecting to Python Alert Server: $e');
    }
    return false;
  }

  /// Fetch all active alerts for a user from the Python server
  static Future<List<Map<String, dynamic>>> fetchUserAlerts(String userId) async {
    try {
      final url = Uri.parse('$effectiveBaseUrl/api/alerts/$userId');
      final response = await http.get(url, headers: _buildHeaders()).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(utf8.decode(response.bodyBytes));
        return data.cast<Map<String, dynamic>>();
      } else {
        debugPrint('❌ Fetch user alerts failed: ${_parseErrorMessage(response)}');
      }
    } catch (e) {
      debugPrint('❌ Error fetching alerts from Python server: $e');
    }
    return [];
  }

  /// Delete an alert from the Python server by ID
  static Future<bool> deleteAlertFromServer(String alertId) async {
    try {
      final url = Uri.parse('$effectiveBaseUrl/api/alerts/$alertId');
      final response = await http.delete(url, headers: _buildHeaders()).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        debugPrint('✅ Alert $alertId deleted from Python server.');
        return true;
      } else {
        debugPrint('❌ Delete alert failed: ${_parseErrorMessage(response)}');
      }
    } catch (e) {
      debugPrint('❌ Error deleting alert from Python server: $e');
    }
    return false;
  }

  /// Fetch live price via Python server proxy for filtered exchanges (Binance, MEXC, Yahoo Finance, etc.)
  static Future<double?> fetchPriceViaServer(String exchange, String symbol) async {
    if (!isServerAvailable) return null;
    try {
      final sanitizedSym = symbol.replaceAll('/', '').replaceAll(' ', '');
      final url = Uri.parse('$effectiveBaseUrl/api/price/${exchange.toLowerCase()}/$sanitizedSym');
      final response = await http.get(url, headers: _buildHeaders()).timeout(const Duration(seconds: 4));

      if (response.statusCode == 200) {
        _circuitBreakerUntil = null;
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        if (data is Map && data.containsKey('price') && data['price'] is num) {
          final p = (data['price'] as num).toDouble();
          if (p > 0) return p;
        }
      }
    } catch (_) {
      // Temporarily trip circuit breaker so local scheduler doesn't retry unreachable host
      _circuitBreakerUntil = DateTime.now().add(const Duration(minutes: 2));
    }
    return null;
  }

  /// Fetch full price details including market status, market_open, carried_over, etc.
  static Future<Map<String, dynamic>?> fetchPriceDetailsViaServer(String exchange, String symbol) async {
    if (!isServerAvailable) return null;
    try {
      final sanitizedSym = symbol.replaceAll('/', '').replaceAll(' ', '');
      final url = Uri.parse('$effectiveBaseUrl/api/price/${exchange.toLowerCase()}/$sanitizedSym');
      final response = await http.get(url, headers: _buildHeaders()).timeout(const Duration(seconds: 6));

      if (response.statusCode == 200) {
        _circuitBreakerUntil = null;
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        if (data is Map<String, dynamic>) {
          return data;
        }
      }
    } catch (_) {}
    return null;
  }

  /// Fetch overall markets status (TSE schedule, open/closed, next_open, exchange_state_fa)
  static Future<Map<String, dynamic>?> fetchMarketsStatus() async {
    if (!isServerAvailable) return null;
    try {
      final url = Uri.parse('$effectiveBaseUrl/api/markets/status');
      final response = await http.get(url, headers: _buildHeaders()).timeout(const Duration(seconds: 6));
      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        if (data is Map<String, dynamic>) {
          return data['markets'] as Map<String, dynamic>? ?? data;
        }
      }
    } catch (_) {}
    return null;
  }

  /// Fetch complete market overview including TSE schedule and all items with states/prices
  static Future<Map<String, dynamic>?> fetchMarketsOverview() async {
    if (!isServerAvailable) return null;
    try {
      final url = Uri.parse('$effectiveBaseUrl/api/markets/status');
      final response = await http.get(url, headers: _buildHeaders()).timeout(const Duration(seconds: 8));
      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        if (data is Map<String, dynamic>) {
          return data;
        }
      }
    } catch (_) {}
    return null;
  }

  /// Run deep server-side diagnostics on a specific exchange & market symbol
  static Future<Map<String, dynamic>?> inspectMarketSource(String exchange, String symbol) async {
    try {
      final sanitizedSym = symbol.replaceAll('/', '').replaceAll(' ', '');
      final url = Uri.parse('$effectiveBaseUrl/api/debug/inspect/${exchange.toLowerCase()}/$sanitizedSym');
      final response = await http.get(url, headers: _buildHeaders()).timeout(const Duration(seconds: 12));

      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        if (data is Map<String, dynamic>) return data;
      }
    } catch (e) {
      debugPrint('❌ Error running deep server inspection: $e');
    }
    return null;
  }

  /// Fetch recent server diagnostic logs
  static Future<List<Map<String, dynamic>>> fetchDebugLogs() async {
    try {
      final url = Uri.parse('$effectiveBaseUrl/api/debug/logs');
      final response = await http.get(url, headers: _buildHeaders()).timeout(const Duration(seconds: 8));

      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        if (data is Map && data.containsKey('logs') && data['logs'] is List) {
          return (data['logs'] as List).cast<Map<String, dynamic>>();
        }
      }
    } catch (e) {
      debugPrint('❌ Error fetching debug logs: $e');
    }
    return [];
  }

  /// Sends a test verification push notification from server to verify live mobile delivery
  static Future<Map<String, dynamic>> sendTestPush({String? customTitle, String? customBody}) async {
    try {
      final token = await FCMNotificationService.getFCMToken();
      final uri = Uri.parse('$effectiveBaseUrl/api/test/push').replace(
        queryParameters: {
          if (token.isNotEmpty) 'fcm_token': token,
          if (customTitle != null && customTitle.isNotEmpty) 'title': customTitle,
          if (customBody != null && customBody.isNotEmpty) 'body': customBody,
        },
      );
      final response = await http.get(uri, headers: _buildHeaders()).timeout(const Duration(seconds: 10));
      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        if (data is Map<String, dynamic>) return data;
      }
      return {'success': false, 'error': _parseErrorMessage(response)};
    } catch (e) {
      debugPrint('❌ Error sending test push: $e');
      return {'success': false, 'error': e.toString()};
    }
  }

  /// Dispatches a real test message to verify the user's Telegram Chat ID connection
  static Future<Map<String, dynamic>> sendTelegramTestAlert(String chatId) async {
    final cleanId = chatId.trim();
    if (cleanId.isEmpty) {
      debugPrint('⚠️ [Telegram Test] Chat ID is empty, aborted.');
      return {'success': false, 'error': 'شناسه چت آیدی خالی است (Chat ID is empty)'};
    }

    debugPrint('🚀 [Telegram Test] Initiating test alert for Chat ID: $cleanId');

    // 1. If server is available, try server endpoint first
    if (isServerAvailable) {
      try {
        final serverEndpoint = '$effectiveBaseUrl/api/telegram/test-message';
        debugPrint('🌐 [Telegram Test] Attempting via Python Server: $serverEndpoint');
        final response = await http.post(
          Uri.parse(serverEndpoint),
          headers: _buildHeaders(),
          body: jsonEncode({'chat_id': cleanId}),
        ).timeout(const Duration(seconds: 8));

        debugPrint('📥 [Telegram Test] Server response status: ${response.statusCode}, body: ${utf8.decode(response.bodyBytes)}');
        if (response.statusCode == 200) {
          try {
            final data = jsonDecode(utf8.decode(response.bodyBytes));
            if (data is Map && data['status'] == 'error') {
              final detail = data['detail'] ?? 'خطای تلگرام';
              debugPrint('⚠️ [Telegram Test] Server returned business error: $detail');
              return {'success': false, 'error': 'خطای سرور تلگرام: $detail'};
            }
          } catch (_) {}
          debugPrint('✅ [Telegram Test] Server successfully dispatched Telegram test message.');
          return {'success': true, 'message': 'پیام تست با موفقیت توسط سرور به تلگرام ارسال شد.'};
        } else {
          debugPrint('⚠️ [Telegram Test] Server returned error ${response.statusCode}: ${utf8.decode(response.bodyBytes)}');
          try {
            final data = jsonDecode(utf8.decode(response.bodyBytes));
            if (data is Map && data['detail'] != null) {
              return {'success': false, 'error': data['detail'].toString()};
            }
          } catch (_) {}
        }
      } catch (e) {
        debugPrint('⚠️ [Telegram Test] Python Server dispatch failed/timeout: $e');
      }
    } else {
      debugPrint('ℹ️ [Telegram Test] Server unavailable or circuit breaker active.');
    }

    return {'success': false, 'error': 'سرور در دسترس نیست؛ لطفاً بعداً دوباره تلاش کنید.'};
  }

  /// Persist user's Telegram Chat ID and connection state on the server
  static Future<bool> saveUserTelegramStatus({
    required String userId,
    required String? chatId,
    bool isConnected = true,
  }) async {
    if (!isServerAvailable || userId.trim().isEmpty) return false;
    try {
      final cleanUser = userId.trim().toLowerCase();
      final url = Uri.parse('$effectiveBaseUrl/api/user/$cleanUser/telegram');
      final response = await http.post(
        url,
        headers: _buildHeaders(),
        body: jsonEncode({
          'chat_id': chatId,
          'is_connected': isConnected && chatId != null && chatId.trim().isNotEmpty,
        }),
      ).timeout(const Duration(seconds: 6));
      return response.statusCode == 200;
    } catch (e) {
      debugPrint('⚠️ Error saving user Telegram status: $e');
      return false;
    }
  }

  /// Retrieve user's saved Telegram Chat ID and connection state from the server
  static Future<Map<String, dynamic>?> fetchUserTelegramStatus(String userId) async {
    if (!isServerAvailable || userId.trim().isEmpty) return null;
    try {
      final cleanUser = userId.trim().toLowerCase();
      final url = Uri.parse('$effectiveBaseUrl/api/user/$cleanUser/telegram');
      final response = await http.get(url, headers: _buildHeaders()).timeout(const Duration(seconds: 6));
      if (response.statusCode == 200) {
        final data = jsonDecode(utf8.decode(response.bodyBytes));
        if (data is Map<String, dynamic>) {
          return data;
        }
      }
    } catch (e) {
      debugPrint('⚠️ Error fetching user Telegram status: $e');
    }
    return null;
  }
}
