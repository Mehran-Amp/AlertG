import 'package:flutter/material.dart';
import '../../features/settings/services/settings_service.dart';
import '../config.dart';

/// Service managing optional Google Account Authentication and Cloud Sync
/// preparation.
///
/// AUTH-OFF-1: Google Sign-In is disabled until the server verifies Google
/// ID tokens. The previous implementation showed a mock Google dialog with
/// a hardcoded email (the project owner's account), which let any user on
/// any device sign in as that account. The cloud-sync pipeline itself
/// (`ServerAlertService.restoreUserAlertsFromCloud`, `claimGuestAlerts`,
/// `syncAllRulesToServer`) is unchanged and will be re-enabled once real
/// server-side token verification is in place.
class GoogleAuthService {
  /// AUTH-OFF-1: no-op. Returns false and shows nothing.
  ///
  /// Set [AppConfig.kCloudAccountEnabled] to true only after the server
  /// verifies Google ID tokens and a real device build has been tested.
  static Future<bool> promptGoogleSignIn(
      BuildContext context,
      SettingsService settingsService,
      String lang,
      ) async {
    if (!AppConfig.kCloudAccountEnabled) {
      debugPrint('ℹ [GoogleAuth] Cloud account is disabled (AUTH-OFF-1).');
      return false;
    }
    debugPrint('⚠ [GoogleAuth] Cloud account flag is on but feature is not implemented yet.');
    return false;
  }
}