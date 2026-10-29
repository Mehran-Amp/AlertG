import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';
import '../../../core/services/service_logger.dart';
import '../../../core/services/delivery_ack_service.dart';
import '../../../core/services/device_health_service.dart';
import '../../../core/services/fcm_notification_service.dart';
import '../../../core/services/server_alert_service.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/utils/app_lifecycle_helper.dart';
import '../services/settings_service.dart';

/// Comprehensive Notification Health & Diagnostic Page (Phase 3B-2)
class NotificationHealthPage extends StatefulWidget {
  final String lang;

  const NotificationHealthPage({
    super.key,
    required this.lang,
  });

  @override
  State<NotificationHealthPage> createState() => _NotificationHealthPageState();
}

class _NotificationHealthPageState extends State<NotificationHealthPage> {
  bool _isLoading = true;
  bool _isSendingTestPush = false;
  bool _isTestingFlash = false;
  bool _isSendingHeartbeat = false;

  bool _notificationGranted = false;
  bool _batteryExempt = false;

  DateTime? _lastSyncOk;
  bool _syncPending = false;

  Map<String, dynamic>? _deviceHealthData;
  int? _heartbeatAgeSeconds;
  String? _fcmTail;

  int _pendingAcksCount = 0;
  String _serviceLogPreview = '';

  @override
  void initState() {
    super.initState();
    _loadHealthStatus();
  }

  Future<void> _loadHealthStatus() async {
    if (!mounted) return;
    setState(() => _isLoading = true);

    bool notif = false;
    bool battery = false;

    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      try {
        notif = await Permission.notification.status.isGranted;
        battery = await Permission.ignoreBatteryOptimizations.status.isGranted;
      } catch (e, st) {
        ServiceLogger.logError('notification_health.line66', e, st).ignore();
      }
    }

    final lastSync = ServerAlertService.lastSyncOk;
    final pendingSync = ServerAlertService.syncPending;

    String? tokenTail;
    try {
      final token = FCMNotificationService.currentToken;
      if (token != null && token.trim().isNotEmpty) {
        final t = token.trim();
        tokenTail = t.length > 6 ? t.substring(t.length - 6) : t;
      }
    } catch (e, st) {
      ServiceLogger.logError('notification_health.line79', e, st).ignore();
    }

    Map<String, dynamic>? healthRecord;
    int? heartbeatAge;
    try {
      final settingsService = context.read<SettingsService>();
      final uid = settingsService.settings.userEmail ?? '';
      if (uid.isNotEmpty) {
        healthRecord = await DeviceHealthService.getDeviceHealth(userId: uid);
        if (healthRecord != null) {
          heartbeatAge = healthRecord['age_seconds'] as int?;
        }
      }
    } catch (e, st) {
      ServiceLogger.logError('notification_health.line92', e, st).ignore();
    }

    int pendingAcks = 0;
    String logPreview = '';
    try {
      final dir = await getApplicationDocumentsDirectory();
      final acksDir = Directory('${dir.path}/acks');
      if (acksDir.existsSync()) {
        pendingAcks = acksDir
            .listSync()
            .whereType<File>()
            .where((f) => f.path.endsWith('.json') && !f.path.endsWith('.tmp'))
            .length;
      }

      final logFile = File('${dir.path}/service_log.txt');
      if (logFile.existsSync()) {
        final content = await logFile.readAsString();
        final lines = LineSplitter.split(content).toList();
        if (lines.isNotEmpty) {
          final start = lines.length > 8 ? lines.length - 8 : 0;
          logPreview = lines.sublist(start).join('\n');
        }
      }
    } catch (e, st) {
      ServiceLogger.logError('notification_health.line116', e, st).ignore();
    }

