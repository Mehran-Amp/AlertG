import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../settings/services/settings_service.dart';
import '../models/market_event.dart';
import '../services/market_events_service.dart';
import 'social_event_card.dart';

/// Sleek single-line Market Event Banner positioned directly below the Titlebar.
/// Features:
/// - Category Pill (Crypto, Macro, Energy, Stocks)
/// - Auto-cycling High-Impact Event Title & Time
/// - Compact Share Button featuring the Share Emoji (📤) with ZERO text
/// - ZERO Close (×) button (managed purely from Settings)
class MarketEventBanner extends StatefulWidget {
  const MarketEventBanner({super.key});

  @override
  State<MarketEventBanner> createState() => _MarketEventBannerState();
}

class _MarketEventBannerState extends State<MarketEventBanner> {
  int _currentIndex = 0;
  Timer? _cycleTimer;
  List<MarketEvent> _events = [];

  @override
  void initState() {
    super.initState();
    _loadEvents();
  }

  @override
  void dispose() {
    _cycleTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadEvents() async {
    final events = await MarketEventsService.instance.fetchEvents();
    if (mounted) {
      setState(() {
        _events = events;
      });
      _startTimer();
    }
  }

  void _startTimer() {
    _cycleTimer?.cancel();
    if (_events.length > 1) {
      _cycleTimer = Timer.periodic(const Duration(seconds: 8), (_) {
        if (mounted && _events.isNotEmpty) {
          setState(() {
            _currentIndex = (_currentIndex + 1) % _events.length;
          });
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final settingsService = context.watch<SettingsService>();
    final settings = settingsService.settings;

    // If user disabled banner in Settings, render nothing
    if (!settings.showMarketEventsBanner) {
      return const SizedBox.shrink();
    }

    final filtered = MarketEventsService.instance.getFilteredEvents(settings);
    if (filtered.isEmpty) {
      return const SizedBox.shrink();
    }

    final activeIndex = _currentIndex < filtered.length ? _currentIndex : 0;
    final currentEvent = filtered[activeIndex];
    final theme = Theme.of(context);
    final accentColor = currentEvent.categoryColor;

    return Container(
      height: 36,
      width: double.infinity,
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border(
          bottom: BorderSide(
            color: accentColor.withValues(alpha: 0.3),
            width: 1.0,
          ),
        ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // 1. Category Pill (e.g. 🌐 MACRO or 🪙 CRYPTO)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: accentColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(
                color: accentColor.withValues(alpha: 0.5),
                width: 0.8,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  currentEvent.categoryEmoji,
                  style: const TextStyle(fontSize: 10),
                ),
                const SizedBox(width: 3),
                Text(
                  currentEvent.categoryLabel,
                  style: TextStyle(
                    color: accentColor,
                    fontSize: 9.5,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0.4,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),

          // 2. Animated Event Title & Time (Tappable to cycle or view)
          Expanded(
            child: InkWell(
              onTap: () {
                if (filtered.length > 1) {
                  setState(() {
                    _currentIndex = (_currentIndex + 1) % filtered.length;
                  });
                }
              },
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 550),
                transitionBuilder: (child, animation) {
                  final offsetAnimation = Tween<Offset>(
                    begin: const Offset(1.0, 0.0), // Right to Left Entry
                    end: Offset.zero,
                  ).animate(CurvedAnimation(
                    parent: animation,
                    curve: Curves.easeOutCubic,
                  ));
                  return ClipRect(
                    child: SlideTransition(
                      position: offsetAnimation,
                      child: child,
                    ),
                  );
                },
                child: Row(
                  key: ValueKey(currentEvent.id),
                  children: [
                    const Text('🔴 ', style: TextStyle(fontSize: 9)),
                    Expanded(
                      child: Text(
                        '${currentEvent.title} • ${currentEvent.timeUtc}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 11.5,
                          fontWeight: FontWeight.w600,
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.95),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 6),

          // 3. Share Button featuring Emoji Only (📤) as explicitly requested (NO text word "Share")
          Material(
            color: Colors.transparent,
            child: InkWell(
              borderRadius: BorderRadius.circular(6),
              onTap: () {
                showEventSocialShareSheet(context, currentEvent);
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                  color: accentColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(
                    color: accentColor.withValues(alpha: 0.35),
                    width: 0.8,
                  ),
                ),
                child: const Text(
                  '📤',
                  style: TextStyle(fontSize: 13),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
