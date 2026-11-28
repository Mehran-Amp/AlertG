import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../features/alert_engine/models/alert_rule.dart';
import '../../features/exchanges/stocks/iran_domestic_exchange.dart';
import '../../features/settings/models/app_settings.dart';
import '../utils/format_utils.dart';
import 'server_alert_service.dart';

/// Resolved presentation model for a single 2-line rich financial row in the Home Widget.
class WidgetAlertItemViewModel {
  final String symbolTitle;
  final String subtitle;
  final String formattedPrice;
  final String badgeText;
  final bool isPositive;
  final bool isNegative;
  final bool isDone;
  final bool isNearTarget;
  final bool isIranAsset;
  final int proximity; // 0..100

  const WidgetAlertItemViewModel({
    required this.symbolTitle,
    required this.subtitle,
    required this.formattedPrice,
    required this.badgeText,
    required this.isPositive,
    required this.isNegative,
    required this.isDone,
    required this.isNearTarget,
    required this.isIranAsset,
    required this.proximity,
  });
}

/// Service that serializes active alerts to the Native Android Home Screen Widget
/// with a fixed Obsidian Dark Luxury aesthetic, 2-line rich financial cards,
/// readable Persian names for Iranian markets & clean English pairs for global crypto,
/// target proximity micro-bar, and background silent refresh metadata.
class NativeWidgetSyncService {
  static const _appLifecycleChannel =
      MethodChannel('com.example.bitcoin_checker/app_lifecycle');
  static const _widgetChannel =
      MethodChannel('com.example.bitcoin_checker/widget');

  static List<AlertRule> _cachedRules = [];
  static AppThemePalette _cachedPalette = AppThemePalette.darkGreen;
  static String _cachedLang = 'fa';

  static const Map<String, String> _conciseIranNames = {
    'USD_TMN': 'دلار آزاد',
    'EUR_TMN': 'یورو آزاد',
    'GBP_TMN': 'پوند انگلیس',
    'AED_TMN': 'درهم امارات',
    'AED_REMIT_DUB': 'حواله درهم دبی',
    'CNY_REMIT': 'حواله یوآن چین',
    'TRY_TMN': 'لیر ترکیه',
    'CAD_TMN': 'دلار کانادا',
    'AUD_TMN': 'دلار استرالیا',
    'CNY_TMN': 'یوآن چین',
    'CHF_TMN': 'فرانک سوئیس',
    'SAR_TMN': 'ریال عربستان',
    'KWD_TMN': 'دینار کویت',
    'BHD_TMN': 'دینار بحرین',
    'OMR_TMN': 'ریال عمان',
    'QAR_TMN': 'ریال قطر',
    'IQD_TMN': 'دینار عراق',
    'JPY_TMN': 'ین ژاپن',
    'RUB_TMN': 'روبل روسیه',
    'AZN_TMN': 'منات آذربایجان',
    'AMD_TMN': 'درام ارمنستان',
    'GEL_TMN': 'لاری گرجستان',
    'AFN_TMN': 'افغانی افغانستان',
    'PKR_TMN': 'روپیه پاکستان',
    'INR_TMN': 'روپیه هند',
    'MYR_TMN': 'رینگیت مالزی',
    'THB_TMN': 'بات تایلند',
    'SGD_TMN': 'دلار سنگاپور',
    'HKD_TMN': 'دلار هنگ‌کنگ',
    'SEK_TMN': 'کرون سوئد',
    'NOK_TMN': 'کرون نروژ',
    'DKK_TMN': 'کرون دانمارک',
    'SYP_TMN': 'لیر سوریه',
    'GERAM18': 'طلای ۱۸ عیار',
    'GERAM24': 'طلای ۲۴ عیار',
    'MESGHAL': 'مثقال طلا',
    'MITHQAL': 'مثقال طلا',
    'GOLD_USED': 'طلای دست دوم',
    'GOLD_MELTED': 'آبشده نقدی',
    'COIN_EMAMI': 'سکه امامی',
    'SEKE_EMAMI': 'سکه امامی',
    'COIN_BAHAR': 'سکه بهار آزادی',
    'SEKE_BAHAR': 'سکه بهار آزادی',
    'COIN_HALF': 'نیم سکه',
    'SEKE_NIM': 'نیم سکه',
    'COIN_QUARTER': 'ربع سکه',
    'SEKE_ROB': 'ربع سکه',
    'COIN_GRAM': 'سکه گرمی',
    'SEKE_GERAMI': 'سکه گرمی',
    'USDT_TABDEAL': 'تتر تبدیل',
    'USDT_KIFPOOL': 'تتر کیف پول من',
    'GOLD_TABDEAL': 'پکس گلد تبدیل',
    'XAUT_TABDEAL': 'تتر گلد تبدیل',
    'GOLD_KIFPOOL': 'پکس گلد کیف پول من',
    'XAUT_KIFPOOL': 'تتر گلد کیف پول من',
  };

