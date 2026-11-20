import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_quote.dart';
import '../theme/bourse_text.dart';
import '../utils/bourse_format.dart';
import 'bourse_state_badge.dart';

/// Detail card of one Bourse quote: price in Rial, change, limits, volume, NAV, queue, times.
///
/// Every price is Rial. Optional data (NAV, queue, labels) is hidden when the server has none.
class BourseQuoteCard extends StatelessWidget {
  final BourseQuote quote;
  final bool persianDigits;

  const BourseQuoteCard({super.key, required this.quote, this.persianDigits = false});

  Color _changeColor(BuildContext context, double? pct) {
    if (pct == null || pct == 0) return BourseText.secondaryColor(context);
    return pct > 0 ? AppTokens.positive : AppTokens.negative;
  }

  Widget _row(BuildContext context, String label, String value, {Key? key}) {
    return Padding(
      key: key,
      padding: const EdgeInsets.symmetric(vertical: AppTokens.space4),
      child: Row(
        children: [
          Expanded(
            child: Text(label, style: BourseText.secondary(context)),
          ),
          Text(value, style: BourseText.body(context)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final q = quote;
    final d = persianDigits;
    final title = q.ticker.isNotEmpty ? q.ticker : q.name;
    final queue = q.queueLabel;

    return Card(
      key: const Key('bourse_quote_card'),
      elevation: 0,
      margin: EdgeInsets.zero,
      color: BourseText.cardColor(context),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(BourseText.cardRadius),
        side: BorderSide(color: BourseText.borderColor(context)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppTokens.space16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, style: BourseText.header(context)),
                      if (q.name.isNotEmpty && q.name != title)
                        Text(q.name, style: BourseText.secondary(context)),
                    ],
                  ),
                ),
                BourseStateBadge(state: q.state),
              ],
            ),
            const SizedBox(height: AppTokens.space12),
            Text(
              BourseFormat.rial(q.hasPrice ? q.price : null, persianDigits: d),
              key: const Key('bourse_price'),
              textDirection: TextDirection.ltr,
              style: BourseText.price(context),
            ),
            const SizedBox(height: AppTokens.space4),
            Text(
              BourseFormat.signedPercent(q.changePct, persianDigits: d),
              key: const Key('bourse_change_pct'),
              textDirection: TextDirection.ltr,
              style: BourseText.body(context).copyWith(color: _changeColor(context, q.changePct)),
            ),
            const SizedBox(height: AppTokens.space8),
            Text(
              BourseStrings.stateDescription(q.state),
              key: const Key('bourse_state_description'),
              style: BourseText.secondary(context),
            ),
            const Divider(height: AppTokens.space24),
            _row(context, BourseStrings.prevClose, BourseFormat.rial(q.prevClose, persianDigits: d)),
            _row(context, BourseStrings.closePrice, BourseFormat.rial(q.close, persianDigits: d)),
            _row(context, BourseStrings.dayRange, BourseFormat.range(q.low, q.high, persianDigits: d)),
            _row(context, BourseStrings.upperLimit, BourseFormat.rial(q.upperLimit, persianDigits: d)),
            _row(context, BourseStrings.lowerLimit, BourseFormat.rial(q.lowerLimit, persianDigits: d)),
            _row(context, BourseStrings.volume, BourseFormat.number(q.volume, persianDigits: d)),
            if (q.nav != null)
              _row(context, BourseStrings.nav, BourseFormat.rial(q.nav, persianDigits: d),
                  key: const Key('bourse_row_nav')),
            if (queue != null)
              _row(context, BourseStrings.queue, queue, key: const Key('bourse_row_queue')),
            _row(context, BourseStrings.lastTradeTime,
                q.lastTradeTime == null
                    ? BourseFormat.dash
                    : (d ? BourseFormat.toPersianDigits(q.lastTradeTime!) : q.lastTradeTime!)),
            _row(context, BourseStrings.updatedAt, BourseFormat.tehranTime(q.asOf, persianDigits: d)),
            if (q.marketLabel != null)
              _row(context, BourseStrings.market, q.marketLabel!, key: const Key('bourse_row_market')),
            if (q.typeLabel != null)
              _row(context, BourseStrings.type, q.typeLabel!, key: const Key('bourse_row_type')),
            if (q.sector != null)
              _row(context, BourseStrings.sector, q.sector!, key: const Key('bourse_row_sector')),
            const SizedBox(height: AppTokens.space8),
            Text(BourseStrings.unitNote, style: BourseText.caption(context)),
          ],
        ),
      ),
    );
  }
}
