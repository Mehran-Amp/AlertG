import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../core/localization/app_strings.dart';
import '../../../core/utils/app_lifecycle_helper.dart';
import '../services/settings_service.dart';

/// Comprehensive First Launch Onboarding Wizard
/// Step 1: Language Selection (10 languages)
/// Step 2: High-Converting Background Optimization & 24/7 Alert Reliability Guidance
/// Includes direct 1-tap launchers for Autostart, Battery Optimization, and Lockscreen Pop-ups,
/// with intelligent risk warnings if the user attempts to skip without enabling.
class FirstLaunchOnboardingWizard extends StatefulWidget {
  const FirstLaunchOnboardingWizard({super.key});

  static Future<void> showIfNeeded(BuildContext context) async {
    final settingsService = context.read<SettingsService>();
    if (!settingsService.settings.hasCompletedLanguageSetup) {
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => const FirstLaunchOnboardingWizard(),
      );
    }
  }

  @override
  State<FirstLaunchOnboardingWizard> createState() => _FirstLaunchOnboardingWizardState();
}

class _FirstLaunchOnboardingWizardState extends State<FirstLaunchOnboardingWizard> {
  int _currentStep = 0; // 0 = Language Selection, 1 = Background Optimization
  late String _selectedLanguageCode;

  bool _autostartClicked = false;
  bool _batteryClicked = false;
  bool _otherPermissionsClicked = false;

  final List<Map<String, String>> _languages = const [
    {'code': 'fa', 'flag': '🇮🇷', 'name': 'Persian', 'native': 'فارسی'},
    {'code': 'en', 'flag': '🇺🇸', 'name': 'English', 'native': 'English'},
    {'code': 'ckb', 'flag': '☀️', 'name': 'Kurdish', 'native': 'کوردی'},
    {'code': 'ar', 'flag': '🇸🇦', 'name': 'Arabic', 'native': 'العربية'},
    {'code': 'tr', 'flag': '🇹🇷', 'name': 'Turkish', 'native': 'Türkçe'},
    {'code': 'de', 'flag': '🇩🇪', 'name': 'German', 'native': 'Deutsch'},
    {'code': 'fr', 'flag': '🇫🇷', 'name': 'French', 'native': 'Français'},
    {'code': 'es', 'flag': '🇪🇸', 'name': 'Spanish', 'native': 'Español'},
    {'code': 'zh', 'flag': '🇨🇳', 'name': 'Chinese', 'native': '中文'},
    {'code': 'ko', 'flag': '🇰🇷', 'name': 'Korean', 'native': '한국어'},
  ];

  @override
  void initState() {
    super.initState();
    final current = context.read<SettingsService>().settings.language;
    _selectedLanguageCode = current.isNotEmpty ? current : 'fa';
  }

  bool get _isFa => _selectedLanguageCode == 'fa' || _selectedLanguageCode == 'ckb' || _selectedLanguageCode == 'ar';
  bool get _isRtl => AppStrings.isRtl(_selectedLanguageCode);

  Future<void> _handleProceedToApp() async {
    final settingsService = context.read<SettingsService>();
    await settingsService.setLanguage(_selectedLanguageCode);
    await settingsService.completeLanguageSetup();
    if (mounted) {
      Navigator.of(context).pop();
    }
  }

