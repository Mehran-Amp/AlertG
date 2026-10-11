import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../core/localization/app_strings.dart';
import '../services/settings_service.dart';

/// Modal dialog shown on very first launch of the app to prompt the user
/// to select their preferred language out of the 10 supported languages.
class FirstLaunchLanguageDialog extends StatefulWidget {
  const FirstLaunchLanguageDialog({super.key});

  static Future<void> showIfNeeded(BuildContext context) async {
    final settingsService = context.read<SettingsService>();
    if (!settingsService.settings.hasCompletedLanguageSetup) {
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => const FirstLaunchLanguageDialog(),
      );
    }
  }

  @override
  State<FirstLaunchLanguageDialog> createState() => _FirstLaunchLanguageDialogState();
}

class _FirstLaunchLanguageDialogState extends State<FirstLaunchLanguageDialog> {
  late String _selectedCode;

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
    _selectedCode = current.isNotEmpty ? current : 'fa';
  }

  @override
  Widget build(BuildContext context) {
    final settingsService = context.watch<SettingsService>();
    final theme = Theme.of(context);
    final isRtl = AppStrings.isRtl(_selectedCode);

    return Directionality(
      textDirection: isRtl ? TextDirection.rtl : TextDirection.ltr,
      child: PopScope(
        canPop: false, // User must choose a language to proceed
        child: Dialog(
          backgroundColor: theme.colorScheme.surface,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
          insetPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Header
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.primary.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Text(
                          '🌍',
                          style: const TextStyle(fontSize: 26),
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              isRtl ? 'انتخاب زبان برنامه' : 'Select App Language',
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                                color: theme.colorScheme.onSurface,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              isRtl
                                  ? '۱۰ زبان بین‌المللی • قابل تغییر در تنظیمات'
                                  : '10 Languages • Change anytime in settings',
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

                  const SizedBox(height: 18),
                  Divider(height: 1, color: theme.dividerColor),
                  const SizedBox(height: 14),

                  // Languages List
                  Flexible(
                    child: ListView.separated(
                      shrinkWrap: true,
                      itemCount: _languages.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 8),
                      itemBuilder: (context, index) {
                        final lang = _languages[index];
                        final isSelected = lang['code'] == _selectedCode;

                        return InkWell(
                          onTap: () {
                            setState(() => _selectedCode = lang['code']!);
                            settingsService.setLanguage(lang['code']!);
                          },
                          borderRadius: BorderRadius.circular(14),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                            decoration: BoxDecoration(
                              color: isSelected
                                  ? theme.colorScheme.primary.withValues(alpha: 0.12)
                                  : theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(
                                color: isSelected
                                    ? theme.colorScheme.primary
                                    : theme.dividerColor,
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
                                          color: isSelected
                                              ? theme.colorScheme.primary
                                              : theme.colorScheme.onSurface,
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

                  // Confirm & Continue Button
                  ElevatedButton(
                    onPressed: () async {
                      await settingsService.setLanguage(_selectedCode);
                      await settingsService.completeLanguageSetup();
                      if (context.mounted) {
                        Navigator.of(context).pop();
                      }
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
                          isRtl ? 'تأیید و شروع به کار' : 'Confirm & Get Started',
                          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(width: 8),
                        Icon(isRtl ? Icons.arrow_back_rounded : Icons.arrow_forward_rounded, size: 18),
                      ],
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
}
