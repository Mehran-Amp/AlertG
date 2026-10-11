import 'package:flutter/material.dart';

enum AppThemePalette {
  darkGreen,
  lightGreen,
  darkOrange,
  lightOrange,
  darkPurpleBlue,
  lightPurpleBlue,
  darkGold,
  lightGold,
  darkSapphire,
  lightSapphire,
}

class AppSettings {
  final AppThemePalette themePalette;
  final String language;
  final String ttsVoiceLanguage;
  final bool soundEnabled;
  final bool vibrationEnabled;
  final bool ttsEnabled;
  final String soundName;
  final double alarmVolume;
  final int alarmDurationSec;
  final bool hasCompletedLanguageSetup;
  final String? userEmail;
  final String? userDisplayName;
  final String? userPhotoUrl;
  final bool isPremium;
  final String accountType; // 'guest' | 'google'
  final String? telegramChatId;
  final bool telegramAlertsEnabled;

  const AppSettings({
    this.themePalette = AppThemePalette.lightPurpleBlue,
    this.language = 'en',
    this.ttsVoiceLanguage = 'app_default',
    this.soundEnabled = true,
    this.vibrationEnabled = true,
    this.ttsEnabled = true,
    this.soundName = 'alarm_siren',
    this.alarmVolume = 1.0,
    this.alarmDurationSec = 5,
    this.hasCompletedLanguageSetup = false,
    this.userEmail,
    this.userDisplayName,
    this.userPhotoUrl,
    this.isPremium = false,
    this.accountType = 'guest',
    this.telegramChatId,
    this.telegramAlertsEnabled = false,
  });

  /// Helper whether user is logged in with Google
  bool get isSignedInWithGoogle => accountType == 'google' && userEmail != null && userEmail!.isNotEmpty;

  /// Helper whether Telegram bot integration is active
  bool get isTelegramConnected => telegramChatId != null && telegramChatId!.trim().isNotEmpty;

  /// Resolves effective TTS voice language code ('fa', 'en', 'ar', etc.)
  String get effectiveTtsLanguage =>
      ttsVoiceLanguage == 'app_default' ? language : ttsVoiceLanguage;

  static const Object _sentinel = Object();

  AppSettings copyWith({
    AppThemePalette? themePalette,
    String? language,
    String? ttsVoiceLanguage,
    bool? soundEnabled,
    bool? vibrationEnabled,
    bool? ttsEnabled,
    String? soundName,
    double? alarmVolume,
    int? alarmDurationSec,
    bool? hasCompletedLanguageSetup,
    Object? userEmail = _sentinel,
    Object? userDisplayName = _sentinel,
    Object? userPhotoUrl = _sentinel,
    bool? isPremium,
    String? accountType,
    Object? telegramChatId = _sentinel,
    bool? telegramAlertsEnabled,
  }) {
    return AppSettings(
      themePalette: themePalette ?? this.themePalette,
      language: language ?? this.language,
      ttsVoiceLanguage: ttsVoiceLanguage ?? this.ttsVoiceLanguage,
      soundEnabled: soundEnabled ?? this.soundEnabled,
      vibrationEnabled: vibrationEnabled ?? this.vibrationEnabled,
      ttsEnabled: ttsEnabled ?? this.ttsEnabled,
      soundName: soundName ?? this.soundName,
      alarmVolume: alarmVolume ?? this.alarmVolume,
      alarmDurationSec: alarmDurationSec ?? this.alarmDurationSec,
      hasCompletedLanguageSetup: hasCompletedLanguageSetup ?? this.hasCompletedLanguageSetup,
      userEmail: identical(userEmail, _sentinel) ? this.userEmail : (userEmail as String?),
      userDisplayName: identical(userDisplayName, _sentinel) ? this.userDisplayName : (userDisplayName as String?),
      userPhotoUrl: identical(userPhotoUrl, _sentinel) ? this.userPhotoUrl : (userPhotoUrl as String?),
      isPremium: isPremium ?? this.isPremium,
      accountType: accountType ?? this.accountType,
      telegramChatId: identical(telegramChatId, _sentinel) ? this.telegramChatId : (telegramChatId as String?),
      telegramAlertsEnabled: telegramAlertsEnabled ?? this.telegramAlertsEnabled,
    );
  }

