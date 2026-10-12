import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../../core/localization/app_strings.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/utils/crypto_icons.dart';
import '../../../core/utils/format_utils.dart';
import '../../settings/services/settings_service.dart';
import '../models/alert_rule.dart';
import 'cooldown_timer.dart';

/// Modern Redesigned Alert Row Widget:
/// - Dual Swipe Gestures:
///     * Swipe Left (End-to-Start): Delete alert with confirmation undo
///     * Swipe Right (Start-to-End): Toggle Active / Inactive (No toggle switch needed on card)
/// - Top Row: Asset Logo, Symbol & Full English Name on left, Live Price in front of symbol, and 24h/Delta Percent under price
/// - Toman / IRT font size reduction for unit label ("تومان" / "IRT") while price remains bold
/// - Target condition header with proximity progress bar
/// - Feature indicator pills: [🔊 Snd], [📳 Vib], [🎙️ TTS], [⏱️ 30s]
/// - Zero pixel-overflow guarantee with strict constraints & ellipsis
class AlertRow extends StatelessWidget {
  final AlertRule rule;
  final ValueChanged<bool> onToggle;
  final VoidCallback onSwipeDelete;
  final VoidCallback onRearm;
  final VoidCallback onDuplicate;
  final VoidCallback onEdit;
  final VoidCallback onExport;
  final VoidCallback? onManualCheck;
  final bool isChecking;

