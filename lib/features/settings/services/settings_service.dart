import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import '../../../core/services/native_widget_sync_service.dart';
import '../../../core/services/server_alert_service.dart';
import '../models/app_settings.dart';

/// Local-First Persistent Settings Service.
/// Stores user preferences in `<storageDirectoryPath>/settings.json`.
class SettingsService extends ChangeNotifier {
  final String _storageDirectoryPath;
  AppSettings _settings = const AppSettings();

  SettingsService(this._storageDirectoryPath);

  AppSettings get settings => _settings;

  File get _file => File('$_storageDirectoryPath/settings.json');

  Future<void> load() async {
    try {
      final file = _file;
      if (await file.exists()) {
        final content = await file.readAsString();
        if (content.trim().isNotEmpty) {
          final decoded = jsonDecode(content) as Map<String, dynamic>;
          _settings = AppSettings.fromJson(decoded);
          notifyListeners();
          NativeWidgetSyncService.syncTheme(_settings.themePalette);
          return;
        }
      }
    } catch (e) {
      debugPrint('Failed to load settings.json: $e');
    }
    _settings = const AppSettings();
    notifyListeners();
    NativeWidgetSyncService.syncTheme(_settings.themePalette);
  }

  Future<void> update(AppSettings newSettings) async {
    final themeChanged = _settings.themePalette != newSettings.themePalette;
    _settings = newSettings;
    notifyListeners();
    if (themeChanged) {
      NativeWidgetSyncService.syncTheme(_settings.themePalette);
    }
    try {
      final file = _file;
      await file.writeAsString(jsonEncode(_settings.toJson()));
    } catch (e) {
      debugPrint('Failed to save settings.json: $e');
    }
  }

  Future<void> setPalette(AppThemePalette palette) async {
    await update(_settings.copyWith(themePalette: palette));
  }

  Future<void> setLanguage(String langCode) async {
    await update(_settings.copyWith(language: langCode));
  }

  Future<void> toggleSound(bool val) async {
    await update(_settings.copyWith(soundEnabled: val));
  }

  Future<void> toggleVibration(bool val) async {
    await update(_settings.copyWith(vibrationEnabled: val));
  }

  Future<void> toggleTts(bool val) async {
    await update(_settings.copyWith(ttsEnabled: val));
  }

  Future<void> setSoundName(String soundId) async {
    await update(_settings.copyWith(soundName: soundId));
  }

  Future<void> setAlarmVolume(double volume) async {
    await update(_settings.copyWith(alarmVolume: volume));
  }

  Future<void> setTtsVoiceLanguage(String voiceLang) async {
    await update(_settings.copyWith(ttsVoiceLanguage: voiceLang));
  }

  Future<void> completeLanguageSetup() async {
    await update(_settings.copyWith(hasCompletedLanguageSetup: true));
  }

  Future<void> setTelegramChatId(String? chatId) async {
    final cleanId = (chatId != null && chatId.trim().isNotEmpty) ? chatId.trim() : null;
    await update(_settings.copyWith(
      telegramChatId: cleanId,
      telegramAlertsEnabled: cleanId != null,
    ));

    // Automatically sync Telegram connection state to cloud for logged in user
    final email = _settings.userEmail;
    if (email != null && email.isNotEmpty) {
      ServerAlertService.saveUserTelegramStatus(
        userId: email,
        chatId: cleanId,
        isConnected: cleanId != null,
      );
    }
  }

  Future<void> toggleTelegramAlerts(bool enabled) async {
    await update(_settings.copyWith(telegramAlertsEnabled: enabled));
  }

  Future<void> setPremium(bool isPremium) async {
    await update(_settings.copyWith(isPremium: isPremium));
  }

  Future<void> signInWithGoogle({
    required String email,
    required String displayName,
    String? photoUrl,
  }) async {
    await update(_settings.copyWith(
      accountType: 'google',
      userEmail: email,
      userDisplayName: displayName,
      userPhotoUrl: photoUrl,
      isPremium: true, // Google sign-in unlocks Premium perks!
    ));
  }

  Future<void> signOut() async {
    await update(_settings.copyWith(
      accountType: 'guest',
      userEmail: null,
      userDisplayName: null,
      userPhotoUrl: null,
      isPremium: false,
      telegramChatId: null,
      telegramAlertsEnabled: false,
    ));
  }
}