  Map<String, dynamic> toJson() => {
        'themePalette': themePalette.name,
        'language': language,
        'ttsVoiceLanguage': ttsVoiceLanguage,
        'soundEnabled': soundEnabled,
        'vibrationEnabled': vibrationEnabled,
        'ttsEnabled': ttsEnabled,
        'soundName': soundName,
        'alarmVolume': alarmVolume,
        'alarmDurationSec': alarmDurationSec,
        'hasCompletedLanguageSetup': hasCompletedLanguageSetup,
        'userEmail': userEmail,
        'userDisplayName': userDisplayName,
        'userPhotoUrl': userPhotoUrl,
        'isPremium': isPremium,
        'accountType': accountType,
        'telegramChatId': telegramChatId,
        'telegramAlertsEnabled': telegramAlertsEnabled,
      };

  factory AppSettings.fromJson(Map<String, dynamic> json) {
    AppThemePalette palette = AppThemePalette.lightPurpleBlue;
    final paletteName = json['themePalette'] as String?;
    if (paletteName != null) {
      for (final p in AppThemePalette.values) {
        if (p.name == paletteName) {
          palette = p;
          break;
        }
      }
    }

    return AppSettings(
      themePalette: palette,
      language: (json['language'] as String?) ?? 'en',
      ttsVoiceLanguage: (json['ttsVoiceLanguage'] as String?) ?? 'app_default',
      soundEnabled: (json['soundEnabled'] as bool?) ?? true,
      vibrationEnabled: (json['vibrationEnabled'] as bool?) ?? true,
      ttsEnabled: (json['ttsEnabled'] as bool?) ?? true,
      soundName: (json['soundName'] as String?) ?? 'alarm_siren',
      alarmVolume: (json['alarmVolume'] as num?)?.toDouble() ?? 1.0,
      alarmDurationSec: (json['alarmDurationSec'] as int?) ?? 5,
      hasCompletedLanguageSetup: (json['hasCompletedLanguageSetup'] as bool?) ?? false,
      userEmail: json['userEmail'] as String?,
      userDisplayName: json['userDisplayName'] as String?,
      userPhotoUrl: json['userPhotoUrl'] as String?,
      isPremium: (json['isPremium'] as bool?) ?? false,
      accountType: (json['accountType'] as String?) ?? 'guest',
      telegramChatId: json['telegramChatId'] as String?,
      telegramAlertsEnabled: (json['telegramAlertsEnabled'] as bool?) ?? false,
    );
  }

