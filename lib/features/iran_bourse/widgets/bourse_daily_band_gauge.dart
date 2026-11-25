import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_quote.dart';
import '../theme/bourse_text.dart';
import '../utils/bourse_format.dart';

/// Compact horizontal visual gauge of today's permissible Tehran Bourse price band
/// (`lowerLimit` -> `upperLimit`), highlighting:
/// - today's traded `[low, high]` segment
/// - the live `lastPrice` dot
/// - live target marker pin(s) as the user types a single or two-way price target.
class BourseDailyBandGauge extends StatelessWidget {
  final BourseQuote quote;
  final double? targetPrice;
  final double? upperTargetPrice;
  final double? lowerTargetPrice;
  final bool persianDigits;

  const BourseDailyBandGauge({
    super.key,
    required this.quote,
    this.targetPrice,
    this.upperTargetPrice,
    this.lowerTargetPrice,
    this.persianDigits = false,
  });

  double? _ratio(num? value, double lo, double hi) {
    if (value == null) return null;
    final span = hi - lo;
    if (span <= 0) return null;
    return ((value.toDouble() - lo) / span).clamp(0.0, 1.0);
  }

  @override
  Widget build(BuildContext context) {
    final lo = quote.lowerLimit?.toDouble();
    final hi = quote.upperLimit?.toDouble();
    if (lo == null || hi == null || lo <= 0 || hi <= lo) {
      return const SizedBox.shrink();
    }

    final accent = BourseText.accentColor(context);
    final trackBg = BourseText.borderColor(context);
    final lastRatio = _ratio(quote.price, lo, hi);
    final lowRatio = _ratio(quote.low, lo, hi);
    final highRatio = _ratio(quote.high, lo, hi);
    final targetRatio = _ratio(targetPrice, lo, hi);
    final upperRatio = _ratio(upperTargetPrice, lo, hi);
    final lowerRatio = _ratio(lowerTargetPrice, lo, hi);

    final Color lastColor;
    final pct = quote.changePct;
    if (pct != null && pct > 0) {
      lastColor = AppTokens.positive;
    } else if (pct != null && pct < 0) {
      lastColor = AppTokens.negative;
    } else {
      lastColor = accent;
    }

    return Column(
      key: const Key('bourse_form_daily_band'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        // LTR number line: floor (red) on the left, ceiling (green) on the right.
        Directionality(
          textDirection: TextDirection.ltr,
          child: SizedBox(
            height: 16,
            child: LayoutBuilder(
              builder: (context, constraints) {
                final w = constraints.maxWidth;
                if (w <= 0) return const SizedBox.shrink();

                double xOf(double ratio, double markerSize) {
                  return (ratio * (w - markerSize)).clamp(0.0, w - markerSize);
                }

                return Stack(
                  clipBehavior: Clip.none,
                  alignment: Alignment.centerLeft,
                  children: [
                    // Base permissible band track
                    Positioned(
                      left: 0,
                      right: 0,
                      child: Container(
                        height: 5,
                        decoration: BoxDecoration(
                          color: trackBg,
                          borderRadius: BorderRadius.circular(999),
                        ),
                      ),
                    ),
                    // Subtle green/red end caps
                    Positioned(
                      left: 0,
                      child: Container(
                        width: 4,
                        height: 5,
                        decoration: BoxDecoration(
                          color: AppTokens.negative.withValues(alpha: 0.7),
                          borderRadius: const BorderRadius.horizontal(left: Radius.circular(999)),
                        ),
                      ),
                    ),
                    Positioned(
                      right: 0,
                      child: Container(
                        width: 4,
                        height: 5,
                        decoration: BoxDecoration(
                          color: AppTokens.positive.withValues(alpha: 0.7),
                          borderRadius: const BorderRadius.horizontal(right: Radius.circular(999)),
                        ),
                      ),
                    ),
                    // Today's traded [low .. high] segment
                    if (lowRatio != null && highRatio != null && highRatio >= lowRatio)
                      Positioned(
                        left: lowRatio * w,
                        width: ((highRatio - lowRatio) * w).clamp(4.0, w),
                        child: Container(
                          height: 5,
                          decoration: BoxDecoration(
                            color: accent.withValues(alpha: 0.42),
                            borderRadius: BorderRadius.circular(999),
                          ),
                        ),
                      ),
                    // Live last price dot
                    if (lastRatio != null)
                      Positioned(
                        left: xOf(lastRatio, 10),
                        child: Container(
                          key: const Key('bourse_band_last_marker'),
                          width: 10,
                          height: 10,
                          decoration: BoxDecoration(
                            color: lastColor,
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: Theme.of(context).colorScheme.surface,
                              width: 1.5,
                            ),
                          ),
                        ),
                      ),
                    // Single target pin
                    if (targetRatio != null)
                      Positioned(
                        left: xOf(targetRatio, 12),
                        child: Container(
                          key: const Key('bourse_band_target_marker'),
                          width: 12,
                          height: 12,
                          decoration: BoxDecoration(
                            color: accent,
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: Theme.of(context).colorScheme.surface,
                              width: 2,
                            ),
                          ),
                        ),
                      ),
                    // Two-way upper target pin
                    if (upperRatio != null)
                      Positioned(
                        left: xOf(upperRatio, 12),
                        child: Container(
                          key: const Key('bourse_band_upper_marker'),
                          width: 12,
                          height: 12,
                          decoration: BoxDecoration(
                            color: AppTokens.positive,
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: Theme.of(context).colorScheme.surface,
                              width: 2,
                            ),
                          ),
                        ),
                      ),
                    // Two-way lower target pin
                    if (lowerRatio != null)
                      Positioned(
                        left: xOf(lowerRatio, 12),
                        child: Container(
                          key: const Key('bourse_band_lower_marker'),
                          width: 12,
                          height: 12,
                          decoration: BoxDecoration(
                            color: AppTokens.negative,
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: Theme.of(context).colorScheme.surface,
                              width: 2,
                            ),
                          ),
                        ),
                      ),
                  ],
                );
              },
            ),
          ),
        ),
        const SizedBox(height: 2),
        // Band limits captions (LTR aligned with track ends)
        Directionality(
          textDirection: TextDirection.ltr,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '${BourseFormat.number(lo, persianDigits: persianDigits)} ${BourseStrings.bandFloorShort}',
                style: const TextStyle(
                  fontSize: 10.5,
                  fontWeight: FontWeight.w600,
                  color: AppTokens.negative,
                ),
              ),
              Text(
                '${BourseStrings.bandCeilShort} ${BourseFormat.number(hi, persianDigits: persianDigits)}',
                style: const TextStyle(
                  fontSize: 10.5,
                  fontWeight: FontWeight.w600,
                  color: AppTokens.positive,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
