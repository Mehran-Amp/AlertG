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
        return 'PERCENT MOVE SPIKE';
      case 'absolutePriceChange':
        return 'ABSOLUTE MOVE HIT';
      case 'volumeChange':
        return 'VOLUME SPIKE DETECTED';
      case 'priceThreshold':
      default:
        return 'PRICE TARGET REACHED';
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

    final Color primaryAccent = isUpward
        ? const Color(0xFF10B981) // Emerald Neon Green
        : (isDownward ? const Color(0xFFEF4444) : const Color(0xFF38BDF8));

    final baseSymbol = _extractBaseCurrency();
    final currency = _resolveLogCurrency();

    double? priceMovePct;
    if (log.previousPrice != null && log.previousPrice! > 0) {
      priceMovePct = ((log.triggeredPrice - log.previousPrice!) / log.previousPrice!) * 100.0;
    }

    final cardContent = AspectRatio(
      aspectRatio: 1.0,
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(22),
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFF0F172A), // Deep Slate
              Color(0xFF090D16), // Dark Obsidian
              Color(0xFF030712), // Deepest Black
            ],
          ),
          border: Border.all(
            color: primaryAccent.withValues(alpha: 0.45),
            width: 1.8,
          ),
          boxShadow: [
            BoxShadow(
              color: primaryAccent.withValues(alpha: 0.22),
              blurRadius: 28,
              spreadRadius: 2,
            ),
            const BoxShadow(
              color: Colors.black,
              blurRadius: 18,
              offset: Offset(0, 8),
            ),
          ],
        ),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 1. TOP HEADER BANNER: Immediate Visual Recognition
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: primaryAccent.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: primaryAccent.withValues(alpha: 0.35),
                  width: 1,
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: [
                      Icon(
                        Icons.notifications_active_rounded,
                        size: 14,
                        color: primaryAccent,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'REAL-TIME PRICE ALERT TRIGGERED',
                        style: TextStyle(
                          color: primaryAccent,
                          fontWeight: FontWeight.w900,
                          fontSize: 10,
                          letterSpacing: 0.8,
                        ),
                      ),
                    ],
                  ),
                  Row(
                    children: [
                      Container(
                        width: 6,
                        height: 6,
                        decoration: BoxDecoration(
                          color: primaryAccent,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 4),
                      const Text(
                        'LIVE',
                        style: TextStyle(
                          color: Colors.white70,
                          fontSize: 9,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            // 2. ASSET ROW: Logo + Symbol + Exchange Badge + App Branding
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(2.5),
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: primaryAccent.withValues(alpha: 0.6),
                          width: 1.5,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: primaryAccent.withValues(alpha: 0.25),
                            blurRadius: 8,
                          ),
                        ],
                      ),
                      child: CryptoIcons.buildLogo(baseSymbol, size: 34),
                    ),
                    const SizedBox(width: 10),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          log.marketSymbol,
                          style: const TextStyle(
                            fontFamily: 'sans-serif',
                            fontWeight: FontWeight.w900,
                            fontSize: 18,
                            color: Colors.white,
                            letterSpacing: 0.4,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1.5),
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
                      ],
                    ),
                  ],
                ),

                // App Brand Badge
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1E293B),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.white12),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.radar_rounded, size: 14, color: primaryAccent),
                          const SizedBox(width: 5),
                          const Text(
                            'AlertG Engine',
                            style: TextStyle(
                              fontWeight: FontWeight.w900,
                              fontSize: 11.5,
                              color: Colors.white,
                              letterSpacing: 0.4,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Automated Market Radar',
                      style: TextStyle(
                        fontSize: 8.5,
                        color: Colors.white.withValues(alpha: 0.45),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ],
            ),

            // 3. MAIN TRIGGER DISPLAY: Giant Price + Percentage + Flow
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: const Color(0xFF1E293B).withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: primaryAccent.withValues(alpha: 0.25),
                  width: 1,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        _formatConditionType(log.conditionType),
                        style: TextStyle(
                          color: primaryAccent,
                          fontSize: 9.5,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 0.8,
                        ),
                      ),
                      if (priceMovePct != null)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: primaryAccent.withValues(alpha: 0.2),
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(
                              color: primaryAccent.withValues(alpha: 0.5),
                              width: 1,
                            ),
                          ),
                          child: Text(
                            '${priceMovePct >= 0 ? "▲ +" : "▼ "}${priceMovePct.abs().toStringAsFixed(2)}%',
                            style: TextStyle(
                              color: primaryAccent,
                              fontSize: 12,
                              fontWeight: FontWeight.w900,
                              fontFamily: 'monospace',
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
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
                  if (log.previousPrice != null && log.previousPrice! > 0) ...[
                    const SizedBox(height: 3),
                    Row(
                      children: [
                        Text(
                          'Target: ${FormatUtils.formatPrice(log.previousPrice!, currencySymbol: currency, lang: "en")}',
                          style: TextStyle(
                            fontSize: 11,
                            fontFamily: 'monospace',
                            color: Colors.white.withValues(alpha: 0.6),
                          ),
                        ),
                        const SizedBox(width: 6),
                        const Icon(Icons.arrow_forward_rounded, size: 12, color: Colors.grey),
                        const SizedBox(width: 6),
                        Text(
                          'TRIGGER REACHED',
                          style: TextStyle(
                            fontSize: 9.5,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 0.6,
                            color: primaryAccent,
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),

            // 4. STRATEGY NOTE (if present)
            if (log.customNote != null && log.customNote!.trim().isNotEmpty)
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
                          fontSize: 11,
                          fontStyle: FontStyle.italic,
                          fontWeight: FontWeight.w600,
                          color: Colors.white.withValues(alpha: 0.9),
                        ),
                      ),
                    ),
                  ],
                ),
              ),

            // 5. STORE BADGES (Google Play & App Store) + TELEGRAM BOT
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color: const Color(0xFF1E293B).withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: Colors.white10),
              ),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      // Google Play Badge
                      Row(
                        children: [
                          Icon(Icons.play_arrow_rounded, size: 15, color: Colors.greenAccent[400]),
                          const SizedBox(width: 3),
                          const Text(
                            'Google Play',
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w800,
                              color: Colors.white,
                              letterSpacing: 0.2,
                            ),
                          ),
                        ],
                      ),

                      // App Store Badge
                      Row(
                        children: [
                          Icon(Icons.apple_rounded, size: 15, color: Colors.white.withValues(alpha: 0.9)),
                          const SizedBox(width: 3),
                          const Text(
                            'App Store',
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w800,
                              color: Colors.white,
                              letterSpacing: 0.2,
                            ),
                          ),
                        ],
                      ),

                      // Telegram Bot Badge
                      Row(
                        children: [
                          const Icon(Icons.send_rounded, size: 13, color: Color(0xFF38BDF8)),
                          const SizedBox(width: 4),
                          const Text(
                            '@alertsifnalampbot',
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w900,
                              color: Color(0xFF38BDF8),
                              letterSpacing: 0.2,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 5),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Verified Alert: ${DateFormat('yyyy-MM-dd HH:mm').format(log.timestamp.toUtc())} UTC',
                        style: TextStyle(
                          fontSize: 9,
                          fontFamily: 'monospace',
                          color: Colors.white.withValues(alpha: 0.5),
                        ),
                      ),
                      Text(
                        'Instant Alerts • Zero Delay',
                        style: TextStyle(
                          fontSize: 9,
                          fontWeight: FontWeight.bold,
                          color: primaryAccent.withValues(alpha: 0.8),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );

    if (repaintKey != null) {
      return RepaintBoundary(
        key: repaintKey,
        child: cardContent,
      );
    }
    return cardContent;
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

              // 1:1 Square Preview Card
              Center(
                child: SizedBox(
                  width: 320,
                  height: 320,
                  child: SocialAlertCard1x1(
                    log: log,
                    repaintKey: repaintKey,
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // Action Buttons: Share Image (Primary), Save Image & Copy Post Link
              Row(
                children: [
                  Expanded(
                    flex: 5,
                    child: ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF38BDF8),
                        foregroundColor: const Color(0xFF0F172A),
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      icon: const Icon(Icons.share_rounded, size: 17),
                      label: const Text(
                        'Share Image',
                        style: TextStyle(fontWeight: FontWeight.w900, fontSize: 13),
                      ),
                      onPressed: () async {
                        try {
                          final boundary = repaintKey.currentContext?.findRenderObject() as RenderRepaintBoundary?;
                          if (boundary == null) return;
                          final image = await boundary.toImage(pixelRatio: 3.0);
                          final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
                          if (byteData == null) return;
                          final bytes = byteData.buffer.asUint8List();

                          final dir = await getTemporaryDirectory();
                          final file = File('${dir.path}/social_alert_${log.uuid}.png');
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
                  const SizedBox(width: 8),
                  Expanded(
                    flex: 4,
                    child: ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF1E293B),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                          side: BorderSide(color: Colors.white.withValues(alpha: 0.15)),
                        ),
                      ),
                      icon: const Icon(Icons.download_rounded, size: 16),
                      label: const Text('Save PNG', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                      onPressed: () async {
                        try {
                          final boundary = repaintKey.currentContext?.findRenderObject() as RenderRepaintBoundary?;
                          if (boundary == null) return;
                          final image = await boundary.toImage(pixelRatio: 3.0);
                          final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
                          if (byteData == null) return;
                          final bytes = byteData.buffer.asUint8List();

                          final dir = await getApplicationDocumentsDirectory();
                          final file = File('${dir.path}/alert_${log.uuid}.png');
                          await file.writeAsBytes(bytes, flush: true);

                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text('✅ 1:1 Image saved to: ${file.path}'),
                                backgroundColor: const Color(0xFF10B981),
                                behavior: SnackBarBehavior.floating,
                              ),
                            );
                          }
                        } catch (e) {
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text('Error saving image: $e'),
                                backgroundColor: Colors.redAccent,
                              ),
                            );
                          }
                        }
                      },
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      );
    },
  );
}
