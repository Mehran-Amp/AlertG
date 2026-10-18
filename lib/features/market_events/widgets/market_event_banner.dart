import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../settings/services/settings_service.dart';
import '../models/market_event.dart';
import '../services/market_events_service.dart';
import 'social_event_card.dart';

/// Full-Width TV Breaking News Continuous Marquee Ticker Banner.
/// Features:
/// - Clean full-width horizontal ticker stream (No static badges or side share buttons)
/// - Tapping any scrolling news item opens the FULL Event Modal Card with Image & Share Image capability
/// - Managed and toggleable purely from Settings
class MarketEventBanner extends StatefulWidget {
  const MarketEventBanner({super.key});

  @override
  State<MarketEventBanner> createState() => _MarketEventBannerState();
}

class _MarketEventBannerState extends State<MarketEventBanner> {
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
      padding: const EdgeInsets.symmetric(horizontal: 6),
      child: Row(
        children: [
          Expanded(
            child: _ContinuousMarqueeStream(
              events: filtered,
              theme: theme,
              onEventTap: (event) => showMarketEventsListModalSheet(context, filtered),
            ),
          ),
          const SizedBox(width: 6),
          InkWell(
            onTap: () => showMarketEventsListModalSheet(context, filtered),
            borderRadius: BorderRadius.circular(6),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
              decoration: BoxDecoration(
                color: primaryAccent.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(
                  color: primaryAccent.withValues(alpha: 0.4),
                  width: 0.8,
                ),
              ),
              child: const Text(
                '📅',
                style: TextStyle(fontSize: 12),
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

      // Smooth TV News ticker scroll speed (~30px per sec)
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
            borderRadius: BorderRadius.circular(6),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text('🔴 ', style: TextStyle(fontSize: 8)),
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
