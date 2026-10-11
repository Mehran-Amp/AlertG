import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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
import 'debug_diagnostics_page.dart';

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
                      color: theme.colorScheme.surface,
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

          // Section 3: Alarm Sound, Ringtone & Vibration (بخش تنظیمات آلارم‌ها)
          _buildSectionHeader(isFa ? '۳. تنظیمات صدای آلارم و زنگ هشدار' : '3. Alarm Sound & Ringtone', theme),
          const SizedBox(height: AppTokens.space8),

          Container(
            padding: const EdgeInsets.symmetric(horizontal: AppTokens.space16, vertical: AppTokens.space12),
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: theme.dividerColor),
            ),
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
                SwitchListTile(
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
                Divider(height: 1, color: theme.dividerColor),

                // 2. 🔊 صدا (Sound)
                SwitchListTile(
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
                Divider(height: 1, color: theme.dividerColor),

                // 3. 🗣️ Voice Speech (خوانش صوتی هوشمند)
                SwitchListTile(
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
                            color: !isSignedIn
                                ? AppTokens.warning.withValues(alpha: 0.15)
                                : (isConnected
                                    ? AppTokens.positive.withValues(alpha: 0.15)
                                    : theme.colorScheme.surfaceContainerHighest),
                            borderRadius: BorderRadius.circular(5),
                          ),
                          child: Text(
                            !isSignedIn
                                ? (isFa ? '🔒 نیاز به ورود' : '🔒 LOGIN REQUIRED')
                                : (isConnected
                                    ? (isFa ? 'متصل شد ✅' : 'CONNECTED ✅')
                                    : (isFa ? 'در انتظار اتصال ⏳' : 'PENDING ⏳')),
                            style: TextStyle(
                              fontSize: 9.5,
                              fontWeight: FontWeight.bold,
                              color: !isSignedIn
                                  ? AppTokens.warning
                                  : (isConnected ? AppTokens.positive : theme.colorScheme.onSurface.withValues(alpha: 0.6)),
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

          if (!isSignedIn) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTokens.warning.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: AppTokens.warning.withValues(alpha: 0.3), width: 0.8),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.info_outline_rounded, color: AppTokens.warning, size: 17),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          isFa
                              ? 'اتصال به تلگرام نیازمند ورود به حساب کاربری است'
                              : 'Telegram integration requires an active account',
                          style: TextStyle(
                            fontSize: 11.5,
                            fontWeight: FontWeight.bold,
                            color: AppTokens.warning,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    isFa
                        ? 'برای ثبت اختصاصی آلارم‌ها در سرور و مدیریت دقیق اعلان‌های ارسالی به تلگرام، ابتدا باید وارد حساب کاربری گوگل خود شوید.'
                        : 'To bind alerts exclusively to your account and control notifications, please sign in with your Google account first.',
                    style: TextStyle(
                      fontSize: 11,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.8),
                      height: 1.35,
                    ),
                  ),
                  const SizedBox(height: 10),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: () async {
                        final signedIn = await GoogleAuthService.promptGoogleSignIn(context, settingsService, lang);
                        if (signedIn && context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(isFa ? '🎉 با موفقیت وارد شدید! اکنون می‌توانید ربات تلگرام را متصل کنید.' : '🎉 Signed in! You can now connect the Telegram bot.'),
                              backgroundColor: AppTokens.positive,
                              behavior: SnackBarBehavior.floating,
                            ),
                          );
                        }
                      },
                      icon: const Icon(Icons.login_rounded, size: 15),
                      label: Text(
                        isFa ? 'ورود با حساب گوگل جهت فعال‌سازی تلگرام' : 'Sign In with Google to Enable Telegram',
                        style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: theme.colorScheme.primary,
                        foregroundColor: Colors.white,
                        elevation: 0,
                        padding: const EdgeInsets.symmetric(vertical: 9),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ] else if (isConnected) ...[
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color: telegramColor.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: telegramColor.withValues(alpha: 0.25), width: 0.8),
              ),
              child: Row(
                children: [
                  Icon(Icons.check_circle_outline_rounded, size: 16, color: telegramColor),
                  const SizedBox(width: 6),
                  Text(
                    'Chat ID: ${settings.telegramChatId}',
                    style: TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      color: telegramColor,
                    ),
                  ),
                  const Spacer(),
                  InkWell(
                    onTap: () => _showTelegramSetupDialog(context, settingsService, settings, lang, isFa),
                    child: Text(
                      isFa ? 'ویرایش / تغییر' : 'Change',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.primary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () async {
                      await settingsService.setTelegramChatId(null);
                      if (context.mounted) {
                        ServerAlertService.syncWithServer(context);
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(isFa ? 'اتصال تلگرام با موفقیت قطع شد.' : 'Telegram disconnected successfully.'),
                            behavior: SnackBarBehavior.floating,
                          ),
                        );
                      }
                    },
                    icon: const Icon(Icons.link_off_rounded, size: 14),
                    label: Text(
                      isFa ? 'قطع اتصال' : 'Disconnect',
                      style: const TextStyle(fontSize: 11),
                    ),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppTokens.negative,
                      side: BorderSide(color: AppTokens.negative.withValues(alpha: 0.4)),
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: () async {
                      if (settings.telegramChatId != null && settings.telegramChatId!.isNotEmpty) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(isFa ? '⏳ در حال ارسال پیام تست به تلگرام...' : '⏳ Sending test alert to Telegram...'),
                            duration: const Duration(seconds: 1),
                            behavior: SnackBarBehavior.floating,
                          ),
                        );
                        final res = await ServerAlertService.sendTelegramTestAlert(settings.telegramChatId!);
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
                      }
                    },
                    icon: const Icon(Icons.notifications_active_rounded, size: 14),
                    label: Text(
                      isFa ? 'تست ارسال پیام' : 'Test Alert',
                      style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold),
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: telegramColor,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                  ),
                ),
              ],
            ),
          ] else ...[
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: () => _showTelegramSetupDialog(context, settingsService, settings, lang, isFa),
                icon: const Icon(Icons.send_rounded, size: 15),
                label: Text(
                  isFa ? 'اتصال به ربات تلگرام 📱 (دریافت Chat ID)' : 'Connect Telegram Bot 📱 (Get Chat ID)',
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: telegramColor,
                  foregroundColor: Colors.white,
                  elevation: 0,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  void _showTelegramSetupDialog(
    BuildContext context,
    SettingsService settingsService,
    AppSettings settings,
    String lang,
    bool isFa,
  ) {
    if (!settings.isSignedInWithGoogle) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(isFa ? '⚠️ برای اتصال تلگرام ابتدا باید با حساب گوگل وارد شوید.' : '⚠️ Please sign in with Google first to connect Telegram.'),
          backgroundColor: AppTokens.warning,
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }
    final controller = TextEditingController(text: settings.telegramChatId ?? '');
    final theme = Theme.of(context);
    final isRtl = AppStrings.isRtl(lang);
    final telegramColor = const Color(0xFF229ED9);
    const botUsername = '@aisocialfeedbot';

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) {
          bool isTesting = false;
          return Directionality(
            textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
            child: AlertDialog(
              backgroundColor: theme.colorScheme.surface,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
              title: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(
                      color: telegramColor.withValues(alpha: 0.15),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(Icons.send_rounded, color: telegramColor, size: 20),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      isFa ? 'اتصال به ربات تلگرام SignalAlert' : 'Connect Telegram Alert Bot',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 15,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                  ),
                ],
              ),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isFa
                          ? 'مراحل اتصال ربات:\n'
                            '۱. در تلگرام وارد ربات زیر شوید:\n'
                          : 'Setup Steps:\n'
                            '1. Open the Telegram bot:\n',
                      style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurface.withValues(alpha: 0.8), height: 1.4),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                      decoration: BoxDecoration(
                        color: telegramColor.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: telegramColor.withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            botUsername,
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontFamily: 'monospace',
                              color: telegramColor,
                              fontSize: 13,
                            ),
                          ),
                          InkWell(
                            onTap: () {
                              Clipboard.setData(const ClipboardData(text: botUsername));
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text(isFa ? 'آیدی ربات کپی شد 📋' : 'Bot handle copied 📋'),
                                  duration: const Duration(seconds: 2),
                                  behavior: SnackBarBehavior.floating,
                                ),
                              );
                            },
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              decoration: BoxDecoration(
                                color: telegramColor,
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                isFa ? 'کپی آیدی' : 'Copy',
                                style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: Colors.white),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      isFa
                          ? '۲. دکمه /start را در ربات بزنید تا شناسه عددی (Chat ID) شما را تحویل دهد.\n'
                            '۳. عدد Chat ID را در کادر زیر وارد کنید:'
                          : '2. Send /start to the bot to get your numeric Chat ID.\n'
                            '3. Paste your Chat ID below:',
                      style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurface.withValues(alpha: 0.8), height: 1.4),
                    ),
                    const SizedBox(height: 10),
                    TextField(
                      controller: controller,
                      keyboardType: TextInputType.number,
                      style: TextStyle(fontFamily: 'monospace', fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
                      decoration: InputDecoration(
                        labelText: 'Telegram Chat ID',
                        hintText: 'e.g. 712345678',
                        prefixIcon: Icon(Icons.numbers_rounded, color: telegramColor),
                        filled: true,
                        fillColor: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.4),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                      ),
                    ),
                  ],
                ),
              ),
              actions: [
                if (settings.isTelegramConnected)
                  TextButton(
                    onPressed: () async {
                      await settingsService.setTelegramChatId(null);
                      if (context.mounted) {
                        Navigator.of(ctx).pop();
                        ServerAlertService.syncWithServer(context);
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(isFa ? 'اتصال تلگرام با موفقیت قطع شد.' : 'Telegram disconnected successfully.'),
                            behavior: SnackBarBehavior.floating,
                          ),
                        );
                      }
                    },
                    child: Text(
                      isFa ? 'قطع اتصال' : 'Disconnect',
                      style: const TextStyle(color: AppTokens.negative, fontWeight: FontWeight.bold),
                    ),
                  ),
                TextButton(
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: Text(
                    AppStrings.get('cancel', lang),
                    style: TextStyle(color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
                  ),
                ),
                ElevatedButton(
                  onPressed: () async {
                    final id = controller.text.trim();
                    if (id.isNotEmpty) {
                      await settingsService.setTelegramChatId(id);
                      if (context.mounted) {
                        Navigator.of(ctx).pop();
                        ServerAlertService.syncWithServer(context);
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(isFa ? '🎉 اتصال تلگرام با موفقیت فعال شد!' : '🎉 Telegram connected successfully!'),
                            backgroundColor: AppTokens.positive,
                            behavior: SnackBarBehavior.floating,
                          ),
                        );
                      }
                    } else {
                      await settingsService.setTelegramChatId(null);
                      if (context.mounted) {
                        Navigator.of(ctx).pop();
                        ServerAlertService.syncWithServer(context);
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(isFa ? 'اتصال تلگرام قطع شد.' : 'Telegram disconnected.'),
                            behavior: SnackBarBehavior.floating,
                          ),
                        );
                      }
                    }
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: telegramColor,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                  child: Text(isFa ? 'ذخیره و اتصال' : 'Save & Connect'),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
