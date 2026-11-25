import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_quote.dart';
import '../theme/bourse_text.dart';
import '../utils/bourse_format.dart';

/// Compact mobile-first market snapshot embedded directly inside the alert workspace.
///
/// Features:
/// - Compact metric tiles (`پایانی`, `دیروز`, `بازه امروز`, `حجم امروز`, plus ETF `NAV` + bubble %).
/// - Top-of-book order strip (`سرخط خرید و فروش`: `best_bid` / `best_ask`) when provided.
/// - Tap-to-fill: tapping any price cell (close, prevClose, NAV, bestBid, bestAsk) populates
///   the alert target price directly via [onFillPrice].
/// - Collapsible «جزئیات بیشتر نماد» section (collapsed by default) keeping the screen uncluttered.
class BourseQuickBoard extends StatefulWidget {
  final BourseQuote quote;
  final ValueChanged<num>? onFillPrice;
  final bool persianDigits;

  const BourseQuickBoard({
    super.key,
    required this.quote,
    this.onFillPrice,
    this.persianDigits = false,
  });

  @override
  State<BourseQuickBoard> createState() => _BourseQuickBoardState();
}

class _BourseQuickBoardState extends State<BourseQuickBoard> {
  bool _expanded = false;

  bool get _hasOrderBook => widget.quote.bestBid != null || widget.quote.bestAsk != null;

  bool get _hasNav => widget.quote.nav != null && widget.quote.nav! > 0;

  bool get _hasSecondaryDetails {
    final q = widget.quote;
    return (q.lastTradeTime != null && q.lastTradeTime!.isNotEmpty) ||
        q.asOf != null ||
        (q.marketLabel != null && q.marketLabel!.isNotEmpty) ||
        (q.typeLabel != null && q.typeLabel!.isNotEmpty) ||
        (q.sector != null && q.sector!.isNotEmpty) ||
        (q.low != null && q.high != null) ||
        (q.volume != null && q.volume! > 0) ||
        _hasNav;
  }

  List<_MetricTileData> _buildMetrics() {
    final q = widget.quote;
    final d = widget.persianDigits;
    final items = <_MetricTileData>[];

    if (q.close != null && q.close! > 0) {
      final closePct = q.closeChangePct;
      items.add(_MetricTileData(
        key: const Key('bourse_quick_close'),
        label: BourseStrings.closeShort,
        value: BourseFormat.number(q.close, persianDigits: d),
        subLabel: closePct != null ? BourseFormat.signedPercent(closePct, persianDigits: d) : null,
        subColor: closePct == null
            ? null
            : (closePct > 0 ? AppTokens.positive : (closePct < 0 ? AppTokens.negative : null)),
        tapPrice: q.close,
      ));
    }

    if (q.prevClose != null && q.prevClose! > 0) {
      items.add(_MetricTileData(
        key: const Key('bourse_quick_prev_close'),
        label: BourseStrings.prevCloseShort,
        value: BourseFormat.number(q.prevClose, persianDigits: d),
        tapPrice: q.prevClose,
      ));
    }

    if (q.volume != null && q.volume! > 0) {
      items.add(_MetricTileData(
        key: const Key('bourse_quick_volume'),
        label: BourseStrings.volumeShort,
        value: BourseFormat.compactVolume(q.volume, persianDigits: d),
      ));
    }

    if (_hasNav) {
      final bubble = q.navBubblePct;
      // Positive bubble = trading above NAV (premium/expensive -> crimson);
      // Negative bubble = trading below NAV (discount -> emerald).
      final Color? bubbleColor = bubble == null
          ? null
          : (bubble > 0.05 ? AppTokens.negative : (bubble < -0.05 ? AppTokens.positive : null));
      items.add(_MetricTileData(
        key: const Key('bourse_quick_nav'),
        label: BourseStrings.navShort,
        value: BourseFormat.number(q.nav, persianDigits: d),
        subLabel: bubble != null
            ? BourseStrings.navBubble(BourseFormat.signedPercent(bubble, persianDigits: d))
            : null,
        subColor: bubbleColor,
        tapPrice: q.nav,
      ));
    }

    return items;
  }

