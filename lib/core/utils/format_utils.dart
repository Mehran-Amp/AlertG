import 'package:intl/intl.dart';

/// Universal Price and Decimal Formatter (inspired by BitcoinChecker FormatUtilsBase)
/// Supports dynamic significant digits, sub-cent cryptos (Shiba, Pepe, etc.),
/// and international fiat/crypto currency symbols and subunits.
class FormatUtils {
  static final NumberFormat _noDecimal = NumberFormat('#,###', 'en_US');
  static final NumberFormat _twoDecimal = NumberFormat('#,###.00', 'en_US');

  /// Resolves currency symbol display name based on the current app language.
  /// Rule:
  /// - TMN, IRT, TOMAN, تومان, ت: "تومان" in Farsi (fa), "IRT" in all other languages.
  /// - IRR, RLS, ریال: "ریال" in Farsi (fa), "IRR" in all other languages.
  /// - Other currencies (USD, EUR, BTC, etc.): unchanged.
  static String resolveCurrencyDisplayName(String? unit, {String lang = 'fa'}) {
    if (unit == null || unit.trim().isEmpty) return '';
    final trimmed = unit.trim();
    final upper = trimmed.toUpperCase();

    final isToman = upper == 'TMN' ||
        upper == 'IRT' ||
        upper == 'TOMAN' ||
        trimmed == 'تومان' ||
        trimmed == 'ت';

    final isRial = upper == 'IRR' ||
        upper == 'RLS' ||
        trimmed == 'ریال';

    final isFa = lang == 'fa';

    if (isToman) {
      return isFa ? 'تومان' : 'IRT';
    }
    if (isRial) {
      return isFa ? 'ریال' : 'IRR';
    }
    return trimmed;
  }

  /// Formats scaled currency abbreviations like 'B USD', 'M USD', 'Billion USD'
  /// without rounding or altering the original numerical precision of the price.
  /// Format pattern: <CurrencySymbol><FormattedNumber><ScaleLetter> (e.g. $2,450.37B, -$1.2B)
  static String? formatScaledCurrencyPrice(double price, String currencySymbol) {
    final trimmed = currencySymbol.trim();
    final upper = trimmed.toUpperCase();

    // Check for Billion (B) or Million (M) scale indicators
    String? scaleLetter;
    String baseCurr = 'USD';

    final bMatch = RegExp(r'^(B|BILLION)\s*(USD|EUR|GBP|BTC|JPY|CNY|USDT|USDC)?$', caseSensitive: false).firstMatch(upper);
    final mMatch = RegExp(r'^(M|MILLION)\s*(USD|EUR|GBP|BTC|JPY|CNY|USDT|USDC)?$', caseSensitive: false).firstMatch(upper);
    final bSuffixMatch = RegExp(r'^(USD|EUR|GBP|BTC|JPY|CNY|USDT|USDC)\s*(B|BILLION)$', caseSensitive: false).firstMatch(upper);
    final mSuffixMatch = RegExp(r'^(USD|EUR|GBP|BTC|JPY|CNY|USDT|USDC)\s*(M|MILLION)$', caseSensitive: false).firstMatch(upper);

    int maxDecimals = 3;

    if (upper == 'TOTAL' || upper == 'TOTAL2' || upper == 'TOTAL3') {
      scaleLetter = 'B';
      baseCurr = 'USD';
      maxDecimals = 3;
    } else if (bMatch != null) {
      scaleLetter = 'B';
      baseCurr = (bMatch.group(2) ?? 'USD').toUpperCase();
      maxDecimals = 3;
    } else if (mMatch != null) {
      scaleLetter = 'M';
      baseCurr = (mMatch.group(2) ?? 'USD').toUpperCase();
      maxDecimals = 2;
    } else if (bSuffixMatch != null) {
      scaleLetter = 'B';
      baseCurr = bSuffixMatch.group(1)!.toUpperCase();
      maxDecimals = 3;
    } else if (mSuffixMatch != null) {
      scaleLetter = 'M';
      baseCurr = mSuffixMatch.group(1)!.toUpperCase();
      maxDecimals = 2;
    }

    if (scaleLetter == null) {
      return null;
    }

    String sym;
    switch (baseCurr) {
      case 'EUR': sym = '€'; break;
      case 'GBP': sym = '£'; break;
      case 'JPY':
      case 'CNY': sym = '¥'; break;
      case 'BTC': sym = '₿'; break;
      case 'USD':
      case 'USDT':
      case 'USDC':
      default: sym = '\$'; break;
    }

    // Exact precision with thousand separators and restricted decimals per scale (B: max 3, M: max 2)
    final absPrice = price.abs();
    final fixedStr = absPrice.toStringAsFixed(maxDecimals);
    final parts = fixedStr.split('.');
    final intPart = _noDecimal.format(int.parse(parts[0]));
    String formattedNum = intPart;
    if (parts.length > 1) {
      final decPart = parts[1].replaceAll(RegExp(r'0+$'), '');
      if (decPart.isNotEmpty) {
        formattedNum = '$intPart.$decPart';
      }
    }

    final isNegative = price < 0;
    final prefix = isNegative ? '-$sym' : sym;
    // Wrapped in LTR isolate (\u202A ... \u202C) so $ always stays locked in front in RTL contexts
    return '\u202A$prefix$formattedNum$scaleLetter\u202C';
  }

