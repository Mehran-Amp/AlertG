import 'package:flutter/material.dart';
import '../../../core/localization/app_strings.dart';
import '../../../core/theme/tokens.dart';

/// Group header for separating notification logs by day (Today, Yesterday, or MMM d, yyyy).
class HistoryGroupHeader extends StatelessWidget {
  final DateTime date;
  final String? lang;

  const HistoryGroupHeader({super.key, required this.date, this.lang});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final activeLang = lang ?? 'en';
    final title = _formatHeader(date, activeLang);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: AppTokens.space16,
        vertical: AppTokens.space8,
      ),
      color: theme.scaffoldBackgroundColor,
      child: Text(
        title.toUpperCase(),
        style: TextStyle(
          fontSize: 11,
          letterSpacing: 1.0,
          fontWeight: FontWeight.w700,
          color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
        ),
      ),
    );
  }

  String _formatHeader(DateTime dt, String activeLang) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final yesterday = today.subtract(const Duration(days: 1));
    final checkDate = DateTime(dt.year, dt.month, dt.day);

    if (checkDate == today) {
      return AppStrings.get('date_today', activeLang);
    } else if (checkDate == yesterday) {
      return AppStrings.get('date_yesterday', activeLang);
    } else {
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      return '${months[dt.month - 1]} ${dt.day}, ${dt.year}';
    }
  }
}