  const AlertRow({
    super.key,
    required this.rule,
    required this.onToggle,
    required this.onSwipeDelete,
    required this.onRearm,
    required this.onDuplicate,
    required this.onEdit,
    required this.onExport,
    this.onManualCheck,
    this.isChecking = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final lang = context.watch<SettingsService>().settings.language;
    final conditionDescription = _buildConditionDescription(rule, lang);

    // Calculate progress ratio toward target (0.0 to 1.0)
    final progress = _calculateProgressRatio();

    return Dismissible(
      key: Key(rule.uuid),
      direction: DismissDirection.horizontal,
      // Swipe Right (Start to End) -> Toggle Active / Inactive
      background: Container(
        margin: const EdgeInsets.symmetric(horizontal: AppTokens.space16, vertical: AppTokens.space6),
        padding: const EdgeInsets.symmetric(horizontal: AppTokens.space20),
        alignment: Alignment.centerLeft,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          gradient: LinearGradient(
            colors: rule.isActive
                ? [const Color(0xFFF59E0B), const Color(0xFFD97706)]
                : [const Color(0xFF10B981), const Color(0xFF059669)],
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              rule.isActive ? Icons.pause_circle_filled_rounded : Icons.play_circle_filled_rounded,
              color: Colors.white,
              size: 26,
            ),
            const SizedBox(width: 8),
            Text(
              rule.isActive
                  ? (lang == 'fa' ? 'غیرفعال‌سازی' : 'Deactivate')
                  : (lang == 'fa' ? 'فعال‌سازی' : 'Activate'),
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                fontSize: 13,
              ),
            ),
          ],
        ),
      ),
      // Swipe Left (End to Start) -> Delete Alert
      secondaryBackground: Container(
        margin: const EdgeInsets.symmetric(horizontal: AppTokens.space16, vertical: AppTokens.space6),
        padding: const EdgeInsets.symmetric(horizontal: AppTokens.space20),
        alignment: Alignment.centerRight,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          gradient: const LinearGradient(
            colors: [Color(0xFFEF4444), Color(0xFFDC2626)],
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              lang == 'fa' ? 'حذف آلارم' : 'Delete Alert',
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                fontSize: 13,
              ),
            ),
            const SizedBox(width: 8),
            const Icon(
              Icons.delete_sweep_rounded,
              color: Colors.white,
              size: 26,
            ),
          ],
        ),
      ),
      confirmDismiss: (direction) async {
        if (direction == DismissDirection.startToEnd) {
          // Toggle active state without removing widget
          HapticFeedback.mediumImpact();
          onToggle(!rule.isActive);
          return false; // Snap back smoothly to reflect toggled state
        } else if (direction == DismissDirection.endToStart) {
          HapticFeedback.heavyImpact();
          return true; // Dismiss and trigger delete
        }
        return false;
      },
      onDismissed: (direction) {
        if (direction == DismissDirection.endToStart) {
          onSwipeDelete();
        }
      },
      child: GestureDetector(
        onTap: onEdit,
        onLongPressStart: (details) => _showContextMenu(context, details.globalPosition, lang),
        child: AnimatedOpacity(
          duration: const Duration(milliseconds: 200),
          opacity: rule.isActive ? 1.0 : 0.65,
          child: Container(
            margin: const EdgeInsets.symmetric(
              horizontal: AppTokens.space16,
              vertical: AppTokens.space6,
            ),
            padding: const EdgeInsets.all(AppTokens.space14),
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: rule.isInCooldown
                    ? AppTokens.warning.withValues(alpha: 0.6)
                    : (rule.isActive ? theme.dividerColor.withValues(alpha: 0.8) : theme.dividerColor.withValues(alpha: 0.3)),
                width: rule.isInCooldown ? 1.5 : 1.0,
              ),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: theme.brightness == Brightness.dark ? 0.25 : 0.04),
                  blurRadius: 8,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                // ==============================================================
                // 1. TOP HEADER ROW:
                // [Logo] Symbol & Full English Name  |  Price & [% Change]
                // ==============================================================
                Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    // Coin / Asset High-Res Logo
                    CryptoIcons.buildLogo(rule.baseCurrency, size: 36),
                    const SizedBox(width: AppTokens.space10),

                    // Left Column: Symbol & Full English Name
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Row(
                            children: [
                              Flexible(
                                child: Text(
                                  '${rule.baseCurrency} / ${rule.counterCurrency}',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                    fontWeight: FontWeight.w800,
                                    fontSize: 14.5,
                                    letterSpacing: -0.2,
                                    color: rule.isActive
                                        ? theme.colorScheme.onSurface
                                        : theme.colorScheme.onSurface.withValues(alpha: 0.5),
                                  ),
                                ),
                              ),
                              const SizedBox(width: AppTokens.space6),
                              Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 5,
                                  vertical: 1.5,
                                ),
                                decoration: BoxDecoration(
                                  color: theme.colorScheme.surfaceContainerHighest,
                                  borderRadius: BorderRadius.circular(5),
                                  border: Border.all(color: theme.dividerColor.withValues(alpha: 0.5), width: 0.8),
                                ),
                                child: Text(
                                  rule.exchangeId.toUpperCase(),
                                  style: TextStyle(
                                    color: theme.colorScheme.primary,
                                    fontSize: 9.5,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 2),
                          // Full English Name (Overflow protected)
                          Text(
                            _resolveFullEnglishName(rule.baseCurrency),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w500,
                              color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
                            ),
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(width: AppTokens.space8),

                    // Right Column: Live Price & Percent (Percent UNDER Price!)
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _buildPriceWidget(theme, lang),
                        const SizedBox(height: 3),
                        _buildPercentBadge(theme),
                      ],
                    ),
                  ],
                ),

                const SizedBox(height: AppTokens.space10),

                // ==============================================================
                // 2. TARGET CONDITION & PROXIMITY PROGRESS BAR
                // ==============================================================
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: theme.dividerColor.withValues(alpha: 0.35)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Row(
                        children: [
                          Icon(
                            Icons.bolt_rounded,
                            size: 14,
                            color: rule.isActive ? AppTokens.warning : theme.colorScheme.onSurface.withValues(alpha: 0.4),
                          ),
                          const SizedBox(width: 4),
                          Expanded(
                            child: Text(
                              conditionDescription,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 11.5,
                                fontWeight: FontWeight.w600,
                                color: rule.isActive
                                    ? theme.colorScheme.onSurface.withValues(alpha: 0.85)
                                    : theme.colorScheme.onSurface.withValues(alpha: 0.45),
                              ),
                            ),
                          ),
                          if (progress != null) ...[
                            const SizedBox(width: 6),
                            Text(
                              '${(progress * 100).clamp(0, 999).toInt()}%',
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.bold,
                                color: progress >= 1.0 ? AppTokens.positive : theme.colorScheme.primary,
                              ),
                            ),
                          ],
                        ],
                      ),
                      if (progress != null) ...[
                        const SizedBox(height: 6),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(3),
                          child: LinearProgressIndicator(
                            value: progress.clamp(0.0, 1.0),
                            minHeight: 4,
                            backgroundColor: theme.colorScheme.surfaceContainerHighest,
                            valueColor: AlwaysStoppedAnimation<Color>(
                              progress >= 1.0 ? AppTokens.positive : theme.colorScheme.primary,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),

                // Custom Note (Trade Thesis) if present
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

                // ==============================================================
                // 3. ACTION / STATUS PILLS ROW
                // [🔊 Snd] [📳 Vib] [🎙️ TTS]          ⏱️ 30s  [🔄 Cooldown]
                // ==============================================================
                Row(
                  children: [
                    _buildFeaturePill(
                      icon: Icons.volume_up_rounded,
                      label: 'Snd',
                      isActive: rule.soundEnabled,
                      theme: theme,
                    ),
                    const SizedBox(width: 5),
                    _buildFeaturePill(
                      icon: Icons.vibration_rounded,
                      label: 'Vib',
                      isActive: rule.vibrationEnabled,
                      theme: theme,
                    ),
                    const SizedBox(width: 5),
                    _buildFeaturePill(
                      icon: Icons.record_voice_over_rounded,
                      label: 'TTS',
                      isActive: rule.ttsEnabled,
                      theme: theme,
                    ),
                    const Spacer(),

                    // Inactive Tag if disabled
                    if (!rule.isActive)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        margin: const EdgeInsets.only(right: 6),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(5),
                        ),
                        child: Text(
                          lang == 'fa' ? 'غیرفعال' : 'Disabled',
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                          ),
                        ),
                      ),

                    // Polling Interval Badge
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.6),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.timer_outlined, size: 11, color: theme.colorScheme.onSurface.withValues(alpha: 0.55)),
                          const SizedBox(width: 3),
                          Text(
                            '${rule.checkIntervalSeconds}s',
                            style: TextStyle(
                              fontSize: 10.5,
                              fontWeight: FontWeight.bold,
                              color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
                            ),
                          ),
                        ],
                      ),
                    ),

                    // Manual Check Button [🔄 Check]
                    if (onManualCheck != null) ...[
                      const SizedBox(width: 6),
                      InkWell(
                        onTap: isChecking ? null : onManualCheck,
                        borderRadius: BorderRadius.circular(6),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                          decoration: BoxDecoration(
                            color: theme.colorScheme.primary.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(
                              color: theme.colorScheme.primary.withValues(alpha: 0.3),
                              width: 0.8,
                            ),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (isChecking)
                                SizedBox(
                                  width: 9,
                                  height: 9,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 1.5,
                                    color: theme.colorScheme.primary,
                                  ),
                                )
                              else
                                Icon(Icons.sync_rounded, size: 11, color: theme.colorScheme.primary),
                              const SizedBox(width: 3),
                              Text(
                                AppStrings.get('check_now', lang),
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
                    ],

                    // Cooldown Indicator
                    if (rule.isInCooldown && rule.cooldownUntil != null) ...[
                      const SizedBox(width: 6),
                      InkWell(
                        onTap: onRearm,
                        borderRadius: BorderRadius.circular(6),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: AppTokens.warning.withValues(alpha: 0.15),
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(color: AppTokens.warning.withValues(alpha: 0.4), width: 0.8),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(Icons.refresh_rounded, size: 11, color: AppTokens.warning),
                              const SizedBox(width: 2),
                              Text(
                                'Cooldown',
                                style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: AppTokens.warning),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ],
                ),

                if (rule.isInCooldown && rule.cooldownUntil != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: CooldownTimer(
                      cooldownUntil: rule.cooldownUntil!,
                      onRearmPressed: onRearm,
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// Resolves full English asset name for cryptocurrencies, totals and macro indices
  String _resolveFullEnglishName(String baseCurrency) {
    final clean = baseCurrency.toUpperCase().trim();
    if (clean == 'TOTAL') return 'CRYPTO TOTAL MARKET';
    if (clean == 'TOTAL2') return 'CRYPTO TOTAL EXCL BTC';
    if (clean == 'TOTAL3') return 'CRYPTO TOTAL EXCL BTC & ETH';
    if (clean == 'BTC.D' || clean == 'BTCD') return 'Bitcoin Dominance';
    if (clean == 'USDT.D') return 'Tether Dominance';
    if (clean == 'OTHERS.D') return 'Altcoin Dominance';

    final name = CryptoIcons.getName(clean);
    if (name.isNotEmpty && name != clean) {
      return name;
    }
    return clean;
  }

  /// Builds live price widget with small font size for Toman / IRT unit
  Widget _buildPriceWidget(ThemeData theme, String lang) {
    final price = rule.currentDisplayPrice ?? rule.targetPrice ?? 0.0;
    final counter = rule.counterCurrency.trim();
    final upper = counter.toUpperCase();
    final isToman = upper == 'TMN' || upper == 'IRT' || upper == 'TOMAN' || counter == 'تومان' || counter == 'ت';
    final isRial = upper == 'IRR' || upper == 'RLS' || counter == 'ریال';

    if (isToman || isRial) {
      final numStr = price >= 1000
          ? NumberFormat('#,###', 'en_US').format(price)
          : (price == price.roundToDouble() ? price.toInt().toString() : price.toStringAsFixed(2));
      final displayNum = (lang == 'fa') ? FormatUtils.toPersianDigits(numStr) : numStr;
      final displayUnit = FormatUtils.resolveCurrencyDisplayName(counter, lang: lang);

      // Render Price with smaller font size for "تومان" / "IRT" unit!
      return RichText(
        textAlign: TextAlign.end,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        text: TextSpan(
          children: [
            TextSpan(
              text: displayNum,
              style: TextStyle(
                fontWeight: FontWeight.w800,
                fontSize: 15,
                color: rule.isActive
                    ? theme.colorScheme.onSurface
                    : theme.colorScheme.onSurface.withValues(alpha: 0.5),
              ),
            ),
            const TextSpan(text: ' '),
            TextSpan(
              text: displayUnit,
              style: TextStyle(
                fontWeight: FontWeight.w600,
                fontSize: 10, // Specifically smaller font size for Toman / IRT!
                color: rule.isActive
                    ? theme.colorScheme.primary
                    : theme.colorScheme.onSurface.withValues(alpha: 0.4),
              ),
            ),
          ],
        ),
      );
    }

    // Scaled or standard international currency format (e.g. $67,450.00, $2,450.37B)
    final scaled = FormatUtils.formatScaledCurrencyPrice(price, counter);
    final formatted = scaled ?? FormatUtils.formatPrice(price, currencySymbol: counter, lang: lang);

    return Text(
      formatted,
      textAlign: TextAlign.end,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(
        fontWeight: FontWeight.w800,
        fontSize: 15,
        color: rule.isActive
            ? theme.colorScheme.onSurface
            : theme.colorScheme.onSurface.withValues(alpha: 0.5),
      ),
    );
  }

  /// Builds percent badge located UNDER the price
  Widget _buildPercentBadge(ThemeData theme) {
    double? pct;
    if (rule.currentDisplayPrice != null && rule.previousPrice != null && rule.previousPrice! > 0) {
      pct = ((rule.currentDisplayPrice! - rule.previousPrice!) / rule.previousPrice!) * 100;
    } else if (rule.currentDisplayPrice != null && rule.basePrice != null && rule.basePrice! > 0 && rule.currentDisplayPrice != rule.basePrice) {
      pct = ((rule.currentDisplayPrice! - rule.basePrice!) / rule.basePrice!) * 100;
    } else if (rule.conditionType == AlertConditionType.percentChange && rule.percent != null) {
      pct = rule.direction == AlertDirection.below ? -rule.percent! : rule.percent!;
    } else if (rule.currentDisplayPrice != null && rule.targetPrice != null && rule.targetPrice! > 0) {
      pct = ((rule.currentDisplayPrice! - rule.targetPrice!) / rule.targetPrice!) * 100;
    }

    final val = pct ?? 0.0;
    final isPositive = val >= 0;
    final sign = isPositive ? '+' : '';
    final pctText = '${sign}${val.toStringAsFixed(2)}%';
    final color = isPositive ? AppTokens.positive : AppTokens.negative;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1.5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(5),
        border: Border.all(color: color.withValues(alpha: 0.3), width: 0.8),
      ),
      child: Text(
        pctText,
        style: TextStyle(
          fontSize: 10.5,
          fontWeight: FontWeight.bold,
          color: color,
          letterSpacing: -0.2,
        ),
      ),
    );
  }

  /// Builds feature pill indicator [🔊 Snd], [📳 Vib], [🎙️ TTS]
  Widget _buildFeaturePill({
    required IconData icon,
    required String label,
    required bool isActive,
    required ThemeData theme,
  }) {
    final color = isActive
        ? theme.colorScheme.primary
        : theme.colorScheme.onSurface.withValues(alpha: 0.35);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
      decoration: BoxDecoration(
        color: isActive
            ? theme.colorScheme.primary.withValues(alpha: 0.1)
            : theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(5),
        border: Border.all(
          color: isActive ? theme.colorScheme.primary.withValues(alpha: 0.3) : theme.dividerColor.withValues(alpha: 0.4),
          width: 0.8,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: color),
          const SizedBox(width: 3),
          Text(
            label,
            style: TextStyle(
              fontSize: 9.5,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  /// Calculates proximity ratio toward target condition
  double? _calculateProgressRatio() {
    final cur = rule.currentDisplayPrice;
    final target = rule.targetPrice;
    if (cur == null || target == null || target <= 0) return null;

    if (rule.direction == AlertDirection.above) {
      return (cur / target);
    } else if (rule.direction == AlertDirection.below) {
      return cur <= target ? 1.0 : (target / cur);
    }
    return (cur / target);
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
            return 'شکست قیمت: بالا > $upT یا پایین < $lowT';
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
}
