import 'dart:convert';
import 'package:flutter/foundation.dart';
import '../../../core/services/server_alert_service.dart';
import '../../settings/models/app_settings.dart';
import '../models/market_event.dart';

class MarketEventsService {
  static final MarketEventsService instance = MarketEventsService._internal();
  MarketEventsService._internal();

  List<MarketEvent> _cachedEvents = [];
  DateTime? _lastFetchTime;

  List<MarketEvent> get cachedEvents => List.unmodifiable(_cachedEvents);

  static final List<MarketEvent> fallbackEvents = [
    const MarketEvent(
      id: 'macro_fomc_rate',
      category: 'macro',
      market: 'Forex & Global',
      title: 'US Fed Interest Rate Decision (FOMC)',
      summary: 'Federal Reserve monetary policy announcement & benchmark rate decision. High volatility expected.',
      impact: 'high',
      timeUtc: 'Wednesday 18:00 UTC',
      badgeColorHex: '#0284C7',
      symbol: 'USD',
    ),
    const MarketEvent(
      id: 'crypto_eth_upgrade',
      category: 'crypto',
      market: 'Ethereum Ecosystem',
      title: 'Ethereum Network Upgrade & Hard Fork',
      summary: 'Major Ethereum consensus and execution client upgrade activated across global validators.',
      impact: 'high',
      timeUtc: 'Friday 14:00 UTC',
      badgeColorHex: '#10B981',
      symbol: 'ETH',
    ),
    const MarketEvent(
      id: 'energy_eia_crude',
      category: 'energy',
      market: 'Crude Oil & Commodities',
      title: 'EIA US Crude Oil Inventories Report',
      summary: 'Weekly change in commercial crude oil barrels held by US firms. Key driver for WTI & Brent.',
      impact: 'high',
      timeUtc: 'Wednesday 14:30 UTC',
      badgeColorHex: '#F59E0B',
      symbol: 'WTI',
    ),
    const MarketEvent(
      id: 'stocks_nvda_earnings',
      category: 'stocks',
      market: 'NASDAQ / S&P 500',
      title: 'NVIDIA (NVDA) Q3 Fiscal Earnings Release',
      summary: 'Nvidia reports quarterly revenue, data center GPU sales, and AI infrastructure guidance.',
      impact: 'high',
      timeUtc: 'Thursday 20:00 UTC (AMC)',
      badgeColorHex: '#8B5CF6',
      symbol: 'NVDA',
    ),
  ];

  Future<List<MarketEvent>> fetchEvents({bool forceRefresh = false}) async {
    final now = DateTime.now();
    if (!forceRefresh &&
        _cachedEvents.isNotEmpty &&
        _lastFetchTime != null &&
        now.difference(_lastFetchTime!).inMinutes < 60) {
      return _cachedEvents;
    }

    try {
      final response = await ServerAlertService.get('/api/market-events');
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final rawList = data['events'] as List<dynamic>? ?? [];
        final parsed = rawList
            .map((e) => MarketEvent.fromJson(e as Map<String, dynamic>))
            .toList();

        if (parsed.isNotEmpty) {
          _cachedEvents = parsed;
          _lastFetchTime = now;
          return _cachedEvents;
        }
      }
    } catch (e) {
      debugPrint('⚠️ [MarketEventsService] Fetch error: $e. Using verified fallback events.');
    }

    if (_cachedEvents.isEmpty) {
      _cachedEvents = List.of(fallbackEvents);
    }
    return _cachedEvents;
  }

  List<MarketEvent> getFilteredEvents(AppSettings settings) {
    final all = _cachedEvents.isNotEmpty ? _cachedEvents : fallbackEvents;
    return all.where((ev) {
      switch (ev.category) {
        case 'crypto':
          return settings.eventsCryptoEnabled;
        case 'macro':
          return settings.eventsMacroEnabled;
        case 'energy':
          return settings.eventsEnergyEnabled;
        case 'stocks':
          return settings.eventsStocksEnabled;
        default:
          return true;
      }
    }).toList();
  }
}
