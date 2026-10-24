import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

import '../../../core/services/device_health_service.dart';
import '../../../core/services/fcm_notification_service.dart';
import '../../../core/theme/tokens.dart';
import '../services/settings_service.dart';

/// Interactive Device Health & 24/7 Background Delivery Monitor (Phase 3B)
class DeviceHealthCard extends StatefulWidget {
  final String lang;
  final VoidCallback? onHealthUpdated;

  const DeviceHealthCard({
    super.key,
    required this.lang,
    this.onHealthUpdated,
  });

  @override
  State<DeviceHealthCard> createState() => _DeviceHealthCardState();
}

class _DeviceHealthCardState extends State<DeviceHealthCard> {
  bool _isLoading = false;
  bool _isSendingPing = false;
  Map<String, dynamic>? _serverHealthData;
  int? _ageSeconds;
  bool? _localNotifGranted;
  bool? _localBatteryUnrestricted;
  bool? _localFgsRunning;
  String? _fcmTail;

  @override
  void initState() {
    super.initState();
    _refreshHealth();
  }

  Future<void> _refreshHealth() async {
    if (!mounted) return;
    setState(() => _isLoading = true);

    // 1. Gather local device indicators
    String? tokenTail;
    try {
      final token = FCMNotificationService.fcmToken;
      if (token != null && token.trim().isNotEmpty) {
        final t = token.trim();
        tokenTail = t.length > 6 ? t.substring(t.length - 6) : t;
      }
    } catch (_) {}

    bool? notif;
    bool? batt;
    bool? fgs;
    try {
      if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
        notif = await Permission.notification.status.isGranted;
        batt = await Permission.ignoreBatteryOptimizations.status.isGranted;
        fgs = await FlutterBackgroundService().isRunning();
      }
    } catch (_) {}

    // 2. Query server for latest registered heartbeat
    Map<String, dynamic>? serverRes;
    int? age;
    try {
      final settingsService = context.read<SettingsService>();
      final uid = settingsService.settings.userEmail ?? '';
      if (uid.isNotEmpty) {
        serverRes = await DeviceHealthService.getDeviceHealth(userId: uid);
        if (serverRes != null) {
          age = serverRes['age_seconds'] as int?;
        }
      }
    } catch (_) {}