  /// Determines whether an AlertRule belongs to the Iranian domestic/crypto/bourse ecosystem.
  static bool isIranMarketRule(AlertRule rule) {
    final ex = rule.exchangeId.toLowerCase().trim();
    if (ex == 'iran_market' ||
        ex == 'iran_domestic' ||
        ex == 'iran_bourse' ||
        ex == 'tse' ||
        ex == 'tabdeal' ||
        ex == 'kifpool') {
      return true;
    }
    final symUpper = rule.marketSymbol.toUpperCase().trim();
    final baseUpper = rule.baseCurrency.toUpperCase().trim();
    if (_conciseIranNames.containsKey(symUpper) ||
        _conciseIranNames.containsKey(baseUpper)) {
      return true;
    }
    final counter = rule.counterCurrency.toUpperCase().trim();
    return counter == 'TMN' ||
        counter == 'IRT' ||
        counter == 'IRR' ||
        rule.counterCurrency.contains('تومان') ||
        rule.counterCurrency.contains('ریال');
  }

  /// Resolves a crisp, human-readable Persian title for Iranian market assets
  /// and clean English pair format for global crypto & international markets.
  static String resolveReadableSymbolTitle(AlertRule rule) {
    final symUpper = rule.marketSymbol.toUpperCase().trim();
    final baseUpper = rule.baseCurrency.toUpperCase().trim();
    final ex = rule.exchangeId.toLowerCase().trim();

    if (_conciseIranNames.containsKey(symUpper)) {
      return _conciseIranNames[symUpper]!;
    }
    if (_conciseIranNames.containsKey(baseUpper)) {
      return _conciseIranNames[baseUpper]!;
    }

    // Lookup in IranDomesticExchange.predefinedAssets
    for (final asset in IranDomesticExchange.predefinedAssets) {
      final code = (asset['symbol']?.toString() ?? '').toUpperCase();
      if (code.isNotEmpty && (code == symUpper || code == baseUpper)) {
        final nameFa = (asset['nameFa']?.toString() ?? '').trim();
        if (nameFa.isNotEmpty) {
          return nameFa
              .replaceAll('(بازار آزاد)', '')
              .replaceAll('(اسکناس بازار آزاد)', '')
              .replaceAll('(هر گرم)', '')
              .trim();
        }
      }
    }

    if (ex == 'tabdeal') {
      if (baseUpper == 'USDT') return 'تتر تبدیل';
      if (baseUpper == 'PAXG') return 'پکس گلد تبدیل';
      if (baseUpper == 'XAUT') return 'تتر گلد تبدیل';
      final counterLabel = (rule.counterCurrency.toUpperCase() == 'IRT' ||
              rule.counterCurrency.toUpperCase() == 'TMN' ||
              rule.counterCurrency.contains('تومان'))
          ? 'تومان'
          : rule.counterCurrency.toUpperCase();
      return '$baseUpper / $counterLabel';
    }

    if (ex == 'kifpool') {
      if (baseUpper == 'USDT') return 'تتر کیف پول من';
      if (baseUpper == 'PAXG') return 'پکس گلد کیف پول من';
      if (baseUpper == 'XAUT') return 'تتر گلد کیف پول من';
      final counterLabel = (rule.counterCurrency.toUpperCase() == 'IRT' ||
              rule.counterCurrency.toUpperCase() == 'TMN' ||
              rule.counterCurrency.contains('تومان'))
          ? 'تومان'
          : rule.counterCurrency.toUpperCase();
      return '$baseUpper / $counterLabel';
    }

    if (ex == 'iran_bourse' || ex == 'tse') {
      return rule.baseCurrency.trim();
    }

    // Global Crypto / International Markets -> Clean English Symbol
    final base = rule.baseCurrency.trim();
    final counter = rule.counterCurrency.trim().toUpperCase();
    if (counter.isEmpty ||
        counter == base.toUpperCase() ||
        ex == 'global_stocks' ||
        ex == 'macro') {
      return base;
    }
    return '$base / $counter';
  }

