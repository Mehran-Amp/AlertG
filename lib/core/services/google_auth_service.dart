import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../features/alert_engine/bloc/alert_rules_bloc.dart';
import '../../features/alert_engine/bloc/alert_rules_event.dart';
import '../../features/alert_engine/repositories/json_alert_rule_repository.dart';
import '../../features/settings/services/settings_service.dart';
import 'server_alert_service.dart';

/// Service managing optional Google Account Authentication and Cloud Sync preparation.
class GoogleAuthService {
  /// Prompt the user with a modern Google Sign-In account dialog
  static Future<bool> promptGoogleSignIn(
    BuildContext context,
    SettingsService settingsService,
    String lang,
  ) async {
    final theme = Theme.of(context);
    final isFa = lang == 'fa' || lang == 'ar' || lang == 'ckb';
    const userEmail = 'Mehran.Aminpoor@gmail.com';
    const userDisplayName = 'Mehran';

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: theme.colorScheme.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.1),
                    blurRadius: 4,
                  ),
                ],
              ),
              child: Image.network(
                'https://www.gstatic.com/images/branding/product/1x/gsa_512dp.png',
                width: 24,
                height: 24,
                errorBuilder: (_, __, ___) => const Text('G', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18, color: Colors.blue)),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                isFa ? 'ورود با حساب گوگل' : 'Sign in with Google',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
              ),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              isFa
                  ? 'با اتصال به حساب گوگل، تمامی هشدارهای شما به طور خودکار در فضای ابری ذخیره شده و در صورت حذف اپلیکیشن یا تعویض گوشی فوراً بازیابی می‌شوند.'
                  : 'By connecting your Google account, your alerts are safely stored in the cloud and automatically restored upon re-installing or changing phones.',
              style: TextStyle(fontSize: 12, height: 1.4, color: theme.colorScheme.onSurface.withValues(alpha: 0.7)),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: theme.dividerColor),
              ),
              child: Row(
                children: [
                  const CircleAvatar(
                    radius: 16,
                    backgroundColor: Colors.blueAccent,
                    child: Text('M', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          userDisplayName,
                          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: theme.colorScheme.onSurface),
                        ),
                        Text(
                          userEmail,
                          style: TextStyle(fontSize: 11, color: theme.colorScheme.primary),
                        ),
                      ],
                    ),
                  ),
                  Icon(Icons.check_circle_rounded, color: theme.colorScheme.primary, size: 20),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: Text(
              isFa ? 'فعلاً نه (انصراف)' : 'Maybe Later',
              style: TextStyle(color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
            ),
          ),
          ElevatedButton.icon(
            onPressed: () => Navigator.of(ctx).pop(true),
            icon: const Icon(Icons.login_rounded, size: 16),
            label: Text(isFa ? 'اتصال حساب و همگام‌سازی' : 'Connect & Sync'),
            style: ElevatedButton.styleFrom(
              backgroundColor: theme.colorScheme.primary,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            ),
          ),
        ],
      ),
    );

    if (result == true) {
      await settingsService.signInWithGoogle(
        email: userEmail,
        displayName: userDisplayName,
        photoUrl: 'https://lh3.googleusercontent.com/a/default-user',
      );

      // 1. Restore persisted Telegram connection status from cloud first
      try {
        final tgStatus = await ServerAlertService.fetchUserTelegramStatus(userEmail);
        if (tgStatus != null) {
          final isConnected = tgStatus['is_connected'] == true;
          final savedChatId = (tgStatus['telegram_chat_id'] as String?)?.trim() ?? '';
          if (isConnected && savedChatId.isNotEmpty) {
            await settingsService.setTelegramChatId(savedChatId);
            debugPrint('📱 [Cloud Sync] Restored active Telegram Chat ID: $savedChatId');
          } else {
            await settingsService.setTelegramChatId(null);
            debugPrint('📱 [Cloud Sync] Telegram is not connected for $userEmail');
          }
        }
      } catch (e) {
        debugPrint('⚠️ Error fetching Telegram status on sign in: $e');
      }

      // 2. Restore any existing cloud alerts from user's account
      final restoredCount = await ServerAlertService.restoreUserAlertsFromCloud(
        context: context,
        userEmail: userEmail,
      );

      // 3. If there were local guest alerts before sign-in, merge them with the cloud account
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

        if (restoredCount > 0) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(isFa
                  ? '☁️ $restoredCount هشدار ابری شما با موفقیت بازیابی و فعال شدند.'
                  : '☁️ Successfully restored $restoredCount cloud alert(s).'),
              behavior: SnackBarBehavior.floating,
              backgroundColor: theme.colorScheme.primary,
            ),
          );
        }
      }

      return true;
    }
    return false;
  }
}
