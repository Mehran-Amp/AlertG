import 'dart:async';
import 'package:flutter/material.dart';
import '../../../core/constants/strings.dart';
import '../../../core/theme/tokens.dart';

/// Dedicated, self-rebuilding countdown timer for rules in the 3-minute cooldown period.
/// Rebuilds only itself every second without causing parent list or row rebuilds.
class CooldownTimer extends StatefulWidget {
  final DateTime cooldownUntil;
  final VoidCallback onRearmPressed;
  final VoidCallback? onCooldownExpired;

  const CooldownTimer({
    super.key,
    required this.cooldownUntil,
    required this.onRearmPressed,
    this.onCooldownExpired,
  });

  @override
  State<CooldownTimer> createState() => _CooldownTimerState();
}

class _CooldownTimerState extends State<CooldownTimer> {
  Timer? _ticker;
  late Duration _remaining;
  static const int _totalCooldownSeconds = 180; // 3 minutes = 180s

  @override
  void initState() {
    super.initState();
    _updateRemaining();
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      _updateRemaining();
    });
  }

  void _updateRemaining() {
    final now = DateTime.now();
    if (now.isAfter(widget.cooldownUntil)) {
      _ticker?.cancel();
      _remaining = Duration.zero;
      widget.onCooldownExpired?.call();
    } else {
      _remaining = widget.cooldownUntil.difference(now);
    }
    if (mounted) setState(() {});
  }

  @override
  void didUpdateWidget(covariant CooldownTimer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.cooldownUntil != widget.cooldownUntil) {
      _updateRemaining();
    }
  }

  @override
  void dispose() {
    _ticker?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_remaining == Duration.zero) {
      return const SizedBox.shrink();
    }

    final totalSecs = _remaining.inSeconds;
    final mins = totalSecs ~/ 60;
    final secs = totalSecs % 60;
    final formattedTime = mins > 0 ? '${mins}m ${secs}s remaining' : '${secs}s remaining';
    final progress = (totalSecs / _totalCooldownSeconds).clamp(0.0, 1.0);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: AppTokens.space8),

        // Thin Cooldown Progress Bar
        ClipRRect(
          borderRadius: AppTokens.borderSmall,
          child: LinearProgressIndicator(
            value: progress,
            minHeight: 2.5,
            backgroundColor: AppTokens.surfaceElevated,
            valueColor: const AlwaysStoppedAnimation<Color>(AppTokens.warning),
          ),
        ),
        const SizedBox(height: AppTokens.space6),

        // Countdown text & "Re-arm Now" button
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              children: [
                const Icon(
                  Icons.timelapse_rounded,
                  size: 13,
                  color: AppTokens.warning,
                ),
                const SizedBox(width: AppTokens.space4),
                Text(
                  formattedTime,
                  style: AppTokens.caption.copyWith(
                    color: AppTokens.warning,
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
              ],
            ),
            InkWell(
              onTap: widget.onRearmPressed,
              borderRadius: AppTokens.borderSmall,
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppTokens.space6,
                  vertical: AppTokens.space2,
                ),
                child: Text(
                  S.rearmNow,
                  style: AppTokens.caption.copyWith(
                    color: AppTokens.warning,
                    fontWeight: FontWeight.w700,
                    decoration: TextDecoration.underline,
                  ),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