  ThemeData buildThemeData() {
    switch (themePalette) {
      case AppThemePalette.darkGreen:
        return _buildTheme(
          isDark: true,
          scaffoldBg: const Color(0xFF090D16),
          surface: const Color(0xFF111827),
          surfaceElevated: const Color(0xFF1F2937),
          primary: const Color(0xFF10B981),
          secondary: const Color(0xFF06B6D4),
          border: const Color(0xFF374151),
          textPrimary: const Color(0xFFF9FAFB),
          textSecondary: const Color(0xFF9CA3AF),
          onPrimaryText: Colors.white,
        );
      case AppThemePalette.lightGreen:
        return _buildTheme(
          isDark: false,
          scaffoldBg: const Color(0xFFF3F4F6),
          surface: const Color(0xFFFFFFFF),
          surfaceElevated: const Color(0xFFE5E7EB),
          primary: const Color(0xFF059669),
          secondary: const Color(0xFF0891B2),
          border: const Color(0xFFD1D5DB),
          textPrimary: const Color(0xFF111827),
          textSecondary: const Color(0xFF4B5563),
          onPrimaryText: Colors.white,
        );
      case AppThemePalette.darkOrange:
        return _buildTheme(
          isDark: true,
          scaffoldBg: const Color(0xFF0C0A09),
          surface: const Color(0xFF1C1917),
          surfaceElevated: const Color(0xFF292524),
          primary: const Color(0xFFF97316),
          secondary: const Color(0xFFFBBF24),
          border: const Color(0xFF44403C),
          textPrimary: const Color(0xFFFAFAF9),
          textSecondary: const Color(0xFFA8A29E),
          onPrimaryText: Colors.white,
        );
      case AppThemePalette.lightOrange:
        return _buildTheme(
          isDark: false,
          scaffoldBg: const Color(0xFFFAF8F5),
          surface: const Color(0xFFFFFFFF),
          surfaceElevated: const Color(0xFFF4EFEA),
          primary: const Color(0xFFEA580C),
          secondary: const Color(0xFFD97706),
          border: const Color(0xFFE7E5E4),
          textPrimary: const Color(0xFF1C1917),
          textSecondary: const Color(0xFF78716C),
          onPrimaryText: Colors.white,
        );
      case AppThemePalette.darkPurpleBlue:
        return _buildTheme(
          isDark: true,
          scaffoldBg: const Color(0xFF0B0D1B),
          surface: const Color(0xFF13172E),
          surfaceElevated: const Color(0xFF1E2345),
          primary: const Color(0xFF8B5CF6), // Violet Purple
          secondary: const Color(0xFF3B82F6), // Royal Blue
          border: const Color(0xFF2E365E),
          textPrimary: const Color(0xFFF8FAFC),
          textSecondary: const Color(0xFF94A3B8),
          onPrimaryText: Colors.white,
        );
      case AppThemePalette.lightPurpleBlue:
        return _buildTheme(
          isDark: false,
          scaffoldBg: const Color(0xFFF5F6FF),
          surface: const Color(0xFFFFFFFF),
          surfaceElevated: const Color(0xFFEBEFFF),
          primary: const Color(0xFF7C3AED), // Deep Purple
          secondary: const Color(0xFF2563EB), // Sapphire Blue
          border: const Color(0xFFD6DBF5),
          textPrimary: const Color(0xFF0F172A),
          textSecondary: const Color(0xFF475569),
          onPrimaryText: Colors.white,
        );
      case AppThemePalette.darkGold:
        return _buildTheme(
          isDark: true,
          scaffoldBg: const Color(0xFF09090B), // Deep Obsidian Black
          surface: const Color(0xFF141416),
          surfaceElevated: const Color(0xFF1E1E22),
          primary: const Color(0xFFF59E0B), // Titanium Warm Gold
          secondary: const Color(0xFFFBBF24), // Champagne Gold
          border: const Color(0x4DF59E0B), // Golden crystalline border
          textPrimary: const Color(0xFFF9FAFB),
          textSecondary: const Color(0xFFD4D4D8),
          onPrimaryText: Colors.black,
        );
      case AppThemePalette.lightGold:
        return _buildTheme(
          isDark: false,
          scaffoldBg: const Color(0xFFFAF9F5), // Warm Titanium Alabaster
          surface: const Color(0xFFFFFFFF),
          surfaceElevated: const Color(0xFFF4F3EE),
          primary: const Color(0xFFD97706), // Titanium Amber Gold
          secondary: const Color(0xFFB45309), // Warm Metallic Gold
          border: const Color(0xFFFDE68A), // Light Golden Crystalline Border
          textPrimary: const Color(0xFF18181B),
          textSecondary: const Color(0xFF71717A),
          onPrimaryText: Colors.white,
        );
      case AppThemePalette.darkSapphire:
        return _buildTheme(
          isDark: true,
          scaffoldBg: const Color(0xFF030712), // Deep Midnight Navy
          surface: const Color(0xFF0B132B),
          surfaceElevated: const Color(0xFF172554),
          primary: const Color(0xFF38BDF8), // Platinum Cyan & Sapphire
          secondary: const Color(0xFF0284C7),
          border: const Color(0x4D38BDF8),
          textPrimary: const Color(0xFFF9FAFB),
          textSecondary: const Color(0xFF94A3B8),
          onPrimaryText: Colors.white,
        );
      case AppThemePalette.lightSapphire:
        return _buildTheme(
          isDark: false,
          scaffoldBg: const Color(0xFFF0F7FF), // Ice Pearl Blue
          surface: const Color(0xFFFFFFFF),
          surfaceElevated: const Color(0xFFE0F2FE),
          primary: const Color(0xFF0284C7), // Royal Sapphire Blue
          secondary: const Color(0xFF0369A1), // Deep Royal Cyan
          border: const Color(0xFFBAE6FD), // Light Sapphire Pearl Border
          textPrimary: const Color(0xFF0F172A),
          textSecondary: const Color(0xFF475569),
          onPrimaryText: Colors.white,
        );
    }
  }

