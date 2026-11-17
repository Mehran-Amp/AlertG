import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_board.dart';
import '../utils/bourse_format.dart';

/// One symbol in the browse list: ticker, name, last price (Rial), change % and a small tag
/// that says when the price is not live (IB-16c).
class BourseBoardRow extends StatelessWidget {
  final BourseBoardItem item;
  final BourseSession session;
  final VoidCallback? onTap;
  final bool persianDigits;

  const BourseBoardRow({
    super.key,
    required this.item,
    required this.session,
    this.onTap,
    this.persianDigits = false,
  });

  /// The small tag under the price, or null when the price is live and fresh.
  static String? tagFor(BourseBoardItem item, BourseSession session) {
    if (item.price == null) return null;
    if (!session.isLive) return BourseStrings.tagLastPrice;
    if (!item.traded) return BourseStrings.tagNotTradedToday;
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final d = persianDigits;
    final subtitle = <String>[
      if (item.name.isNotEmpty && item.name != item.displayTicker) item.name,
      if (item.type != null) item.type!,
    ].join(' · ');
    final pct = item.changePct;
    final pctColor = (pct == null || pct == 0)
        ? AppTokens.textSecondary
        : (pct > 0 ? AppTokens.positive : AppTokens.negative);
    final tag = tagFor(item, session);

    return ListTile(
      key: ValueKey('bourse_board_row_${item.id}'),
      title: Text(item.displayTicker, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: subtitle.isEmpty ? null : Text(subtitle, maxLines: 1, overflow: TextOverflow.ellipsis),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(BourseFormat.rial(item.price, persianDigits: d), textDirection: TextDirection.ltr),
          Text(
            BourseFormat.signedPercent(pct, persianDigits: d),
            textDirection: TextDirection.ltr,
            style: TextStyle(color: pctColor, fontSize: 12),
          ),
          if (tag != null)
            Text(
              tag,
              key: const Key('bourse_row_tag'),
              style: const TextStyle(color: AppTokens.textMuted, fontSize: 10),
            ),
        ],
      ),
      onTap: onTap,
    );
  }
}