  /// Formats raw numeric value for text input fields without currency symbols or thousand separators:
  /// - Billion (B USD, Billion USD): max 3 decimals, stripped zeros (e.g. 831.737, 2450.5)
  /// - Million (M USD, Million USD): max 2 decimals, stripped zeros (e.g. 850)
  /// - Percent (%): 2 decimals (e.g. 58.78)
  /// - Standard: standard smart precision without commas
  static String formatInputNumberForUnit(double price, String? quoteCurrency) {
    if (quoteCurrency != null) {
      final upper = quoteCurrency.trim().toUpperCase();
      final isBillion = upper == 'B USD' ||
          upper == 'BILLION USD' ||
          upper == 'B' ||
          upper == 'BILLION' ||
          upper == 'TOTAL' ||
          upper == 'TOTAL2' ||
          upper == 'TOTAL3' ||
          upper.startsWith('B ') ||
          upper.endsWith(' B');
      if (isBillion) {
        final fixedStr = price.abs().toStringAsFixed(3);
        final parts = fixedStr.split('.');
        final intPart = parts[0];
        if (parts.length > 1) {
          final decPart = parts[1].replaceAll(RegExp(r'0+$'), '');
          final res = decPart.isNotEmpty ? '$intPart.$decPart' : intPart;
          return price < 0 ? '-$res' : res;
        }
        return price < 0 ? '-$intPart' : intPart;
      }

      final isMillion = upper == 'M USD' ||
          upper == 'MILLION USD' ||
          upper == 'M' ||
          upper == 'MILLION' ||
          upper.startsWith('M ') ||
          upper.endsWith(' M');
      if (isMillion) {
        final fixedStr = price.abs().toStringAsFixed(2);
        final parts = fixedStr.split('.');
        final intPart = parts[0];
        if (parts.length > 1) {
          final decPart = parts[1].replaceAll(RegExp(r'0+$'), '');
          final res = decPart.isNotEmpty ? '$intPart.$decPart' : intPart;
          return price < 0 ? '-$res' : res;
        }
        return price < 0 ? '-$intPart' : intPart;
      }

      if (upper == '%' || upper == 'BTC.D' || upper == 'USDT.D' || upper == 'ETH.D' || upper.endsWith('.D')) {
        return price.toStringAsFixed(2);
      }
    }

    if (price >= 1000) {
      return price.toStringAsFixed(2);
    } else if (price >= 1) {
      return price.toStringAsFixed(4);
    } else if (price >= 0.0001) {
      return price.toStringAsFixed(6);
    } else {
      return price.toStringAsFixed(8);
    }
  }

