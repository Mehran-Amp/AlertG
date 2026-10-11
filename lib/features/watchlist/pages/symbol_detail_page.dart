import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/localization/app_strings.dart';
import '../../../core/services/catalog_sync_service.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/utils/format_utils.dart';
import '../../alert_engine/repositories/json_alert_rule_repository.dart';
import '../../exchanges/registry/exchange_registry.dart';
import '../services/watchlist_service.dart';
import 'create_alert_flow.dart';

/// Full-screen or modal Symbol Detail Page (Phase 8 Requirement)
/// Displays:
/// 1. Real-time/cached price & 24h change
/// 2. Market Status: باز (Open) / بسته (Closed) / وقفه (Intermission)
/// 3. Opening Hours & Next Open Session (ساعت بازگشایی)
/// 4. Source Provider Label (منبع داده)
/// 5. Latency / Delay Tag (تأخیر)
/// 6. Set Alert Button (تنظیم هشدار هوشمند)
/// 7. Add/Remove Watchlist Button
/// 8. Prominent Financial Legal Disclaimer (پیام حقوقی)
class SymbolDetailPage extends StatefulWidget {
  final String symbol;
  final String exchange;
  final String nameEn;
  final String nameFa;
  final String category;
  final String unit;
  final double? initialPrice;

  const SymbolDetailPage({
    super.key,
    required this.symbol,
    this.exchange = 'global_stocks',
    required this.nameEn,
    required this.nameFa,
    required this.category,
    this.unit = '\$',
    this.initialPrice,
  });

  static Future<void> show(
    BuildContext context, {
    required String symbol,
    String exchange = 'global_stocks',
    required String nameEn,
    required String nameFa,
    required String category,
    String unit = '\$',
    double? initialPrice,
  }) {
    return Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => SymbolDetailPage(
          symbol: symbol,
          exchange: exchange,
          nameEn: nameEn,
          nameFa: nameFa,
          category: category,
          unit: unit,
          initialPrice: initialPrice,
        ),
      ),
    );
  }

  @override
  State<SymbolDetailPage> createState() => _SymbolDetailPageState();
}

class _SymbolDetailPageState extends State<SymbolDetailPage> {
  Map<String, dynamic>? _marketData;
  bool _isLoading = true;
  double? _livePrice;

  @override
  void initState() {
    super.initState();
    _livePrice = widget.initialPrice;
    _fetchDetails();
  }