    if (mounted) {
      setState(() {
        _notificationGranted = notif;
        _batteryExempt = battery;
        _lastSyncOk = lastSync;
        _syncPending = pendingSync;
        _deviceHealthData = healthRecord;
        _heartbeatAgeSeconds = heartbeatAge;
        _fcmTail = tokenTail;
        _pendingAcksCount = pendingAcks;
        _serviceLogPreview = logPreview;
        _isLoading = false;
      });
    }
  }

  Future<void> _requestNotificationPermission() async {
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      final status = await Permission.notification.request();
      if (mounted) {
        setState(() => _notificationGranted = status.isGranted);
      }
    }
  }

  Future<void> _requestBatteryExemption() async {
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      final status = await Permission.ignoreBatteryOptimizations.request();
      if (mounted) {
        setState(() => _batteryExempt = status.isGranted);
        _sendHeartbeat();
      }
    }
  }

  Future<void> _openAutostartSettings() async {
    final opened = await AppLifecycleHelper.openAutostartSettings();
    if (!opened) {
      await openAppSettings();
    }
  }

  Future<void> _sendHeartbeat() async {
    setState(() => _isSendingHeartbeat = true);
    final settingsService = context.read<SettingsService>();
    final uid = settingsService.settings.userEmail ?? '';
    final isFa = widget.lang == 'fa' || widget.lang == 'ar' || widget.lang == 'ckb';

    bool ok = false;
    if (uid.isNotEmpty) {
      ok = await DeviceHealthService.sendHeartbeat(userId: uid);
    }

    if (mounted) {
      setState(() => _isSendingHeartbeat = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            ok
                ? (isFa ? '✅ نبض سلامت دستگاه ارسال و ثبت شد' : '✅ Device heartbeat recorded')
                : (isFa ? '⚠️ ارسال نبض ناموفق بود' : '⚠️ Failed to send heartbeat'),
          ),
          backgroundColor: ok ? AppTokens.positive : AppTokens.negative,
          behavior: SnackBarBehavior.floating,
        ),
      );
      await _loadHealthStatus();
    }
  }

  Future<void> _sendTestPush() async {
    setState(() => _isSendingTestPush = true);
    final isFa = widget.lang == 'fa' || widget.lang == 'ar' || widget.lang == 'ckb';

    final res = await ServerAlertService.sendTestPush(
      customTitle: '🔔 تست سلامت اعلان‌ها',
      customBody: '✅ کانال ارتباطی سرور و پوش نوتیفیکیشن دستگاه کاملاً فعال و پایدار است.',
    );

    if (mounted) {
      setState(() => _isSendingTestPush = false);
      final ok = res['success'] == true;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            ok
                ? (isFa ? '🎉 پوش تست با موفقیت از سرور ارسال شد' : '🎉 Test push sent successfully')
                : (res['error'] ?? (isFa ? 'خطا در ارسال پوش تست' : 'Failed to send test push')),
          ),
          backgroundColor: ok ? AppTokens.positive : AppTokens.negative,
          behavior: SnackBarBehavior.floating,
        ),
      );
      await _loadHealthStatus();
    }
  }

  Future<void> _testFlash() async {
    setState(() => _isTestingFlash = true);
    final isFa = widget.lang == 'fa' || widget.lang == 'ar' || widget.lang == 'ckb';
    String result = '';
    try {
      const mChannel = MethodChannel('com.example.bitcoin_checker/app_lifecycle');
      await mChannel.invokeMethod('startFlashSOS');
      result = isFa ? '✅ فلش SOS روشن شد (۵ ثانیه)' : '✅ SOS flash started (5s)';
      await Future.delayed(const Duration(seconds: 5));
      await mChannel.invokeMethod('stopFlashSOS');
    } catch (e) {
      result = isFa ? '❌ خطا: $e' : '❌ Error: $e';
    }
    if (mounted) {
      setState(() => _isTestingFlash = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(result)));
    }
  }

  Future<void> _copyServiceLog() async {
    final isFa = widget.lang == 'fa' || widget.lang == 'ar' || widget.lang == 'ckb';
    String fullLogs = '';
    try {
      final dir = await getApplicationDocumentsDirectory();
      final logFile = File('${dir.path}/service_log.txt');
      if (logFile.existsSync()) {
        fullLogs = await logFile.readAsString();
      }
    } catch (e, st) {
      ServiceLogger.logError('notification_health.line225', e, st).ignore();
    }

    if (fullLogs.isEmpty) {
      fullLogs = 'لاگی در حافظه ثبت نشده است یا سرویس هنوز لاگی تولید نکرده است.';
    }

    await Clipboard.setData(ClipboardData(text: fullLogs));

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            isFa
                ? '📋 متن کامل لاگ سرویس در کلیپ‌بورد کپی شد (${fullLogs.length} کاراکتر)'
                : '📋 Service log copied to clipboard (${fullLogs.length} chars)',
          ),
          backgroundColor: AppTokens.positive,
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  String _formatDateTime(DateTime? dt, bool isFa) {
    if (dt == null) return isFa ? 'ثبت نشده' : 'Never';
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inSeconds < 60) {
      return isFa ? '${diff.inSeconds} ثانیه قبل' : '${diff.inSeconds}s ago';
    }
    if (diff.inMinutes < 60) {
      return isFa ? '${diff.inMinutes} دقیقه قبل' : '${diff.inMinutes}m ago';
    }
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    return '$h:$m';
  }

  String _formatHeartbeatAge(int? seconds, bool isFa) {
    if (seconds == null) return isFa ? 'نامشخص' : 'Unknown';
    if (seconds < 60) return isFa ? '$seconds ثانیه قبل' : '${seconds}s ago';
    final m = seconds ~/ 60;
    if (m < 60) return isFa ? '$m دقیقه قبل' : '${m}m ago';
    final h = m ~/ 60;
    return isFa ? '$h ساعت قبل' : '${h}h ago';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final isFa = widget.lang == 'fa' || widget.lang == 'ar' || widget.lang == 'ckb';
    final isSilent = DeviceHealthService.isSilent(_heartbeatAgeSeconds);

    return Directionality(
      textDirection: isFa ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          title: Text(
            isFa ? 'سلامت اعلان‌ها و تحویل ۲۴/۷' : 'Notification Health & Delivery',
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
          ),
          elevation: 0,
          backgroundColor: theme.colorScheme.surface,
          actions: [
            IconButton(
              icon: const Icon(Icons.refresh_rounded),
              tooltip: isFa ? 'بروزرسانی وضعیت' : 'Refresh Status',
              onPressed: _loadHealthStatus,
            ),
          ],
        ),
        body: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _loadHealthStatus,
                child: ListView(
                  padding: const EdgeInsets.all(AppTokens.space16),
                  children: [
                    // Section 1: OS Permissions & Battery
                    _buildSectionHeader(
                      theme: theme,
                      icon: Icons.security_rounded,
                      title: isFa ? '۱. مجوزها و تنظیمات سیستم‌عامل' : '1. OS Permissions & Battery',
                    ),
                    const SizedBox(height: AppTokens.space8),
                    _buildCard(
                      theme: theme,
                      isDark: isDark,
                      children: [
                        _buildStatusRow(
                          theme: theme,
                          label: isFa ? 'مجوز اعلان‌ها (POST_NOTIFICATIONS)' : 'Notification Permission',
                          isOk: _notificationGranted,
                          okText: isFa ? 'مجاز ✅' : 'Granted ✅',
                          failText: isFa ? 'غیرمجاز ❌' : 'Denied ❌',
                          actionButton: !_notificationGranted
                              ? _buildSmallButton(
                                  label: isFa ? 'درخواست مجوز' : 'Request',
                                  onPressed: _requestNotificationPermission,
                                  theme: theme,
                                )
                              : null,
                        ),
                        const Divider(height: 18),
                        _buildStatusRow(
                          theme: theme,
                          label: isFa ? 'بهینه‌سازی باتری (Doze Mode)' : 'Battery Optimization (Doze)',
                          isOk: _batteryExempt,
                          okText: isFa ? 'معاف (پایش پیوسته) ✅' : 'Unrestricted ✅',
                          failText: isFa ? 'محدودشده توسط سیستم ⚠️' : 'Restricted ⚠️',
                          actionButton: !_batteryExempt
                              ? _buildSmallButton(
                                  label: isFa ? 'رفع محدودیت' : 'Unrestrict',
                                  onPressed: _requestBatteryExemption,
                                  theme: theme,
                                )
                              : null,
                        ),
                        const Divider(height: 18),
                        Row(
                          children: [
                            Icon(Icons.power_settings_new_rounded, size: 18, color: theme.colorScheme.primary),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                isFa ? 'شروع خودکار (Autostart - شیائومی/سامسونگ)' : 'Autostart Settings (MIUI/Samsung)',
                                style: const TextStyle(fontSize: 12.5),
                              ),
                            ),
                            _buildSmallButton(
                              label: isFa ? 'تنظیمات گوشی' : 'Open',
                              onPressed: _openAutostartSettings,
                              theme: theme,
                            ),
                          ],
                        ),
                      ],
                    ),

                    const SizedBox(height: AppTokens.space20),

                    // Section 2: Sync & Server Heartbeat
                    _buildSectionHeader(
                      theme: theme,
                      icon: Icons.sync_rounded,
                      title: isFa ? '۲. همگام‌سازی و نبض سلامت سرور' : '2. Sync & Server Heartbeat',
                    ),
                    const SizedBox(height: AppTokens.space8),
                    _buildCard(
                      theme: theme,
                      isDark: isDark,
                      borderColor: isSilent ? AppTokens.warning.withValues(alpha: 0.6) : null,
                      children: [
                        _buildInfoRow(
                          label: isFa ? 'آخرین همگام‌سازی موفق (lastSyncOk)' : 'Last Successful Sync',
                          value: _formatDateTime(_lastSyncOk, isFa),
                          isOk: _lastSyncOk != null,
                          theme: theme,
                        ),
                        const Divider(height: 18),
                        _buildStatusRow(
                          theme: theme,
                          label: isFa ? 'وضعیت صف همگام‌سازی (syncPending)' : 'Sync Queue State',
                          isOk: !_syncPending,
                          okText: isFa ? 'همگام و کامل' : 'Up to date',
                          failText: isFa ? 'در انتظار ارسال' : 'Pending Sync',
                        ),
                        const Divider(height: 18),
                        _buildStatusRow(
                          theme: theme,
                          label: isFa ? 'نبض سلامت سرور (Heartbeat)' : 'Server Heartbeat Status',
                          isOk: !isSilent && _heartbeatAgeSeconds != null,
                          okText: isFa ? 'فعال و برخط' : 'Active & Online',
                          failText: isSilent
                              ? (isFa ? 'ساکت (>۴۵ دقیقه)' : 'Silent (>45m)')
                              : (isFa ? 'در انتظار پالس' : 'Awaiting pulse'),
                        ),
                        const Divider(height: 18),
                        _buildInfoRow(
                          label: isFa ? 'سن آخرین پالس سلامت' : 'Last Heartbeat Age',
                          value: _formatHeartbeatAge(_heartbeatAgeSeconds, isFa),
                          isOk: !isSilent && _heartbeatAgeSeconds != null,
                          theme: theme,
                        ),
                        const Divider(height: 18),
                        _buildInfoRow(
                          label: isFa ? 'شناسه انتهای توکن پوش (FCM Tail)' : 'Push Token Tail',
                          value: _fcmTail != null ? '...$_fcmTail' : '---',
                          isOk: _fcmTail != null,
                          theme: theme,
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          width: double.infinity,
                          child: OutlinedButton.icon(
                            onPressed: _isSendingHeartbeat ? null : _sendHeartbeat,
                            icon: _isSendingHeartbeat
                                ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                                : const Icon(Icons.favorite_rounded, size: 16, color: Colors.pinkAccent),
                            label: Text(
                              _isSendingHeartbeat
                                  ? (isFa ? 'در حال ارسال پالس...' : 'Sending Pulse...')
                                  : (isFa ? 'ارسال فوری نبض سلامت به سرور' : 'Send Heartbeat Ping Now'),
                              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
                            ),
                          ),
                        ),
                      ],
                    ),

                    const SizedBox(height: AppTokens.space20),

                    // Section 3: Delivery & Ack Status
                    _buildSectionHeader(
                      theme: theme,
                      icon: Icons.checklist_rounded,
                      title: isFa ? '۳. وضعیت تایید دریافت (Delivery Ack)' : '3. Delivery Ack Status',
                    ),
                    const SizedBox(height: AppTokens.space8),
                    _buildCard(
                      theme: theme,
                      isDark: isDark,
                      children: [
                        _buildInfoRow(
                          label: isFa ? 'تاییدهای در انتظار ارسال (Pending Acks)' : 'Pending Outbox Acks',
                          value: '$_pendingAcksCount عدد',
                          isOk: _pendingAcksCount == 0,
                          theme: theme,
                        ),
                        const Divider(height: 18),
                        _buildInfoRow(
                          label: isFa ? 'وضعیت پایش ۲۴/۷ پیش‌زمینه' : '24/7 FGS Monitor',
                          value: isFa ? 'فعال (dataSync)' : 'Active (dataSync)',
                          isOk: true,
                          theme: theme,
                        ),
                      ],
                    ),

                    const SizedBox(height: AppTokens.space24),

                    // Section 4: Diagnostics Actions (ارسال پوش آزمایشی و کپی لاگ سرویس)
                    _buildSectionHeader(
                      theme: theme,
                      icon: Icons.build_rounded,
                      title: isFa ? '۴. عملیات تست و بررسی' : '4. Diagnostic Actions',
                    ),
                    const SizedBox(height: AppTokens.space12),

                    // Action 1: Send Test Push
                    SizedBox(
                      width: double.infinity,
                      height: 46,
                      child: ElevatedButton.icon(
                        onPressed: _isSendingTestPush ? null : _sendTestPush,
                        icon: _isSendingTestPush
                            ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                            : const Icon(Icons.send_rounded, size: 18),
                        label: Text(
                          _isSendingTestPush
                              ? (isFa ? 'در حال ارسال پوش تست...' : 'Sending Test Push...')
                              : (isFa ? '🔔 ارسال پوش آزمایشی' : '🔔 Send Test Push'),
                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: theme.colorScheme.primary,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppTokens.radiusMedium)),
                        ),
                      ),

                    ),
                    const SizedBox(height: 12),

                    // Action 3: Test SOS Flash
                    SizedBox(
                      width: double.infinity,
                      height: 46,
                      child: ElevatedButton.icon(
                        onPressed: _isTestingFlash ? null : _testFlash,
                        icon: _isTestingFlash
                            ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                            : const Icon(Icons.flashlight_on_rounded, size: 18),
                        label: Text(
                          _isTestingFlash
                              ? (isFa ? 'در حال تست فلش...' : 'Testing Flash...')
                              : (isFa ? '🔦 تست فلش SOS' : '🔦 Test SOS Flash'),
                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppTokens.warning,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppTokens.radiusMedium)),
                        ),
                      ),
                    ),

                    // Log Preview Card if available
                    if (_serviceLogPreview.isNotEmpty) ...[
                      const SizedBox(height: AppTokens.space16),
                      Text(
                        isFa ? 'آخرین خطوط لاگ سرویس (service_log.txt):' : 'Recent Service Log Lines:',
                        style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface.withValues(alpha: 0.7)),
                      ),
                      const SizedBox(height: 6),
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: isDark ? const Color(0xFF0D1117) : const Color(0xFFF3F4F6),
                          borderRadius: BorderRadius.circular(AppTokens.radiusMedium),
                          border: Border.all(color: theme.dividerColor),
                        ),
                        child: Text(
                          _serviceLogPreview,
                          style: const TextStyle(
                            fontFamily: 'Courier',
                            fontSize: 10,
                            height: 1.4,
                          ),
                        ),
                      ),
                    ],

                    const SizedBox(height: 40),
                  ],
                ),
              ),
      ),
    );
  }

  Widget _buildSectionHeader({
    required ThemeData theme,
    required IconData icon,
    required String title,
  }) {
    return Row(
      children: [
        Icon(icon, size: 18, color: theme.colorScheme.primary),
        const SizedBox(width: 8),
        Text(
          title,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.bold,
            color: theme.colorScheme.primary,
          ),
        ),
      ],
    );
  }

  Widget _buildCard({
    required ThemeData theme,
    required bool isDark,
    required List<Widget> children,
    Color? borderColor,
  }) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: theme.cardColor,
        borderRadius: BorderRadius.circular(AppTokens.radiusLarge),
        border: Border.all(
          color: borderColor ?? theme.dividerColor,
          width: borderColor != null ? 1.5 : 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.04),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: children,
      ),
    );
  }

  Widget _buildStatusRow({
    required ThemeData theme,
    required String label,
    required bool isOk,
    required String okText,
    required String failText,
    Widget? actionButton,
  }) {
    final color = isOk ? AppTokens.positive : AppTokens.negative;
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: const TextStyle(fontSize: 12),
          ),
        ),
        if (actionButton != null) ...[
          actionButton,
          const SizedBox(width: 8),
        ],
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(AppTokens.radiusSmall),
          ),
          child: Text(
            isOk ? okText : failText,
            style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: color),
          ),
        ),
      ],
    );
  }

  Widget _buildInfoRow({
    required String label,
    required String value,
    required bool isOk,
    required ThemeData theme,
  }) {
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: const TextStyle(fontSize: 12),
          ),
        ),
        Text(
          value,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.bold,
            color: isOk ? theme.colorScheme.onSurface : AppTokens.warning,
          ),
        ),
      ],
    );
  }

  Widget _buildSmallButton({
    required String label,
    required VoidCallback onPressed,
    required ThemeData theme,
  }) {
    return TextButton(
      onPressed: onPressed,
      style: TextButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        minimumSize: Size.zero,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: theme.colorScheme.primary),
      ),
    );
  }
}
