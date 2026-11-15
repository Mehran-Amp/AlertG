import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_quote.dart';
import '../utils/bourse_format.dart';
import 'bourse_state_badge.dart';

/// Detail card of one Bourse quote: price in Rial, change, limits, volume, NAV, queue, times.
///
/// Every price is Rial. Optional data (NAV, queue, labels) is hidden when the server has none.
class BourseQuoteCard extends StatelessWidget {
  final BourseQuote quote;
  final bool persianDigits;

  const BourseQuoteCard({super.key, required this.quote, this.persianDigits = false});

  Color _changeColor(double? pct) {
    if (pct == null || pct == 0) return AppTokens.textSecondary;
    return pct > 0 ? AppTokens.positive : AppTokens.negative;
  }

  Widget _row(String label, String value, {Key? key}) {
    return Padding(
      key: key,
      padding: const EdgeInsets.symmetric(vertical: AppTokens.space4),
      child: Row(
        children: [
          Expanded(
            child: Text(label, style: AppTokens.bodySecondary),
          ),
          Text(value, style: AppTokens.body),
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
                      Text(title, style: AppTokens.sectionHeader),
                      if (q.name.isNotEmpty && q.name != title)
                        Text(q.name, style: AppTokens.bodySecondary),
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
              style: AppTokens.monoNumbers.copyWith(fontSize: 24),
            ),
            const SizedBox(height: AppTokens.space4),
            Text(
              BourseFormat.signedPercent(q.changePct, persianDigits: d),
              key: const Key('bourse_change_pct'),
              textDirection: TextDirection.ltr,
              style: AppTokens.body.copyWith(color: _changeColor(q.changePct)),
            ),
            const SizedBox(height: AppTokens.space8),
            Text(
              BourseStrings.stateDescription(q.state),
              key: const Key('bourse_state_description'),
              style: AppTokens.bodySecondary,
            ),
            const Divider(height: AppTokens.space24),
            _row(BourseStrings.prevClose, BourseFormat.rial(q.prevClose, persianDigits: d)),
            _row(BourseStrings.closePrice, BourseFormat.rial(q.close, persianDigits: d)),
            _row(BourseStrings.dayRange, BourseFormat.range(q.low, q.high, persianDigits: d)),
            _row(BourseStrings.upperLimit, BourseFormat.rial(q.upperLimit, persianDigits: d)),
            _row(BourseStrings.lowerLimit, BourseFormat.rial(q.lowerLimit, persianDigits: d)),
            _row(BourseStrings.volume, BourseFormat.number(q.volume, persianDigits: d)),
            if (q.nav != null)
              _row(BourseStrings.nav, BourseFormat.rial(q.nav, persianDigits: d),
                  key: const Key('bourse_row_nav')),
            if (queue != null)
              _row(BourseStrings.queue, queue, key: const Key('bourse_row_queue')),
            _row(BourseStrings.lastTradeTime,
                q.lastTradeTime == null
                    ? BourseFormat.dash
                    : (d ? BourseFormat.toPersianDigits(q.lastTradeTime!) : q.lastTradeTime!)),
            _row(BourseStrings.updatedAt, BourseFormat.tehranTime(q.asOf, persianDigits: d)),
            if (q.marketLabel != null)
              _row(BourseStrings.market, q.marketLabel!, key: const Key('bourse_row_market')),
            if (q.typeLabel != null)
              _row(BourseStrings.type, q.typeLabel!, key: const Key('bourse_row_type')),
            if (q.sector != null)
              _row(BourseStrings.sector, q.sector!, key: const Key('bourse_row_sector')),
            const SizedBox(height: AppTokens.space8),
            Text(BourseStrings.unitNote, style: AppTokens.caption),
          ],
        ),
      ),
    );
  }
}