  /// Formats any double price with intelligent precision based on its scale:
  /// - Large assets (BTC, Gold, Indices >= $1,000): 2 decimals with thousand separators ($94,520.50)
  /// - Standard assets ($1 to $1,000): 2 decimals ($18.45)
  /// - Penny assets ($0.01 to $1): 4 decimals ($0.0452)
  /// - Micro assets ($0.0001 to $0.01): 6 decimals ($0.004210)
  /// - Nano assets (< $0.0001, e.g. PEPE, SHIB): up to 8 decimals ($0.00000845)
  static String formatPrice(
    double price, {
    String? currencySymbol,
    bool showSymbol = true,
    String lang = 'fa',
  }) {
    if (price.isNaN || price.isInfinite) return '0.00';

    // 1. Check for scaled currency abbreviation (e.g. 'B USD', 'M USD', 'Billion USD', 'TOTAL')
    if (currencySymbol != null && currencySymbol.isNotEmpty) {
      if (showSymbol) {
        final scaled = formatScaledCurrencyPrice(price, currencySymbol);
        if (scaled != null) {
          return scaled;
        }
      } else {
        final scaled = formatScaledCurrencyPrice(price, currencySymbol);
        if (scaled != null) {
          return formatInputNumberForUnit(price, currencySymbol);
        }
      }
    }

    // 1b. Check for percentage unit (BTC.D, USDT.D, %, etc.)
    final upperSym = currencySymbol?.trim().toUpperCase();
    if (upperSym != null && (upperSym == '%' || upperSym == 'BTC.D' || upperSym == 'USDT.D' || upperSym == 'ETH.D' || upperSym.endsWith('.D'))) {
      final fixed = price.toStringAsFixed(2);
      return showSymbol ? '$fixed%' : fixed;
    }

    String formattedNumber;
    final absPrice = price.abs();

    if (absPrice >= 1000) {
      if (price == price.roundToDouble()) {
        formattedNumber = _noDecimal.format(price);
      } else {
        formattedNumber = _twoDecimal.format(price);
      }
    } else if (absPrice >= 1) {
      if (price == price.roundToDouble()) {
        formattedNumber = price.toInt().toString();
      } else {
        formattedNumber = price.toStringAsFixed(2);
      }
    } else if (absPrice >= 0.01) {
      formattedNumber = price.toStringAsFixed(4);
    } else if (absPrice >= 0.0001) {
      formattedNumber = price.toStringAsFixed(6);
    } else if (absPrice >= 0.00000001) {
      // Strip trailing zeros for micro assets
      formattedNumber = price.toStringAsFixed(8).replaceAll(RegExp(r'0+$'), '').replaceAll(RegExp(r'\.$'), '');
    } else if (absPrice == 0) {
      formattedNumber = '0.00';
    } else {
      formattedNumber = price.toStringAsFixed(8);
    }

    if (!showSymbol || currencySymbol == null || currencySymbol.isEmpty) {
      return formattedNumber;
    }

    final trimmed = currencySymbol.trim();
    final upper = trimmed.toUpperCase();

    // Handle Persian / RTL counter currencies
    final isToman = upper == 'TMN' ||
        upper == 'IRT' ||
        upper == 'TOMAN' ||
        trimmed == 'تومان' ||
        trimmed == 'ت';

    final isRial = upper == 'IRR' ||
        upper == 'RLS' ||
        trimmed == 'ریال';

    if (isToman) {
      final tmnNumber = absPrice >= 1 ? _noDecimal.format(price) : formattedNumber;
      final displayUnit = resolveCurrencyDisplayName(currencySymbol, lang: lang);
      return '$tmnNumber $displayUnit';
    }
    if (isRial) {
      final rialNumber = absPrice >= 1 ? _noDecimal.format(price) : formattedNumber;
      final displayUnit = resolveCurrencyDisplayName(currencySymbol, lang: lang);
      return '$rialNumber $displayUnit';
    }

    final isNegative = price < 0;
    final cleanNum = isNegative && formattedNumber.startsWith('-')
        ? formattedNumber.substring(1)
        : formattedNumber;

    // Universal symbols: always lock symbol to front using LTR isolate
    switch (upper) {
      case 'USD':
      case 'USDT':
      case 'USDC':
        return isNegative ? '\u202A-\$$cleanNum\u202C' : '\u202A\$$formattedNumber\u202C';
      case 'EUR':
        return isNegative ? '\u202A-€$cleanNum\u202C' : '\u202A€$formattedNumber\u202C';
      case 'GBP':
        return isNegative ? '\u202A-£$cleanNum\u202C' : '\u202A£$formattedNumber\u202C';
      case 'JPY':
      case 'CNY':
        return isNegative ? '\u202A-¥$cleanNum\u202C' : '\u202A¥$formattedNumber\u202C';
      case 'BTC':
        return isNegative ? '\u202A-₿$cleanNum\u202C' : '\u202A₿$formattedNumber\u202C';
      case 'SAT':
      case 'SATOSHI':
        return '${_noDecimal.format(price)} sats';
      default:
        // Rule 5: If unknown currency is non-Latin or length > 6, do not append to price
        final isCleanLatin = RegExp(r'^[A-Za-z0-9%$#€£¥₿]+$').hasMatch(trimmed);
        if (trimmed.length > 6 || !isCleanLatin) {
          return formattedNumber;
        }
        return '$formattedNumber $trimmed';
    }
  }

