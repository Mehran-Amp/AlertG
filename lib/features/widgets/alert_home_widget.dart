import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../core/services/native_widget_sync_service.dart';
import '../alert_engine/models/alert_rule.dart';
import '../alert_engine/repositories/json_alert_rule_repository.dart';

/// Obsidian Dark Luxury Home Screen Widget preview & in-app card for Alarmer Pro.
/// Matches the Native Android AppWidget 1:1:
/// - 2-Line Rich Financial Card per alert (Readable Persian/English Name + Live Price on Line 1,
///   Exchange/Source + Target Condition + Status Pill Badge on Line 2)
/// - Left Vertical Status Accent Strip & Bottom Target Proximity Micro-Bar
/// - Smart Live Telemetry Header with Quick Add (+) and Silent Refresh (⟳)
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
    final allRules = repository.allRules;
    final activeCount =
        allRules.where((r) => r.isActive && !r.isTriggered).length;
    final hitCount =
        allRules.where((r) => r.isTriggered || !r.isActive).length;
    final timeNow = DateFormat('HH:mm').format(DateTime.now());
    final subtitleText = hitCount > 0
        ? '$activeCount فعال • $hitCount زده‌شده • $timeNow'
        : '$activeCount آلارم فعال • بروزرسانی $timeNow';

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF080D1A),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: const Color(0xFF1E293B),
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.4),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Smart Live Telemetry Header
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: const Color(0xFF10B981).withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: const Color(0xFF10B981).withValues(alpha: 0.35),
                    width: 0.8,
                  ),
                ),
                child: const Icon(
                  Icons.bolt_rounded,
                  color: Color(0xFF10B981),
                  size: 16,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Text(
                          'Alarmer Pro',
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w800,
                            color: Color(0xFFF8FAFC),
                            letterSpacing: 0.2,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 5,
                            vertical: 1.5,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFF062E22),
                            borderRadius: BorderRadius.circular(5),
                          ),
                          child: const Text(
                            '● LIVE',
                            style: TextStyle(
                              fontSize: 8.5,
                              fontWeight: FontWeight.w800,
                              color: Color(0xFF10B981),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 1.5),
                    Text(
                      subtitleText,
                      style: const TextStyle(
                        fontSize: 9.5,
                        color: Color(0xFF94A3B8),
                      ),
                    ),
                  ],
                ),
              ),
              if (onAddNew != null) ...[
                Material(
                  color: const Color(0xFF111E34),
                  borderRadius: BorderRadius.circular(9),
                  child: InkWell(
                    onTap: onAddNew,
                    borderRadius: BorderRadius.circular(9),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 5,
                      ),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(9),
                        border: Border.all(
                          color: const Color(0xFF38BDF8),
                          width: 0.9,
                        ),
                      ),
                      child: const Icon(
                        Icons.add_rounded,
                        size: 14,
                        color: Color(0xFF38BDF8),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 6),
              ],
              Material(
                color: const Color(0xFF0F2922),
                borderRadius: BorderRadius.circular(9),
                child: InkWell(
                  onTap: onRefresh,
                  borderRadius: BorderRadius.circular(9),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 9,
                      vertical: 5,
                    ),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(9),
                      border: Border.all(
                        color: const Color(0xFF10B981),
                        width: 0.9,
                      ),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.refresh_rounded,
                          size: 13,
                          color: Color(0xFF10B981),
                        ),
                        SizedBox(width: 4),
                        Text(
                          'بروزرسانی',
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF10B981),
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
          const Divider(height: 1, color: Color(0xFF1E293B)),
          const SizedBox(height: 7),

          if (allRules.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 16),
              child: Center(
                child: Text(
                  'هیچ آلارم فعالی ثبت نشده است',
                  style: TextStyle(
                    fontSize: 11,
                    color: Color(0xFF94A3B8),
                  ),
                ),
              ),
            )
          else
            ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: isCompact
                  ? allRules.take(3).length
                  : allRules.take(5).length,
              separatorBuilder: (_, __) => const SizedBox(height: 6),
              itemBuilder: (context, index) {
                final rule = allRules[index];
                return _buildTwoLineRichAlertCard(rule);
              },
            ),

          if (allRules.length > (isCompact ? 3 : 5)) ...[
            const SizedBox(height: 6),
            Center(
              child: Text(
                '+ ${allRules.length - (isCompact ? 3 : 5)} آلارم دیگر در پس‌زمینه فعال است',
                style: const TextStyle(
                  fontSize: 9.5,
                  color: Color(0xFF64748B),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildTwoLineRichAlertCard(AlertRule rule) {
    final vm = NativeWidgetSyncService.computeRowViewModel(rule);

    final Color accentColor;
    final Color badgeBgColor;
    final Color badgeBorderColor;
    final Color badgeTextColor;

    if (vm.isDone || vm.isNearTarget) {
      accentColor = const Color(0xFFF59E0B);
      badgeBgColor = const Color(0xFF332409);
      badgeBorderColor = const Color(0xFFF59E0B);
      badgeTextColor = const Color(0xFFFBBF24);
    } else if (vm.isPositive) {
      accentColor = const Color(0xFF10B981);
      badgeBgColor = const Color(0xFF062E22);
      badgeBorderColor = const Color(0xFF10B981);
      badgeTextColor = const Color(0xFF10B981);
    } else {
      accentColor = const Color(0xFFF43F5E);
      badgeBgColor = const Color(0xFF311019);
      badgeBorderColor = const Color(0xFFF43F5E);
      badgeTextColor = const Color(0xFFF43F5E);
    }

    return Container(
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 7),
      decoration: BoxDecoration(
        color: vm.isDone ? const Color(0xFF18160F) : const Color(0xFF111827),
        borderRadius: BorderRadius.circular(11),
        border: Border.all(
          color: vm.isDone ? const Color(0xFFB45309) : const Color(0xFF1E293B),
          width: 1,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              // Left Vertical Accent Bar
              Container(
                width: 3.5,
                height: 32,
                decoration: BoxDecoration(
                  color: accentColor,
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
              const SizedBox(width: 8),
              // 2-Line Financial Details
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Line 1: Readable Symbol Title + Live Price
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            vm.symbolTitle,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 12.5,
                              fontWeight: FontWeight.w800,
                              color: vm.isDone
                                  ? const Color(0xFFFBBF24)
                                  : const Color(0xFFF8FAFC),
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          vm.formattedPrice,
                          style: const TextStyle(
                            fontSize: 12.5,
                            fontWeight: FontWeight.w800,
                            fontFamily: 'monospace',
                            color: Color(0xFFF8FAFC),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 3.5),
                    // Line 2: Exchange & Target Subtitle + Status Pill Badge
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            vm.subtitle,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 10,
                              color: Color(0xFF94A3B8),
                            ),
                          ),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 7,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: badgeBgColor,
                            borderRadius: BorderRadius.circular(7),
                            border: Border.all(
                              color: badgeBorderColor,
                              width: 0.8,
                            ),
                          ),
                          child: Text(
                            vm.badgeText,
                            style: TextStyle(
                              fontSize: 9.5,
                              fontWeight: FontWeight.bold,
                              color: badgeTextColor,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          // Target Proximity Micro-Bar
          ClipRRect(
            borderRadius: BorderRadius.circular(2),
            child: LinearProgressIndicator(
              value: (vm.proximity.clamp(0, 100)) / 100.0,
              minHeight: 2.5,
              backgroundColor: const Color(0xFF1E293B),
              valueColor: AlwaysStoppedAnimation<Color>(accentColor),
            ),
          ),
        ],
      ),
    );
  }
}