  void _showSkipWarningDialog(BuildContext context, ThemeData theme) {
    showDialog<void>(
      context: context,
      barrierDismissible: true,
      builder: (ctx) {
        return Directionality(
          textDirection: _isRtl ? TextDirection.rtl : TextDirection.ltr,
          child: AlertDialog(
            backgroundColor: theme.colorScheme.surface,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
            title: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.amber.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.warning_amber_rounded, color: Colors.amber, size: 28),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    _isFa ? '⚠️ هشدار حساسیت هشدارها' : '⚠️ Critical Alert Warning',
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                      color: theme.colorScheme.onSurface,
                    ),
                  ),
                ),
              ],
            ),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _isFa
                      ? 'در صورت فعال نکردن شروع خودکار و تنظیمات باتری، سیستم‌عامل گوشی شما (به‌ویژه شیائومی، سامسونگ و هواوی) ممکن است در زمان بسته بودن اپ یا قفل بودن صفحه، دریافت هشدارهای زنده قیمت و سیگنال‌ها را به تعویق بیندازد یا متوقف کند.\n\nآیا مطمئن هستید که می‌خواهید بدون این تنظیمات ادامه دهید؟'
                      : 'Without enabling Autostart and disabling Battery Optimization, your device OS (especially Xiaomi, Samsung, and Huawei) may suppress live price notifications when the screen is locked or the app is closed.\n\nAre you sure you want to proceed without enabling them?',
                  style: TextStyle(
                    fontSize: 12.5,
                    height: 1.5,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.85),
                  ),
                ),
              ],
            ),
            actionsPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            actions: [
              TextButton(
                onPressed: () {
                  Navigator.of(ctx).pop();
                  _handleProceedToApp();
                },
                child: Text(
                  _isFa ? 'متوجه هستم، ورود به هر حال' : 'I Understand, Skip Anyway',
                  style: TextStyle(
                    fontSize: 12,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
              ),
              ElevatedButton(
                onPressed: () {
                  Navigator.of(ctx).pop();
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: theme.colorScheme.primary,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  elevation: 0,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                ),
                child: Text(
                  _isFa ? 'بازگشت به فعال‌سازی (توصیه می‌شود)' : 'Back to Enable (Recommended)',
                  style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final settingsService = context.watch<SettingsService>();

    return Directionality(
      textDirection: _isRtl ? TextDirection.rtl : TextDirection.ltr,
      child: PopScope(
        canPop: false, // Prevent dismissing without choosing
        child: Dialog(
          backgroundColor: theme.colorScheme.surface,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(26)),
          insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480, maxHeight: 680),
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 300),
              child: _currentStep == 0
                  ? _buildLanguageStep(context, theme, settingsService)
                  : _buildOptimizationStep(context, theme),
            ),
          ),
        ),
      ),
    );
  }

  // -------------------------------------------------------------
  // STEP 1: LANGUAGE SELECTION
  // -------------------------------------------------------------
  Widget _buildLanguageStep(BuildContext context, ThemeData theme, SettingsService settingsService) {
    return Padding(
      key: const ValueKey('step_language'),
      padding: const EdgeInsets.all(22),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: theme.colorScheme.primary.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Text('🌍', style: TextStyle(fontSize: 26)),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _isRtl ? 'انتخاب زبان برنامه' : 'Select App Language',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _isRtl
                          ? '۱۰ زبان بین‌المللی • قابل تغییر در تنظیمات'
                          : '10 Global Languages • Change anytime in settings',
                      style: TextStyle(
                        fontSize: 11,
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Divider(height: 1, color: theme.dividerColor),
          const SizedBox(height: 12),

          // List of languages
          Flexible(
            child: ListView.separated(
              shrinkWrap: true,
              itemCount: _languages.length,
              separatorBuilder: (_, __) => const SizedBox(height: 8),
              itemBuilder: (context, index) {
                final lang = _languages[index];
                final isSelected = lang['code'] == _selectedLanguageCode;

                return InkWell(
                  onTap: () {
                    setState(() => _selectedLanguageCode = lang['code']!);
                    settingsService.setLanguage(lang['code']!);
                  },
                  borderRadius: BorderRadius.circular(14),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: isSelected
                          ? theme.colorScheme.primary.withValues(alpha: 0.12)
                          : theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.4),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(
                        color: isSelected ? theme.colorScheme.primary : theme.dividerColor,
                        width: isSelected ? 1.5 : 1.0,
                      ),
                    ),
                    child: Row(
                      children: [
                        Text(lang['flag']!, style: const TextStyle(fontSize: 22)),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                lang['native']!,
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 13,
                                  color: isSelected ? theme.colorScheme.primary : theme.colorScheme.onSurface,
                                ),
                              ),
                              Text(
                                lang['name']!,
                                style: TextStyle(
                                  fontSize: 10.5,
                                  color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
                                ),
                              ),
                            ],
                          ),
                        ),
                        if (isSelected)
                          Icon(
                            Icons.check_circle_rounded,
                            color: theme.colorScheme.primary,
                            size: 20,
                          ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),

          const SizedBox(height: 16),
          Divider(height: 1, color: theme.dividerColor),
          const SizedBox(height: 14),

          // Next Step: Background Optimization
          ElevatedButton(
            onPressed: () {
              setState(() => _currentStep = 1);
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: theme.colorScheme.primary,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 13),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
              elevation: 0,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  _isRtl ? 'ادامه به تنظیمات پایداری هشدارها' : 'Continue to Alert Reliability Setup',
                  style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.bold),
                ),
                const SizedBox(width: 8),
                Icon(_isRtl ? Icons.arrow_back_rounded : Icons.arrow_forward_rounded, size: 18),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // -------------------------------------------------------------
  // STEP 2: BACKGROUND 24/7 OPTIMIZATION (PERSUASIVE ONBOARDING)
  // -------------------------------------------------------------
  Widget _buildOptimizationStep(BuildContext context, ThemeData theme) {
    return Padding(
      key: const ValueKey('step_optimization'),
      padding: const EdgeInsets.all(20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header Badge
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      theme.colorScheme.primary.withValues(alpha: 0.2),
                      Colors.amber.withValues(alpha: 0.2),
                    ],
                  ),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Text('⚡', style: TextStyle(fontSize: 26)),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _isFa ? 'تضمین دریافت ۲۴ ساعته هشدارها' : 'Guarantee 24/7 Live Alerts',
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _isFa
                          ? 'دریافت بدون وقفه، آژیر صوتی و رفع خواب پس‌زمینه'
                          : 'Zero-delay push notifications, sirens & voice speech',
                      style: TextStyle(
                        fontSize: 11,
                        color: theme.colorScheme.primary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: theme.colorScheme.primary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.2)),
            ),
            child: Row(
              children: [
                const Icon(Icons.info_outline_rounded, size: 18, color: Colors.amber),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _isFa
                        ? 'برای اینکه در زمان قفل بودن گوشی هشدارهای نوسان قیمت با صدای آژیر و گفتار صوتی پخش شوند، ۳ مجوز زیر را ۱ بار فعال نمایید:'
                        : 'To ensure alerts trigger loud sirens and voice announcements when the screen is locked, please enable these 3 quick permissions:',
                    style: TextStyle(fontSize: 11, height: 1.4, color: theme.colorScheme.onSurface.withValues(alpha: 0.85)),
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 12),

          // 3 Action Cards
          Flexible(
            child: ListView(
              shrinkWrap: true,
              children: [
                // CARD 1: Autostart
                _buildActionCard(
                  theme: theme,
                  icon: Icons.rocket_launch_rounded,
                  iconColor: Colors.blueAccent,
                  title: _isFa ? '۱. فعال‌سازی شروع خودکار (Autostart)' : '1. Enable Autostart (Background Launch)',
                  subtitle: _isFa
                      ? 'اجازه اجرای مداوم و بیدار ماندن اپلیکیشن در پس‌زمینه (بسیار مهم برای شیائومی و هواوی)'
                      : 'Allows SignalAlert to stay active in background (Critical for Xiaomi, Samsung & Huawei)',
                  buttonText: _isFa ? '⚙️ باز کردن تنظیمات Autostart' : '⚙️ Open Autostart Settings',
                  isDone: _autostartClicked,
                  onTap: () async {
                    setState(() => _autostartClicked = true);
                    await AppLifecycleHelper.openAutostartSettings();
                  },
                ),
                const SizedBox(height: 8),

                // CARD 2: Battery Saver (No restrictions)
                _buildActionCard(
                  theme: theme,
                  icon: Icons.battery_charging_full_rounded,
                  iconColor: Colors.greenAccent,
                  title: _isFa ? '۲. حذف محدودیت باتری (No Restrictions)' : '2. Remove Battery Limits (No Restrictions)',
                  subtitle: _isFa
                      ? 'تنظیم Battery Saver روی «بدون محدودیت» تا اینترنت و پردازش پس‌زمینه قطع نشود'
                      : 'Set Battery Saver to "No restrictions" so background network and timers never sleep',
                  buttonText: _isFa ? '🔋 باز کردن تنظیمات باتری' : '🔋 Open Battery Settings',
                  isDone: _batteryClicked,
                  onTap: () async {
                    setState(() => _batteryClicked = true);
                    await AppLifecycleHelper.openBatteryOptimizationSettings();
                  },
                ),
                const SizedBox(height: 8),

                // CARD 3: Lockscreen & Pop-up Window permissions
                _buildActionCard(
                  theme: theme,
                  icon: Icons.screen_lock_portrait_rounded,
                  iconColor: Colors.purpleAccent,
                  title: _isFa ? '۳. نمایش روی صفحه قفل (Lock Screen & Pop-up)' : '3. Lock Screen & Pop-Up Windows',
                  subtitle: _isFa
                      ? 'تیک زدن Show on Lock screen و Display pop-up windows در بخش دسترسی‌های برنامه'
                      : 'Allow "Show on Lock screen" & "Display pop-up windows" under Other permissions',
                  buttonText: _isFa ? '📱 باز کردن سایر دسترسی‌ها (App Details)' : '📱 Open App Details (Other Permissions)',
                  isDone: _otherPermissionsClicked,
                  onTap: () async {
                    setState(() => _otherPermissionsClicked = true);
                    await AppLifecycleHelper.openAppSettings();
                  },
                ),
              ],
            ),
          ),

          const SizedBox(height: 12),
          Divider(height: 1, color: theme.dividerColor),
          const SizedBox(height: 12),

          // Primary Done Button
          ElevatedButton(
            onPressed: _handleProceedToApp,
            style: ElevatedButton.styleFrom(
              backgroundColor: theme.colorScheme.primary,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 13),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
              elevation: 0,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.check_circle_outline_rounded, size: 20),
                const SizedBox(width: 8),
                Text(
                  _isFa ? '✅ تنظیمات را اعمال کردم • ورود به برنامه' : '✅ I Completed the Setup • Launch App',
                  style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.bold),
                ),
              ],
            ),
          ),

          const SizedBox(height: 6),

          // Secondary Skip with Warning Button
          TextButton(
            onPressed: () => _showSkipWarningDialog(context, theme),
            child: Text(
              _isFa ? 'رد شدن و ورود (عدم توصیه - ممکن است آلارم‌ها با تأخیر باشند)' : 'Skip and Enter (Not Recommended - Alerts may be delayed)',
              style: TextStyle(
                fontSize: 11,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActionCard({
    required ThemeData theme,
    required IconData icon,
    required Color iconColor,
    required String title,
    required String subtitle,
    required String buttonText,
    required bool isDone,
    required VoidCallback onTap,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isDone
            ? theme.colorScheme.primary.withValues(alpha: 0.08)
            : theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isDone ? theme.colorScheme.primary.withValues(alpha: 0.4) : theme.dividerColor,
          width: isDone ? 1.5 : 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(icon, color: iconColor, size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.onSurface,
                  ),
                ),
              ),
              if (isDone)
                const Icon(Icons.check_circle_rounded, color: Colors.green, size: 18),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            subtitle,
            style: TextStyle(
              fontSize: 10.5,
              height: 1.35,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
            ),
          ),
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: onTap,
            style: OutlinedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
              side: BorderSide(
                color: isDone ? theme.colorScheme.primary : theme.colorScheme.primary.withValues(alpha: 0.5),
              ),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              backgroundColor: isDone ? theme.colorScheme.primary.withValues(alpha: 0.1) : Colors.transparent,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  buttonText,
                  style: TextStyle(
                    fontSize: 11.5,
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.primary,
                  ),
                ),
                const SizedBox(width: 6),
                const Icon(Icons.open_in_new_rounded, size: 14),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