  /// Resolves the exchange/market source label + target price condition summary for Line 2.
  static String resolveSubtitleAndTarget(AlertRule rule, bool isIran) {
    final ex = rule.exchangeId.toLowerCase().trim();
    final symUpper = rule.marketSymbol.toUpperCase().trim();
    final baseUpper = rule.baseCurrency.toUpperCase().trim();

    String sourceLabel;
    if (symUpper.endsWith('_TABDEAL') ||
        baseUpper.endsWith('_TABDEAL') ||
        ex == 'tabdeal') {
      sourceLabel = 'تبدیل';
    } else if (symUpper.endsWith('_KIFPOOL') ||
        baseUpper.endsWith('_KIFPOOL') ||
        ex == 'kifpool') {
      sourceLabel = 'کیف پول من';
    } else if (ex == 'iran_bourse' || ex == 'tse') {
      sourceLabel = 'بورس تهران';
    } else if (ex == 'iran_market' || ex == 'iran_domestic') {
      String? cat;
      for (final asset in IranDomesticExchange.predefinedAssets) {
        final code = (asset['symbol']?.toString() ?? '').toUpperCase();
        if (code == symUpper || code == baseUpper) {
          cat = asset['cat']?.toString();
          break;
        }
      }
      if (cat == 'GoldFunds' ||
          cat == 'LeveragedFunds' ||
          cat == 'IndexFunds' ||
          cat == 'TopStocks') {
        sourceLabel = 'بورس تهران';
      } else {
        sourceLabel = 'بازار آزاد';
      }
    } else {
      switch (ex) {
        case 'binance':
          sourceLabel = 'Binance';
          break;
        case 'kucoin':
          sourceLabel = 'KuCoin';
          break;
        case 'bybit':
          sourceLabel = 'Bybit';
          break;
        case 'okx':
          sourceLabel = 'OKX';
          break;
        case 'mexc':
          sourceLabel = 'MEXC';
          break;
        case 'gateio':
          sourceLabel = 'Gate.io';
          break;
        case 'bitget':
          sourceLabel = 'Bitget';
          break;
        case 'bingx':
          sourceLabel = 'BingX';
          break;
        case 'coinbase':
          sourceLabel = 'Coinbase';
          break;
        case 'kraken':
          sourceLabel = 'Kraken';
          break;
        case 'lbank':
          sourceLabel = 'LBank';
          break;
        case 'xt':
          sourceLabel = 'XT.com';
          break;
        case 'toobit':
          sourceLabel = 'Toobit';
          break;
        case 'ourbit':
          sourceLabel = 'Ourbit';
          break;
        case 'kcex':
          sourceLabel = 'KCEX';
          break;
        case 'global_stocks':
          sourceLabel = 'Wall Street';
          break;
        case 'forex':
          sourceLabel = 'Forex';
          break;
        case 'macro':
          sourceLabel = 'Macro';
          break;
        default:
          sourceLabel = ex.isNotEmpty
              ? '${ex[0].toUpperCase()}${ex.substring(1)}'
              : 'Market';
      }
    }

    String targetSummary = '';
    switch (rule.conditionType) {
      case AlertConditionType.priceThreshold:
        if (rule.direction == AlertDirection.bothSides &&
            rule.upperTargetPrice != null &&
            rule.lowerTargetPrice != null) {
          final upStr = _formatCompactTarget(
              rule.upperTargetPrice!, rule.counterCurrency, isIran);
          final lowStr = _formatCompactTarget(
              rule.lowerTargetPrice!, rule.counterCurrency, isIran);
          targetSummary =
              isIran ? 'هدف: ▲$upStr / ▼$lowStr' : 'Target: ▲$upStr / ▼$lowStr';
        } else {
          final tp = rule.targetPrice ??
              rule.upperTargetPrice ??
              rule.lowerTargetPrice ??
              0.0;
          if (tp > 0) {
            final tpStr =
                _formatCompactTarget(tp, rule.counterCurrency, isIran);
            final dirArrow = rule.direction == AlertDirection.below ? '▼' : '▲';
            targetSummary =
                isIran ? 'هدف: $dirArrow $tpStr' : 'Target: $dirArrow $tpStr';
          }
        }
        break;
      case AlertConditionType.percentChange:
        final pct = rule.percent ?? 0.0;
        if (pct > 0) {
          final dirPrefix = rule.direction == AlertDirection.bothSides
              ? '±'
              : (rule.direction == AlertDirection.below ? '-' : '+');
          targetSummary = isIran
              ? 'هدف نوسان: $dirPrefix${pct.toStringAsFixed(1)}%'
              : 'Target: $dirPrefix${pct.toStringAsFixed(1)}%';
        }
        break;
      case AlertConditionType.absolutePriceChange:
        final delta = rule.deltaAbsolute ?? 0.0;
        if (delta > 0) {
          final dStr =
              _formatCompactTarget(delta, rule.counterCurrency, isIran);
          targetSummary = isIran ? 'نوسان هدف: ±$dStr' : 'Delta: ±$dStr';
        }
        break;
      case AlertConditionType.queueBuy:
        targetSummary = isIran ? 'هشدار صف خرید' : 'Buy Queue';
        break;
      case AlertConditionType.queueSell:
        targetSummary = isIran ? 'هشدار صف فروش' : 'Sell Queue';
        break;
      case AlertConditionType.volumeChange:
      case AlertConditionType.volumeAbove:
        targetSummary = isIran ? 'هشدار حجم معاملات' : 'Volume Surge';
        break;
    }

    if (targetSummary.isEmpty) {
      return sourceLabel;
    }
    return '$sourceLabel • $targetSummary';
  }

