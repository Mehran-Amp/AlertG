import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';

import '../models/notification_log.dart';
import '../../../core/utils/app_lifecycle_helper.dart';
import '../../../core/utils/crypto_icons.dart';
import '../../../core/utils/format_utils.dart';

/// Full English 1:1 Square Branded Social Share Card
/// Engineered with a fixed 440x440 virtual canvas, TextScaler.noScaling,
/// and FittedBox constraints to guarantee ZERO pixel overflow on any device or font scale.
class SocialAlertCard1x1 extends StatelessWidget {
  final NotificationLog log;
  final GlobalKey? repaintKey;

  const SocialAlertCard1x1({
    super.key,
    required this.log,
    this.repaintKey,
  });

  String _resolveLogCurrency() {
    final sym = log.marketSymbol.toUpperCase();
    final baseSym = sym.contains('/') ? sym.split('/')[0].trim() : sym;
    if (baseSym == 'TOTAL' ||
        baseSym == 'TOTAL2' ||
        baseSym == 'TOTAL3' ||
        sym.contains('B USD') ||
        sym.contains('/B USD')) {
      return 'B USD';
    }
    if (sym.contains('M USD') || sym.contains('/M USD')) {
      return 'M USD';
    }
    if (baseSym == 'BTC.D' ||
        baseSym == 'USDT.D' ||
        baseSym == 'ETH.D' ||
        baseSym.endsWith('.D') ||
        sym.contains('%')) {
      return '%';
    }
    if (sym.contains('/')) {
      final parts = sym.split('/');
      if (parts.length > 1) return parts[1];
    }
    return 'USD';
  }

  String _extractBaseCurrency() {
    if (log.marketSymbol.contains('/')) {
      return log.marketSymbol.split('/')[0].trim().toUpperCase();
    }
    return log.marketSymbol.trim().toUpperCase();
  }

  String _formatConditionType(String? type) {
    switch (type) {
      case 'percentChange':
        return 'PERCENT SPIKE DETECTED';
      case 'absolutePriceChange':
        return 'ABSOLUTE MOVE REACHED';
      case 'volumeChange':
        return 'VOLUME SPIKE ALERT';
      case 'priceThreshold':
      default:
        return 'PRICE TARGET TRIGGERED';
    }
  }