  static ThemeData _buildTheme({
    required bool isDark,
    required Color scaffoldBg,
    required Color surface,
    required Color surfaceElevated,
    required Color primary,
    required Color secondary,
    required Color border,
    required Color textPrimary,
    required Color textSecondary,
    required Color onPrimaryText,
  }) {
    final textTheme = TextTheme(
      displayLarge: TextStyle(color: textPrimary, fontSize: 32, fontWeight: FontWeight.bold),
      displayMedium: TextStyle(color: textPrimary, fontSize: 24, fontWeight: FontWeight.bold),
      displaySmall: TextStyle(color: textPrimary, fontSize: 20, fontWeight: FontWeight.bold),
      headlineMedium: TextStyle(color: textPrimary, fontSize: 18, fontWeight: FontWeight.w700),
      headlineSmall: TextStyle(color: textPrimary, fontSize: 16, fontWeight: FontWeight.w600),
      titleLarge: TextStyle(color: textPrimary, fontSize: 16, fontWeight: FontWeight.w600),
      titleMedium: TextStyle(color: textPrimary, fontSize: 14, fontWeight: FontWeight.w600),
      titleSmall: TextStyle(color: textSecondary, fontSize: 12, fontWeight: FontWeight.w500),
      bodyLarge: TextStyle(color: textPrimary, fontSize: 14, fontWeight: FontWeight.normal),
      bodyMedium: TextStyle(color: textPrimary, fontSize: 13, fontWeight: FontWeight.normal),
      bodySmall: TextStyle(color: textSecondary, fontSize: 11, fontWeight: FontWeight.normal),
      labelLarge: TextStyle(color: onPrimaryText, fontSize: 13, fontWeight: FontWeight.bold),
      labelMedium: TextStyle(color: textSecondary, fontSize: 11, fontWeight: FontWeight.w500),
    );

    return ThemeData(
      useMaterial3: true,
      brightness: isDark ? Brightness.dark : Brightness.light,
      scaffoldBackgroundColor: scaffoldBg,
      canvasColor: scaffoldBg,
      cardColor: surface,
      dividerColor: border,
      textTheme: textTheme,
      colorScheme: ColorScheme(
        brightness: isDark ? Brightness.dark : Brightness.light,
        primary: primary,
        onPrimary: onPrimaryText,
        secondary: secondary,
        onSecondary: Colors.white,
        error: const Color(0xFFEF4444),
        onError: Colors.white,
        surface: surface,
        onSurface: textPrimary,
        surfaceContainerHighest: surfaceElevated,
        outline: border,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: surface,
        foregroundColor: textPrimary,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          color: textPrimary,
          fontSize: 16,
          fontWeight: FontWeight.bold,
        ),
        iconTheme: IconThemeData(color: textPrimary),
      ),
      cardTheme: CardThemeData(
        color: surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(color: border, width: 1),
        ),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: surface,
        titleTextStyle: TextStyle(color: textPrimary, fontSize: 16, fontWeight: FontWeight.bold),
        contentTextStyle: TextStyle(color: textSecondary, fontSize: 13),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: border, width: 1),
        ),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: surface,
        modalBackgroundColor: surface,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primary,
          foregroundColor: onPrimaryText,
          elevation: 0,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: primary,
          side: BorderSide(color: border),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceElevated,
        labelStyle: TextStyle(color: textSecondary, fontSize: 12),
        hintStyle: TextStyle(color: textSecondary.withValues(alpha: 0.6), fontSize: 12),
        prefixIconColor: textSecondary,
        suffixIconColor: textSecondary,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: primary, width: 1.5),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: surfaceElevated,
        contentTextStyle: TextStyle(color: textPrimary, fontSize: 13),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
          side: BorderSide(color: border),
        ),
        behavior: SnackBarBehavior.floating,
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) return Colors.white;
          return textSecondary;
        }),
        trackColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) return primary;
          return border;
        }),
      ),
    );
  }
}