  static String _formatCompactTarget(
      double value, String counterCurrency, bool isIran) {
    final upper = counterCurrency.toUpperCase().trim();
    final isToman = isIran ||
        upper == 'TMN' ||
        upper == 'IRT' ||
        counterCurrency.contains('تومان');
    if (isToman) {
      return NumberFormat('#,###', 'en_US').format(value.round());
    }
    final prefix = (upper == 'USD' || upper == 'USDT' || upper == 'USDC')
        ? '\$'
        : '';
    if (value >= 1000) {
      return '$prefix${NumberFormat('#,##0.##', 'en_US').format(value)}';
    } else if (value >= 1) {
      return '$prefix${NumberFormat('#,##0.####', 'en_US').format(value)}';
    } else {
      return '$prefix${value.toStringAsFixed(5)}';
    }
  }

  /// Computes the complete presentation view model for a single alert row
  /// (used identically by Native Android AppWidget and In-App Widget Preview).
  static WidgetAlertItemViewModel computeRowViewModel(AlertRule rule) {
    final isIran = isIranMarketRule(rule);
    final symbolTitle = resolveReadableSymbolTitle(rule);
    final subtitle = resolveSubtitleAndTarget(rule, isIran);

    final currentPrice = rule.lastCheckedPrice ?? rule.basePrice ?? 0.0;
    final formattedPrice = currentPrice > 0
        ? FormatUtils.formatPrice(
            currentPrice,
            currencySymbol: isIran ? 'TMN' : rule.pair.counterCurrency,
            lang: isIran ? 'fa' : 'en',
          )
        : '—';

    final isPermanentBothWayPercent =
        rule.conditionType == AlertConditionType.percentChange &&
            rule.direction == AlertDirection.bothSides;
    final isDone =
        !isPermanentBothWayPercent && (!rule.isActive || rule.isTriggered);

    String badgeText;
    bool isPositive = true;
    bool isNearTarget = false;
    int proximity = isDone ? 100 : 35;

    final effTarget = rule.targetPrice ??
        rule.upperTargetPrice ??
        rule.lowerTargetPrice ??
        0.0;
    final base = rule.basePrice ?? 0.0;

    if (isDone) {
      badgeText = isIran ? '🔔 فعال شد' : '🔔 Triggered';
      isPositive = true;
      proximity = 100;
    } else {
      double diffPct = 0.0;

      if (base > 0 && currentPrice > 0 && (currentPrice - base).abs() > 0.0001) {
        diffPct = ((currentPrice - base) / base) * 100.0;
      } else if (rule.conditionType == AlertConditionType.priceThreshold &&
          effTarget > 0 &&
          currentPrice > 0) {
        diffPct = ((effTarget - currentPrice) / currentPrice) * 100.0;
      } else if (rule.percent != null && rule.percent! > 0) {
        diffPct = rule.direction == AlertDirection.below
            ? -rule.percent!
            : rule.percent!;
      }

      // Compute proximity (0..100) & near-target warning (< 1.0% distance)
      if (effTarget > 0 && currentPrice > 0) {
        final distPct = ((effTarget - currentPrice).abs() / currentPrice) * 100.0;
        isNearTarget = distPct <= 1.0;
        if (base > 0 && (effTarget - base).abs() > 0.0001) {
          final totalDist = (effTarget - base).abs();
          final remDist = (effTarget - currentPrice).abs();
          proximity = (((totalDist - remDist) / totalDist) * 100.0)
              .round()
              .clamp(8, 99);
        } else {
          proximity = (100.0 - (distPct * 12.0)).round().clamp(10, 99);
        }
      } else if (rule.conditionType == AlertConditionType.percentChange &&
          rule.percent != null &&
          rule.percent! > 0) {
        final progressRatio = (diffPct.abs() / rule.percent!) * 100.0;
        proximity = progressRatio.round().clamp(10, 99);
        isNearTarget = progressRatio >= 85.0;
      }

      final isUp = diffPct >= 0;
      isPositive = isUp;
      final sign = isUp ? '+' : '';
      final arrow = isUp ? '▲' : '▼';
      final pctCore = '$sign${diffPct.toStringAsFixed(2)}% $arrow';
      badgeText = isNearTarget ? '🔥 $pctCore' : pctCore;
    }

    return WidgetAlertItemViewModel(
      symbolTitle: symbolTitle,
      subtitle: subtitle,
      formattedPrice: formattedPrice,
      badgeText: badgeText,
      isPositive: isPositive,
      isNegative: !isPositive && !isDone,
      isDone: isDone,
      isNearTarget: isNearTarget,
      isIranAsset: isIran,
      proximity: proximity,
    );
  }

