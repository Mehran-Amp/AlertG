import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../alert_engine/models/alert_rule.dart';
import '../alert_engine/repositories/json_alert_rule_repository.dart';
import '../../core/utils/format_utils.dart';

/// Redesigned, ultra-clean Home Screen Widget representation for Alarmer.
/// - Exact alert order
/// - Clean single-line row: Symbol | Price | Pure Percentage + Arrow
/// - Dedicated Check/Refresh All button in header
/// - 100% Theme unified with active app palette
/// - No exchange name, no notes, compact wrap-content height
class AlertHomeWidgetView extends StatelessWidget {
  final JsonAlertRuleRepository repository;
  final String lang;
  final VoidCallback? onRefresh;
  final VoidCallback? onAddNew;
  final ValueChanged<AlertRule>? onToggleRule;
  final bool isCompact;

  const AlertHomeWidgetView({
    super.key,
    required this.repository,
    required this.lang,
    this.onRefresh,
    this.onAddNew,
    this.onToggleRule,
    this.isCompact = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final allRules = repository.allRules;
    final activeRules = allRules.where((r) => r.isActive).toList();

    return Container(
      decoration: BoxDecoration(
        color: theme.cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: theme.dividerColor,
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.25 : 0.05),
            blurRadius: 10,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Header Bar with Check All Button
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(5),
                decoration: BoxDecoration(
                  color: theme.colorScheme.primary.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  Icons.bolt_rounded,
                  color: theme.colorScheme.primary,
                  size: 16,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Alarmer Live',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                    Text(
                      '${activeRules.length} active • ${DateFormat('HH:mm').format(DateTime.now())}',
                      style: TextStyle(
                        fontSize: 9.5,
                        color: isDark ? const Color(0xFF9CA3AF) : const Color(0xFF4B5563),
                      ),
                    ),
                  ],
                ),
              ),
              // Check / Refresh All Currencies Button
              Material(
                color: theme.colorScheme.primary.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
                child: InkWell(
                  onTap: onRefresh,
                  borderRadius: BorderRadius.circular(8),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.refresh_rounded,
                          size: 13,
                          color: theme.colorScheme.primary,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          'Check All',
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.primary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 8),
          Divider(height: 1, color: theme.dividerColor),
          const SizedBox(height: 6),

          // Alert Items List (One horizontal line per alert, wrap height)
          if (allRules.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Center(
                child: Text(
                  'No active alerts configured',
                  style: TextStyle(
                    fontSize: 11,
                    color: isDark ? const Color(0xFF9CA3AF) : const Color(0xFF4B5563),
                  ),
                ),
              ),
            )
          else
            ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: isCompact ? allRules.take(3).length : allRules.take(5).length,
              separatorBuilder: (_, __) => const SizedBox(height: 5),
              itemBuilder: (context, index) {
                final rule = allRules[index];
                return _buildSingleLineAlertRow(context, rule, theme, isDark);
              },
            ),

          if (allRules.length > (isCompact ? 3 : 5)) ...[
            const SizedBox(height: 4),
            Center(
              child: Text(
                '+ ${allRules.length - (isCompact ? 3 : 5)} more alerts in background',
                style: TextStyle(
                  fontSize: 9.5,
                  color: isDark ? const Color(0xFF9CA3AF) : const Color(0xFF4B5563),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// Single line alert row: Symbol | Price | Percentage+Arrow Badge
  Widget _buildSingleLineAlertRow(
    BuildContext context,
    AlertRule rule,
    ThemeData theme,
    bool isDark,
  ) {
    final currentPrice = rule.lastCheckedPrice ?? rule.basePrice ?? 0.0;
    final formattedPrice = currentPrice > 0
        ? FormatUtils.formatPrice(currentPrice, currencySymbol: rule.pair.counterCurrency, lang: lang)
        : '—';

    // Check if one-shot condition fulfilled
    // All types close with Done EXCEPT Percent Change Both Way which stays permanently active!
    final isPermanentBothWayPercent = rule.conditionType == AlertConditionType.percentChange &&
        rule.direction == AlertDirection.bothSides;
    final isDone = !isPermanentBothWayPercent && (!rule.isActive || rule.isTriggered);

    String badgeText;
    Color badgeBgColor;
    Color badgeTextColor;

    if (isDone) {
      badgeText = '✅ Done';
      badgeBgColor = isDark ? const Color(0xFF2B2410) : const Color(0xFFFEF3C7);
      badgeTextColor = isDark ? const Color(0xFFE3B341) : const Color(0xFFD97706);
    } else {
      // Calculate authentic real percentage change (never stuck on +0.00%)
      double diffPct = 0.0;
      final base = rule.basePrice;

      if (base != null && base > 0 && currentPrice > 0 && (currentPrice - base).abs() > 0.0001) {
        diffPct = ((currentPrice - base) / base) * 100.0;
      } else if (rule.conditionType == AlertConditionType.priceThreshold && rule.targetPrice != null && rule.targetPrice! > 0 && currentPrice > 0) {
        // For price target: show real percentage distance to target
        diffPct = ((rule.targetPrice! - currentPrice) / currentPrice) * 100.0;
      } else if (rule.percent != null && rule.percent! > 0) {
        // For percent change: show active target rule threshold
        diffPct = rule.direction == AlertDirection.below ? -rule.percent! : rule.percent!;
      } else if (base != null && base > 0 && currentPrice > 0) {
        diffPct = ((currentPrice - base) / base) * 100.0;
      }

      final isUp = diffPct >= 0;
      final sign = isUp ? '+' : '';
      final arrow = isUp ? '▲' : '▼';
      badgeText = '$sign${diffPct.toStringAsFixed(2)}% $arrow';

      if (isUp) {
        // Entire percentage badge (text, number, %, sign, arrow) in unified green
        badgeBgColor = isDark ? const Color(0xFF1A2E20) : const Color(0xFFDCFCE7);
        badgeTextColor = isDark ? const Color(0xFF3FB950) : const Color(0xFF15803D);
      } else {
        // Entire percentage badge in unified red
        badgeBgColor = isDark ? const Color(0xFF2E1A1D) : const Color(0xFFFEE2E2);
        badgeTextColor = isDark ? const Color(0xFFF85149) : const Color(0xFFB91C1C);
      }
    }

    final priceColor = isDark ? const Color(0xFFF59E0B) : const Color(0xFFD97706);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
      decoration: BoxDecoration(
        color: isDark
            ? theme.scaffoldBackgroundColor.withValues(alpha: 0.8)
            : theme.scaffoldBackgroundColor,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: theme.dividerColor.withValues(alpha: 0.6),
          width: 0.8,
        ),
      ),
      child: Row(
        children: [
          // Symbol (Fixed Left)
          Text(
            rule.pair.displayName,
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: theme.colorScheme.onSurface,
            ),
          ),
          const SizedBox(width: 8),

          // Price (Middle Expanded)
          Expanded(
            child: Text(
              formattedPrice,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w800,
                fontFamily: 'monospace',
                color: priceColor,
              ),
            ),
          ),

          // Percentage + Arrow (Fixed Right, Unified Color)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2.5),
            decoration: BoxDecoration(
              color: badgeBgColor,
              borderRadius: BorderRadius.circular(5),
            ),
            child: Text(
              badgeText,
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.bold,
                color: badgeTextColor,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
