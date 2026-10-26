import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';
import '../../../core/localization/app_strings.dart';
import '../../../core/services/google_auth_service.dart';
import '../../../core/services/server_alert_service.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/utils/app_lifecycle_helper.dart';
import '../../alert_engine/bloc/alert_rules_bloc.dart';
import '../../alert_engine/bloc/alert_rules_event.dart';
import '../../alert_engine/repositories/json_alert_rule_repository.dart';
import '../../notifications/repositories/notification_repository.dart';
import '../../notifications/services/notification_service.dart';
import '../models/app_settings.dart';
import '../services/settings_service.dart';
import '../services/sound_manager.dart';
import '../../../core/services/tts_service.dart';
import '../widgets/device_health_card.dart';
import 'debug_diagnostics_page.dart';
import 'notification_health_page.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  bool _isBatteryExempt = false;

  final List<Map<String, String>> _supportedLanguages = const [
    {'code': 'fa', 'name': 'فارسی', 'native': 'فارسی', 'flag': '🇮🇷'},
    {'code': 'en', 'name': 'English', 'native': 'English', 'flag': '🇺🇸'},
    {'code': 'ckb', 'name': 'Kurdish Sorani', 'native': 'کوردی سۆرانی', 'flag': '☀️'},
    {'code': 'ar', 'name': 'Arabic', 'native': 'العربية', 'flag': '🇸🇦'},
    {'code': 'de', 'name': 'German', 'native': 'Deutsch', 'flag': '🇩🇪'},
    {'code': 'fr', 'name': 'French', 'native': 'Français', 'flag': '🇫🇷'},
    {'code': 'es', 'name': 'Spanish', 'native': 'Español', 'flag': '🇪🇸'},
    {'code': 'tr', 'name': 'Turkish', 'native': 'Türkçe', 'flag': '🇹🇷'},
    {'code': 'zh', 'name': 'Chinese', 'native': '中文', 'flag': '🇨🇳'},
    {'code': 'ko', 'name': 'Korean', 'native': '한국어', 'flag': '🇰🇷'},
  ];

  @override
  void initState() {
    super.initState();
    _checkBatteryStatus();
  }

  Future<void> _checkBatteryStatus() async {
    if (defaultTargetPlatform == TargetPlatform.android) {
      final status = await Permission.ignoreBatteryOptimizations.status;
      if (mounted) {
        setState(() {
          _isBatteryExempt = status.isGranted;
        });
      }
    }
  }

  Future<void> _requestBatteryExemption(String lang) async {
    final status = await Permission.ignoreBatteryOptimizations.request();
    if (mounted) {
      setState(() {
        _isBatteryExempt = status.isGranted;
      });
      if (status.isGranted) {
        final theme = Theme.of(context);
        ScaffoldMessenger.of(context).hideCurrentSnackBar();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            duration: const Duration(seconds: 3),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            content: Text(AppStrings.get('battery_exempt_success', lang)),
            backgroundColor: theme.colorScheme.surfaceContainerHighest,
          ),
        );
      }
    }
  }

  void _showLanguagePicker(BuildContext context, SettingsService settingsService, String currentLang) {
    final theme = Theme.of(context);
    final isRtl = AppStrings.isRtl(currentLang);

    showModalBottomSheet(
      context: context,
      backgroundColor: theme.colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => Directionality(
        textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    AppStrings.get('select_language', currentLang),
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: theme.colorScheme.onSurface,
                    ),
                  ),
                  IconButton(
                    icon: Icon(Icons.close_rounded, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
                    onPressed: () => Navigator.pop(ctx),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Expanded(
                child: ListView.separated(
                  itemCount: _supportedLanguages.length,
                  separatorBuilder: (_, __) => Divider(height: 1, color: theme.dividerColor),
                  itemBuilder: (context, index) {
                    final l = _supportedLanguages[index];
                    final isSelected = currentLang == l['code'];
                    return Material(
                      color: Colors.transparent,
                      child: ListTile(
                        leading: Text(l['flag']!, style: const TextStyle(fontSize: 22)),
                        title: Text(
                          l['native']!,
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            fontSize: 14,
                            color: theme.colorScheme.onSurface,
                          ),
                        ),
                        subtitle: Text(
                          l['name']!,
                          style: TextStyle(
                            fontSize: 11,
                            color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
                          ),
                        ),
                        trailing: isSelected
                            ? Icon(Icons.check_circle_rounded, color: theme.colorScheme.primary)
                            : null,
                        selected: isSelected,
                        selectedTileColor: theme.colorScheme.primary.withValues(alpha: 0.12),
                        onTap: () async {
                          await settingsService.setLanguage(l['code']!);
                          if (ctx.mounted) Navigator.pop(ctx);
                        },
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showSoundPicker(BuildContext context, SettingsService settingsService, String currentSoundId, String lang) {
    final theme = Theme.of(context);
    final isRtl = AppStrings.isRtl(lang);

    showModalBottomSheet(
      context: context,
      backgroundColor: theme.colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) => Directionality(
          textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.music_note_rounded, size: 22),
                        const SizedBox(width: 8),
                        Text(
                          AppStrings.get('select_alarm_sound', lang),
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.onSurface,
                          ),
                        ),
                      ],
                    ),
                    IconButton(
                      icon: Icon(Icons.close_rounded, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
                      onPressed: () {
                        SoundManager().stop();
                        Navigator.pop(ctx);
                      },
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Expanded(
                  child: ListView.separated(
                    itemCount: SoundManager.presets.length,
                    separatorBuilder: (_, __) => Divider(height: 1, color: theme.dividerColor),
                    itemBuilder: (context, index) {
                      final preset = SoundManager.presets[index];
                      final isSelected = currentSoundId == preset.id;
                      final isPlaying = SoundManager().isSoundPlaying(preset.id);
                      final title = preset.getTitle(lang);

                      return InkWell(
                        onTap: () async {
                          await SoundManager().playPreset(preset.id, volume: settingsService.settings.alarmVolume);
                          await settingsService.setSoundName(preset.id);
                          if (ctx.mounted) {
                            setModalState(() {});
                          }
                        },
                        borderRadius: BorderRadius.circular(12),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                          decoration: BoxDecoration(
                            color: isSelected
                                ? theme.colorScheme.primary.withValues(alpha: 0.1)
                                : Colors.transparent,
                            borderRadius: BorderRadius.circular(12),
                            border: isSelected
                                ? Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.35))
                                : null,
                          ),
                          child: Row(
                            children: [
                              Text(preset.icon, style: const TextStyle(fontSize: 22)),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Text(
                                  title,
                                  style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    fontSize: 13,
                                    color: isSelected ? theme.colorScheme.primary : theme.colorScheme.onSurface,
                                  ),
                                ),
                              ),
                              IconButton(
                                icon: Icon(
                                  isPlaying ? Icons.stop_circle_rounded : Icons.play_circle_filled_rounded,
                                  color: isPlaying ? AppTokens.negative : theme.colorScheme.primary,
                                  size: 28,
                                ),
                                onPressed: () async {
                                  if (isPlaying) {
                                    await SoundManager().stop();
                                  } else {
                                    await SoundManager().playPreset(preset.id, volume: settingsService.settings.alarmVolume);
                                  }
                                  setModalState(() {});
                                },
                              ),
                              if (isSelected)
                                Icon(Icons.check_circle_rounded, color: theme.colorScheme.primary, size: 22),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: () {
                      SoundManager().stop();
                      Navigator.pop(ctx);
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: theme.colorScheme.primary,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      padding: const EdgeInsets.symmetric(vertical: 12),
                    ),
                    child: Text(AppStrings.get('confirm_sound_btn', lang), style: const TextStyle(fontWeight: FontWeight.bold)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ).whenComplete(() {
      SoundManager().stop();
    });
  }

  Widget _buildTelegramStepItem({
    required String stepNum,
    required String text,
    required ThemeData theme,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 22,
          height: 22,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: const Color(0xFF0288D1).withValues(alpha: 0.18),
            shape: BoxShape.circle,
          ),
          child: Text(
            stepNum,
            style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.bold,
              color: Color(0xFF0288D1),
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            text,
            style: TextStyle(
              fontSize: 11,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.85),
              height: 1.35,
            ),
          ),
        ),
      ],
    );
  }

  void _showTelegramConnectSheet(BuildContext context, SettingsService settingsService, String currentLang) {
    final theme = Theme.of(context);
    final isRtl = AppStrings.isRtl(currentLang);
    final isFa = currentLang == 'fa' || currentLang == 'ar' || currentLang == 'ckb';
    final currentChatId = settingsService.settings.telegramChatId;
    final textController = TextEditingController(text: currentChatId != null && currentChatId != '@aegkalair_bot' ? currentChatId : '');

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: theme.colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => StatefulBuilder(
        builder: (context, setSheetState) => Directionality(
          textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
          child: Padding(
            padding: EdgeInsets.only(
              left: 20,
              right: 20,
              top: 20,
              bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
            ),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Title Bar
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: const Color(0xFF29B6F6).withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Icon(Icons.send_rounded, color: Color(0xFF29B6F6), size: 22),
                          ),
                          const SizedBox(width: 10),
                          Text(
                            isFa ? 'اتصال به تلگرام و ثبت شناسه چت' : 'Connect Telegram & Set ID',
                            style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.bold,
                              color: theme.colorScheme.onSurface,
                            ),
                          ),
                        ],
                      ),
                      IconButton(
                        icon: Icon(Icons.close_rounded, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
                        onPressed: () => Navigator.pop(ctx),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),

                  // 3-Step Guidance Box
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: const Color(0xFF29B6F6).withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: const Color(0xFF29B6F6).withValues(alpha: 0.25), width: 1),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          isFa ? 'راهنمای ۳ مرحله‌ای فعال‌سازی هشدارها در تلگرام:' : '3-Step Setup Guide:',
                          style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF0288D1),
                          ),
                        ),
                        const SizedBox(height: 8),
                        _buildTelegramStepItem(
                          stepNum: '۱',
                          text: isFa
                              ? 'روی دکمهٔ «۱. باز کردن ربات تلگرام» در زیر بزنید و در تلگرام گزینه Start یا /start را ارسال کنید.'
                              : 'Tap "1. Open Telegram Bot" below and send /start in Telegram.',
                          theme: theme,
                        ),
                        const SizedBox(height: 6),
                        _buildTelegramStepItem(
                          stepNum: '۲',
                          text: isFa
                              ? 'ربات بلافاصله شناسهٔ اختصاصی عددی (Chat ID) شما را می‌فرستد؛ آن را لمس کرده و کپی کنید.'
                              : 'The bot replies with your unique numerical Chat ID; tap to copy it.',
                          theme: theme,
                        ),
                        const SizedBox(height: 6),
                        _buildTelegramStepItem(
                          stepNum: '۳',
                          text: isFa
                              ? 'به اینجا برگردید، شناسه را در کادر زیر وارد (یا Paste) کرده و دکمهٔ «۲. تأیید و اتصال نهایی» را بزنید.'
                              : 'Paste your Chat ID into the box below and tap "2. Confirm & Connect".',
                          theme: theme,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),

                  // Button 1: Open Bot directly
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: () async {
                        await AppLifecycleHelper.openTelegramBot();
                      },
                      icon: const Icon(Icons.open_in_new_rounded, size: 18),
                      label: Text(
                        isFa ? '۱. باز کردن ربات تلگرام (@aegkalair_bot)' : '1. Open Telegram Bot (@aegkalair_bot)',
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
                      ),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFF0288D1),
                        side: const BorderSide(color: Color(0xFF0288D1), width: 1.5),
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    isFa
                        ? '💡 با لمس دکمه بالا، ربات در تلگرام باز می‌شود. دکمه Start را بزنید، شناسه عددی را کپی کرده و به این پنجره بازگردید.'
                        : '💡 Tapping opens the bot in Telegram. Tap Start, copy your unique Chat ID, and return to this window.',
                    style: TextStyle(
                      fontSize: 10.5,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
                      height: 1.3,
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Text Box for Chat ID
                  Text(
                    isFa ? 'شناسه تلگرام شما (Chat ID عددی یا نام کاربری):' : 'Your Telegram Chat ID (Number or @username):',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.8),
                    ),
                  ),
                  const SizedBox(height: 6),
                  TextField(
                    controller: textController,
                    keyboardType: TextInputType.text,
                    style: const TextStyle(fontSize: 14, fontFamily: 'monospace', fontWeight: FontWeight.bold),
                    decoration: InputDecoration(
                      hintText: isFa ? 'مثلاً: 123456789 یا @username' : 'e.g. 123456789 or @username',
                      hintStyle: TextStyle(
                        fontSize: 12,
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.35),
                        fontFamily: 'sans-serif',
                      ),
                      prefixIcon: const Icon(Icons.badge_rounded, color: Color(0xFF29B6F6), size: 20),
                      suffixIcon: IconButton(
                        icon: const Icon(Icons.content_paste_rounded, size: 18),
                        tooltip: isFa ? 'جای‌گذاری از کلیپ‌بورد' : 'Paste from clipboard',
                        onPressed: () async {
                          final data = await Clipboard.getData(Clipboard.kTextPlain);
                          if (data?.text != null && data!.text!.trim().isNotEmpty) {
                            textController.text = data.text!.trim();
                          }
                        },
                      ),
                      filled: true,
                      fillColor: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: BorderSide(color: theme.dividerColor),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(color: Color(0xFF0288D1), width: 1.8),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Button 2: Save and Connect
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: () async {
                        final entered = textController.text.trim();
                        if (entered.isEmpty) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(isFa ? 'لطفاً شناسه تلگرام (Chat ID) خود را وارد کنید.' : 'Please enter your Telegram Chat ID.'),
                              backgroundColor: AppTokens.negative,
                              behavior: SnackBarBehavior.floating,
                            ),
                          );
                          return;
                        }

                        // 1. Save chat ID in settings
                        await settingsService.setTelegramChatId(entered);

                        // 2. Persist to disk files
                        final email = settingsService.settings.userEmail;
                        final targetUid = (email != null && email.trim().isNotEmpty) ? email.trim() : 'user_default';
                        try {
                          final dir = await getApplicationDocumentsDirectory();
                          final lastTgFile = File('${dir.path}/last_telegram_chat.txt');
                          await lastTgFile.writeAsString(entered);

                          if (email != null && email.trim().isNotEmpty) {
                            final profFile = File('${dir.path}/account_profile_${email.trim().toLowerCase()}.json');
                            await profFile.writeAsString(jsonEncode({
                              'email': email,
                              'telegram_chat_id': entered,
                              'is_connected': true,
                              'last_updated': DateTime.now().toIso8601String(),
                            }));
                          }
                        } catch (_) {}

                        // 3. Save to server profile and sync all active alert rules
                        ServerAlertService.saveUserTelegramStatus(
                          userId: targetUid,
                          chatId: entered,
                          isConnected: true,
                        );
                        if (context.mounted) {
                          try {
                            final repo = context.read<JsonAlertRuleRepository>();
                            if (repo.allRules.isNotEmpty) {
                              ServerAlertService.syncAllRulesToServer(repo.allRules, userId: targetUid);
                            }
                          } catch (_) {}

                          ServerAlertService.syncWithServer(context);
                          Navigator.pop(ctx);
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(isFa ? '🎉 شناسه تلگرام ($entered) ثبت شد! وضعیت: متصل به تلگرام ✅' : '🎉 Telegram ID ($entered) saved! Status: CONNECTED ✅'),
                              backgroundColor: AppTokens.positive,
                              behavior: SnackBarBehavior.floating,
                            ),
                          );
                        }
                      },
                      icon: const Icon(Icons.check_circle_rounded, size: 18),
                      label: Text(
                        isFa ? '۲. تأیید و اتصال به تلگرام (Connect)' : '2. Confirm & Connect',
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF0288D1),
                        foregroundColor: Colors.white,
                        elevation: 2,
                        padding: const EdgeInsets.symmetric(vertical: 13),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _testAlarm(BuildContext context, String lang) async {
    final notifService = context.read<NotificationService>();
    final settingsService = context.read<SettingsService>();
    final theme = Theme.of(context);

    // Ensure permissions are granted
    await notifService.requestPermissions();

    await notifService.showCriticalAlert(
      id: 99999,
      title: '🟢 BTC/USDT +3.52% \$87,420.00 ▲',
      body: '📝 ${AppStrings.get('test_alert_body', lang)}',
      soundName: settingsService.settings.soundName,
      volume: settingsService.settings.alarmVolume,
      soundEnabled: settingsService.settings.soundEnabled,
      vibrationEnabled: settingsService.settings.vibrationEnabled,
    );

    if (context.mounted) {
      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(AppStrings.get('test_alert_body', lang)),
          backgroundColor: theme.colorScheme.surfaceContainerHighest,
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 3),
        ),
      );
    }
  }

  Future<void> _exportBackup(BuildContext context, String lang) async {
    final repo = context.read<JsonAlertRuleRepository>();
    final theme = Theme.of(context);
    final jsonString = await repo.exportAlertsToJson();
    await Clipboard.setData(ClipboardData(text: jsonString));

    if (context.mounted) {
      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(AppStrings.get('backup_copied', lang)),
          backgroundColor: theme.colorScheme.surfaceContainerHighest,
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 3),
        ),
      );
    }
  }

  Future<void> _importBackup(BuildContext context, String lang) async {
    final controller = TextEditingController();
    final theme = Theme.of(context);
    final isRtl = AppStrings.isRtl(lang);

    final jsonString = await showDialog<String>(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
        child: AlertDialog(
          backgroundColor: theme.colorScheme.surface,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Text(
            AppStrings.get('restore_backup', lang),
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: theme.colorScheme.onSurface),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                AppStrings.get('restore_dialog_hint', lang),
                style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurface.withValues(alpha: 0.7)),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: controller,
                maxLines: 6,
                style: TextStyle(fontFamily: 'monospace', fontSize: 12, color: theme.colorScheme.onSurface),
                decoration: InputDecoration(
                  hintText: '[{"uuid": "...", "marketSymbol": "BTCUSDT", ...}]',
                  filled: true,
                  fillColor: theme.colorScheme.surfaceContainerHighest,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: Text(
                AppStrings.get('cancel', lang),
                style: TextStyle(color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
              ),
            ),
            ElevatedButton(
              onPressed: () => Navigator.of(ctx).pop(controller.text.trim()),
              style: ElevatedButton.styleFrom(
                backgroundColor: theme.colorScheme.primary,
                foregroundColor: Colors.white,
              ),
              child: Text(AppStrings.get('restore_dialog_btn', lang)),
            ),
          ],
        ),
      ),
    );

    if (jsonString != null && jsonString.isNotEmpty && context.mounted) {
      try {
        final repo = context.read<JsonAlertRuleRepository>();
        final count = await repo.importAlertsFromJson(jsonString);
        if (context.mounted) {
          ScaffoldMessenger.of(context).hideCurrentSnackBar();
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('🎉 $count ${AppStrings.get('restore_success', lang)}'),
              backgroundColor: theme.colorScheme.surfaceContainerHighest,
              behavior: SnackBarBehavior.floating,
              duration: const Duration(seconds: 3),
            ),
          );
        }
      } catch (e) {
        if (context.mounted) {
          ScaffoldMessenger.of(context).hideCurrentSnackBar();
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(AppStrings.get('format_error_json', lang)),
              backgroundColor: AppTokens.negative,
              behavior: SnackBarBehavior.floating,
              duration: const Duration(seconds: 3),
            ),
          );
        }
      }
    }
  }

  Future<void> _clearHistory(BuildContext context, String lang) async {
    final theme = Theme.of(context);
    final isRtl = AppStrings.isRtl(lang);

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
        child: AlertDialog(
          backgroundColor: theme.colorScheme.surface,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Text(
            AppStrings.get('clear_history', lang),
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: theme.colorScheme.onSurface),
          ),
          content: Text(
            AppStrings.get('clear_history_confirm', lang),
            style: TextStyle(color: theme.colorScheme.onSurface.withValues(alpha: 0.7)),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: Text(
                AppStrings.get('cancel', lang),
                style: TextStyle(color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
              ),
            ),
            ElevatedButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTokens.negative,
                foregroundColor: Colors.white,
              ),
              child: Text(AppStrings.get('clear_history_btn', lang)),
            ),
          ],
        ),
      ),
    );

    if (confirmed == true && context.mounted) {
      final repo = context.read<NotificationRepository>();
      await repo.clearAllLogs();
      if (context.mounted) {
        ScaffoldMessenger.of(context).hideCurrentSnackBar();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(AppStrings.get('clear_history_success', lang)),
            backgroundColor: theme.colorScheme.surfaceContainerHighest,
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 3),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final settingsService = context.watch<SettingsService>();
    final settings = settingsService.settings;
    final lang = settings.language;
    final isFa = lang == 'fa' || lang == 'ar' || lang == 'ckb';
    final theme = Theme.of(context);

    final currentLangObj = _supportedLanguages.firstWhere(
      (l) => l['code'] == lang,
      orElse: () => _supportedLanguages[0],
    );

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: theme.colorScheme.surface,
        elevation: 0,
        title: Text(
          AppStrings.get('settings', lang),
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.bold,
            color: theme.colorScheme.onSurface,
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.symmetric(horizontal: AppTokens.space16, vertical: AppTokens.space20),
        children: [
          // Section 1: User Profile & VIP Google Sign-In (بخش لاگین)
          _buildUserAccountCard(context, settingsService, settings, theme, lang, isFa),

          // Section 2: Telegram Bot VIP Alerts (بخش تلگرام)
          _buildTelegramIntegrationCard(context, settingsService, settings, theme, lang, isFa),

          // Section 2.5: Market Events Radar (بخش رادار رویدادهای بازار)
          _buildMarketEventsCard(context, settingsService, settings, theme, lang, isFa),

          // Section 3: Alarm Sound, Ringtone & Vibration (بخش تنظیمات آلارم‌ها)
          _buildSectionHeader(isFa ? '۳. تنظیمات صدای آلارم و زنگ هشدار' : '3. Alarm Sound & Ringtone', theme),
          const SizedBox(height: AppTokens.space8),

          Material(
            color: theme.colorScheme.surface,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
              side: BorderSide(color: theme.dividerColor),
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppTokens.space16, vertical: AppTokens.space12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                // 1. Current Selected Sound Tile
                Builder(builder: (context) {
                  final currentPreset = SoundManager.presets.firstWhere(
                    (p) => p.id == settings.soundName,
                    orElse: () => SoundManager.presets.first,
                  );
                  final soundTitle = currentPreset.getTitle(lang);
                  final isPlaying = SoundManager().isSoundPlaying(currentPreset.id);

                  return InkWell(
                    onTap: () => _showSoundPicker(context, settingsService, settings.soundName, lang),
                    borderRadius: BorderRadius.circular(12),
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.primary.withValues(alpha: 0.07),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.25)),
                      ),
                      child: Row(
                        children: [
                          Text(currentPreset.icon, style: const TextStyle(fontSize: 24)),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  AppStrings.get('selected_sound_label', lang),
                                  style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  soundTitle,
                                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: theme.colorScheme.primary),
                                ),
                              ],
                            ),
                          ),
                          IconButton(
                            icon: Icon(
                              isPlaying ? Icons.stop_circle_rounded : Icons.play_circle_filled_rounded,
                              color: isPlaying ? AppTokens.negative : theme.colorScheme.primary,
                              size: 30,
                            ),
                            onPressed: () async {
                              if (isPlaying) {
                                await SoundManager().stop();
                              } else {
                                await SoundManager().playPreset(currentPreset.id, volume: settings.alarmVolume);
                              }
                              setState(() {});
                            },
                          ),
                          const SizedBox(width: 4),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.primary,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              AppStrings.get('change_sound_btn', lang),
                              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.white),
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }),
                const SizedBox(height: 12),

                // 2. Volume Slider
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.volume_up_rounded, size: 18, color: theme.colorScheme.primary),
                        const SizedBox(width: 6),
                        Text(
                          AppStrings.get('alarm_volume_label', lang),
                          style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
                        ),
                      ],
                    ),
                    Text(
                      '${(settings.alarmVolume * 100).toInt()}%',
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, fontFamily: 'monospace', color: theme.colorScheme.primary),
                    ),
                  ],
                ),
                SliderTheme(
                  data: SliderTheme.of(context).copyWith(
                    activeTrackColor: theme.colorScheme.primary,
                    thumbColor: theme.colorScheme.primary,
                    inactiveTrackColor: theme.dividerColor,
                    trackHeight: 4,
                  ),
                  child: Slider(
                    value: settings.alarmVolume,
                    min: 0.1,
                    max: 1.0,
                    divisions: 9,
                    onChanged: (val) => settingsService.setAlarmVolume(val),
                  ),
                ),
                Divider(height: 1, color: theme.dividerColor),
                const SizedBox(height: 8),

                // Helper Note for Global Master Switches
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.info_outline_rounded, size: 15, color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          isFa
                              ? 'تنظیمات سراسری (Master): با خاموش کردن هر گزینه، آن مورد برای تمام آلارم‌ها متوقف شده و با روشن کردن مجدد، تنظیمات قبلی هر آلارم بازیابی می‌شود.'
                              : 'Global Master Switches: Disabling a master switch mutes it for all alerts, and enabling it automatically restores each alert\'s previous state.',
                          style: TextStyle(
                            fontSize: 10,
                            color: theme.colorScheme.onSurface.withValues(alpha: 0.75),
                            height: 1.35,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),

                // 1. 🔔 ویبره (Vibration)
                  Material(
                    color: Colors.transparent,
                    child: SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      secondary: Icon(Icons.vibration_rounded, color: settings.vibrationEnabled ? theme.colorScheme.primary : theme.colorScheme.onSurface.withValues(alpha: 0.4)),
                      title: Text(
                        isFa ? '🔔 ویبره (Vibration)' : '🔔 Vibration',
                        style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
                      ),
                      subtitle: Text(
                        isFa ? 'لرزش سراسری دستگاه هنگام وقوع هشدارها' : 'Global device vibration upon alert trigger',
                        style: TextStyle(fontSize: 10.5, color: theme.colorScheme.onSurface.withValues(alpha: 0.55)),
                      ),
                      value: settings.vibrationEnabled,
                      activeThumbColor: Colors.white,
                      activeTrackColor: theme.colorScheme.primary,
                      inactiveThumbColor: Colors.grey.shade400,
                      inactiveTrackColor: theme.colorScheme.surfaceContainerHighest,
                      onChanged: (val) => settingsService.toggleVibration(val),
                    ),
                  ),
                Divider(height: 1, color: theme.dividerColor),

                  // 2. 🔊 صدا (Sound)
                  Material(
                    color: Colors.transparent,
                    child: SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      secondary: Icon(Icons.volume_up_rounded, color: settings.soundEnabled ? theme.colorScheme.primary : theme.colorScheme.onSurface.withValues(alpha: 0.4)),
                      title: Text(
                        isFa ? '🔊 صدا (Sound)' : '🔊 Sound & Alarm Tone',
                        style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
                      ),
                      subtitle: Text(
                        isFa ? 'پخش صدای زنگ و آهنگ هشدار برای آلارم‌ها' : 'Global alarm sound chime playback',
                        style: TextStyle(fontSize: 10.5, color: theme.colorScheme.onSurface.withValues(alpha: 0.55)),
                      ),
                      value: settings.soundEnabled,
                      activeThumbColor: Colors.white,
                      activeTrackColor: theme.colorScheme.primary,
                      inactiveThumbColor: Colors.grey.shade400,
                      inactiveTrackColor: theme.colorScheme.surfaceContainerHighest,
                      onChanged: (val) => settingsService.toggleSound(val),
                    ),
                  ),
                Divider(height: 1, color: theme.dividerColor),

                  // 3. 🗣️ Voice Speech (خوانش صوتی هوشمند)
                  Material(
                    color: Colors.transparent,
                    child: SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      secondary: Icon(Icons.record_voice_over_rounded, color: settings.ttsEnabled ? theme.colorScheme.primary : theme.colorScheme.onSurface.withValues(alpha: 0.4)),
                      title: Text(
                        isFa ? '🗣️ اعلام صوتی (Voice Speech)' : '🗣️ Voice Speech (TTS)',
                        style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
                      ),
                      subtitle: Text(
                        isFa ? 'خوانش نام دارایی و قیمت به زبان انگلیسی با صدای طبیعی' : 'Global voice speech announcement for alerts',
                        style: TextStyle(fontSize: 10.5, color: theme.colorScheme.onSurface.withValues(alpha: 0.55)),
                      ),
                      value: settings.ttsEnabled,
                      activeThumbColor: Colors.white,
                      activeTrackColor: theme.colorScheme.primary,
                      inactiveThumbColor: Colors.grey.shade400,
                      inactiveTrackColor: theme.colorScheme.surfaceContainerHighest,
                      onChanged: (val) => settingsService.toggleTts(val),
                    ),
                  ),
                const SizedBox(height: 10),

                // Test Alarm & Voice Speech Buttons
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton.icon(
                        onPressed: () => _testAlarm(context, lang),
                        icon: const Icon(Icons.notifications_active_rounded, size: 16),
                        label: Text(
                          isFa ? 'تست زنگ هشدار' : 'Test Alarm',
                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: theme.colorScheme.primary,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () async {
                          await TtsService.instance.testVoice();
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).hideCurrentSnackBar();
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text(
                                  isFa
                                      ? 'پخش گفتار صوتی: Bitcoin 87,420 dollars'
                                      : 'Speaking voice announcement: Bitcoin 87,420 dollars',
                                ),
                                backgroundColor: theme.colorScheme.surfaceContainerHighest,
                                behavior: SnackBarBehavior.floating,
                                duration: const Duration(seconds: 2),
                              ),
                            );
                          }
                        },
                        icon: const Icon(Icons.record_voice_over_rounded, size: 16),
                        label: Text(
                          isFa ? 'تست گفتار صوتی' : 'Test Voice',
                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
                        ),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: theme.colorScheme.primary,
                          side: BorderSide(color: theme.colorScheme.primary),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
          const SizedBox(height: AppTokens.space20),

          // Section 4: Themes & Colors (بخش تم‌ها)
          _buildSectionHeader(isFa ? '۴. ${AppStrings.get('theme_and_colors', lang)}' : '4. ${AppStrings.get('theme_and_colors', lang)}', theme),
          const SizedBox(height: AppTokens.space8),

          Container(
            padding: const EdgeInsets.all(AppTokens.space16),
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: theme.dividerColor),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                GridView.count(
                  crossAxisCount: 2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  crossAxisSpacing: 8,
                  mainAxisSpacing: 8,
                  childAspectRatio: 2.3,
                  children: [
                    _buildThemeCard(
                      palette: AppThemePalette.darkGold,
                      currentPalette: settings.themePalette,
                      title: isFa ? '👑 تیتانیوم طلایی (دارک)' : 'Titanium Gold Luxury (Dark)',
                      bgPreview: const Color(0xFF09090B),
                      accent: const Color(0xFFF59E0B),
                      onSelect: () => settingsService.setPalette(AppThemePalette.darkGold),
                    ),
                    _buildThemeCard(
                      palette: AppThemePalette.lightGold,
                      currentPalette: settings.themePalette,
                      title: isFa ? '👑 تیتانیوم طلایی (لایت)' : 'Titanium Gold Luxury (Light)',
                      bgPreview: const Color(0xFFFAF9F5),
                      accent: const Color(0xFFD97706),
                      onSelect: () => settingsService.setPalette(AppThemePalette.lightGold),
                    ),
                    _buildThemeCard(
                      palette: AppThemePalette.darkSapphire,
                      currentPalette: settings.themePalette,
                      title: isFa ? '💎 یاقوتی رویال (دارک)' : 'Midnight Royal Sapphire (Dark)',
                      bgPreview: const Color(0xFF030712),
                      accent: const Color(0xFF38BDF8),
                      onSelect: () => settingsService.setPalette(AppThemePalette.darkSapphire),
                    ),
                    _buildThemeCard(
                      palette: AppThemePalette.lightSapphire,
                      currentPalette: settings.themePalette,
                      title: isFa ? '💎 یاقوتی رویال (لایت)' : 'Midnight Royal Sapphire (Light)',
                      bgPreview: const Color(0xFFF0F7FF),
                      accent: const Color(0xFF0284C7),
                      onSelect: () => settingsService.setPalette(AppThemePalette.lightSapphire),
                    ),
                    _buildThemeCard(
                      palette: AppThemePalette.darkGreen,
                      currentPalette: settings.themePalette,
                      title: AppStrings.get('theme_dark_green', lang),
                      bgPreview: const Color(0xFF090D16),
                      accent: const Color(0xFF10B981),
                      onSelect: () => settingsService.setPalette(AppThemePalette.darkGreen),
                    ),
                    _buildThemeCard(
                      palette: AppThemePalette.lightGreen,
                      currentPalette: settings.themePalette,
                      title: AppStrings.get('theme_light_green', lang),
                      bgPreview: const Color(0xFFF3F4F6),
                      accent: const Color(0xFF059669),
                      onSelect: () => settingsService.setPalette(AppThemePalette.lightGreen),
                    ),
                    _buildThemeCard(
                      palette: AppThemePalette.darkOrange,
                      currentPalette: settings.themePalette,
                      title: AppStrings.get('theme_dark_orange', lang),
                      bgPreview: const Color(0xFF0C0A09),
                      accent: const Color(0xFFF97316),
                      onSelect: () => settingsService.setPalette(AppThemePalette.darkOrange),
                    ),
                    _buildThemeCard(
                      palette: AppThemePalette.lightOrange,
                      currentPalette: settings.themePalette,
                      title: AppStrings.get('theme_light_orange', lang),
                      bgPreview: const Color(0xFFFAF8F5),
                      accent: const Color(0xFFEA580C),
                      onSelect: () => settingsService.setPalette(AppThemePalette.lightOrange),
                    ),
                    _buildThemeCard(
                      palette: AppThemePalette.darkPurpleBlue,
                      currentPalette: settings.themePalette,
                      title: AppStrings.get('theme_dark_purple_blue', lang),
                      bgPreview: const Color(0xFF0B0D1B),
                      accent: const Color(0xFF8B5CF6),
                      onSelect: () => settingsService.setPalette(AppThemePalette.darkPurpleBlue),
                    ),
                    _buildThemeCard(
                      palette: AppThemePalette.lightPurpleBlue,
                      currentPalette: settings.themePalette,
                      title: AppStrings.get('theme_light_purple_blue', lang),
                      bgPreview: const Color(0xFFF5F6FF),
                      accent: const Color(0xFF7C3AED),
                      onSelect: () => settingsService.setPalette(AppThemePalette.lightPurpleBlue),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: AppTokens.space20),

          // Section 5: Backup & Restore (بخش پشتیبان‌گیری و بازیابی)
          _buildSectionHeader(isFa ? '۵. ${AppStrings.get('backup_and_restore', lang)}' : '5. ${AppStrings.get('backup_and_restore', lang)}', theme),
          const SizedBox(height: AppTokens.space8),

          _buildActionTile(
            context: context,
            title: AppStrings.get('export_backup', lang),
            subtitle: AppStrings.get('export_backup_desc', lang),
            icon: Icons.cloud_upload_rounded,
            color: theme.colorScheme.primary,
            onTap: () => _exportBackup(context, lang),
          ),
          const SizedBox(height: AppTokens.space8),

          _buildActionTile(
            context: context,
            title: AppStrings.get('restore_backup', lang),
            subtitle: AppStrings.get('restore_backup_desc', lang),
            icon: Icons.cloud_download_rounded,
            color: theme.colorScheme.secondary,
            onTap: () => _importBackup(context, lang),
          ),
          const SizedBox(height: AppTokens.space8),

          _buildActionTile(
            context: context,
            title: AppStrings.get('clear_history', lang),
            subtitle: AppStrings.get('clear_history_desc', lang),
            icon: Icons.delete_outline_rounded,
            color: AppTokens.negative,
            onTap: () => _clearHistory(context, lang),
          ),
          const SizedBox(height: AppTokens.space20),

          // Section 6: Languages (بخش زبان)
          _buildSectionHeader(isFa ? '۶. ${AppStrings.get('select_language', lang)}' : '6. ${AppStrings.get('select_language', lang)}', theme),
          const SizedBox(height: AppTokens.space8),

          InkWell(
            onTap: () => _showLanguagePicker(context, settingsService, lang),
            borderRadius: BorderRadius.circular(14),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: AppTokens.space16, vertical: AppTokens.space12),
              decoration: BoxDecoration(
                color: theme.colorScheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: theme.dividerColor),
              ),
              child: Row(
                children: [
                  Text(currentLangObj['flag']!, style: const TextStyle(fontSize: 22)),
                  const SizedBox(width: AppTokens.space12),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        currentLangObj['native']!,
                        style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: theme.colorScheme.onSurface),
                      ),
                      Text(
                        '${currentLangObj['name']} (10 Languages)',
                        style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurface.withValues(alpha: 0.55)),
                      ),
                    ],
                  ),
                  const Spacer(),
                  Icon(
                    Icons.arrow_drop_down_rounded,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                    size: 28,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: AppTokens.space20),

          // Section 7: 24/7 Background Alert Delivery Guide & Battery (بخش تنظیمات باتری و پس‌زمینه)
          _buildSectionHeader(isFa ? '۷. پایش ۲۴/۷ و تنظیمات پس‌زمینه و باتری' : '7. 24/7 Background Sync & Battery', theme),
          const SizedBox(height: AppTokens.space8),
          DeviceHealthCard(lang: lang),
          _buildActionTile(
            context: context,
            title: isFa ? '🩺 وضعیت و سلامت اعلان‌ها (Notification Health)' : '🩺 Notification Health & Delivery',
            subtitle: isFa
                ? 'مشاهده وضعیت مجوزها، باتری Doze، شروع خودکار، آخرین Sync و نبض سلامت، ارسال تست و کپی لاگ'
                : 'Permissions, Doze mode, Autostart, sync state, heartbeat, test push, and service logs',
            icon: Icons.health_and_safety_rounded,
            color: theme.colorScheme.primary,
            onTap: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => NotificationHealthPage(lang: lang)),
              );
            },
          ),
          const SizedBox(height: AppTokens.space12),
          _buildBackgroundReliabilityCard(context, theme, lang, isFa),
          const SizedBox(height: AppTokens.space20),

          // Section 8: Deep Debug & Diagnostics Center (بخش پنل ادمین و عیب‌یابی)
          _buildSectionHeader(isFa ? '۸. مرکز عیب‌یابی و دیباگ هوشمند' : '8. Debug & Diagnostics Center', theme),
          const SizedBox(height: AppTokens.space8),

          _buildActionTile(
            context: context,
            title: isFa ? '🛠️ عیب‌یابی و تست عمیق نمادها و صرافی‌ها' : '🛠️ Deep Market & Server Diagnostics',
            subtitle: isFa ? 'تست لحظه‌ای دریافت قیمت هر نماد با گزارش دقیق قابل کپی جهت ارسال به پشتیبان' : 'Step-by-step trace and diagnostic inspection for any failing market symbol',
            icon: Icons.bug_report_rounded,
            color: theme.colorScheme.primary,
            onTap: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const DebugDiagnosticsPage()),
              );
            },
          ),
          const SizedBox(height: AppTokens.space20),

          // Section 9: Legal Disclaimer & Risk Warning (پیام حقوقی و سلب مسئولیت ریسک)
          _buildSectionHeader(isFa ? '۹. پیام حقوقی و سلب مسئولیت' : '9. Legal Disclaimer & Risk Warning', theme),
          const SizedBox(height: AppTokens.space8),

          Container(
            padding: const EdgeInsets.all(AppTokens.space16),
            decoration: BoxDecoration(
              color: Colors.amber.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Colors.amber.withValues(alpha: 0.3)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(Icons.gavel_rounded, color: Colors.amber, size: 20),
                    const SizedBox(width: 8),
                    Text(
                      AppStrings.get('legal_disclaimer_title', lang),
                      style: const TextStyle(
                        fontSize: 13.5,
                        fontWeight: FontWeight.bold,
                        color: Colors.amber,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  AppStrings.get('legal_disclaimer_text', lang),
                  style: TextStyle(
                    fontSize: 11.5,
                    height: 1.6,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.8),
                  ),
                  textAlign: TextAlign.justify,
                ),
              ],
            ),
          ),
          const SizedBox(height: AppTokens.space24),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(String title, ThemeData theme) {
    return Text(
      title,
      style: TextStyle(
        fontSize: 13,
        fontWeight: FontWeight.bold,
        color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
      ),
    );
  }

  Widget _buildBackgroundReliabilityCard(
    BuildContext context,
    ThemeData theme,
    String lang,
    bool isFa,
  ) {
    return Container(
      padding: const EdgeInsets.all(AppTokens.space16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: theme.colorScheme.primary.withValues(alpha: 0.35),
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: theme.colorScheme.primary.withValues(alpha: 0.04),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: theme.colorScheme.primary.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.bolt_rounded, color: theme.colorScheme.primary, size: 20),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isFa ? 'راهنمای دریافت ۲۴/۷ هشدارها (حتی با بستن اپ)' : '24/7 Background Alert Reliability Guide',
                      style: TextStyle(
                        fontSize: 13.5,
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      isFa ? 'تنظیمات ضروری برای گوشی‌های شیائومی (MIUI)، سامسونگ و اندروید' : 'Essential steps for Xiaomi (MIUI), Samsung & Android OS',
                      style: TextStyle(
                        fontSize: 10.5,
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Divider(height: 1, color: theme.dividerColor),
          const SizedBox(height: 12),

          // Step 1: Autostart
          _buildSetupStep(
            number: isFa ? '۱' : '1',
            title: isFa ? 'فعال‌سازی شروع خودکار (Autostart)' : 'Enable Autostart',
            description: isFa
                ? 'برای دریافت پایدار و همیشگی هشدارها، گزینه Autostart برنامه SignalAlert را در گوشی خود فعال کنید.'
                : 'Turn Autostart ON for SignalAlert in your phone settings to receive 24/7 background alerts.',
            icon: Icons.power_settings_new_rounded,
            theme: theme,
            trailingWidget: TextButton.icon(
              onPressed: () async {
                final opened = await AppLifecycleHelper.openAutostartSettings();
                if (!opened) {
                  await openAppSettings();
                }
              },
              icon: Icon(
                Icons.launch_rounded,
                size: 14,
                color: theme.colorScheme.primary,
              ),
              label: Text(
                isFa ? 'باز کردن خودکار' : 'Open Direct',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: theme.colorScheme.primary,
                ),
              ),
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                backgroundColor: theme.colorScheme.primary.withValues(alpha: 0.1),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
          ),
          const SizedBox(height: 10),

          // Step 2: Battery Optimization
          _buildSetupStep(
            number: isFa ? '۲' : '2',
            title: isFa ? 'برداشتن محدودیت باتری (No restrictions)' : 'Remove Battery Restrictions',
            description: isFa
                ? 'روی دکمه «اعمال مستقیم» بزنید یا در تنظیمات باتری گزینه بدون محدودیت (No restrictions) را انتخاب کنید.'
                : 'Tap "Grant" or set Battery saver to "No restrictions".',
            icon: Icons.battery_charging_full_rounded,
            theme: theme,
            trailingWidget: TextButton.icon(
              onPressed: () => _requestBatteryExemption(lang),
              icon: Icon(
                _isBatteryExempt ? Icons.check_circle_rounded : Icons.offline_bolt_outlined,
                size: 14,
                color: _isBatteryExempt ? AppTokens.positive : theme.colorScheme.primary,
              ),
              label: Text(
                _isBatteryExempt
                    ? (isFa ? 'فعال شد ✅' : 'Exempted ✅')
                    : (isFa ? 'اعمال مستقیم' : 'Grant'),
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: _isBatteryExempt ? AppTokens.positive : theme.colorScheme.primary,
                ),
              ),
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                backgroundColor: (_isBatteryExempt ? AppTokens.positive : theme.colorScheme.primary).withValues(alpha: 0.1),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
          ),
          const SizedBox(height: 10),

          // Step 3: Lock in Recent Apps
          _buildSetupStep(
            number: isFa ? '۳' : '3',
            title: isFa ? 'قفل کردن برنامه در برنامه‌های اخیر (Recent Apps)' : 'Lock in Recent Apps',
            description: isFa
                ? 'در صفحه برنامه‌های اخیر (Recent Apps)، انگشت خود را روی پنجره برنامه نگه داشته و آیکون 🔒 قفل را بزنید تا هنگام پاک‌کردن برنامه‌ها بسته نشود.'
                : 'Open Recent Apps ➔ Long press SignalAlert window ➔ Tap the 🔒 Lock icon.',
            icon: Icons.lock_outline_rounded,
            theme: theme,
          ),
          const SizedBox(height: 14),

          // Quick Action Buttons
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: () async {
                    final opened = await AppLifecycleHelper.openAutostartSettings();
                    if (!opened) {
                      await openAppSettings();
                    }
                  },
                  icon: const Icon(Icons.rocket_launch_rounded, size: 15),
                  label: Text(
                    isFa ? 'مدیریت Autostart گوشی' : 'Autostart Manager',
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 11.5),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.colorScheme.primary,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    padding: const EdgeInsets.symmetric(vertical: 10),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => openAppSettings(),
                  icon: const Icon(Icons.settings_outlined, size: 15),
                  label: Text(
                    isFa ? 'اطلاعات برنامه در سیستم' : 'App Details',
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 11.5),
                  ),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: theme.colorScheme.onSurface,
                    side: BorderSide(color: theme.dividerColor),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    padding: const EdgeInsets.symmetric(vertical: 10),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSetupStep({
    required String number,
    required String title,
    required String description,
    required IconData icon,
    required ThemeData theme,
    Widget? trailingWidget,
  }) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              color: theme.colorScheme.primary.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Icon(icon, size: 16, color: theme.colorScheme.primary),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        '$number. $title',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                          color: theme.colorScheme.onSurface,
                        ),
                      ),
                    ),
                    if (trailingWidget != null) trailingWidget,
                  ],
                ),
                const SizedBox(height: 3),
                Text(
                  description,
                  style: TextStyle(
                    fontSize: 10.5,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
                    height: 1.35,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildThemeCard({
    required AppThemePalette palette,
    required AppThemePalette currentPalette,
    required String title,
    required Color bgPreview,
    required Color accent,
    required VoidCallback onSelect,
  }) {
    final isSelected = currentPalette == palette;
    return InkWell(
      onTap: onSelect,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: bgPreview,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: isSelected ? accent : Colors.grey.withValues(alpha: 0.3),
            width: isSelected ? 2.0 : 1.0,
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 16,
              height: 16,
              decoration: BoxDecoration(
                color: accent,
                shape: BoxShape.circle,
              ),
              child: isSelected
                  ? const Icon(Icons.check, size: 10, color: Colors.white)
                  : null,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                title,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                  color: bgPreview.computeLuminance() > 0.5 ? const Color(0xFF111827) : Colors.white,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActionTile({
    required BuildContext context,
    required String title,
    required String subtitle,
    required IconData icon,
    required Color color,
    required VoidCallback onTap,
  }) {
    final theme = Theme.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: AppTokens.space16, vertical: AppTokens.space12),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: theme.dividerColor),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(icon, color: color, size: 22),
              ),
              const SizedBox(width: AppTokens.space12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      style: TextStyle(
                        fontSize: 11,
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
                      ),
                    ),
                  ],
                ),
              ),
              Icon(
                Icons.arrow_forward_ios_rounded,
                size: 14,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.4),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildUserAccountCard(
    BuildContext context,
    SettingsService settingsService,
    AppSettings settings,
    ThemeData theme,
    String lang,
    bool isFa,
  ) {
    final isSignedIn = settings.isSignedInWithGoogle;
    final isPremium = settings.isPremium || isSignedIn;

    return Container(
      margin: const EdgeInsets.only(bottom: AppTokens.space16),
      padding: const EdgeInsets.all(AppTokens.space16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isPremium
              ? AppTokens.warning.withValues(alpha: 0.6)
              : theme.dividerColor,
          width: isPremium ? 1.4 : 1.0,
        ),
        boxShadow: isPremium
            ? [
                BoxShadow(
                  color: AppTokens.warning.withValues(alpha: 0.08),
                  blurRadius: 12,
                  offset: const Offset(0, 3),
                )
              ]
            : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: isPremium
                      ? AppTokens.warning.withValues(alpha: 0.15)
                      : theme.colorScheme.surfaceContainerHighest,
                  border: Border.all(
                    color: isPremium ? AppTokens.warning : theme.dividerColor,
                    width: 1.5,
                  ),
                ),
                child: Center(
                  child: isPremium
                      ? const Text('👑', style: TextStyle(fontSize: 22))
                      : Image.network(
                          'https://www.gstatic.com/images/branding/product/1x/gsa_512dp.png',
                          width: 22,
                          height: 22,
                          errorBuilder: (_, __, ___) => const Icon(Icons.account_circle_outlined, size: 24),
                        ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            isSignedIn
                                ? (settings.userDisplayName ?? 'Google User')
                                : (isFa ? 'حساب کاربری مهمان' : 'Guest User'),
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.bold,
                              color: theme.colorScheme.onSurface,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: isPremium
                                ? AppTokens.warning.withValues(alpha: 0.2)
                                : theme.colorScheme.surfaceContainerHighest,
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(
                              color: isPremium ? AppTokens.warning : theme.dividerColor,
                            ),
                          ),
                          child: Text(
                            isPremium
                                ? (isFa ? '👑 عضو ویژه (PRO / VIP)' : '👑 VIP PRO')
                                : (isFa ? 'طرح رایگان' : 'FREE PLAN'),
                            style: TextStyle(
                              fontSize: 9.5,
                              fontWeight: FontWeight.bold,
                              color: isPremium ? AppTokens.warning : theme.colorScheme.onSurface.withValues(alpha: 0.6),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text(
                      isSignedIn
                          ? (settings.userEmail ?? '')
                          : (isFa
                              ? 'ورود با گوگل برای فعال‌سازی رایگان اشتراک ویژه VIP'
                              : 'Sign in to unlock VIP perks & Cloud sync'),
                      style: TextStyle(
                        fontSize: 11,
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            ],
          ),

          // VIP Perks Highlights Banner
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              color: isPremium
                  ? AppTokens.warning.withValues(alpha: 0.08)
                  : theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.4),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(
                color: isPremium
                    ? AppTokens.warning.withValues(alpha: 0.25)
                    : theme.dividerColor.withValues(alpha: 0.5),
                width: 0.8,
              ),
            ),
            child: Row(
              children: [
                Icon(
                  isPremium ? Icons.verified_rounded : Icons.star_rounded,
                  size: 16,
                  color: isPremium ? AppTokens.warning : theme.colorScheme.primary,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    isFa
                        ? (isPremium
                            ? '⭐️ تمام امکانات ویژه فعال است: آلارم در تلگرام، عبور از محدودیت باتری و آلارم نامحدود'
                            : '⭐️ با ورود با حساب گوگل، اتصال به تلگرام و قابلیت‌های VIP برای شما فعال می‌شود.')
                        : (isPremium
                            ? '⭐️ VIP Active: Telegram alerts, bypass sleep & unlimited alerts'
                            : '⭐️ Sign in with Google to activate VIP Telegram & Pro alerts.'),
                    style: TextStyle(
                      fontSize: 10.5,
                      fontWeight: FontWeight.w600,
                      color: isPremium ? AppTokens.warning : theme.colorScheme.onSurface.withValues(alpha: 0.8),
                      height: 1.35,
                    ),
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 12),
          Divider(height: 1, color: theme.dividerColor),
          const SizedBox(height: 10),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                isSignedIn
                    ? (isFa ? '☁️ آماده پشتیبان‌گیری ابری' : '☁️ Cloud Backup Ready')
                    : (isFa ? 'بدون نیاز به پرداخت هزینه' : '100% Free & Local-First'),
                style: TextStyle(
                  fontSize: 10.5,
                  color: isSignedIn ? AppTokens.positive : theme.colorScheme.onSurface.withValues(alpha: 0.5),
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (isSignedIn)
                TextButton.icon(
                  onPressed: () async {
                    // 0. Snapshot account state BEFORE signing out so alerts and telegram state are preserved
                    final currentEmail = settingsService.settings.userEmail;
                    final currentChatId = settingsService.settings.telegramChatId;
                    if (currentEmail != null && currentEmail.trim().isNotEmpty) {
                      try {
                        final dir = await getApplicationDocumentsDirectory();
                        final profFile = File('${dir.path}/account_profile_${currentEmail.trim().toLowerCase()}.json');
                        await profFile.writeAsString(jsonEncode({
                          'email': currentEmail,
                          'telegram_chat_id': currentChatId ?? '@aegkalair_bot',
                          'is_connected': currentChatId != null && currentChatId.isNotEmpty,
                          'last_updated': DateTime.now().toIso8601String(),
                        }));
                        if (currentChatId != null && currentChatId.isNotEmpty) {
                          final lastTgFile = File('${dir.path}/last_telegram_chat.txt');
                          await lastTgFile.writeAsString(currentChatId);
                        }
                      } catch (_) {}
                    }

                    // Complete logout: purge Google cached account credentials AND local settings
                    await GoogleAuthService.signOut();
                    await settingsService.signOut();
                    if (context.mounted) {
                      try {
                        final repo = context.read<JsonAlertRuleRepository>();
                        await repo.clearLocalOnly();
                        if (context.mounted) {
                          context.read<AlertRulesBloc>().add(const LoadAlertRules());
                        }
                      } catch (_) {}
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(isFa ? 'از حساب گوگل خارج شدید.' : 'Signed out of Google account.'),
                            behavior: SnackBarBehavior.floating,
                          ),
                        );
                      }
                    }
                  },
                  icon: const Icon(Icons.logout_rounded, size: 14),
                  label: Text(
                    isFa ? 'خروج از حساب' : 'Sign Out',
                    style: const TextStyle(fontSize: 11),
                  ),
                  style: TextButton.styleFrom(
                    foregroundColor: AppTokens.negative,
                    visualDensity: VisualDensity.compact,
                  ),
                )
              else
                ElevatedButton.icon(
                  onPressed: () async {
                    final signedIn = await GoogleAuthService.promptGoogleSignIn(context, settingsService, lang);
                    if (signedIn && context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(isFa ? '🎉 با موفقیت به حساب گوگل متصل شدید (عضو ویژه VIP)!' : '🎉 Connected to Google account (VIP Activated)!'),
                          backgroundColor: AppTokens.positive,
                          behavior: SnackBarBehavior.floating,
                        ),
                      );
                    }
                  },
                  icon: const Icon(Icons.login_rounded, size: 15),
                  label: Text(
                    isFa ? 'ورود با حساب گوگل' : 'Sign In with Google',
                    style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.colorScheme.primary,
                    foregroundColor: Colors.white,
                    elevation: 0,
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildTelegramIntegrationCard(
    BuildContext context,
    SettingsService settingsService,
    AppSettings settings,
    ThemeData theme,
    String lang,
    bool isFa,
  ) {
    final isSignedIn = settings.isSignedInWithGoogle;
    final isConnected = isSignedIn && settings.isTelegramConnected;
    final telegramColor = const Color(0xFF229ED9); // Telegram Official Blue

    return Container(
      margin: const EdgeInsets.only(bottom: AppTokens.space20),
      padding: const EdgeInsets.all(AppTokens.space16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isConnected
              ? telegramColor.withValues(alpha: 0.6)
              : (!isSignedIn ? AppTokens.warning.withValues(alpha: 0.4) : theme.dividerColor),
          width: isConnected ? 1.4 : 1.0,
        ),
        boxShadow: isConnected
            ? [
                BoxShadow(
                  color: telegramColor.withValues(alpha: 0.08),
                  blurRadius: 10,
                  offset: const Offset(0, 2),
                )
              ]
            : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: !isSignedIn
                      ? AppTokens.warning.withValues(alpha: 0.12)
                      : telegramColor.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: !isSignedIn
                        ? AppTokens.warning.withValues(alpha: 0.4)
                        : telegramColor.withValues(alpha: 0.4),
                    width: 1.2,
                  ),
                ),
                child: Center(
                  child: Icon(
                    !isSignedIn ? Icons.lock_outline_rounded : Icons.send_rounded,
                    color: !isSignedIn ? AppTokens.warning : telegramColor,
                    size: 20,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            isFa ? '📡 اتصال به ربات تلگرام (VIP)' : '📡 Telegram Bot Alerts (VIP)',
                            style: TextStyle(
                              fontSize: 13.5,
                              fontWeight: FontWeight.bold,
                              color: theme.colorScheme.onSurface,
                            ),
                          ),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1.5),
                          decoration: BoxDecoration(
                            color: isConnected
                                ? AppTokens.positive.withValues(alpha: 0.15)
                                : theme.colorScheme.surfaceContainerHighest,
                            borderRadius: BorderRadius.circular(5),
                          ),
                          child: Text(
                            isConnected
                                ? (isFa ? 'متصل به تلگرام ✅' : 'CONNECTED ✅')
                                : (isFa ? 'غیرمتصل ❌' : 'DISCONNECTED ❌'),
                            style: TextStyle(
                              fontSize: 9.5,
                              fontWeight: FontWeight.bold,
                              color: isConnected ? AppTokens.positive : theme.colorScheme.onSurface.withValues(alpha: 0.6),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      isFa
                          ? 'دریافت ۱۰۰٪ تضمینی آلارم‌ها در چت یا کانال تلگرام حتی در حالت خواب گوشی'
                          : '100% Guaranteed instant alert delivery to Telegram chat or channel',
                      style: TextStyle(
                        fontSize: 10.5,
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          if (isConnected) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTokens.positive.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: AppTokens.positive.withValues(alpha: 0.3), width: 1),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.check_circle_rounded, size: 20, color: AppTokens.positive),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          isFa
                              ? 'ربات متصل است: تمامی هشدارهای فعال شما به‌طور بلادرنگ به تلگرام ارسال می‌شوند.'
                              : 'Telegram Bot Connected: All active price alerts are sent in real time.',
                          style: const TextStyle(
                            fontSize: 11.5,
                            fontWeight: FontWeight.bold,
                            color: AppTokens.positive,
                            height: 1.3,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surface,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: AppTokens.positive.withValues(alpha: 0.2)),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Row(
                          children: [
                            Icon(Icons.badge_rounded, size: 14, color: theme.colorScheme.primary),
                            const SizedBox(width: 6),
                            Text(
                              isFa ? 'شناسه چت شما:' : 'Your Chat ID:',
                              style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurface.withValues(alpha: 0.7)),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              settings.telegramChatId ?? '@aegkalair_bot',
                              style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold, fontFamily: 'monospace'),
                            ),
                          ],
                        ),
                        InkWell(
                          onTap: () => _showTelegramConnectSheet(context, settingsService, lang),
                          borderRadius: BorderRadius.circular(6),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            child: Row(
                              children: [
                                Icon(Icons.edit_rounded, size: 13, color: theme.colorScheme.primary),
                                const SizedBox(width: 3),
                                Text(
                                  isFa ? 'ویرایش آیدی' : 'Edit ID',
                                  style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: theme.colorScheme.primary),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () async {
                      await settingsService.setTelegramChatId(null);
                      try {
                        final dir = await getApplicationDocumentsDirectory();
                        final lastTgFile = File('${dir.path}/last_telegram_chat.txt');
                        if (await lastTgFile.exists()) {
                          await lastTgFile.delete();
                        }
                        final email = settingsService.settings.userEmail;
                        if (email != null && email.trim().isNotEmpty) {
                          final profFile = File('${dir.path}/account_profile_${email.trim().toLowerCase()}.json');
                          await profFile.writeAsString(jsonEncode({
                            'email': email,
                            'telegram_chat_id': null,
                            'is_connected': false,
                            'last_updated': DateTime.now().toIso8601String(),
                          }));
                        }
                      } catch (_) {}

                      if (context.mounted) {
                        ServerAlertService.syncWithServer(context);
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(isFa ? 'اتصال تلگرام قطع شد و دیگر هیچ آلارمی به ربات ارسال نخواهد شد.' : 'Telegram disconnected. No alerts will be sent.'),
                            behavior: SnackBarBehavior.floating,
                          ),
                        );
                      }
                    },
                    icon: const Icon(Icons.link_off_rounded, size: 16),
                    label: Text(
                      isFa ? 'قطع اتصال (Disconnect)' : 'Disconnect',
                      style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold),
                    ),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppTokens.negative,
                      side: BorderSide(color: AppTokens.negative.withValues(alpha: 0.5)),
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: () async {
                      final targetChat = settings.telegramChatId ?? '@aegkalair_bot';
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(isFa ? '⏳ در حال ارسال پیام تست به تلگرام...' : '⏳ Sending test alert to Telegram...'),
                          duration: const Duration(seconds: 1),
                          behavior: SnackBarBehavior.floating,
                        ),
                      );
                      final res = await ServerAlertService.sendTelegramTestAlert(targetChat);
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).hideCurrentSnackBar();
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(res['success'] == true
                                ? (isFa ? '🎉 پیام تست با موفقیت به تلگرام شما ارسال شد!' : '🎉 Test alert sent to Telegram!')
                                : (res['error'] ?? 'خطا در ارسال پیام')),
                            backgroundColor: res['success'] == true ? AppTokens.positive : AppTokens.negative,
                            behavior: SnackBarBehavior.floating,
                          ),
                        );
                      }
                    },
                    icon: const Icon(Icons.notifications_active_rounded, size: 16),
                    label: Text(
                      isFa ? 'تست ارسال پیام' : 'Test Alert',
                      style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold),
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: telegramColor,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Center(
              child: TextButton.icon(
                onPressed: () async {
                  await AppLifecycleHelper.openTelegramBot();
                },
                icon: const Icon(Icons.open_in_new_rounded, size: 14),
                label: const Text(
                  'https://t.me/aegkalair_bot',
                  style: TextStyle(fontSize: 11, fontFamily: 'monospace'),
                ),
                style: TextButton.styleFrom(
                  foregroundColor: telegramColor,
                  visualDensity: VisualDensity.compact,
                ),
              ),
            ),
          ] else ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: telegramColor.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: telegramColor.withValues(alpha: 0.25), width: 1),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.mark_chat_unread_rounded, color: telegramColor, size: 18),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          isFa
                              ? 'اتصال به ربات تلگرام و ثبت آیدی'
                              : 'Connect Telegram Bot & Set ID',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.onSurface,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    isFa
                        ? 'برای فعال‌سازی و دریافت ۲۴ ساعته اعلان‌های قیمت در تلگرام، روی دکمهٔ زیر بزنید تا پنجرهٔ راهنما، باز کردن ربات و کادر وارد کردن آیدی باز شود.'
                        : 'Tap the button below to open the setup window with bot link, instructions, and Chat ID input box.',
                    style: TextStyle(
                      fontSize: 11,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.75),
                      height: 1.35,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: () {
                  _showTelegramConnectSheet(context, settingsService, lang);
                },
                icon: const Icon(Icons.send_rounded, size: 18),
                label: Text(
                  isFa ? 'اتصال به ربات تلگرام (Connect)' : 'Connect Telegram Bot (Connect)',
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: telegramColor,
                  foregroundColor: Colors.white,
                  elevation: 2,
                  padding: const EdgeInsets.symmetric(vertical: 13),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildMarketEventsCard(
    BuildContext context,
    SettingsService settingsService,
    AppSettings settings,
    ThemeData theme,
    String lang,
    bool isFa,
  ) {
    final accentColor = const Color(0xFF6366F1);

    return Container(
      margin: const EdgeInsets.only(bottom: AppTokens.space20),
      padding: const EdgeInsets.all(AppTokens.space16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: accentColor.withValues(alpha: 0.35),
          width: 1.2,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: accentColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(Icons.local_fire_department_rounded, color: accentColor, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isFa ? 'رادار رویدادهای کلیدی بازار' : 'Market Catalysts Radar',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      isFa ? 'نوار تک‌خطی زیر عنوان + فیلتر ۶ ساعته ۴ بازار' : 'Single-line ticker + 6h scan for 4 markets',
                      style: TextStyle(
                        fontSize: 11,
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                      ),
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: accentColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: accentColor.withValues(alpha: 0.3)),
                ),
                child: Text(
                  '6h Scan',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                    color: accentColor,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppTokens.space12),
          const Divider(height: 1),
          const SizedBox(height: AppTokens.space8),

          // 1. Switch for Banner Display
          Material(
            color: Colors.transparent,
            child: SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              title: Text(
                isFa ? 'نمایش نوار رویدادها زیر عنوان صفحه' : 'Display Market Events Banner',
                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
              ),
              subtitle: Text(
                isFa ? 'رویدادهای داغ کریپتو، فارکس، نفت و سهام' : 'Show single-line ticker below titlebar',
                style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
              ),
              value: settings.showMarketEventsBanner,
              activeColor: accentColor,
              onChanged: (val) {
                settingsService.updateSettings(settings.copyWith(showMarketEventsBanner: val));
              },
            ),
          ),

          // 2. Switch for Notifications
          Material(
            color: Colors.transparent,
            child: SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              title: Text(
                isFa ? 'دریافت ناتیفیکیشن برای رویدادهای مهم' : 'Receive Event Notifications',
                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
              ),
              subtitle: Text(
                isFa ? 'ارسال خودکار به اپلیکیشن و ربات تلگرام' : 'Send push and Telegram alert for major events',
                style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
              ),
              value: settings.eventsNotificationEnabled,
              activeColor: accentColor,
              onChanged: (val) {
                settingsService.updateSettings(settings.copyWith(eventsNotificationEnabled: val));
              },
            ),
          ),

          const SizedBox(height: 8),
          Text(
            isFa ? 'انتخاب بازارهای هدف:' : 'Target Market Categories:',
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
          ),
          const SizedBox(height: 8),

          // 3. Category Checkboxes Grid
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _buildCategoryFilterChip(
                label: '🪙 ' + (isFa ? 'کریپتو' : 'Crypto'),
                isSelected: settings.eventsCryptoEnabled,
                accentColor: accentColor,
                theme: theme,
                onTap: () => settingsService.updateSettings(
                  settings.copyWith(eventsCryptoEnabled: !settings.eventsCryptoEnabled),
                ),
              ),
              _buildCategoryFilterChip(
                label: '🌐 ' + (isFa ? 'فارکس و کلان' : 'Macro & Forex'),
                isSelected: settings.eventsMacroEnabled,
                accentColor: accentColor,
                theme: theme,
                onTap: () => settingsService.updateSettings(
                  settings.copyWith(eventsMacroEnabled: !settings.eventsMacroEnabled),
                ),
              ),
              _buildCategoryFilterChip(
                label: '🛢️ ' + (isFa ? 'نفت و انرژی' : 'Energy & Oil'),
                isSelected: settings.eventsEnergyEnabled,
                accentColor: accentColor,
                theme: theme,
                onTap: () => settingsService.updateSettings(
                  settings.copyWith(eventsEnergyEnabled: !settings.eventsEnergyEnabled),
                ),
              ),
              _buildCategoryFilterChip(
                label: '📈 ' + (isFa ? 'سهام مگا-کپ' : 'Mega-Cap Stocks'),
                isSelected: settings.eventsStocksEnabled,
                accentColor: accentColor,
                theme: theme,
                onTap: () => settingsService.updateSettings(
                  settings.copyWith(eventsStocksEnabled: !settings.eventsStocksEnabled),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildCategoryFilterChip({
    required String label,
    required bool isSelected,
    required Color accentColor,
    required ThemeData theme,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? accentColor.withValues(alpha: 0.18) : theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.4),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? accentColor : theme.dividerColor,
            width: isSelected ? 1.2 : 0.8,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isSelected ? Icons.check_circle_rounded : Icons.circle_outlined,
              size: 14,
              color: isSelected ? accentColor : theme.colorScheme.onSurface.withValues(alpha: 0.4),
            ),
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                color: isSelected ? theme.colorScheme.onSurface : theme.colorScheme.onSurface.withValues(alpha: 0.7),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
