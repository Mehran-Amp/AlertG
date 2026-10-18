import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../settings/services/settings_service.dart';
import '../models/market_event.dart';
import '../services/market_events_service.dart';
import 'social_event_card.dart';

/// TV Breaking News Continuous Marquee Ticker Banner positioned directly below the Titlebar.
/// Features:
/// - Continuous smooth horizontal scrolling stream (like TV news tickers)
/// - Category Badges & Live Breaking News Indicators
/// - Compact Share Button featuring the Share Emoji (📤) with ZERO text
/// - ZERO Close (×) button (managed purely from Settings)
class MarketEventBanner extends StatefulWidget {
  const MarketEventBanner({super.key});

  @override
  State<MarketEventBanner> createState() => _MarketEventBannerState();
}

class _MarketEventBannerState extends State<MarketEventBanner> {
  List<MarketEvent> _events = [];

  @override
  void initState() {
    super.initState();
    _loadEvents();
  }

  Future<void> _loadEvents() async {
    final events = await MarketEventsService.instance.fetchEvents();
    if (mounted) {
      setState(() {
        _events = events;
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

    final theme = Theme.of(context);
    final primaryAccent = filtered.first.categoryColor;

    return Container(
      height: 36,
      width: double.infinity,
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border(
          bottom: BorderSide(
            color: primaryAccent.withValues(alpha: 0.35),
            width: 1.0,
          ),
        ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // 1. Live Breaking Badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: Colors.red.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(
                color: Colors.red.withValues(alpha: 0.5),
                width: 0.8,
              ),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('🔴 ', style: TextStyle(fontSize: 8)),
                Text(
                  'NEWS TICKER',
                  style: TextStyle(
                    color: Colors.redAccent,
                    fontSize: 9.0,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0.4,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),

          // 2. Continuous Infinite Scrolling TV Marquee Ticker Stream
          Expanded(
            child: _ContinuousMarqueeStream(
              events: filtered,
              theme: theme,
              onEventTap: (event) => showEventSocialShareSheet(context, event),
            ),
          ),
          const SizedBox(width: 6),

          // 3. Compact Share Button (📤)
          Material(
            color: Colors.transparent,
            child: InkWell(
              borderRadius: BorderRadius.circular(6),
              onTap: () {
                if (filtered.isNotEmpty) {
                  showEventSocialShareSheet(context, filtered.first);
                }
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                  color: primaryAccent.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(
                    color: primaryAccent.withValues(alpha: 0.35),
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

/// Helper widget that continuously scrolls the text stream smoothly horizontally.
class _ContinuousMarqueeStream extends StatefulWidget {
  final List<MarketEvent> events;
  final ThemeData theme;
  final Function(MarketEvent) onEventTap;

  const _ContinuousMarqueeStream({
    required this.events,
    required this.theme,
    required this.onEventTap,
  });

  @override
  State<_ContinuousMarqueeStream> createState() => _ContinuousMarqueeStreamState();
}

class _ContinuousMarqueeStreamState extends State<_ContinuousMarqueeStream> {
  late final ScrollController _scrollController;
  bool _isScrolling = false;

  @override
  void initState() {
    super.initState();
    _scrollController = ScrollController();
    WidgetsBinding.instance.addPostFrameCallback((_) => _startContinuousScroll());
  }

  void _startContinuousScroll() async {
    if (_isScrolling) return;
    _isScrolling = true;

    while (mounted) {
      if (!_scrollController.hasClients) {
        await Future.delayed(const Duration(milliseconds: 300));
        continue;
      }

      final maxScroll = _scrollController.position.maxScrollExtent;
      if (maxScroll <= 0) {
        await Future.delayed(const Duration(milliseconds: 500));
        continue;
      }

      // Smooth TV News ticker scroll speed (e.g. 30px per sec)
      final durationMs = (maxScroll * 30).toInt();

      await _scrollController.animateTo(
        maxScroll,
        duration: Duration(milliseconds: durationMs),
        curve: Curves.linear,
      );

      if (!mounted) break;
      await Future.delayed(const Duration(milliseconds: 200));
      if (!_scrollController.hasClients) break;

      // Jump back seamlessly to 0 for infinite looping ticker
      _scrollController.jumpTo(0);
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Duplicate event list to create a seamless infinite stream loop
    final streamEvents = [...widget.events, ...widget.events, ...widget.events];

    return SingleChildScrollView(
      controller: _scrollController,
      scrollDirection: Axis.horizontal,
      physics: const NeverScrollableScrollPhysics(),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: streamEvents.map((event) {
          final accent = event.categoryColor;
          return InkWell(
            onTap: () => widget.onEventTap(event),
            borderRadius: BorderRadius.circular(4),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Category Pill in Stream
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                    decoration: BoxDecoration(
                      color: accent.withValues(alpha: 0.18),
                      borderRadius: BorderRadius.circular(3),
                      border: Border.all(color: accent.withValues(alpha: 0.4), width: 0.6),
                    ),
                    child: Text(
                      '${event.categoryEmoji} ${event.categoryLabel}',
                      style: TextStyle(
                        color: accent,
                        fontSize: 9,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    '${event.title} • ${event.timeUtc}',
                    style: TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w600,
                      color: widget.theme.colorScheme.onSurface.withValues(alpha: 0.95),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Text(
                    '❖',
                    style: TextStyle(
                      fontSize: 10,
                      color: widget.theme.colorScheme.onSurface.withValues(alpha: 0.3),
                    ),
                  ),
                ],
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}
