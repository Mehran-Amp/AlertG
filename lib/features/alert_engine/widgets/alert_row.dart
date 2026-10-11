import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../core/localization/app_strings.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/utils/format_utils.dart';
import '../../settings/services/settings_service.dart';
import '../models/alert_rule.dart';
import 'cooldown_timer.dart';

/// Single alert rule row widget with swipe-to-delete, direct toggle,
/// long-press contextual actions, and independent cooldown timer.
class AlertRow extends StatelessWidget {
  final AlertRule rule;
  final ValueChanged<bool> onToggle;
  final VoidCallback onSwipeDelete;
  final VoidCallback onRearm;
  final VoidCallback onDuplicate;
  final VoidCallback onEdit;
  final VoidCallback onExport;

  const AlertRow({
    super.key,
    required this.rule,
    required this.onToggle,
    required this.onSwipeDelete,
    required this.onRearm,
    required this.onDuplicate,
    required this.onEdit,
    required this.onExport,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final lang = context.watch<SettingsService>().settings.language;
    final conditionDescription = _buildConditionDescription(rule, lang);

    return Dismissible(
      key: Key(rule.uuid),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: AppTokens.space24),
        decoration: BoxDecoration(
          color: AppTokens.negative,
          borderRadius: BorderRadius.circular(12),
        ),
        child: const Icon(
          Icons.delete_sweep_rounded,
          color: Colors.white,
          size: 26,
        ),
      ),
      onDismissed: (_) => onSwipeDelete(),
      child: GestureDetector(
        onLongPressStart: (details) => _showContextMenu(context, details.globalPosition, lang),
        child: Container(
          margin: const EdgeInsets.symmetric(
            horizontal: AppTokens.space16,
            vertical: AppTokens.space6,
          ),
          padding: const EdgeInsets.all(AppTokens.space16),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: rule.isInCooldown
                  ? AppTokens.warning.withValues(alpha: 0.5)
                  : theme.dividerColor,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header Row: Pair, Exchange & Active Switch
              Row(
                children: [
                  Text(
                    '${rule.baseCurrency} / ${FormatUtils.resolveCurrencyDisplayName(rule.counterCurrency, lang: lang)}',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 14,
                      color: rule.isActive
                          ? theme.colorScheme.onSurface
                          : theme.colorScheme.onSurface.withValues(alpha: 0.45),
                    ),
                  ),
                  const SizedBox(width: AppTokens.space8),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppTokens.space6,
                      vertical: 1.5,
                    ),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: theme.dividerColor),
                    ),
                    child: Text(
                      rule.exchangeId.toUpperCase(),
                      style: TextStyle(
                        color: theme.colorScheme.primary,
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  const Spacer(),
                  Transform.scale(
                    scale: 0.8,
                    child: Switch(
                      value: rule.isActive,
                      activeThumbColor: Colors.white,
                      activeTrackColor: theme.colorScheme.primary,
                      onChanged: onToggle,
                    ),
                  ),
                ],
              ),

              const SizedBox(height: AppTokens.space6),

              // Condition description
              Text(
                conditionDescription,
                style: TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                  color: rule.isActive
                      ? theme.colorScheme.onSurface.withValues(alpha: 0.8)
                      : theme.colorScheme.onSurface.withValues(alpha: 0.4),
                ),
              ),

