import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_board.dart';
import '../theme/bourse_text.dart';

/// Tells the user that the prices on screen are the last known ones, not live (IB-16c).
///
/// Shows nothing while the market is open and the feed is fresh. When the market is closed it
/// also reminds that alerts can still be created and start working when the market opens.
class BourseSessionBanner extends StatelessWidget {
  final BourseSession session;

  /// True when the server's market data is old, whatever the schedule says.
  final bool stale;

  const BourseSessionBanner({super.key, required this.session, this.stale = false});

  /// The banner text, or null when everything is live.
  static String? messageFor(BourseSession session, {bool stale = false}) {
    if (session == BourseSession.stale || (stale && session != BourseSession.closed)) {
      return BourseStrings.bannerStale;
    }
    switch (session) {
      case BourseSession.open:
        return null;
      case BourseSession.closed:
        return BourseStrings.bannerClosed;
      case BourseSession.stale:
        return BourseStrings.bannerStale;
      case BourseSession.unknown:
        return BourseStrings.bannerUnknown;
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = messageFor(session, stale: stale);
    if (text == null) return const SizedBox.shrink();
    return Container(
      key: const Key('bourse_session_banner'),
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(AppTokens.space16, 0, AppTokens.space16, AppTokens.space8),
      padding: const EdgeInsets.all(AppTokens.space12),
      decoration: BoxDecoration(
        color: AppTokens.warningSubtle,
        borderRadius: AppTokens.borderSmall,
        border: Border.all(color: AppTokens.warning.withAlpha(120)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline, size: 18, color: AppTokens.warning),
          const SizedBox(width: AppTokens.space8),
          Expanded(child: Text(text, style: BourseText.secondary(context))),
        ],
      ),
    );
  }
}