  Widget _buildMetricTile(BuildContext context, _MetricTileData item) {
    final theme = Theme.of(context);
    final tappable = item.tapPrice != null && widget.onFillPrice != null;
    final accent = BourseText.accentColor(context);

    final content = Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: theme.scaffoldBackgroundColor,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: tappable ? accent.withValues(alpha: 0.22) : BourseText.borderColor(context),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  item.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: BourseText.caption(context).copyWith(fontSize: 10.5),
                ),
              ),
              if (tappable)
                Icon(Icons.touch_app_rounded, size: 11, color: accent.withValues(alpha: 0.75)),
            ],
          ),
          const SizedBox(height: 2),
          Text(
            item.value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textDirection: TextDirection.ltr,
            style: TextStyle(
              fontFamily: 'monospace',
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: BourseText.primaryColor(context),
            ),
          ),
          if (item.subLabel != null)
            Text(
              item.subLabel!,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textDirection: TextDirection.ltr,
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w600,
                color: item.subColor ?? BourseText.secondaryColor(context),
              ),
            ),
        ],
      ),
    );

    if (!tappable) {
      return KeyedSubtree(key: item.key, child: content);
    }
    return InkWell(
      key: item.key,
      borderRadius: BorderRadius.circular(10),
      onTap: () => widget.onFillPrice!(item.tapPrice!),
      child: content,
    );
  }

  Widget _buildOrderSide(
    BuildContext context, {
    required Key key,
    required String title,
    required String emptyLabel,
    required BourseOrderLevel? level,
    required Color tone,
  }) {
    final d = widget.persianDigits;
    final tappable = level != null && widget.onFillPrice != null;

    final box = Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: tone.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: tone),
                ),
              ),
              if (tappable) Icon(Icons.touch_app_rounded, size: 12, color: tone),
            ],
          ),
          const SizedBox(height: 2),
          if (level != null) ...[
            Text(
              BourseFormat.number(level.price, persianDigits: d),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textDirection: TextDirection.ltr,
              style: TextStyle(
                fontFamily: 'monospace',
                fontSize: 13,
                fontWeight: FontWeight.bold,
                color: tone,
              ),
            ),
            const SizedBox(height: 1),
            Text(
              level.orders != null && level.orders! > 0
                  ? '${BourseFormat.compactVolume(level.volume, persianDigits: d)} · ${BourseStrings.ordersCount(BourseFormat.number(level.orders, persianDigits: d))}'
                  : BourseFormat.compactVolume(level.volume, persianDigits: d),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: BourseText.caption(context).copyWith(fontSize: 10),
            ),
          ] else
            Text(
              emptyLabel,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: BourseText.caption(context).copyWith(fontSize: 11),
            ),
        ],
      ),
    );

    if (!tappable) return KeyedSubtree(key: key, child: box);
    return InkWell(
      key: key,
      borderRadius: BorderRadius.circular(10),
      onTap: () => widget.onFillPrice!(level.price),
      child: box,
    );
  }

  Widget _detailRow(BuildContext context, String label, String value, {bool ltr = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 5,
            child: Text(label, style: BourseText.caption(context).copyWith(fontSize: 11.5)),
          ),
          Expanded(
            flex: 6,
            child: Text(
              value,
              textAlign: TextAlign.end,
              textDirection: ltr ? TextDirection.ltr : null,
              style: BourseText.body(context).copyWith(
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildExpandedDetails(BuildContext context) {
    final q = widget.quote;
    final d = widget.persianDigits;
    final dayRange = BourseFormat.range(q.low, q.high, persianDigits: d);
    final updatedAt = BourseFormat.tehranTime(q.asOf, persianDigits: d);

    return Padding(
      key: const Key('bourse_quick_board_details'),
      padding: const EdgeInsets.only(top: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Divider(height: 1, color: BourseText.borderColor(context)),
          const SizedBox(height: 6),
          if (dayRange != BourseFormat.dash)
            _detailRow(context, BourseStrings.dayRange, '$dayRange ${BourseFormat.rialWord}'),
          if (q.volume != null && q.volume! > 0)
            _detailRow(context, BourseStrings.volume, BourseFormat.number(q.volume, persianDigits: d), ltr: true),
          if (_hasNav)
            _detailRow(context, BourseStrings.nav, BourseFormat.rial(q.nav, persianDigits: d)),
          if (q.lastTradeTime != null && q.lastTradeTime!.isNotEmpty)
            _detailRow(
              context,
              BourseStrings.lastTradeTime,
              d ? BourseFormat.toPersianDigits(q.lastTradeTime!) : q.lastTradeTime!,
              ltr: true,
            ),
          if (updatedAt != BourseFormat.dash)
            _detailRow(context, BourseStrings.updatedAt, updatedAt, ltr: true),
          if (q.marketLabel != null && q.marketLabel!.isNotEmpty)
            _detailRow(context, BourseStrings.market, q.marketLabel!),
          if (q.typeLabel != null && q.typeLabel!.isNotEmpty)
            _detailRow(context, BourseStrings.type, q.typeLabel!),
          if (q.sector != null && q.sector!.isNotEmpty)
            _detailRow(context, BourseStrings.sector, q.sector!),
          const SizedBox(height: 4),
          Text(BourseStrings.unitNote, style: BourseText.caption(context).copyWith(fontSize: 10.5)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final metrics = _buildMetrics();
    final hasOrderBook = _hasOrderBook;
    final hasSecondary = _hasSecondaryDetails;
    if (metrics.isEmpty && !hasOrderBook && !hasSecondary) {
      return const SizedBox.shrink();
    }

    final hasTappable = widget.onFillPrice != null &&
        (hasOrderBook || metrics.any((m) => m.tapPrice != null));

    return Material(
      key: const Key('bourse_quick_board'),
      color: BourseText.cardColor(context),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(BourseText.cardRadius),
        side: BorderSide(color: BourseText.borderColor(context)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            // Single compact horizontal strip of up to 4 key metrics (fits cleanly on 1 row!)
            if (metrics.isNotEmpty)
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (int i = 0; i < metrics.length; i++) ...[
                    if (i > 0) const SizedBox(width: 6),
                    Expanded(child: _buildMetricTile(context, metrics[i])),
                  ],
                ],
              ),

            // Top-of-book Buy / Sell strip
            if (hasOrderBook) ...[
              if (metrics.isNotEmpty) const SizedBox(height: 8),
              Row(
                key: const Key('bourse_quick_order_book'),
                children: [
                  Expanded(
                    child: _buildOrderSide(
                      context,
                      key: const Key('bourse_quick_best_bid'),
                      title: BourseStrings.bestBidLabel,
                      emptyLabel: BourseStrings.noBuyer,
                      level: widget.quote.bestBid,
                      tone: AppTokens.positive,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _buildOrderSide(
                      context,
                      key: const Key('bourse_quick_best_ask'),
                      title: BourseStrings.bestAskLabel,
                      emptyLabel: BourseStrings.noSeller,
                      level: widget.quote.bestAsk,
                      tone: AppTokens.negative,
                    ),
                  ),
                ],
              ),
            ],

            // Compact footer row: tap-to-fill hint + expandable "more details" toggle
            if (hasTappable || hasSecondary) ...[
              const SizedBox(height: 6),
              Row(
                children: [
                  if (hasTappable)
                    Expanded(
                      child: Text(
                        BourseStrings.tapToFillHint,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: BourseText.caption(context).copyWith(fontSize: 10),
                      ),
                    )
                  else
                    const Spacer(),
                  if (hasSecondary)
                    InkWell(
                      key: const Key('bourse_quick_board_more_toggle'),
                      borderRadius: BorderRadius.circular(8),
                      onTap: () => setState(() => _expanded = !_expanded),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              _expanded ? BourseStrings.lessDetails : BourseStrings.moreDetails,
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                                color: BourseText.accentColor(context),
                              ),
                            ),
                            const SizedBox(width: 2),
                            Icon(
                              _expanded ? Icons.keyboard_arrow_up_rounded : Icons.keyboard_arrow_down_rounded,
                              size: 16,
                              color: BourseText.accentColor(context),
                            ),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
            ],

            if (_expanded && hasSecondary) _buildExpandedDetails(context),
          ],
        ),
      ),
    );
  }
}

class _MetricTileData {
  final Key key;
  final String label;
  final String value;
  final String? subLabel;
  final Color? subColor;
  final num? tapPrice;

  const _MetricTileData({
    required this.key,
    required this.label,
    required this.value,
    this.subLabel,
    this.subColor,
    this.tapPrice,
  });
}
