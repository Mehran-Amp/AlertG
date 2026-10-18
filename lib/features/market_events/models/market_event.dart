import 'package:flutter/material.dart';

class MarketEvent {
  final String id;
  final String category; // 'crypto' | 'macro' | 'energy' | 'stocks'
  final String market;
  final String title;
  final String summary;
  final String impact; // 'high' | 'medium'
  final String timeUtc;
  final String badgeColorHex;
  final String symbol;

  const MarketEvent({
    required this.id,
    required this.category,
    required this.market,
    required this.title,
    required this.summary,
    required this.impact,
    required this.timeUtc,
    required this.badgeColorHex,
    required this.symbol,
  });

  factory MarketEvent.fromJson(Map<String, dynamic> json) {
    return MarketEvent(
      id: json['id'] as String? ?? 'event_${DateTime.now().millisecondsSinceEpoch}',
      category: (json['category'] as String? ?? 'macro').toLowerCase(),
      market: json['market'] as String? ?? 'Global Market',
      title: json['title'] as String? ?? 'Market Catalyst',
      summary: json['summary'] as String? ?? 'High-impact market event.',
      impact: json['impact'] as String? ?? 'high',
      timeUtc: json['time_utc'] as String? ?? 'Upcoming',
      badgeColorHex: json['badge_color'] as String? ?? '#0284C7',
      symbol: json['symbol'] as String? ?? 'GLOBAL',
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'category': category,
    'market': market,
    'title': title,
    'summary': summary,
    'impact': impact,
    'time_utc': timeUtc,
    'badge_color': badgeColorHex,
    'symbol': symbol,
  };

  Color get categoryColor {
    switch (category) {
      case 'crypto':
        return const Color(0xFF10B981); // Emerald
      case 'energy':
        return const Color(0xFFF59E0B); // Amber
      case 'stocks':
        return const Color(0xFF8B5CF6); // Purple
      case 'macro':
      default:
        return const Color(0xFF0284C7); // Sky Blue
    }
  }

  String get categoryLabel {
    switch (category) {
      case 'crypto':
        return 'CRYPTO';
      case 'energy':
        return 'ENERGY';
      case 'stocks':
        return 'STOCKS';
      case 'macro':
      default:
        return 'MACRO';
    }
  }

  String get categoryEmoji {
    switch (category) {
      case 'crypto':
        return '🪙';
      case 'energy':
        return '🛢️';
      case 'stocks':
        return '📈';
      case 'macro':
      default:
        return '🌐';
    }
  }
}