  Future<void> _fetchDetails() async {
    setState(() => _isLoading = true);
    final data = await CatalogSyncService.instance.fetchSymbolDetail(
      widget.symbol,
      exchange: widget.exchange,
    );
    if (mounted) {
      setState(() {
        _marketData = data;
        _isLoading = false;
        if (data != null && data['price'] != null) {
          _livePrice = (data['price'] as num).toDouble();
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final watchlistService = WatchlistService.instance;
    final isStarred = watchlistService.isWatchlisted(widget.symbol);

    final marketInfo = _marketData?['market'] as Map<String, dynamic>?;
    final bool isOpen = marketInfo?['is_open'] ?? (widget.category == 'crypto');
    final String statusFa = marketInfo?['status_fa'] ?? (isOpen ? 'باز' : 'بسته');
    final String scheduleFa = marketInfo?['schedule_fa'] ?? 'دوشنبه تا جمعه ۰۹:۳۰ تا ۱۶:۰۰ به وقت نیویورک';
    final String nextOpenFa = marketInfo?['next_open_fa'] ?? (isOpen ? 'معاملات هم‌اکنون فعال است' : 'جلسه معاملاتی بعدی: ساعت ۱۸:۰۰');
    final String sourceLabel = marketInfo?['source'] ?? 'Yahoo Finance / FRED';
    final String delayLabel = marketInfo?['delay'] ?? 'تأخیر ۱۵ دقیقه (15m Delayed)';

    final Color statusColor = isOpen ? const Color(0xFF089981) : const Color(0xFFF23645);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: Text(widget.symbol, style: const TextStyle(fontWeight: FontWeight.bold)),
        centerTitle: true,
        actions: [
          IconButton(
            icon: Icon(
              isStarred ? Icons.star : Icons.star_border,
              color: isStarred ? Colors.amber : null,
            ),
            tooltip: isStarred ? 'حذف از دیده‌بان' : 'افزودن به دیده‌بان',
            onPressed: () {
              final item = WatchlistItem(
                symbol: widget.symbol,
                exchange: widget.exchange,
                nameEn: widget.nameEn,
                nameFa: widget.nameFa,
                category: widget.category,
                unit: widget.unit,
                source: sourceLabel,
                delay: delayLabel,
                price: _livePrice,
              );
              watchlistService.toggleWatchlist(item);
              setState(() {});
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(
                    !isStarred ? '✅ نماد به دیده‌بان بازار اضافه شد' : 'از دیده‌بان حذف شد',
                    textAlign: TextAlign.center,
                  ),
                  duration: const Duration(seconds: 2),
                ),
              );
            },
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _fetchDetails,
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 1. Header Card (Symbol, Persian Name, Price)
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: theme.cardColor,
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: theme.dividerColor.withValues(alpha: 0.1)),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.05),
                    blurRadius: 10,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.primary.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          widget.category.toUpperCase(),
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.primary,
                          ),
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: statusColor.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: statusColor.withValues(alpha: 0.4)),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 8,
                              height: 8,
                              decoration: BoxDecoration(
                                color: statusColor,
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              statusFa,
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                                color: statusColor,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Text(
                    widget.nameFa,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    widget.nameEn,
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
                  ),
                  const SizedBox(height: 16),
                  if (_livePrice != null && _livePrice! > 0)
                    Text(
                      '${FormatUtils.formatPrice(_livePrice)} ${widget.unit}',
                      style: const TextStyle(
                        fontSize: 32,
                        fontWeight: FontWeight.w900,
                        letterSpacing: -0.5,
                      ),
                    )
                  else
                    Text(
                      '-- ${widget.unit}',
                      style: TextStyle(
                        fontSize: 28,
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.4),
                      ),
                    ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // 2. Market Schedule & Status Card
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: theme.cardColor,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: theme.dividerColor.withValues(alpha: 0.1)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.schedule, color: theme.colorScheme.primary, size: 20),
                      const SizedBox(width: 8),
                      const Text(
                        'وضعیت بازار و ساعات کار',
                        style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  const Divider(height: 24),
                  _buildDetailRow(
                    title: 'وضعیت معامله:',
                    value: statusFa,
                    valueColor: statusColor,
                    badge: true,
                  ),
                  const SizedBox(height: 10),
                  _buildDetailRow(
                    title: 'ساعت بازگشایی / نوبت بعد:',
                    value: nextOpenFa,
                  ),
                  const SizedBox(height: 10),
                  _buildDetailRow(
                    title: 'برنامه کاری رسمی:',
                    value: scheduleFa,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // 3. Provider & Latency Card
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: theme.cardColor,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: theme.dividerColor.withValues(alpha: 0.1)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.hub_outlined, color: theme.colorScheme.secondary, size: 20),
                      const SizedBox(width: 8),
                      const Text(
                        'منبع داده و تأخیر نرخ',
                        style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  const Divider(height: 24),
                  _buildDetailRow(
                    title: 'تأمین‌کننده قیمت:',
                    value: sourceLabel,
                  ),
                  const SizedBox(height: 10),
                  _buildDetailRow(
                    title: 'سرعت و تأخیر:',
                    value: delayLabel,
                    valueColor: delayLabel.contains('بلادرنگ') ? Colors.green : Colors.orange,
                  ),
                  const SizedBox(height: 10),
                  _buildDetailRow(
                    title: 'نوع دارایی:',
                    value: widget.category == 'macro' ? 'شاخص کلان اقتصادی' : widget.category.toUpperCase(),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 20),

            // 4. Quick Action Buttons
            ElevatedButton.icon(
              icon: const Icon(Icons.add_alert, color: Colors.white),
              label: const Text(
                'تنظیم هشدار هوشمند برای این نماد',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: theme.colorScheme.primary,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              onPressed: () {
                final registry = context.read<ExchangeRegistry>();
                final repo = context.read<JsonAlertRuleRepository>();
                CreateAlertFlow.open(
                  context,
                  registry: registry,
                  repository: repo,
                );
              },
            ),

            const SizedBox(height: 24),

            // 5. Official Financial Legal Disclaimer (پیام حقوقی)
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.amber.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: Colors.amber.withValues(alpha: 0.25)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.gavel, color: Colors.amber, size: 18),
                      const SizedBox(width: 8),
                      Text(
                        AppStrings.get('legal_disclaimer_title'),
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.bold,
                          color: Colors.amber,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    AppStrings.get('legal_disclaimer_text'),
                    style: TextStyle(
                      fontSize: 11.5,
                      height: 1.6,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.75),
                    ),
                    textAlign: TextAlign.justify,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Widget _buildDetailRow({
    required String title,
    required String value,
    Color? valueColor,
    bool badge = false,
  }) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 130,
          child: Text(
            title,
            style: TextStyle(
              fontSize: 13,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
            ),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: valueColor ?? theme.colorScheme.onSurface,
            ),
            textAlign: TextAlign.left,
          ),
        ),
      ],
    );
  }
}