  @override
  Widget build(BuildContext context) {
    final isUpward = log.title.contains('🟢') ||
        log.title.contains('صعود') ||
        log.title.contains('↗️') ||
        log.title.contains('+') ||
        log.title.contains('Surged') ||
        (log.previousPrice != null && log.triggeredPrice >= log.previousPrice!);

    final isDownward = log.title.contains('🔴') ||
        log.title.contains('افت') ||
        log.title.contains('ریزش') ||
        log.title.contains('↘️') ||
        log.title.contains('-') ||
        log.title.contains('Dropped') ||
        (log.previousPrice != null && log.triggeredPrice < log.previousPrice!);

    // Trend Accent: Neon Emerald for Bullish, Neon Coral for Bearish, Azure Cyan for Neutral
    final Color primaryAccent = isUpward
        ? const Color(0xFF10B981) // Neon Emerald
        : (isDownward ? const Color(0xFFF43F5E) : const Color(0xFF06B6D4));

    final baseSymbol = _extractBaseCurrency();
    final currency = _resolveLogCurrency();

    double? priceMovePct;
    if (log.previousPrice != null && log.previousPrice! > 0) {
      priceMovePct = ((log.triggeredPrice - log.previousPrice!) / log.previousPrice!) * 100.0;
    }

    final hasNote = log.customNote != null && log.customNote!.trim().isNotEmpty;

    // Fixed 440x440 canvas with guaranteed zero pixel overflow
    final canvasWidget = MediaQuery(
      data: MediaQuery.of(context).copyWith(
        textScaler: TextScaler.noScaling,
      ),
      child: Container(
        width: 440,
        height: 440,
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFF0F172A), // Dark Slate Navy
              Color(0xFF0A0F1D), // Obsidian Blue
              Color(0xFF030712), // Deepest Onyx Black
            ],
          ),
          border: Border.all(
            color: primaryAccent.withValues(alpha: 0.55),
            width: 2.0,
          ),
          boxShadow: [
            BoxShadow(
              color: primaryAccent.withValues(alpha: 0.28),
              blurRadius: 36,
              spreadRadius: 2,
            ),
            const BoxShadow(
              color: Colors.black,
              blurRadius: 24,
              offset: Offset(0, 12),
            ),
          ],
        ),
        child: Stack(
          children: [
            // Ambient glowing radial accent in top right corner
            Positioned(
              top: -60,
              right: -60,
              child: Container(
                width: 180,
                height: 180,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      primaryAccent.withValues(alpha: 0.22),
                      Colors.transparent,
                    ],
                  ),
                ),
              ),
            ),

            // Main structured content column
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // 1. TOP HEADER BRAND BAR: AlertG + Price Alert Status
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: primaryAccent.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(
                        color: primaryAccent.withValues(alpha: 0.35),
                        width: 1,
                      ),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        // Left: App Brand & Radar Icon
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              padding: const EdgeInsets.all(4),
                              decoration: BoxDecoration(
                                color: primaryAccent.withValues(alpha: 0.2),
                                shape: BoxShape.circle,
                              ),
                              child: Icon(
                                Icons.radar_rounded,
                                size: 14,
                                color: primaryAccent,
                              ),
                            ),
                            const SizedBox(width: 6),
                            const Text(
                              'AlertG',
                              style: TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w900,
                                fontSize: 13,
                                letterSpacing: 0.5,
                              ),
                            ),
                            const SizedBox(width: 5),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: const Text(
                                'PRICE RADAR',
                                style: TextStyle(
                                  color: Colors.white70,
                                  fontSize: 8.5,
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: 0.4,
                                ),
                              ),
                            ),
                          ],
                        ),

                        // Right: Live Trigger Status Pill
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2.5),
                          decoration: BoxDecoration(
                            color: primaryAccent,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Container(
                                width: 5,
                                height: 5,
                                decoration: const BoxDecoration(
                                  color: Colors.black,
                                  shape: BoxShape.circle,
                                ),
                              ),
                              const SizedBox(width: 4),
                              const Text(
                                'REAL-TIME ALERT',
                                style: TextStyle(
                                  color: Colors.black,
                                  fontSize: 9,
                                  fontWeight: FontWeight.w900,
                                  letterSpacing: 0.6,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),

                  // 2. ASSET ROW: Logo + Market Symbol + Exchange Badge + 24h/Move Pill
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      // Asset Icon with glowing neon ring
                      Container(
                        padding: const EdgeInsets.all(2.5),
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: primaryAccent.withValues(alpha: 0.65),
                            width: 1.8,
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: primaryAccent.withValues(alpha: 0.35),
                              blurRadius: 10,
                            ),
                          ],
                        ),
                        child: CryptoIcons.buildLogo(baseSymbol, size: 36),
                      ),
                      const SizedBox(width: 10),

                      // Market Symbol and Exchange Pill
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              log.marketSymbol,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontFamily: 'sans-serif',
                                fontWeight: FontWeight.w900,
                                fontSize: 18,
                                color: Colors.white,
                                letterSpacing: 0.3,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF1E293B),
                                    borderRadius: BorderRadius.circular(4),
                                    border: Border.all(color: Colors.white12),
                                  ),
                                  child: Text(
                                    log.exchangeId.toUpperCase(),
                                    style: TextStyle(
                                      color: primaryAccent,
                                      fontSize: 9.5,
                                      fontWeight: FontWeight.w800,
                                      letterSpacing: 0.5,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 6),
                                const Text(
                                  '• Verified Feed',
                                  style: TextStyle(
                                    fontSize: 9.5,
                                    color: Colors.white54,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),

                      // Move Percentage Badge
                      if (priceMovePct != null)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                          decoration: BoxDecoration(
                            color: primaryAccent.withValues(alpha: 0.18),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                              color: primaryAccent.withValues(alpha: 0.55),
                              width: 1.2,
                            ),
                          ),
                          child: Text(
                            '${priceMovePct >= 0 ? "▲ +" : "▼ "}${priceMovePct.abs().toStringAsFixed(2)}%',
                            style: TextStyle(
                              color: primaryAccent,
                              fontSize: 13,
                              fontWeight: FontWeight.w900,
                              fontFamily: 'monospace',
                            ),
                          ),
                        ),
                    ],
                  ),

                  // 3. MAIN TRIGGER HERO DISPLAY: Trigger Reason + Giant Price + Target Bar
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1E293B).withValues(alpha: 0.55),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: primaryAccent.withValues(alpha: 0.35),
                        width: 1.2,
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Trigger condition header
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(
                              child: Text(
                                _formatConditionType(log.conditionType),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  color: primaryAccent,
                                  fontSize: 9.5,
                                  fontWeight: FontWeight.w900,
                                  letterSpacing: 0.8,
                                ),
                              ),
                            ),
                            Text(
                              'MARKET HIT',
                              style: TextStyle(
                                color: Colors.white.withValues(alpha: 0.5),
                                fontSize: 8.5,
                                fontWeight: FontWeight.bold,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),

                        // Giant Triggered Price
                        SizedBox(
                          width: double.infinity,
                          child: FittedBox(
                            fit: BoxFit.scaleDown,
                            alignment: Alignment.centerLeft,
                            child: Text(
                              FormatUtils.formatPrice(
                                log.triggeredPrice,
                                currencySymbol: currency,
                                lang: 'en',
                              ),
                              style: TextStyle(
                                fontFamily: 'monospace',
                                fontSize: 27,
                                fontWeight: FontWeight.w900,
                                color: primaryAccent,
                                letterSpacing: -0.5,
                              ),
                            ),
                          ),
                        ),

                        // Target Comparison Row (if target exists)
                        if (log.previousPrice != null && log.previousPrice! > 0) ...[
                          const SizedBox(height: 4),
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  'Target: ${FormatUtils.formatPrice(log.previousPrice!, currencySymbol: currency, lang: "en")}',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                    fontSize: 10.5,
                                    fontFamily: 'monospace',
                                    color: Colors.white.withValues(alpha: 0.65),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 6),
                              const Icon(Icons.arrow_forward_rounded, size: 11, color: Colors.grey),
                              const SizedBox(width: 6),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                                decoration: BoxDecoration(
                                  color: primaryAccent.withValues(alpha: 0.15),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(
                                  'TRIGGERED',
                                  style: TextStyle(
                                    fontSize: 9,
                                    fontWeight: FontWeight.w900,
                                    letterSpacing: 0.5,
                                    color: primaryAccent,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),

                  // 4. STRATEGY NOTE OR PROMO HIGHLIGHT (Guaranteed bounded lines)
                  if (hasNote)
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                      decoration: BoxDecoration(
                        color: primaryAccent.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                          color: primaryAccent.withValues(alpha: 0.25),
                          width: 0.8,
                        ),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.format_quote_rounded,
                            size: 15,
                            color: primaryAccent,
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                              log.customNote!.trim(),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 10.5,
                                fontStyle: FontStyle.italic,
                                fontWeight: FontWeight.w600,
                                color: Colors.white.withValues(alpha: 0.95),
                                height: 1.25,
                              ),
                            ),
                          ),
                        ],
                      ),
                    )
                  else
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.04),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.bolt_rounded, size: 14, color: primaryAccent),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                              'Instant multi-market price alerts for crypto, stocks, gold & forex.',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 9.5,
                                color: Colors.white.withValues(alpha: 0.7),
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),

                  // 5. STORE BADGES (Google Play, App Store & Telegram Bot) + Verified Footer
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1E293B).withValues(alpha: 0.65),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: Colors.white12),
                    ),
                    child: Column(
                      children: [
                        // Callout label
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                'Get Instant Alerts on Mobile & Telegram Bot:',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 9,
                                  fontWeight: FontWeight.w700,
                                  color: Colors.white.withValues(alpha: 0.65),
                                  letterSpacing: 0.3,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 5),

                        // 3 Badges side-by-side: Each wrapped in Expanded + FittedBox to prevent any overflow
                        Row(
                          children: [
                            // 1. Google Play
                            Expanded(
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4.5),
                                decoration: BoxDecoration(
                                  color: Colors.white.withValues(alpha: 0.06),
                                  borderRadius: BorderRadius.circular(6),
                                  border: Border.all(color: Colors.white12),
                                ),
                                child: Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Icon(Icons.play_arrow_rounded, size: 14, color: Colors.greenAccent[400]),
                                    const SizedBox(width: 3),
                                    Flexible(
                                      child: FittedBox(
                                        fit: BoxFit.scaleDown,
                                        child: const Text(
                                          'Google Play',
                                          maxLines: 1,
                                          style: TextStyle(
                                            fontSize: 9.5,
                                            fontWeight: FontWeight.w800,
                                            color: Colors.white,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                            const SizedBox(width: 5),

                            // 2. App Store
                            Expanded(
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4.5),
                                decoration: BoxDecoration(
                                  color: Colors.white.withValues(alpha: 0.06),
                                  borderRadius: BorderRadius.circular(6),
                                  border: Border.all(color: Colors.white12),
                                ),
                                child: Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Icon(Icons.apple_rounded, size: 14, color: Colors.white.withValues(alpha: 0.95)),
                                    const SizedBox(width: 3),
                                    Flexible(
                                      child: FittedBox(
                                        fit: BoxFit.scaleDown,
                                        child: const Text(
                                          'App Store',
                                          maxLines: 1,
                                          style: TextStyle(
                                            fontSize: 9.5,
                                            fontWeight: FontWeight.w800,
                                            color: Colors.white,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                            const SizedBox(width: 5),

                            // 3. Telegram Bot
                            Expanded(
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4.5),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF38BDF8).withValues(alpha: 0.12),
                                  borderRadius: BorderRadius.circular(6),
                                  border: Border.all(
                                    color: const Color(0xFF38BDF8).withValues(alpha: 0.35),
                                  ),
                                ),
                                child: Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    const Icon(Icons.send_rounded, size: 12, color: Color(0xFF38BDF8)),
                                    const SizedBox(width: 3),
                                    Flexible(
                                      child: FittedBox(
                                        fit: BoxFit.scaleDown,
                                        child: const Text(
                                          '@alertsifnalampbot',
                                          maxLines: 1,
                                          style: TextStyle(
                                            fontSize: 9,
                                            fontWeight: FontWeight.w900,
                                            color: Color(0xFF38BDF8),
                                          ),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 5),

                        // Timestamp & Verification row
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(
                              child: Text(
                                'Verified Alert: ${DateFormat('yyyy-MM-dd HH:mm').format(log.timestamp.toUtc())} UTC',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 8.5,
                                  fontFamily: 'monospace',
                                  color: Colors.white.withValues(alpha: 0.5),
                                ),
                              ),
                            ),
                            const SizedBox(width: 6),
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Container(
                                  width: 4,
                                  height: 4,
                                  decoration: BoxDecoration(
                                    color: primaryAccent,
                                    shape: BoxShape.circle,
                                  ),
                                ),
                                const SizedBox(width: 4),
                                Text(
                                  'Zero Delay Engine',
                                  style: TextStyle(
                                    fontSize: 8.5,
                                    fontWeight: FontWeight.bold,
                                    color: primaryAccent,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );

    final responsiveWrapper = AspectRatio(
      aspectRatio: 1.0,
      child: FittedBox(
        fit: BoxFit.contain,
        alignment: Alignment.center,
        child: canvasWidget,
      ),
    );

    if (repaintKey != null) {
      return RepaintBoundary(
        key: repaintKey,
        child: canvasWidget,
      );
    }
    return responsiveWrapper;
  }
}

/// Helper bottom sheet modal to preview 1:1 image and invoke native Share Image
void showSocialShareSheet(BuildContext context, NotificationLog log) {
  final GlobalKey repaintKey = GlobalKey();

  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: const Color(0xFF0F172A),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    builder: (ctx) {
      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Sheet Header
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: const [
                      Icon(Icons.share_rounded, color: Color(0xFF38BDF8), size: 20),
                      SizedBox(width: 8),
                      Text(
                        'Share Social Alert (1:1)',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ],
                  ),
                  IconButton(
                    icon: const Icon(Icons.close_rounded, color: Colors.grey, size: 22),
                    onPressed: () => Navigator.pop(ctx),
                  ),
                ],
              ),
              const SizedBox(height: 12),

              // 1:1 Square Preview Card (Contained, responsive & scaled)
              Center(
                child: SizedBox(
                  width: 320,
                  height: 320,
                  child: AspectRatio(
                    aspectRatio: 1.0,
                    child: FittedBox(
                      fit: BoxFit.contain,
                      child: SocialAlertCard1x1(
                        log: log,
                        repaintKey: repaintKey,
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // Primary Action: Share Alert Image Button
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF38BDF8),
                    foregroundColor: const Color(0xFF0F172A),
                    padding: const EdgeInsets.symmetric(vertical: 13),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    elevation: 3,
                  ),
                  icon: const Icon(Icons.share_rounded, size: 18),
                  label: const Text(
                    'Share Image',
                    style: TextStyle(
                      fontWeight: FontWeight.w900,
                      fontSize: 14,
                      letterSpacing: 0.3,
                    ),
                  ),
                  onPressed: () async {
                    try {
                      final boundary =
                          repaintKey.currentContext?.findRenderObject() as RenderRepaintBoundary?;
                      if (boundary == null) return;
                      final image = await boundary.toImage(pixelRatio: 2.5);
                      final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
                      if (byteData == null) return;
                      final bytes = byteData.buffer.asUint8List();

                      final dir = await getTemporaryDirectory();
                      final file = File('${dir.path}/alert_${log.uuid}.png');
                      await file.writeAsBytes(bytes, flush: true);

                      final shareText =
                          '🚨 ${log.marketSymbol} Alert Triggered!\n'
                          'Price: ${FormatUtils.formatPrice(log.triggeredPrice, lang: "en")}\n'
                          'Exchange: ${log.exchangeId.toUpperCase()}\n'
                          '${log.customNote != null && log.customNote!.isNotEmpty ? "Note: ${log.customNote}\n" : ""}'
                          '⚡ Real-time price alerts on Telegram: @alertsifnalampbot';

                      final shared = await AppLifecycleHelper.shareAlertImage(file.path, shareText);
                      if (!shared) {
                        Clipboard.setData(ClipboardData(text: shareText));
                      }

                      if (context.mounted) {
                        Navigator.pop(ctx);
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('🚀 Sharing 1:1 image card...'),
                            backgroundColor: Color(0xFF10B981),
                            behavior: SnackBarBehavior.floating,
                          ),
                        );
                      }
                    } catch (e) {
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text('Error sharing card image: $e'),
                            backgroundColor: Colors.redAccent,
                          ),
                        );
                      }
                    }
                  },
                ),
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      );
    },
  );
}
