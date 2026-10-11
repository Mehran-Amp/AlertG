import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../../core/localization/app_strings.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/utils/crypto_icons.dart';
import '../../../core/utils/format_utils.dart';
import '../../settings/services/settings_service.dart';
import '../models/notification_log.dart';
import '../repositories/notification_repository.dart';
import '../widgets/history_group_header.dart';

enum HistoryFilter { all, triggered, suppressed }

class NotificationHistoryPage extends StatefulWidget {
  const NotificationHistoryPage({super.key});

  @override
  State<NotificationHistoryPage> createState() => _NotificationHistoryPageState();
}

class _NotificationHistoryPageState extends State<NotificationHistoryPage> {
  HistoryFilter _currentFilter = HistoryFilter.all;
  List<NotificationLog> _logs = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadLogs();
  }

  Future<void> _loadLogs() async {
    setState(() => _isLoading = true);
    final repo = context.read<NotificationRepository>();
    final logs = await repo.getAllLogs();

    if (mounted) {
      setState(() {
        _logs = logs;
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final settingsService = context.watch<SettingsService>();
    final lang = settingsService.settings.language;

    final filteredLogs = _logs.where((log) {
      if (_currentFilter == HistoryFilter.all) return true;
      if (_currentFilter == HistoryFilter.triggered) {
        return !log.message.contains('Suppressed');
      }
      if (_currentFilter == HistoryFilter.suppressed) {
        return log.message.contains('Suppressed') || log.message.contains('cooldown');
      }
      return true;
    }).toList();

    final groupedLogs = _groupLogsByDay(filteredLogs);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: theme.colorScheme.surface,
        elevation: 0,
        title: Text(
          AppStrings.get('history', lang),
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.bold,
            color: theme.colorScheme.onSurface,
          ),
        ),
      ),
      body: Column(
        children: [
          // Filter Chips at Top
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppTokens.space16,
              vertical: AppTokens.space12,
            ),
            child: Row(
              children: [
                _buildFilterChip(HistoryFilter.all, AppStrings.get('filter_all', lang), theme),
                const SizedBox(width: AppTokens.space8),
                _buildFilterChip(HistoryFilter.triggered, AppStrings.get('filter_triggered', lang), theme),
                const SizedBox(width: AppTokens.space8),
                _buildFilterChip(HistoryFilter.suppressed, AppStrings.get('filter_suppressed', lang), theme),
              ],
            ),
          ),

          // Log Entries List
          Expanded(
            child: _isLoading
                ? Center(child: CircularProgressIndicator(color: theme.colorScheme.primary))
                : filteredLogs.isEmpty
                    ? Center(
                        child: Padding(
                          padding: const EdgeInsets.all(AppTokens.space32),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Container(
                                padding: const EdgeInsets.all(AppTokens.space24),
                                decoration: BoxDecoration(
                                  color: theme.cardColor,
                                  shape: BoxShape.circle,
                                  border: Border.all(color: theme.dividerColor),
                                ),
                                child: Icon(
                                  Icons.history_toggle_off_rounded,
                                  size: 48,
                                  color: theme.colorScheme.onSurface.withValues(alpha: 0.4),
                                ),
                              ),
                              const SizedBox(height: AppTokens.space16),
                              Text(
                                AppStrings.get('no_history_title', lang),
                                style: TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.bold,
                                  color: theme.colorScheme.onSurface,
                                ),
                              ),
                              const SizedBox(height: AppTokens.space8),
                              Text(
                                AppStrings.get('no_history_desc', lang),
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 12,
                                  color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                                ),
                              ),
                            ],
                          ),
                        ),
                      )
                    : RefreshIndicator(
                        onRefresh: _loadLogs,
                        color: theme.colorScheme.primary,
                        backgroundColor: theme.colorScheme.surface,
                        child: ListView.builder(
                          physics: const AlwaysScrollableScrollPhysics(),
                          itemCount: groupedLogs.length,
                          itemBuilder: (context, index) {
                            final group = groupedLogs[index];

                            return Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                HistoryGroupHeader(date: group.date, lang: lang),
                                ...group.logs.map((log) => _buildLogCard(log, theme, isDark, lang)),
                              ],
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterChip(HistoryFilter filter, String label, ThemeData theme) {
    final isSelected = _currentFilter == filter;
    return ChoiceChip(
      label: Text(label),
      selected: isSelected,
      onSelected: (_) => setState(() => _currentFilter = filter),
      selectedColor: theme.colorScheme.primary.withValues(alpha: 0.15),
      backgroundColor: theme.colorScheme.surfaceContainerHighest,
      labelStyle: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w600,
        color: isSelected ? theme.colorScheme.primary : theme.colorScheme.onSurface.withValues(alpha: 0.7),
      ),
      side: BorderSide(
        color: isSelected ? theme.colorScheme.primary : theme.dividerColor,
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    );
  }

  String? _resolveLogCurrency(NotificationLog log) {
    final sym = log.marketSymbol.toUpperCase();
    final baseSym = sym.contains('/') ? sym.split('/')[0].trim() : sym;
    if (baseSym == 'TOTAL' || baseSym == 'TOTAL2' || baseSym == 'TOTAL3' || sym.contains('B USD') || sym.contains('/B USD')) {
      return 'B USD';
    }
    if (sym.contains('M USD') || sym.contains('/M USD')) {
      return 'M USD';
    }
    if (baseSym == 'BTC.D' || baseSym == 'USDT.D' || baseSym == 'ETH.D' || baseSym.endsWith('.D') || sym.contains('%')) {
      return '%';
    }
    if (sym.contains('/')) {
      final parts = sym.split('/');
      if (parts.length > 1) return parts[1];
    }
    return null;
  }

  Widget _buildLogCard(NotificationLog log, ThemeData theme, bool isDark, String lang) {
    final isWarning = log.message.contains('cooldown') || log.message.contains('Suppressed');
    final isUpward = log.title.contains('🟢') ||
        log.title.contains('صعود') ||
        log.title.contains('↗️') ||
        log.title.contains('+') ||
        log.title.contains('Surged');
    final isDownward = log.title.contains('🔴') ||
        log.title.contains('افت') ||
        log.title.contains('ریزش') ||
        log.title.contains('↘️') ||
        log.title.contains('-') ||
        log.title.contains('Dropped');

    final Color statusColor = isWarning
        ? AppTokens.warning
        : (isUpward
            ? AppTokens.positive
            : (isDownward ? AppTokens.negative : theme.colorScheme.primary));

    final baseSymbol = _extractBaseCurrency(log.marketSymbol);
    final timeAgo = _formatTimeAgo(log.timestamp, lang);
    final hasPrevPrice = log.previousPrice != null &&
        log.previousPrice! > 0 &&
        (log.previousPrice! - log.triggeredPrice).abs() > 1e-6;

    double? priceMovePct;
    if (hasPrevPrice && log.previousPrice! > 0) {
      priceMovePct = ((log.triggeredPrice - log.previousPrice!) / log.previousPrice!) * 100.0;
    }

    return Container(
      margin: const EdgeInsets.symmetric(
        horizontal: AppTokens.space16,
        vertical: AppTokens.space6,
      ),
      padding: const EdgeInsets.all(AppTokens.space12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: statusColor.withValues(alpha: isDark ? 0.35 : 0.25),
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.20 : 0.04),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 1. Header: Logo + Symbol + Exchange Badge + Time / TimeAgo
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(2),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: statusColor.withValues(alpha: 0.35),
                    width: 1.2,
                  ),
                ),
                child: CryptoIcons.buildLogo(baseSymbol, size: 28),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          log.marketSymbol,
                          style: TextStyle(
                            fontWeight: FontWeight.w800,
                            fontSize: 14,
                            color: theme.colorScheme.onSurface,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                          decoration: BoxDecoration(
                            color: theme.colorScheme.surfaceContainerHighest,
                            borderRadius: BorderRadius.circular(5),
                          ),
                          child: Text(
                            log.exchangeId.toUpperCase(),
                            style: TextStyle(
                              color: theme.colorScheme.primary,
                              fontSize: 9.5,
                              fontWeight: FontWeight.bold,
                              letterSpacing: 0.4,
                            ),
                          ),
                        ),
                        if (log.conditionType != null && log.conditionType!.isNotEmpty) ...[
                          const SizedBox(width: 4),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                            decoration: BoxDecoration(
                              color: statusColor.withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(5),
                            ),
                            child: Text(
                              _formatConditionType(log.conditionType!, lang),
                              style: TextStyle(
                                color: statusColor,
                                fontSize: 9.5,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    _formatTimestamp(log.timestamp),
                    style: TextStyle(
                      fontSize: 11,
                      fontFamily: 'monospace',
                      fontWeight: FontWeight.w600,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
                    ),
                  ),
                  Text(
                    timeAgo,
                    style: TextStyle(
                      fontSize: 9.5,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.45),
                    ),
                  ),
                ],
              ),
            ],
          ),

          const SizedBox(height: 10),

          // 2. Price Movement Box: From -> To (or Trigger Price)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
            decoration: BoxDecoration(
              color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                if (hasPrevPrice) ...[
                  Row(
                    children: [
                      Text(
                        FormatUtils.formatPrice(log.previousPrice!, currencySymbol: _resolveLogCurrency(log), lang: lang),
                        style: TextStyle(
                          fontSize: 12,
                          fontFamily: 'monospace',
                          fontWeight: FontWeight.w600,
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                        ),
                      ),
                      const Padding(
                        padding: EdgeInsets.symmetric(horizontal: 6),
                        child: Icon(Icons.arrow_forward_rounded, size: 13, color: Colors.grey),
                      ),
                      Text(
                        FormatUtils.formatPrice(log.triggeredPrice, currencySymbol: _resolveLogCurrency(log), lang: lang),
                        style: TextStyle(
                          fontSize: 13,
                          fontFamily: 'monospace',
                          fontWeight: FontWeight.w900,
                          color: statusColor,
                        ),
                      ),
                    ],
                  ),
                ] else ...[
                  Row(
                    children: [
                      Text(
                        '${AppStrings.get('trigger_price_label', lang)}: ',
                        style: TextStyle(
                          fontSize: 11.5,
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                        ),
                      ),
                      Text(
                        FormatUtils.formatPrice(log.triggeredPrice, currencySymbol: _resolveLogCurrency(log), lang: lang),
                        style: TextStyle(
                          fontSize: 13,
                          fontFamily: 'monospace',
                          fontWeight: FontWeight.w900,
                          color: statusColor,
                        ),
                      ),
                    ],
                  ),
                ],
                if (priceMovePct != null) ...[
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: statusColor.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(5),
                    ),
                    child: Text(
                      '${priceMovePct >= 0 ? "▲ +" : "▼ "}${priceMovePct.abs().toStringAsFixed(2)}%',
                      style: TextStyle(
                        fontSize: 10.5,
                        fontWeight: FontWeight.bold,
                        fontFamily: 'monospace',
                        color: statusColor,
                      ),
                    ),
                  ),
                ] else ...[
                  Icon(
                    isUpward
                        ? Icons.trending_up_rounded
                        : (isDownward ? Icons.trending_down_rounded : Icons.notifications_active_rounded),
                    size: 16,
                    color: statusColor,
                  ),
                ],
              ],
            ),
          ),

          // 3. Title & Message
          if (log.title.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              log.title,
              style: TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.bold,
                color: statusColor,
              ),
            ),
          ],

          if (log.message.trim().isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              log.message,
              style: TextStyle(
                fontSize: 12,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.85),
                height: 1.35,
              ),
            ),
          ],

          // 4. Custom Strategy Note (if present)
          if (log.customNote != null && log.customNote!.trim().isNotEmpty) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: theme.colorScheme.primary.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: theme.colorScheme.primary.withValues(alpha: 0.25),
                  width: 0.8,
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    Icons.edit_note_rounded,
                    size: 16,
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      log.customNote!,
                      style: TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.w600,
                        color: theme.colorScheme.primary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],

          // 5. Card Footer: Status tag + Copy action
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    width: 7,
                    height: 7,
                    decoration: BoxDecoration(
                      color: statusColor,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 5),
                  Text(
                    isWarning
                        ? (lang == 'fa' ? 'محافظت اسپم' : 'Suppressed')
                        : (lang == 'fa' ? 'هشدار صادر شد' : 'Triggered'),
                    style: TextStyle(
                      fontSize: 10.5,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ),
                ],
              ),
              InkWell(
                onTap: () {
                  final textToCopy =
                      '🔔 ${log.marketSymbol} (${log.exchangeId.toUpperCase()})\n'
                      'Price: ${FormatUtils.formatPrice(log.triggeredPrice, currencySymbol: _resolveLogCurrency(log), lang: lang)}\n'
                      '${log.title}\n${log.message}\n'
                      'Time: ${log.timestamp}';
                  Clipboard.setData(ClipboardData(text: textToCopy));
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(
                        lang == 'fa' ? 'گزارش در کلیپ‌بورد کپی شد 📋' : 'Log copied to clipboard 📋',
                      ),
                      duration: const Duration(seconds: 2),
                      behavior: SnackBarBehavior.floating,
                    ),
                  );
                },
                borderRadius: BorderRadius.circular(6),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  child: Row(
                    children: [
                      Icon(
                        Icons.copy_rounded,
                        size: 13,
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.45),
                      ),
                      const SizedBox(width: 4),
                      Text(
                        lang == 'fa' ? 'کپی' : 'Copy',
                        style: TextStyle(
                          fontSize: 10.5,
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _extractBaseCurrency(String marketSymbol) {
    if (marketSymbol.contains('/')) {
      return marketSymbol.split('/').first.trim();
    }
    if (marketSymbol.contains('-')) {
      return marketSymbol.split('-').first.trim();
    }
    return marketSymbol;
  }

  String _formatConditionType(String conditionType, String lang) {
    switch (conditionType) {
      case 'priceThreshold':
        return lang == 'fa' ? 'تارگت قیمت' : 'Target';
      case 'percentChange':
        return lang == 'fa' ? 'تغییر درصدی' : 'Percent';
      case 'volumeChange':
        return lang == 'fa' ? 'حجم معاملات' : 'Volume';
      case 'absolutePriceChange':
        return lang == 'fa' ? 'نوسان دلاری' : 'Delta';
      default:
        return conditionType;
    }
  }

  String _formatTimeAgo(DateTime dt, String lang) {
    final diff = DateTime.now().difference(dt);
    if (diff.inSeconds < 45) {
      return lang == 'fa' ? 'همین الان' : 'Just now';
    }
    if (diff.inMinutes < 60) {
      final m = diff.inMinutes;
      return lang == 'fa' ? '$m دقیقه قبل' : '${m}m ago';
    }
    if (diff.inHours < 24) {
      final h = diff.inHours;
      return lang == 'fa' ? '$h ساعت قبل' : '${h}h ago';
    }
    final d = diff.inDays;
    return lang == 'fa' ? '$d روز قبل' : '${d}d ago';
  }

  List<_GroupedLogItem> _groupLogsByDay(List<NotificationLog> logs) {
    final Map<String, List<NotificationLog>> map = {};

    for (final log in logs) {
      final key = '${log.timestamp.year}-${log.timestamp.month}-${log.timestamp.day}';
      map.putIfAbsent(key, () => []).add(log);
    }

    final groups = <_GroupedLogItem>[];
    for (final entry in map.entries) {
      final firstLog = entry.value.first;
      groups.add(_GroupedLogItem(
        date: DateTime(firstLog.timestamp.year, firstLog.timestamp.month, firstLog.timestamp.day),
        logs: entry.value,
      ));
    }

    return groups;
  }

  String _formatTimestamp(DateTime dt) {
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    final s = dt.second.toString().padLeft(2, '0');
    return '$h:$m:$s';
  }
}

class _GroupedLogItem {
  final DateTime date;
  final List<NotificationLog> logs;

  _GroupedLogItem({required this.date, required this.logs});
}
