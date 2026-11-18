import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_quote.dart';
import '../theme/bourse_text.dart';

/// Small coloured label for a quote state: live, closed, no trade today, stale, unknown.
class BourseStateBadge extends StatelessWidget {
  final BourseState state;

  const BourseStateBadge({super.key, required this.state});

  static Color colorOf(BourseState state) {
    switch (state) {
      case BourseState.live:
        return AppTokens.positive;
      case BourseState.stale:
        return AppTokens.warning;
      case BourseState.closed:
      case BourseState.noTradeToday:
      case BourseState.unknown:
        return AppTokens.textSecondary;
    }
  }

  /// Like [colorOf], but the neutral states follow the app theme (visible on light and dark).
  static Color colorFor(BuildContext context, BourseState state) {
    switch (state) {
      case BourseState.closed:
      case BourseState.noTradeToday:
      case BourseState.unknown:
        return BourseText.secondaryColor(context);
      case BourseState.stale:
        return BourseText.warningColor(context);
      case BourseState.live:
        return colorOf(state);
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = colorFor(context, state);
    return Container(
      key: const Key('bourse_state_badge'),
      padding: const EdgeInsets.symmetric(
        horizontal: AppTokens.space8,
        vertical: AppTokens.space4,
      ),
      decoration: BoxDecoration(
        color: color.withAlpha(38),
        borderRadius: AppTokens.borderFull,
        border: Border.all(color: color.withAlpha(153)),
      ),
      child: Text(
        BourseStrings.stateLabel(state),
        style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600),
      ),
    );
  }
}
