import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../../core/services/fcm_notification_service.dart';
import '../../../core/services/server_alert_service.dart';
import '../../../core/theme/tokens.dart';
import '../../notifications/services/notification_service.dart';
import '../services/settings_service.dart';

/// Comprehensive Market Diagnostics & Deep Server Debugging Page
class DebugDiagnosticsPage extends StatefulWidget {
  const DebugDiagnosticsPage({super.key});

  @override
  State<DebugDiagnosticsPage> createState() => _DebugDiagnosticsPageState();
}

class _DebugDiagnosticsPageState extends State<DebugDiagnosticsPage> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  final TextEditingController _symbolController = TextEditingController(text: 'BTCUSDT');
  String _selectedExchange = 'binance';
  bool _isInspecting = false;
  Map<String, dynamic>? _lastInspectionReport;

  bool _isLoadingLogs = false;
  List<Map<String, dynamic>> _serverLogs = [];

  bool _isPingingExchanges = false;
  Map<String, Map<String, dynamic>> _pingResults = {};

  bool _isSendingTestPush = false;
  Map<String, dynamic>? _testPushResult;
  String? _currentFcmToken;

  final List<Map<String, String>> _exchanges = const [
    {'id': 'nobitex', 'name': 'نوبیتکس (Nobitex)'},
    {'id': 'wallex', 'name': 'والکس (Wallex)'},
    {'id': 'tabdeal', 'name': 'تبدیل (Tabdeal)'},
    {'id': 'ramzinex', 'name': 'رمزینکس (Ramzinex)'},
    {'id': 'tetherland', 'name': 'تترلند (Tetherland)'},
    {'id': 'abantether', 'name': 'آبان‌تتر (AbanTether)'},
    {'id': 'binance', 'name': 'بایننس (Binance)'},
    {'id': 'kucoin', 'name': 'کوکوین (KuCoin)'},
    {'id': 'mexc', 'name': 'مکسی (MEXC)'},
    {'id': 'gateio', 'name': 'گیت (Gate.io)'},
    {'id': 'coinex', 'name': 'کوین‌اکس (CoinEx)'},
    {'id': 'global_stocks', 'name': 'سهام، جفت‌ارزها و طلا (Yahoo Finance)'},
  ];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
    _fetchServerLogs();
    _loadFcmToken();
  }

  Future<void> _loadFcmToken() async {
    final token = await FCMNotificationService.getFCMToken();
    if (mounted) {
      setState(() => _currentFcmToken = token);
    }
  }

  Future<void> _sendLiveTestPush() async {
    setState(() {
      _isSendingTestPush = true;
      _testPushResult = null;
    });

    final res = await ServerAlertService.sendTestPush(
      customTitle: '🔔 [SignalAlert Live Test]',
      customBody: '✅ App is connected to server! Live Push Channel Active.',
    );

    if (mounted) {
      setState(() {
        _isSendingTestPush = false;
        _testPushResult = res;
      });
    }
  }

  @override
  void dispose() {
    _tabController.dispose();
    _symbolController.dispose();
    super.dispose();
  }

  Future<void> _runDeepInspection() async {
    final sym = _symbolController.text.trim();
    if (sym.isEmpty) return;

    setState(() {
      _isInspecting = true;
      _lastInspectionReport = null;
    });

    final report = await ServerAlertService.inspectMarketSource(_selectedExchange, sym);

    if (mounted) {
      setState(() {
        _isInspecting = false;
        _lastInspectionReport = report;
      });
    }
  }

  Future<void> _fetchServerLogs() async {
    setState(() => _isLoadingLogs = true);
    final logs = await ServerAlertService.fetchDebugLogs();
    if (mounted) {
      setState(() {
        _isLoadingLogs = false;
        _serverLogs = logs;
      });
    }
  }

  Future<void> _runExchangePings() async {
    setState(() {
      _isPingingExchanges = true;
      _pingResults.clear();
    });

    final testTargets = [
      {'ex': 'nobitex', 'sym': 'USDTTMN', 'label': 'Nobitex (تتر/تومان)'},
      {'ex': 'wallex', 'sym': 'USDTTMN', 'label': 'Wallex (تتر/تومان)'},
      {'ex': 'tabdeal', 'sym': 'USDTTMN', 'label': 'Tabdeal (تتر/تومان)'},
      {'ex': 'ramzinex', 'sym': 'USDTTMN', 'label': 'Ramzinex (تتر/تومان)'},
      {'ex': 'binance', 'sym': 'BTCUSDT', 'label': 'Binance Spot'},
      {'ex': 'mexc', 'sym': 'BTCUSDT', 'label': 'MEXC Spot'},
      {'ex': 'kucoin', 'sym': 'BTCUSDT', 'label': 'KuCoin Spot'},
      {'ex': 'gateio', 'sym': 'BTCUSDT', 'label': 'Gate.io Spot'},
      {'ex': 'coinex', 'sym': 'BTCUSDT', 'label': 'CoinEx Spot'},
      {'ex': 'global_stocks', 'sym': 'GOLD', 'label': 'انس طلا جهانی (XAU/USD)'},
      {'ex': 'global_stocks', 'sym': 'EURUSD', 'label': 'یورو / دلار (Forex)'},
      {'ex': 'global_stocks', 'sym': 'DX-Y', 'label': 'شاخص دلار (DXY)'},
      {'ex': 'global_stocks', 'sym': 'US10Y', 'label': 'اوراق ۱۰ ساله آمریکا (US10Y)'},
      {'ex': 'global_stocks', 'sym': 'NVDA', 'label': 'سهام انویدیا (NVIDIA / WallStreet)'},
    ];

    // Run all ping tests concurrently in parallel (Fast & Non-blocking)
    final futures = testTargets.map((target) async {
      final res = await ServerAlertService.inspectMarketSource(target['ex']!, target['sym']!);
      return MapEntry(
        target['label']!,
        res ?? {
          'status': 'FAILED',
          'resolved_price': null,
          'recommendation': 'Server Unreachable or Timeout'
        },
      );
    }).toList();

    final resultsList = await Future.wait(futures);

    if (mounted) {
      setState(() {
        for (final entry in resultsList) {
          _pingResults[entry.key] = entry.value;
        }
        _isPingingExchanges = false;
      });
    }
  }

  void _copyReportToClipboard(BuildContext context, Map<String, dynamic> report, String lang) {
    final theme = Theme.of(context);
    final jsonStr = const JsonEncoder.withIndent('  ').convert(report);
    final markdownBlock = '''
```json
// --- SignalAlert Market Diagnostics Report ---
$jsonStr
```
''';
    Clipboard.setData(ClipboardData(text: markdownBlock));

    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(lang == 'fa' ? '📋 گزارش دیباگ با موفقیت کپی شد! می‌توانید آن را ارسال فرمایید.' : '📋 Diagnostic report copied to clipboard!'),
        backgroundColor: theme.colorScheme.surfaceContainerHighest,
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 3),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final settingsService = context.watch<SettingsService>();
    final lang = settingsService.settings.language;
    final isFa = lang == 'fa' || lang == 'ar' || lang == 'ckb';
    final theme = Theme.of(context);

    return Directionality(
      textDirection: isFa ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          backgroundColor: theme.colorScheme.surface,
          elevation: 0,
          title: Text(
            isFa ? '🛠️ مرکز عیب‌یابی و دیباگ هوشمند' : '🛠️ Debug & Diagnostics Center',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
          ),
          bottom: TabBar(
            controller: _tabController,
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            indicatorColor: theme.colorScheme.primary,
            labelColor: theme.colorScheme.primary,
            unselectedLabelColor: theme.colorScheme.onSurface.withValues(alpha: 0.6),
            tabs: [
              Tab(text: isFa ? '🔍 تست نماد' : 'Inspect Symbol'),
              Tab(text: isFa ? '🔔 تست پوش سرور' : 'Test Push'),
              Tab(text: isFa ? '📜 لاگ‌های سرور' : 'Server Logs'),
              Tab(text: isFa ? '🌐 مانیتورینگ صرافی' : 'Health Matrix'),
            ],
          ),
        ),
        body: TabBarView(
          controller: _tabController,
          children: [
            _buildSymbolInspectorTab(context, theme, lang, isFa),
            _buildTestPushTab(context, theme, lang, isFa),
            _buildServerLogsTab(context, theme, lang, isFa),
            _buildHealthMatrixTab(context, theme, lang, isFa),
          ],
        ),
      ),
    );
  }

  // TAB 1: Live Symbol Inspector
  Widget _buildSymbolInspectorTab(BuildContext context, ThemeData theme, String lang, bool isFa) {
    return ListView(
      padding: const EdgeInsets.all(AppTokens.space16),
      children: [
        // Description Card
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: theme.colorScheme.primary.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.2)),
          ),
          child: Row(
            children: [
              Icon(Icons.bug_report_rounded, color: theme.colorScheme.primary, size: 22),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  isFa
                      ? 'هر نمادی که قیمتش دریافتی نشد یا خطا داشت را اینجا تست فرمایید. گزارش عمیق علت عدم دریافت قیمت فوراً تولید شده و قابل کپی جهت عیب‌یابی است.'
                      : 'Deeply test and diagnose any unresolvable market symbol. Generates full step-by-step API trace logs for troubleshooting.',
                  style: TextStyle(fontSize: 11.5, color: theme.colorScheme.onSurface.withValues(alpha: 0.8), height: 1.35),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppTokens.space16),

        // Controls Box
        Container(
          padding: const EdgeInsets.all(AppTokens.space16),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: theme.dividerColor),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Exchange Selector
              Text(
                isFa ? 'صرافی یا منبع بازار:' : 'Target Exchange Source:',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
              ),
              const SizedBox(height: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    value: _selectedExchange,
                    isExpanded: true,
                    dropdownColor: theme.colorScheme.surface,
                    items: _exchanges.map((ex) {
                      return DropdownMenuItem<String>(
                        value: ex['id'],
                        child: Text(
                          ex['name']!,
                          style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurface),
                        ),
                      );
                    }).toList(),
                    onChanged: (val) {
                      if (val != null) setState(() => _selectedExchange = val);
                    },
                  ),
                ),
              ),
              const SizedBox(height: 14),

              // Symbol Input Field
              Text(
                isFa ? 'نماد بازار (مثلاً BTCUSDT, GOLD, EURUSD, USDTTMN):' : 'Market Symbol (e.g. BTCUSDT, GOLD, EURUSD):',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
              ),
              const SizedBox(height: 6),
              TextField(
                controller: _symbolController,
                textCapitalization: TextCapitalization.characters,
                style: TextStyle(fontFamily: 'monospace', fontWeight: FontWeight.bold, fontSize: 14, color: theme.colorScheme.onSurface),
                decoration: InputDecoration(
                  hintText: 'e.g. BTCUSDT, GOLD, EURUSD',
                  filled: true,
                  fillColor: theme.colorScheme.surfaceContainerHighest,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                ),
              ),
              const SizedBox(height: 16),

              // Run Inspection Button
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _isInspecting ? null : _runDeepInspection,
                  icon: _isInspecting
                      ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.manage_search_rounded, size: 20),
                  label: Text(
                    _isInspecting ? (isFa ? 'در حال تست عمیق سرور...' : 'Inspecting Server...') : (isFa ? '🚀 تست و دیباگ عمیق نماد' : '🚀 Run Deep Inspection'),
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: theme.colorScheme.primary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppTokens.space16),

        // Report Card Output
        if (_lastInspectionReport != null) ...[
          _buildInspectionReportCard(context, theme, lang, isFa, _lastInspectionReport!),
        ],
      ],
    );
  }

  Widget _buildInspectionReportCard(BuildContext context, ThemeData theme, String lang, bool isFa, Map<String, dynamic> report) {
    final isSuccess = report['status'] == 'OK' && report['resolved_price'] != null;
    final traces = (report['traces'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final resolvedPrice = report['resolved_price'];
    final duration = report['total_duration_ms'];

    return Container(
      padding: const EdgeInsets.all(AppTokens.space16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isSuccess ? AppTokens.positive.withValues(alpha: 0.5) : AppTokens.negative.withValues(alpha: 0.5),
          width: 1.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header Status Badge
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: isSuccess ? AppTokens.positive.withValues(alpha: 0.15) : AppTokens.negative.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    Icon(
                      isSuccess ? Icons.check_circle_rounded : Icons.cancel_rounded,
                      color: isSuccess ? AppTokens.positive : AppTokens.negative,
                      size: 16,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      isSuccess ? (isFa ? 'شناسایی و دریافت موفق' : 'PRICE RESOLVED') : (isFa ? 'خطا در دریافت قیمت' : 'RESOLVE FAILED'),
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: isSuccess ? AppTokens.positive : AppTokens.negative,
                      ),
                    ),
                  ],
                ),
              ),
              const Spacer(),
              Text(
                '⏱️ ${duration}ms',
                style: TextStyle(fontSize: 11, fontFamily: 'monospace', color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // Price Output if success
          if (resolvedPrice != null) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    isFa ? 'قیمت نهایی شناسایی شده:' : 'Resolved Live Price:',
                    style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurface.withValues(alpha: 0.7)),
                  ),
                  Text(
                    '\$$resolvedPrice',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                      fontFamily: 'monospace',
                      color: theme.colorScheme.primary,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
          ],

          // Recommendation text
          Text(
            isFa ? 'نتیجه و تحلیل دیباگ:' : 'Diagnostic Trace:',
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
          ),
          const SizedBox(height: 4),
          Text(
            report['recommendation'] ?? '',
            style: TextStyle(fontSize: 11.5, color: theme.colorScheme.onSurface.withValues(alpha: 0.75)),
          ),
          const SizedBox(height: 12),

          // Step-by-step traces
          Text(
            isFa ? 'جزئیات تست گیت‌وی‌ها (Step-by-Step API Traces):' : 'API Gateways Test Details:',
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
          ),
          const SizedBox(height: 6),

          ListView.separated(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: traces.length,
            separatorBuilder: (_, __) => const SizedBox(height: 6),
            itemBuilder: (ctx, i) {
              final tr = traces[i];
              final ok = tr['success'] == true;
              final code = tr['status_code'];
              final sourceName = tr['source'];
              final lat = tr['latency_ms'];
              final err = tr['error'];
              final p = tr['parsed_price'];

              return Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: ok ? AppTokens.positive.withValues(alpha: 0.3) : AppTokens.negative.withValues(alpha: 0.3),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(ok ? Icons.check_circle_outline_rounded : Icons.error_outline_rounded, color: ok ? AppTokens.positive : AppTokens.negative, size: 16),
                        const SizedBox(width: 6),
                        Text(sourceName ?? 'API Source', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: theme.colorScheme.onSurface)),
                        const Spacer(),
                        Text('HTTP $code (${lat}ms)', style: TextStyle(fontSize: 10.5, fontFamily: 'monospace', color: theme.colorScheme.onSurface.withValues(alpha: 0.6))),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      tr['url'] ?? '',
                      style: TextStyle(fontSize: 10, fontFamily: 'monospace', color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (ok && p != null) ...[
                      const SizedBox(height: 2),
                      Text('✅ Parsed Price: $p', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppTokens.positive)),
                    ],
                    if (!ok && err != null) ...[
                      const SizedBox(height: 2),
                      Text('❌ Reason: $err', style: const TextStyle(fontSize: 10.5, color: AppTokens.negative)),
                    ],
                  ],
                ),
              );
            },
          ),
          const SizedBox(height: 14),

          // Copy Report Button
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: () => _copyReportToClipboard(context, report, lang),
              icon: const Icon(Icons.copy_rounded, size: 18),
              label: Text(
                isFa ? '📋 کپی کامل گزارش دیباگ جهت ارسال به هوش‌مصنوعی' : '📋 Copy Full Diagnostic Report',
                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
              ),
              style: OutlinedButton.styleFrom(
                foregroundColor: theme.colorScheme.primary,
                side: BorderSide(color: theme.colorScheme.primary),
                padding: const EdgeInsets.symmetric(vertical: 12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // TAB 2: Live Server Logs
  Widget _buildServerLogsTab(BuildContext context, ThemeData theme, String lang, bool isFa) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(AppTokens.space16),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                isFa ? 'آخرین لاگ‌های خطای سرور (${_serverLogs.length}):' : 'Recent Server Diagnostic Logs (${_serverLogs.length}):',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
              ),
              IconButton(
                icon: _isLoadingLogs
                    ? const SizedBox(width: 16, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.refresh_rounded, size: 20),
                onPressed: _fetchServerLogs,
              ),
            ],
          ),
        ),
        Expanded(
          child: _serverLogs.isEmpty
              ? Center(
                  child: Text(
                    isFa ? 'هیچ لاگ خطایی روی سرور ثبت نشده است ✨' : 'No server diagnostic logs found.',
                    style: TextStyle(color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
                  ),
                )
              : ListView.separated(
                  padding: const EdgeInsets.symmetric(horizontal: AppTokens.space16),
                  itemCount: _serverLogs.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 8),
                  itemBuilder: (ctx, i) {
                    final log = _serverLogs[i];
                    return _buildInspectionReportCard(context, theme, lang, isFa, log);
                  },
                ),
        ),
      ],
    );
  }

  // TAB 3: Health Matrix
  Widget _buildHealthMatrixTab(BuildContext context, ThemeData theme, String lang, bool isFa) {
    return ListView(
      padding: const EdgeInsets.all(AppTokens.space16),
      children: [
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            onPressed: _isPingingExchanges ? null : _runExchangePings,
            icon: _isPingingExchanges
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.network_ping_rounded, size: 20),
            label: Text(
              _isPingingExchanges ? (isFa ? 'در حال تست پینگ تمام صرافی‌ها...' : 'Testing All Exchange Gateways...') : (isFa ? '⚡ شروع تست سلامت تمام صرافی‌ها' : '⚡ Test All Exchange Gateways'),
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: theme.colorScheme.primary,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ),
        const SizedBox(height: AppTokens.space16),

        if (_pingResults.isNotEmpty) ...[
          ListView.separated(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: _pingResults.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (ctx, i) {
              final key = _pingResults.keys.elementAt(i);
              final res = _pingResults[key]!;
              final ok = res['status'] == 'OK' && res['resolved_price'] != null;
              final price = res['resolved_price'];
              final duration = res['total_duration_ms'];

              return Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: ok ? AppTokens.positive.withValues(alpha: 0.4) : AppTokens.negative.withValues(alpha: 0.4),
                  ),
                ),
                child: Row(
                  children: [
                    Icon(ok ? Icons.check_circle_rounded : Icons.cancel_rounded, color: ok ? AppTokens.positive : AppTokens.negative, size: 20),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(key, style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: theme.colorScheme.onSurface)),
                          if (ok && price != null) ...[
                            Text('Live Price: \$$price', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppTokens.positive)),
                          ] else ...[
                            Text(res['recommendation'] ?? 'Unreachable', style: const TextStyle(fontSize: 10.5, color: AppTokens.negative)),
                          ]
                        ],
                      ),
                    ),
                    if (duration != null) ...[
                      Text('${duration}ms', style: TextStyle(fontSize: 11, fontFamily: 'monospace', color: theme.colorScheme.onSurface.withValues(alpha: 0.6))),
                    ],
                  ],
                ),
              );
            },
          ),
        ],
      ],
    );
  }

  Future<void> _triggerLocalNotificationTest(String lang) async {
    final isFa = lang == 'fa' || lang == 'ar' || lang == 'ckb';
    final service = NotificationService();
    await service.showCriticalAlert(
      id: 999,
      title: isFa ? '🔔 هشدار تست زنده در صفحه قفل' : '🔔 Live Lock Screen Test Alert',
      body: isFa
          ? 'تست موفقیت‌آمیز! نوتیفیکیشن با حداکثر اولویت (MAX) و صدای اختصاصی در بالای صفحه قفل نمایش داده شد.'
          : 'Success! Max-priority notification with custom alarm triggered on lock screen.',
      soundName: 'alarm_siren',
      volume: 1.0,
      soundEnabled: true,
      vibrationEnabled: true,
    );
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(isFa ? '🚀 اعلان آزمایشی روی صفحه قفل ارسال شد!' : '🚀 Test notification sent to lock screen!'),
          duration: const Duration(seconds: 3),
        ),
      );
    }
  }

  void _showEditServerUrlDialog(BuildContext context, String lang, bool isFa) {
    final controller = TextEditingController(text: ServerAlertService.baseUrl);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(isFa ? 'تنظیم آدرس سرور (IP یا دامنه)' : 'Edit Server URL / IP'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              isFa
                  ? 'آدرس IP سرور یا دامنه خود را وارد کنید (مثال: http://194.5.188.10:8000 یا https://aisocialfeed.com):'
                  : 'Enter your server IP or domain (e.g. http://194.5.188.10:8000 or https://aisocialfeed.com):',
              style: const TextStyle(fontSize: 12),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: controller,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
              decoration: InputDecoration(
                hintText: 'http://127.0.0.1:8000',
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(isFa ? 'انصراف' : 'Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              final newUrl = controller.text.trim();
              if (newUrl.isNotEmpty) {
                await ServerAlertService.setBaseUrl(newUrl);
                setState(() {});
              }
              if (ctx.mounted) Navigator.pop(ctx);
            },
            child: Text(isFa ? 'ذخیره' : 'Save'),
          ),
        ],
      ),
    );
  }

  void _showEditTokenDialog(BuildContext context, String lang, bool isFa) {
    final controller = TextEditingController(text: _currentFcmToken ?? '');
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(isFa ? 'ویرایش یا ثبت توکن اختصاصی' : 'Edit Device / FCM Token'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              isFa
                  ? 'می‌توانید توکن اختصاصی FCM یا شناسه دلخواه دستگاه خود را وارد کنید:'
                  : 'Enter or paste custom FCM Token or device identifier:',
              style: const TextStyle(fontSize: 12),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: controller,
              maxLines: 3,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 11),
              decoration: InputDecoration(
                hintText: 'e.g. dev_xxxx or fcm_token',
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(isFa ? 'انصراف' : 'Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              final newTok = controller.text.trim();
              if (newTok.isNotEmpty) {
                await FCMNotificationService.setCustomToken(newTok);
                setState(() => _currentFcmToken = newTok);
              }
              if (ctx.mounted) Navigator.pop(ctx);
            },
            child: Text(isFa ? 'ذخیره' : 'Save'),
          ),
        ],
      ),
    );
  }

  // TAB 4: Live Server Push Notification Tester
  Widget _buildTestPushTab(BuildContext context, ThemeData theme, String lang, bool isFa) {
    return ListView(
      padding: const EdgeInsets.all(AppTokens.space16),
      children: [
        // Description Card
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: theme.colorScheme.primary.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.2)),
          ),
          child: Row(
            children: [
              Icon(Icons.mark_email_read_rounded, color: theme.colorScheme.primary, size: 24),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  isFa
                      ? 'تست زنده دریافت نوتیفیکیشن با حداکثر اولویت (MAX) در صفحه قفل گوشی همراه با آلارم و لرزش.'
                      : 'Live Push Delivery Verification. Trigger Max-Priority notifications on lock screen with audio & vibration.',
                  style: const TextStyle(fontSize: 11.5, height: 1.4),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppTokens.space16),

        // 1-Tap Instant Local Lock-Screen Notification Test
        SizedBox(
          width: double.infinity,
          height: 48,
          child: ElevatedButton.icon(
            onPressed: () => _triggerLocalNotificationTest(lang),
            icon: const Icon(Icons.notifications_active_rounded, size: 20),
            label: Text(
              isFa ? '⚡ تست فوری اعلان و آلارم در صفحه قفل گوشی' : '⚡ Test Lock Screen Alarm (Instant Local)',
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF10B981),
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ),
        const SizedBox(height: AppTokens.space16),

        // Server URL & Host Configuration Card
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: theme.dividerColor),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: [
                      Icon(Icons.dns_rounded, size: 18, color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Text(
                        isFa ? 'آدرس سرور مرکزی (Server Address):' : 'Server Engine Address:',
                        style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
                      ),
                    ],
                  ),
                  IconButton(
                    icon: const Icon(Icons.edit_rounded, size: 18),
                    tooltip: isFa ? 'تغییر IP / دامنه سرور' : 'Edit Server IP',
                    onPressed: () => _showEditServerUrlDialog(context, lang, isFa),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: SelectableText(
                  ServerAlertService.baseUrl.isNotEmpty
                      ? ServerAlertService.baseUrl
                      : (isFa ? 'تنظیم نشده (حالت دریافت مستقیم و محلی فعال است)' : 'Not configured (Local direct mode active)'),
                  style: TextStyle(
                    fontSize: 11,
                    fontFamily: 'monospace',
                    fontWeight: FontWeight.w600,
                    color: ServerAlertService.baseUrl.isNotEmpty ? theme.colorScheme.onSurface : theme.colorScheme.onSurface.withValues(alpha: 0.6),
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppTokens.space16),

        // Device Token Card
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: theme.dividerColor),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    isFa ? 'توکن اختصاصی این دستگاه (Device Token)' : 'Device FCM / Push Token',
                    style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface),
                  ),
                  Row(
                    children: [
                      IconButton(
                        icon: const Icon(Icons.refresh_rounded, size: 18),
                        tooltip: isFa ? 'دریافت مجدد توکن از گوگل' : 'Refresh Google Token',
                        onPressed: () async {
                          final tok = await FCMNotificationService.getFCMToken();
                          setState(() => _currentFcmToken = tok);
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text(tok.startsWith('dev_') ? (isFa ? 'توکن محلی (آفلاین)' : 'Local Token') : (isFa ? 'توکن رسمی گوگل دریافت شد!' : 'Real Google FCM Token fetched!')),
                                duration: const Duration(seconds: 2),
                              ),
                            );
                          }
                        },
                      ),
                      IconButton(
                        icon: const Icon(Icons.edit_rounded, size: 18),
                        tooltip: isFa ? 'ویرایش توکن' : 'Edit Token',
                        onPressed: () => _showEditTokenDialog(context, lang, isFa),
                      ),
                      if (_currentFcmToken != null)
                        IconButton(
                          icon: const Icon(Icons.copy_rounded, size: 18),
                          tooltip: isFa ? 'کپی توکن' : 'Copy Token',
                          onPressed: () {
                            Clipboard.setData(ClipboardData(text: _currentFcmToken!));
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text(isFa ? 'توکن کپی شد!' : 'Token copied!'),
                                duration: const Duration(seconds: 2),
                              ),
                            );
                          },
                        ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: SelectableText(
                  _currentFcmToken ?? 'Loading device token...',
                  style: const TextStyle(fontSize: 11, fontFamily: 'monospace', fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppTokens.space16),

        // Action Button: Send Test Push from Server
        SizedBox(
          width: double.infinity,
          height: 48,
          child: ElevatedButton.icon(
            onPressed: _isSendingTestPush ? null : _sendLiveTestPush,
            icon: _isSendingTestPush
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.send_rounded, size: 18),
            label: Text(
              _isSendingTestPush
                  ? (isFa ? 'در حال ارسال پیام تست از سرور...' : 'Sending Test Push from Server...')
                  : (isFa ? '🚀 ارسال نوتیفیکیشن تست از سرور به گوشی' : '🚀 Send Live Test Push via Server'),
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: theme.colorScheme.primary,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ),
        const SizedBox(height: AppTokens.space16),

        // Terminal CLI Guide Card
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFF0F172A),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: Colors.white12),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.terminal_rounded, color: Color(0xFF38BDF8), size: 18),
                  const SizedBox(width: 8),
                  Text(
                    isFa ? 'دستور تست از ترمینال سرور (CLI)' : 'Server Terminal CLI Test Command',
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Colors.white),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                isFa
                    ? 'روی سرور یا سیستم خود، دستور زیر را برای تست مستقیم ارسال کنید:'
                    : 'Run this command on your host/VPS to test push delivery:',
                style: const TextStyle(fontSize: 10.5, color: Colors.white70),
              ),
              const SizedBox(height: 8),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.black45,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: SelectableText(
                  'python test_push.py "App is connected to server! 🚀" "Live Push Active" "${_currentFcmToken ?? "YOUR_TOKEN"}"',
                  style: const TextStyle(fontFamily: 'monospace', fontSize: 11, color: Color(0xFF4ADE80)),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppTokens.space16),

        // Test Push Result
        if (_testPushResult != null) ...[
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: theme.colorScheme.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                color: _testPushResult!['success'] == true
                    ? AppTokens.positive.withValues(alpha: 0.5)
                    : AppTokens.negative.withValues(alpha: 0.5),
                width: 1.4,
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      _testPushResult!['success'] == true ? Icons.check_circle_rounded : Icons.error_rounded,
                      color: _testPushResult!['success'] == true ? AppTokens.positive : AppTokens.negative,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        _testPushResult!['success'] == true
                            ? (isFa ? '✅ نوتیفیکیشن با موفقیت توسط سرور شلیک شد!' : '✅ Push Notification Dispatched Successfully!')
                            : (isFa ? '❌ خطا در ارسال نوتیفیکیشن' : '❌ Push Dispatch Failed'),
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.copy_rounded, size: 18),
                      tooltip: isFa ? 'کپی متن خطا و گزارش' : 'Copy Error & Report',
                      onPressed: () {
                        final rawJson = const JsonEncoder.withIndent('  ').convert(_testPushResult);
                        Clipboard.setData(ClipboardData(text: rawJson));
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(isFa ? '📋 متن خطا و گزارش سرور کپی شد!' : '📋 Error & Report copied to clipboard!'),
                            duration: const Duration(seconds: 2),
                          ),
                        );
                      },
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: SelectableText(
                    const JsonEncoder.withIndent('  ').convert(_testPushResult),
                    style: TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 11,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.9),
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: () {
                      final rawJson = const JsonEncoder.withIndent('  ').convert(_testPushResult);
                      Clipboard.setData(ClipboardData(text: rawJson));
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(isFa ? '📋 متن خطا و گزارش سرور کپی شد!' : '📋 Error & Report copied to clipboard!'),
                          duration: const Duration(seconds: 2),
                        ),
                      );
                    },
                    icon: const Icon(Icons.copy_rounded, size: 16),
                    label: Text(
                      isFa ? '📋 کپی متن کامل خطای سرور جهت ارسال' : '📋 Copy Full Error Log',
                      style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
                    ),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: _testPushResult!['success'] == true ? AppTokens.positive : AppTokens.negative,
                      side: BorderSide(
                        color: _testPushResult!['success'] == true ? AppTokens.positive : AppTokens.negative,
                      ),
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}