  /// Converts a price into a specific Subunit (e.g. BTC to Satoshi, Tomans to Rials)
  static double convertToSubunit(double basePrice, String baseCurrency, String targetSubunit) {
    if (baseCurrency.toUpperCase() == 'BTC' && (targetSubunit.toUpperCase() == 'SAT' || targetSubunit.toUpperCase() == 'SATOSHI')) {
      return basePrice * 100000000.0;
    }
    if (baseCurrency.toUpperCase() == 'BTC' && targetSubunit.toUpperCase() == 'MBTC') {
      return basePrice * 1000.0;
    }
    if (targetSubunit.toUpperCase() == 'RLS' && baseCurrency.toUpperCase() == 'TMN') {
      return basePrice * 10.0;
    }
    return basePrice;
  }

  /// Converts any English digits in a string or number to Persian digits (۰-۹)
  static String toPersianDigits(dynamic input) {
    if (input == null) return '';
    final str = input.toString();
    const english = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'];
    const persian = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
    var result = str;
    for (int i = 0; i < english.length; i++) {
      result = result.replaceAll(english[i], persian[i]);
    }
    return result;
  }

  /// Converts Persian (۰-۹) or Arabic (٠-٩) digits to standard ASCII digits (0-9)
  static String normalizePersianDigits(String input) {
    if (input.isEmpty) return '';
    const persian = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
    const arabic = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
    const english = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'];
    var result = input;
    for (int i = 0; i < 10; i++) {
      result = result.replaceAll(persian[i], english[i]).replaceAll(arabic[i], english[i]);
    }
    return result;
  }

  /// Formats prices specifically for the Iran Market UI (respects lang for unit & digits)
  static String formatIranPrice(double price, {String unit = 'TMN', String lang = 'fa'}) {
    final displayUnit = resolveCurrencyDisplayName(unit, lang: lang);
    if (price.isNaN || price.isInfinite) {
      return (lang == 'fa') ? '۰ $displayUnit' : '0 $displayUnit';
    }
    final absPrice = price.abs();
    String formattedEn;
    if (absPrice >= 1000) {
      formattedEn = _noDecimal.format(price);
    } else if (absPrice >= 1) {
      formattedEn = price.toStringAsFixed(2);
    } else {
      formattedEn = price.toStringAsFixed(4);
    }
    final numStr = (lang == 'fa') ? toPersianDigits(formattedEn) : formattedEn;
    return '$numStr $displayUnit';
  }

  /// Formats prices for Alert List / Card rows with dynamic language sensitivity
  static String formatAlertCardPrice(double price, String quoteCurrency, {String lang = 'fa'}) {
    final trimmed = quoteCurrency.trim();
    final upper = trimmed.toUpperCase();
    final isToman = upper == 'TMN' ||
        upper == 'IRT' ||
        upper == 'TOMAN' ||
        trimmed == 'تومان' ||
        trimmed == 'ت';
    final isRial = upper == 'IRR' ||
        upper == 'RLS' ||
        trimmed == 'ریال';

    if (isToman || isRial) {
      final numStr = price >= 1000
          ? _noDecimal.format(price)
          : (price == price.roundToDouble() ? price.toInt().toString() : price.toStringAsFixed(2));
      final displayUnit = resolveCurrencyDisplayName(quoteCurrency, lang: lang);
      return '$numStr $displayUnit';
    }
    return formatPrice(price, currencySymbol: quoteCurrency, lang: lang);
  }

  /// Formats volume with compact SI units (K, M, B)
  static String formatVolume(double volume) {
    if (volume >= 1000000000) {
      return '${(volume / 1000000000).toStringAsFixed(2)}B';
    } else if (volume >= 1000000) {
      return '${(volume / 1000000).toStringAsFixed(2)}M';
    } else if (volume >= 1000) {
      return '${(volume / 1000).toStringAsFixed(1)}K';
    } else {
      return volume.toStringAsFixed(0);
    }
  }
}