  /// Sync list of rules to native Android AppWidget
  static Future<void> syncAlerts(
    List<AlertRule> rules, {
    AppThemePalette? themePalette,
    String? lang,
  }) async {
    try {
      _cachedRules = rules;
      if (themePalette != null) {
        _cachedPalette = themePalette;
      }
      if (lang != null && lang.isNotEmpty) {
        _cachedLang = lang;
      }

      final items = rules.map((rule) {
        final vm = computeRowViewModel(rule);
        final effTarget = rule.targetPrice ??
            rule.upperTargetPrice ??
            rule.lowerTargetPrice ??
            0.0;
        final rawSym = rule.marketSymbol.trim().isNotEmpty
            ? rule.marketSymbol.trim()
            : rule.baseCurrency.trim();

        return {
          'symbol': vm.symbolTitle,
          'subtitle': vm.subtitle,
          'price': vm.formattedPrice,
          'badge': vm.badgeText,
          'isPositive': vm.isPositive,
          'isNegative': vm.isNegative,
          'isDone': vm.isDone,
          'isNearTarget': vm.isNearTarget,
          'isIranAsset': vm.isIranAsset,
          'proximity': vm.proximity,
          'isActive': rule.isActive,
          // Metadata for silent background refresh in Kotlin
          'exchangeId': rule.exchangeId,
          'rawSymbol': rawSym,
          'basePrice': rule.basePrice ?? 0.0,
          'targetPrice': effTarget,
          'conditionType': rule.conditionType.name,
          'direction': rule.direction.name,
          'percent': rule.percent ?? 0.0,
          'counterCurrency': rule.pair.counterCurrency,
        };
      }).toList();

      final activeCount = rules.where((r) => r.isActive && !r.isTriggered).length;
      final hitCount = rules.where((r) => r.isTriggered || !r.isActive).length;
      final timeNow = DateFormat('HH:mm').format(DateTime.now());
      final subtitle = hitCount > 0
          ? '$activeCount فعال • $hitCount زده‌شده • $timeNow'
          : '$activeCount آلارم فعال • بروزرسانی $timeNow';

      final payload = {
        'activeCount': activeCount,
        'hitCount': hitCount,
        'title': 'Alarmer Pro',
        'subtitle': subtitle,
        'refreshText': '⟳ بروزرسانی',
        'footerText': 'برای مدیریت آلارم‌ها ضربه بزنید',
        'lastUpdated': timeNow,
        'serverUrl': ServerAlertService.effectiveBaseUrl,
        'theme': _getObsidianLuxuryPalette(),
        'items': items,
      };

      final jsonStr = jsonEncode(payload);

      // 1. Persist directly to SharedPreferences so it's always saved even in background isolates
      try {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('widget_alerts_json', jsonStr);
      } catch (_) {}

      // 2. Notify via AlarmerNativePlugin (works in all isolates: UI + Background Service + FCM)
      try {
        await _appLifecycleChannel.invokeMethod('updateWidgetList', {
          'json': jsonStr,
        });
      } catch (_) {}

      // 3. Also notify MainActivity widget channel if UI activity is attached
      try {
        await _widgetChannel.invokeMethod('updateWidgetList', {
          'json': jsonStr,
        });
      } catch (_) {}
    } catch (_) {
      // Ignore platform channel exceptions gracefully
    }
  }

  /// Sync theme change (widget maintains fixed Obsidian Dark Luxury palette)
  static Future<void> syncTheme(AppThemePalette palette) async {
    _cachedPalette = palette;
    await syncAlerts(_cachedRules, themePalette: palette);
  }

  static Map<String, dynamic> _getObsidianLuxuryPalette() {
    return {
      'bg': 0xFF080D1A,
      'surface': 0xFF111827,
      'primary': 0xFF10B981,
      'textPrimary': 0xFFF8FAFC,
      'textSecondary': 0xFF94A3B8,
      'border': 0xFF1E293B,
      'price': 0xFFF8FAFC,
      'isDark': 1,
    };
  }
}