              if (rule.customNote != null && rule.customNote!.trim().isNotEmpty) ...[
                const SizedBox(height: AppTokens.space6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.2)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.edit_note_rounded, size: 14, color: theme.colorScheme.primary),
                      const SizedBox(width: 4),
                      Flexible(
                        child: Text(
                          rule.customNote!.trim(),
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: theme.colorScheme.primary,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
              ],

              const SizedBox(height: AppTokens.space8),

              // Metadata Row: Trigger count & last triggered & Sound/Vibrate icons
              Row(
                children: [
                  Text(
                    '${AppStrings.get('triggers_count', lang)} ${rule.triggerCount}',
                    style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
                  ),
                  if (rule.lastTriggeredAt != null) ...[
                    const SizedBox(width: AppTokens.space8),
                    Text('·', style: TextStyle(color: theme.colorScheme.onSurface.withValues(alpha: 0.5))),
                    const SizedBox(width: AppTokens.space8),
                    Text(
                      '${AppStrings.get('last_trigger', lang)} ${_formatTime(rule.lastTriggeredAt!)}',
                      style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
                    ),
                  ],
                  const Spacer(),
                  if (rule.soundEnabled)
                    Padding(
                      padding: const EdgeInsets.only(left: 4),
                      child: Icon(Icons.volume_up_rounded, size: 14, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
                    ),
                  if (rule.vibrationEnabled)
                    Padding(
                      padding: const EdgeInsets.only(left: 4),
                      child: Icon(Icons.vibration_rounded, size: 14, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
                    ),
                ],
              ),

              if (rule.isInCooldown && rule.cooldownUntil != null)
                CooldownTimer(
                  cooldownUntil: rule.cooldownUntil!,
                  onRearmPressed: onRearm,
                ),
            ],
          ),
        ),
      ),
    );
  }

  void _showContextMenu(BuildContext context, Offset position, String lang) {
    final theme = Theme.of(context);
    showMenu<String>(
      context: context,
      position: RelativeRect.fromLTRB(
        position.dx,
        position.dy,
        position.dx + 1,
        position.dy + 1,
      ),
      color: theme.colorScheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: theme.dividerColor),
      ),
      items: [
        PopupMenuItem(
          value: 'duplicate',
          child: Row(
            children: [
              Icon(Icons.copy_rounded, size: 18, color: theme.colorScheme.primary),
              const SizedBox(width: AppTokens.space12),
              Text(AppStrings.get('duplicate_action', lang), style: TextStyle(color: theme.colorScheme.onSurface, fontSize: 13)),
            ],
          ),
        ),
        PopupMenuItem(
          value: 'edit',
          child: Row(
            children: [
              Icon(Icons.edit_rounded, size: 18, color: theme.colorScheme.primary),
              const SizedBox(width: AppTokens.space12),
              Text(AppStrings.get('edit_action', lang), style: TextStyle(color: theme.colorScheme.onSurface, fontSize: 13)),
            ],
          ),
        ),
        PopupMenuItem(
          value: 'export',
          child: Row(
            children: [
              Icon(Icons.ios_share_rounded, size: 18, color: theme.colorScheme.primary),
              const SizedBox(width: AppTokens.space12),
              Text(AppStrings.get('export_rule_action', lang), style: TextStyle(color: theme.colorScheme.onSurface, fontSize: 13)),
            ],
          ),
        ),
      ],
    ).then((selection) {
      if (selection == 'duplicate') onDuplicate();
      if (selection == 'edit') onEdit();
      if (selection == 'export') onExport();
    });
  }

  String _buildConditionDescription(AlertRule rule, String lang) {
    switch (rule.conditionType) {
      case AlertConditionType.priceThreshold:
        if (rule.direction == AlertDirection.bothSides && rule.upperTargetPrice != null && rule.lowerTargetPrice != null) {
          final upT = FormatUtils.formatAlertCardPrice(rule.upperTargetPrice!, rule.counterCurrency, lang: lang);
          final lowT = FormatUtils.formatAlertCardPrice(rule.lowerTargetPrice!, rule.counterCurrency, lang: lang);
          if (lang == 'fa') {
            return 'عبور قیمت: بالا > $upT یا پایین < $lowT';
          }
          return 'Price breakout: > $upT or < $lowT';
        }
        final target = FormatUtils.formatAlertCardPrice(rule.targetPrice ?? 0.0, rule.counterCurrency, lang: lang);
        final isAbove = rule.direction == AlertDirection.above;
        if (lang == 'fa') {
          return 'عبور قیمت ${isAbove ? 'به بالاتر از' : 'به پایین‌تر از'} $target';
        } else if (lang == 'ckb') {
          return 'تێپەڕینی نرخ بۆ ${isAbove ? 'سەرەوەی' : 'خوارەوەی'} $target';
        } else if (lang == 'ar') {
          return 'تجاوز السعر ${isAbove ? 'أعلى من' : 'أدنى من'} $target';
        } else if (lang == 'tr') {
          return 'Fiyat $target ${isAbove ? 'üzerine çıkışı' : 'altına düşüşü'}';
        } else if (lang == 'de') {
          return 'Preis ${isAbove ? 'über' : 'unter'} $target';
        } else if (lang == 'es') {
          return 'Precio ${isAbove ? 'por encima de' : 'por debajo de'} $target';
        } else if (lang == 'fr') {
          return 'Prix ${isAbove ? 'au-dessus de' : 'en dessous de'} $target';
        } else if (lang == 'ru') {
          return 'Цена ${isAbove ? 'выше' : 'ниже'} $target';
        } else if (lang == 'zh') {
          return '价格${isAbove ? '高于' : '低于'} $target';
        }
        final dir = isAbove ? 'ABOVE' : 'BELOW';
        return 'Price crosses $dir $target';

      case AlertConditionType.percentChange:
        final dir = rule.direction == AlertDirection.above
            ? '+'
            : (rule.direction == AlertDirection.below ? '-' : '±');
        final pctNum = rule.percent ?? 0.0;
        final pct = (pctNum == pctNum.roundToDouble()) ? pctNum.toInt().toString() : pctNum.toString();
        final secs = rule.checkIntervalSeconds;
        final windowLabel = secs >= 3600
            ? '${secs ~/ 3600}h'
            : (secs >= 60 ? '${secs ~/ 60}m' : '${secs}s');
        if (lang == 'fa') {
          return 'نوسان قیمت $dir$pct% در $windowLabel';
        } else if (lang == 'ckb') {
          return 'جووڵەی نرخ $dir$pct% لە $windowLabel';
        } else if (lang == 'ar') {
          return 'تغير السعر $dir$pct% خلال $windowLabel';
        } else if (lang == 'de') {
          return 'Preisschwankung $dir$pct% in $windowLabel';
        } else if (lang == 'tr') {
          return '$windowLabel içinde $dir%$pct fiyat hareketi';
        } else if (lang == 'es') {
          return 'Variación de precio $dir$pct% en $windowLabel';
        } else if (lang == 'fr') {
          return 'Variation de prix $dir$pct% en $windowLabel';
        } else if (lang == 'ru') {
          return 'Изменение цены $dir$pct% за $windowLabel';
        } else if (lang == 'zh') {
          return '$windowLabel 内价格变动 $dir$pct%';
        }
        return 'Price moves $dir$pct% in $windowLabel';

      case AlertConditionType.absolutePriceChange:
        final delta = (rule.deltaAbsolute ?? 0.0).toStringAsFixed(2);
        if (lang == 'fa') return 'نوسان دلاری >= \$$delta';
        if (lang == 'ckb') return 'نوسانی دۆلاری >= \$$delta';
        if (lang == 'ar') return 'التغير بالدولار >= \$$delta';
        if (lang == 'de') return 'Preis-Delta >= \$$delta';
        if (lang == 'tr') return 'Fiyat değişimi >= \$$delta';
        if (lang == 'es') return 'Variación >= \$$delta';
        if (lang == 'fr') return 'Écart de prix >= \$$delta';
        if (lang == 'ru') return 'Изменение цены >= \$$delta';
        if (lang == 'zh') return '价格波动 >= \$$delta';
        return 'Price delta >= \$$delta';

      case AlertConditionType.volumeChange:
        final vol = (rule.volumePercent ?? 0.0).toStringAsFixed(0);
        if (lang == 'fa') return 'جهش حجم معاملات >= $vol%';
        if (lang == 'ckb') return 'زیادبوونی قەبارە >= $vol%';
        if (lang == 'ar') return 'ارتفاع الحجم >= $vol%';
        if (lang == 'de') return 'Volumenanstieg >= $vol%';
        if (lang == 'tr') return 'Hacim artışı >= %$vol';
        if (lang == 'es') return 'Pico de volumen >= $vol%';
        if (lang == 'fr') return 'Poussée de volume >= $vol%';
        if (lang == 'ru') return 'Всплеск объема >= $vol%';
        if (lang == 'zh') return '成交量突增 >= $vol%';
        return 'Volume surge >= $vol%';
    }
  }

  String _formatTime(DateTime dt) {
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    return '$h:$m';
  }
}
