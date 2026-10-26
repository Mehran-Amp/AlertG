import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import '../../features/alert_engine/bloc/alert_rules_bloc.dart';
import '../../features/alert_engine/bloc/alert_rules_event.dart';
import '../../features/alert_engine/repositories/json_alert_rule_repository.dart';
import '../../features/settings/services/settings_service.dart';
import 'fcm_notification_service.dart';
import 'server_alert_service.dart';

/// Service managing optional Google Account Authentication and Cloud Sync preparation.
class GoogleAuthService {
  static GoogleSignIn _googleSignIn = GoogleSignIn(
    scopes: ['email'],
  );

  @visibleForTesting
  static GoogleSignIn get googleSignInInstance => _googleSignIn;

  @visibleForTesting
  static set googleSignInInstance(GoogleSignIn instance) {
    _googleSignIn = instance;
  }

  @visibleForTesting
  static Future<GoogleSignInAccount?> Function()? signInOverride;

  @visibleForTesting
  static Future<void> Function()? signOutOverride;

  @visibleForTesting
  static bool forceAccountChooserInvoked = false;

  /// Internal sign-in call ensuring the account chooser dialog is always displayed.
  /// Calling `signOut()` prior to `signIn()` purges any cached OS account session,
  /// matching the expected behavior of `prompt: 'select_account'`.
  static Future<GoogleSignInAccount?> signIn() async {
    forceAccountChooserInvoked = true;
    try {
      if (signOutOverride != null) {
        await signOutOverride!();
      } else {
        await _googleSignIn.signOut();
      }
    } catch (e) {
      debugPrint('ℹ️ [GoogleAuth] Notice clearing previous session: $e');
    }

    if (signInOverride != null) {
      return await signInOverride!();
    }
    return await _googleSignIn.signIn();
  }

  /// Complete logout from Google account.
  /// Purges cached account credentials so future sign-in requests force the account chooser.
  static Future<void> signOut() async {
    try {
      if (signOutOverride != null) {
        await signOutOverride!();
      } else {
        await _googleSignIn.signOut();
      }
    } catch (e) {
      debugPrint('⚠️ [GoogleAuth] Error during Google signOut: $e');
    }
  }

  /// Prompt the user to sign in with Google and synchronize cloud alerts.
  static Future<bool> promptGoogleSignIn(
    BuildContext context,
    SettingsService settingsService,
    String lang,
  ) async {
    final theme = Theme.of(context);
    final isFa = lang == 'fa' || lang == 'ar' || lang == 'ckb';

    final GoogleSignInAccount? account;
    try {
      account = await signIn();
    } catch (e) {
      debugPrint('⚠️ [GoogleAuth] Sign-in error: $e');
      return false;
    }

    if (account == null) {
      // User cancelled account selection
      return false;
    }

    final userEmail = account.email;
    final userDisplayName = (account.displayName != null && account.displayName!.trim().isNotEmpty)
        ? account.displayName!.trim()
        : userEmail.split('@').first;
    final userPhotoUrl = account.photoUrl;

    await settingsService.signInWithGoogle(
      email: userEmail,
      displayName: userDisplayName,
      photoUrl: userPhotoUrl,
    );

      // 1. Restore persisted Telegram connection status from cloud and persistent account cache
      try {
        final tgStatus = await ServerAlertService.fetchUserTelegramStatus(userEmail);
        String? targetChatId;
        if (tgStatus != null && tgStatus['is_connected'] == true) {
          targetChatId = (tgStatus['telegram_chat_id'] as String?)?.trim();
        }

        // Fallback A: Check local account profile snapshot
        if (targetChatId == null || targetChatId.isEmpty) {
          try {
            final dir = await getApplicationDocumentsDirectory();
            final profFile = File('${dir.path}/account_profile_${userEmail.trim().toLowerCase()}.json');
            if (await profFile.exists()) {
              final profData = jsonDecode(await profFile.readAsString());
              final cId = (profData['telegram_chat_id'] as String?)?.trim();
              if (cId != null && cId.isNotEmpty) {
                targetChatId = cId;
              }
            }
          } catch (_) {}
        }

        // Fallback B: Check last connected bot file
        if (targetChatId == null || targetChatId.isEmpty) {
          try {
            final dir = await getApplicationDocumentsDirectory();
            final lastTgFile = File('${dir.path}/last_telegram_chat.txt');
            if (await lastTgFile.exists()) {
              final lastTg = (await lastTgFile.readAsString()).trim();
              if (lastTg.isNotEmpty) {
                targetChatId = lastTg;
              }
            }
          } catch (_) {}
        }

        if (targetChatId != null && targetChatId.isNotEmpty) {
          await settingsService.setTelegramChatId(targetChatId);
          debugPrint('📱 [Cloud Sync] Restored active Telegram Chat ID: $targetChatId');
        }
      } catch (e) {
        debugPrint('⚠️ Error fetching Telegram status on sign in: $e');
      }

      // 2. Explicitly claim any guest alerts created on this device under 'user_default'
      int claimedCount = 0;
      try {
        final fcmToken = await FCMNotificationService.getFCMToken();
        claimedCount = await ServerAlertService.claimGuestAlerts(
          userId: userEmail,
          fcmToken: fcmToken,
        );
        debugPrint('🎉 [GoogleAuth] Claimed $claimedCount guest alert(s) for $userEmail');
      } catch (e) {
        debugPrint('⚠️ Error claiming guest alerts on sign in: $e');
      }

      // 3. Restore all cloud alerts from user's account (including newly claimed alerts)
      final restoredCount = await ServerAlertService.restoreUserAlertsFromCloud(
        context: context,
        userEmail: userEmail,
      );

      // Check if restored alerts or persistent file gave us the active Telegram Chat ID
      if (settingsService.settings.telegramChatId == null || settingsService.settings.telegramChatId!.isEmpty) {
        try {
          final dir = await getApplicationDocumentsDirectory();
          final profFile = File('${dir.path}/account_profile_${userEmail.trim().toLowerCase()}.json');
          if (await profFile.exists()) {
            final profData = jsonDecode(await profFile.readAsString());
            final cId = (profData['telegram_chat_id'] as String?)?.trim();
            if (cId != null && cId.isNotEmpty) {
              await settingsService.setTelegramChatId(cId);
              debugPrint('📱 [Cloud Sync] Restored active Telegram Chat ID from profile: $cId');
            }
          }
        } catch (_) {}
      }

      // 4. If there were local guest alerts before sign-in, merge them with the cloud account
      try {
        final repo = context.read<JsonAlertRuleRepository>();
        if (repo.allRules.isNotEmpty) {
          await ServerAlertService.syncAllRulesToServer(repo.allRules, userId: userEmail);
        }
      } catch (_) {}

      if (context.mounted) {
        try {
          context.read<AlertRulesBloc>().add(const LoadAlertRules());
        } catch (_) {}

        final totalAlerts = restoredCount + claimedCount;
        if (totalAlerts > 0) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(isFa
                  ? '☁️ $totalAlerts هشدار با موفقیت بازیابی و به حساب شما منتقل شدند.'
                  : '☁️ Successfully restored $totalAlerts alert(s) to your account.'),
              behavior: SnackBarBehavior.floating,
              backgroundColor: theme.colorScheme.primary,
            ),
          );
        }
      }

    return true;
  }
}
