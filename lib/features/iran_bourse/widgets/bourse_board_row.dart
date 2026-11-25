import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_board.dart';
import '../theme/bourse_text.dart';
import '../utils/bourse_format.dart';

/// One symbol in the browse list: ticker, name, last price (Rial), change % and a small tag
/// that says when the price is not live (IB-16c).
class BourseBoardRow extends StatelessWidget {
  final BourseBoardItem item;
  final BourseSession session;
  final VoidCallback? onTap;
  final bool persianDigits;
  final int alertCount;

  const BourseBoardRow({
    super.key,
    required this.item,
    required this.session,
    this.onTap,
    this.persianDigits = false,
    this.alertCount = 0,
  });

  /// The small tag under the price, or null when the price is live and fresh.
  static String? tagFor(BourseBoardItem item, BourseSession session) {
    if (item.price == null) return null;
    if (!session.isLive) return BourseStrings.tagLastPrice;
    if (!item.traded) return BourseStrings.tagNotTradedToday;
    return null;
  }

  static IconData _iconForGroup(BourseGroup group) {
    switch (group) {
      case BourseGroup.stocks:
        return Icons.show_chart_rounded;
      case BourseGroup.funds:
        return Icons.pie_chart_rounded;
      case BourseGroup.bonds:
        return Icons.account_balance_rounded;
      case BourseGroup.rights:
        return Icons.receipt_long_rounded;
      case BourseGroup.commodities:
        return Icons.grain_rounded;
      case BourseGroup.derivatives:
        return Icons.swap_vert_rounded;
      case BourseGroup.other:
        return Icons.candlestick_chart_rounded;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final d = persianDigits;
    final subtitle = <String>[
      if (item.name.isNotEmpty && item.name != item.displayTicker) item.name,
      if (item.type != null) item.type!,
    ].join(' · ');
    final pct = item.changePct;
    final pctColor = (pct == null || pct == 0)
        ? BourseText.secondaryColor(context)
        : (pct > 0 ? AppTokens.positive : AppTokens.negative);
    final tag = tagFor(item, session);
    final queueLabel = item.traded ? item.queueLabel : null;
    final isBuyQueue = queueLabel != null && queueLabel.contains('خرید');

    return Material(
      color: Colors.transparent,
      child: InkWell(
        key: ValueKey('bourse_board_row_${item.id}'),
        onTap: onTap,
        borderRadius: BorderRadius.circular(BourseText.cardRadius),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: BourseText.cardColor(context),
            borderRadius: BorderRadius.circular(BourseText.cardRadius),
            border: Border.all(color: BourseText.borderColor(context)),
          ),
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: theme.colorScheme.primary.withValues(alpha: 0.12),
                  shape: BoxShape.circle,
                ),
                alignment: Alignment.center,
                child: Icon(
                  _iconForGroup(item.group),
                  size: 20,
                  color: theme.colorScheme.primary,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            item.displayTicker,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 13,
                              color: BourseText.primaryColor(context),
                            ),
                          ),
                        ),
                        if (queueLabel != null) ...[
                          const SizedBox(width: 6),
                          Container(
                            key: const Key('bourse_row_queue_badge'),
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: (isBuyQueue ? AppTokens.positive : AppTokens.negative)
                                  .withValues(alpha: 0.14),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(
                                color: (isBuyQueue ? AppTokens.positive : AppTokens.negative)
                                    .withValues(alpha: 0.4),
                              ),
                            ),
                            child: Text(
                              queueLabel,
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w700,
                                color: isBuyQueue ? AppTokens.positive : AppTokens.negative,
                              ),
                            ),
                          ),
                        ],
                        if (alertCount > 0) ...[
                          const SizedBox(width: 6),
                          Container(
                            key: const Key('bourse_row_alert_badge'),
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.primary.withValues(alpha: 0.14),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(
                                color: theme.colorScheme.primary.withValues(alpha: 0.35),
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.notifications_active_rounded,
                                  size: 11,
                                  color: BourseText.primaryColor(context),
                                ),
                                const SizedBox(width: 3),
                                Text(
                                  BourseStrings.rowAlertBadge(
                                    BourseFormat.number(alertCount, persianDigits: d),
                                  ),
                                  style: TextStyle(
                                    fontSize: 10,
                                    fontWeight: FontWeight.w700,
                                    color: BourseText.primaryColor(context),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ],
                    ),
                    if (subtitle.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 11,
                          color: BourseText.secondaryColor(context),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.end,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    BourseFormat.rial(item.price, persianDigits: d),
                    textDirection: TextDirection.ltr,
                    style: BourseText.rowPrice(context),
                  ),
                  const SizedBox(height: 3),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                    decoration: BoxDecoration(
                      color: pctColor.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      BourseFormat.signedPercent(pct, persianDigits: d),
                      textDirection: TextDirection.ltr,
                      style: TextStyle(color: pctColor, fontSize: 11, fontWeight: FontWeight.w700),
                    ),
                  ),
                  if (tag != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      tag,
                      key: const Key('bourse_row_tag'),
                      style: TextStyle(color: BourseText.mutedColor(context), fontSize: 10),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