    if (mounted) {
      setState(() {
        _fcmTail = tokenTail;
        _localNotifGranted = notif;
        _localBatteryUnrestricted = batt;
        _localFgsRunning = fgs;
        _serverHealthData = serverRes;
        _ageSeconds = age;
        _isLoading = false;
      });
      widget.onHealthUpdated?.call();
    }
  }

  Future<void> _sendHeartbeatNow() async {
    setState(() => _isSendingPing = true);

    final settingsService = context.read<SettingsService>();
    final uid = settingsService.settings.userEmail ?? '';
    final isFa = widget.lang == 'fa' || widget.lang == 'ar' || widget.lang == 'ckb';

    bool ok = false;
    if (uid.isNotEmpty) {
      ok = await DeviceHealthService.sendHeartbeat(userId: uid);
    }

    if (mounted) {
      setState(() => _isSendingPing = false);
      final theme = Theme.of(context);

      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            ok
                ? (isFa ? '✅ پالس سلامت با موفقیت به سرور ارسال و ثبت شد' : '✅ Health heartbeat sent & recorded on server')
                : (isFa ? '⚠️ ارسال پالس سلامت ناموفق بود یا کاربر تنظیم نشده است' : '⚠️ Failed to send heartbeat or user missing'),
            style: const TextStyle(fontSize: 12),
          ),
          backgroundColor: ok ? AppTokens.positive : AppTokens.negative,
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 3),
        ),
      );

      // Re-fetch server view
      await _refreshHealth();
    }
  }

  Future<void> _requestBatteryOptimization() async {
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      final status = await Permission.ignoreBatteryOptimizations.request();
      if (mounted) {
        setState(() => _localBatteryUnrestricted = status.isGranted);
        final settingsService = context.read<SettingsService>();
        final uid = settingsService.settings.userEmail ?? '';
        if (uid.isNotEmpty) {
          DeviceHealthService.sendHeartbeat(userId: uid).ignore();
        }
      }
    }
  }

  String _formatAge(int? seconds, bool isFa) {
    if (seconds == null) {
      return isFa ? 'نامشخص (بدون رکورد)' : 'Unknown (no record)';
    }
    if (seconds < 60) {
      return isFa ? '$seconds ثانیه قبل' : '${seconds}s ago';
    }
    final minutes = seconds ~/ 60;
    if (minutes < 60) {
      return isFa ? '$minutes دقیقه قبل' : '${minutes}m ago';
    }
    final hours = minutes ~/ 60;
    return isFa ? '$hours ساعت قبل' : '${hours}h ago';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final isFa = widget.lang == 'fa' || widget.lang == 'ar' || widget.lang == 'ckb';

    final isSilent = DeviceHealthService.isSilent(_ageSeconds);
    final isServerActive = _serverHealthData != null;

    final badgeColor = isSilent
        ? AppTokens.warning
        : (isServerActive ? AppTokens.positive : AppTokens.textMuted);

    final badgeText = isSilent
        ? (isFa ? '⚠️ حالت سکوت (>۴۵ دقیقه)' : '⚠️ Silent Mode (>45m)')
        : (isServerActive
            ? (isFa ? '🟢 فعال و متصل به سرور' : '🟢 Active & Online')
            : (isFa ? '⚪ در انتظار اولین پالس' : '⚪ Awaiting First Pulse'));

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.cardColor,
        borderRadius: BorderRadius.circular(AppTokens.radiusLarge),
        border: Border.all(
          color: isSilent
              ? AppTokens.warning.withValues(alpha: 0.5)
              : theme.dividerColor,
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
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header Row: Title + Status Badge
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: badgeColor.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  Icons.phone_android_rounded,
                  color: badgeColor,
                  size: 20,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isFa ? 'سلامت دستگاه و تحویل ۲۴/۷' : 'Device Health & 24/7 Delivery',
                      style: TextStyle(
                        fontSize: 13.5,
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      badgeText,
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: badgeColor,
                      ),
                    ),
                  ],
                ),
              ),
              if (_isLoading)
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else
                IconButton(
                  tooltip: isFa ? 'بروزرسانی وضعیت' : 'Refresh Status',
                  icon: const Icon(Icons.refresh_rounded, size: 18),
                  onPressed: _refreshHealth,
                ),
            ],
          ),

          const SizedBox(height: 14),

          // Silent Device Warning Notice (Phase 3A-3 explanation)
          if (isSilent) ...[
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: AppTokens.warning.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(AppTokens.radiusMedium),
                border: Border.all(color: AppTokens.warning.withValues(alpha: 0.4)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.info_outline_rounded, color: AppTokens.warning, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      isFa
                          ? 'بیش از ۴۵ دقیقه از آخرین پالس دستگاه می‌گذرد. برای جلوگیری از تاخیر در تحویل قیمت‌ها، سامانه به‌طور خودکار فال‌بک سریع تلگرام را فعال کرده است.'
                          : 'No heartbeat received in >45 minutes. The server has automatically shortened ack waits and armed fast Telegram fallback to guarantee you never miss a trade alert.',
                      style: TextStyle(
                        fontSize: 11,
                        height: 1.4,
                        color: isDark ? const Color(0xFFFDE68A) : const Color(0xFF92400E),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
          ],

          // Indicator Rows
          _buildHealthRow(
            theme: theme,
            icon: Icons.notifications_active_rounded,
            label: isFa ? 'مجوز اعلان‌ها (Android 14+)' : 'Notification Permission',
            value: _localNotifGranted == true
                ? (isFa ? 'فعال و مجاز' : 'Granted')
                : (isFa ? 'غیرفعال / محدود' : 'Blocked / Denied'),
            isOk: _localNotifGranted == true,
          ),
          const SizedBox(height: 8),

          _buildHealthRow(
            theme: theme,
            icon: Icons.battery_charging_full_rounded,
            label: isFa ? 'بهینه‌سازی باتری (Doze Mode)' : 'Battery Optimization (Doze)',
            value: _localBatteryUnrestricted == true
                ? (isFa ? 'معاف (پایش مداوم)' : 'Unrestricted')
                : (isFa ? 'محدودشده توسط سیستم' : 'Optimized / Restricted'),
            isOk: _localBatteryUnrestricted == true,
            actionButton: _localBatteryUnrestricted == false
                ? TextButton(
                    onPressed: _requestBatteryOptimization,
                    style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      minimumSize: Size.zero,
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                    child: Text(
                      isFa ? 'رفع محدودیت' : 'Unrestrict',
                      style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold),
                    ),
                  )
                : null,
          ),
          const SizedBox(height: 8),

          _buildHealthRow(
            theme: theme,
            icon: Icons.sync_rounded,
            label: isFa ? 'سرویس پس‌زمینه (FGS DataSync)' : 'Background FGS (DataSync)',
            value: _localFgsRunning == true
                ? (isFa ? 'در حال اجرا' : 'Running')
                : (isFa ? 'آماده‌به‌کار' : 'Standby'),
            isOk: _localFgsRunning == true,
          ),
          const SizedBox(height: 8),

          _buildHealthRow(
            theme: theme,
            icon: Icons.fingerprint_rounded,
            label: isFa ? 'شناسه توکن پوش (FCM Tail)' : 'Push Token Tail (FCM)',
            value: _fcmTail != null ? '...$_fcmTail' : '---',
            isOk: _fcmTail != null,
          ),
          const SizedBox(height: 8),

          _buildHealthRow(
            theme: theme,
            icon: Icons.access_time_filled_rounded,
            label: isFa ? 'آخرین ثبت نبض در سرور' : 'Last Server Heartbeat',
            value: _formatAge(_ageSeconds, isFa),
            isOk: !isSilent && _ageSeconds != null,
          ),

          const SizedBox(height: 16),

          // Action Button: Send Heartbeat Now
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: _isSendingPing ? null : _sendHeartbeatNow,
              icon: _isSendingPing
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.favorite_rounded, size: 16),
              label: Text(
                _isSendingPing
                    ? (isFa ? 'در حال ارسال پالس...' : 'Sending Pulse...')
                    : (isFa ? 'ارسال فوری نبض سلامت (Refresh Heartbeat)' : 'Send Heartbeat Ping Now'),
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: theme.colorScheme.primary,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 10),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppTokens.radiusMedium),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHealthRow({
    required ThemeData theme,
    required IconData icon,
    required String label,
    required String value,
    required bool isOk,
    Widget? actionButton,
  }) {
    final statusColor = isOk ? AppTokens.positive : AppTokens.negative;

    return Row(
      children: [
        Icon(icon, size: 16, color: theme.colorScheme.onSurface.withValues(alpha: 0.6)),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            label,
            style: TextStyle(
              fontSize: 11.5,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.75),
            ),
          ),
        ),
        if (actionButton != null) ...[
          actionButton,
          const SizedBox(width: 6),
        ],
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(
            color: statusColor.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(AppTokens.radiusSmall),
          ),
          child: Text(
            value,
            style: TextStyle(
              fontSize: 10.5,
              fontWeight: FontWeight.bold,
              color: statusColor,
            ),
          ),
        ),
      ],
    );
  }
}
