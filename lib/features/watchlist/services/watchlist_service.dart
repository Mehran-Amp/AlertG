import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import '../../core/services/catalog_sync_service.dart';

class WatchlistItem {
  final String symbol;
  final String exchange;
  final String nameEn;
  final String nameFa;
  final String category;
  final String unit;
  final String source;
  final String delay;
  final double? price;
  final double? change24h;

  WatchlistItem({
    required this.symbol,
    this.exchange = 'global_stocks',
    required this.nameEn,
    required this.nameFa,
    required this.category,
    this.unit = '\$',
    this.source = 'Yahoo Finance',
    this.delay = 'بلادرنگ (Real-Time)',
    this.price,
    this.change24h,
  });

  factory WatchlistItem.fromJson(Map<String, dynamic> json) {
    return WatchlistItem(
      symbol: (json['symbol'] as String? ?? '').toUpperCase(),
      exchange: json['exchange'] as String? ?? 'global_stocks',
      nameEn: json['nameEn'] as String? ?? json['name'] as String? ?? '',
      nameFa: json['nameFa'] as String? ?? json['name_fa'] as String? ?? '',
      category: json['category'] as String? ?? 'stock',
      unit: json['unit'] as String? ?? '\$',
      source: json['source'] as String? ?? 'Yahoo Finance',
      delay: json['delay'] as String? ?? 'بلادرنگ (Real-Time)',
      price: (json['price'] as num?)?.toDouble(),
      change24h: (json['change24h'] as num?)?.toDouble(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'symbol': symbol,
      'exchange': exchange,
      'nameEn': nameEn,
      'nameFa': nameFa,
      'category': category,
      'unit': unit,
      'source': source,
      'delay': delay,
      'price': price,
      'change24h': change24h,
    };
  }

  factory WatchlistItem.fromCatalogItem(CatalogItem item, {String exchange = 'global_stocks', double? price}) {
    return WatchlistItem(
      symbol: item.symbol,
      exchange: exchange,
      nameEn: item.nameEn,
      nameFa: item.nameFa,
      category: item.category,
      unit: item.unit,
      source: item.sourceBadge,
      delay: item.delayBadge,
      price: price ?? item.price,
    );
  }
}

class WatchlistService extends ChangeNotifier {
  static final WatchlistService instance = WatchlistService._internal();

  WatchlistService._internal();

  List<WatchlistItem> _items = [];
  bool _isLoaded = false;

  List<WatchlistItem> get items => _items;

  Future<void> load() async {
    if (_isLoaded) return;
    _isLoaded = true;

    try {
      final dir = await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/watchlist.json');
      if (await file.exists()) {
        final content = await file.readAsString();
        final List<dynamic> list = jsonDecode(content);
        _items = list
            .whereType<Map<String, dynamic>>()
            .map((e) => WatchlistItem.fromJson(e))
            .toList();
      }
    } catch (e) {
      debugPrint('⚠️ [WatchlistService] Error loading watchlist: $e');
    }

    if (_items.isEmpty) {
      _seedDefaultWatchlist();
      _save();
    }

    notifyListeners();
  }

  void _seedDefaultWatchlist() {
    _items = [
      WatchlistItem(symbol: 'BTCUSDT', exchange: 'binance', nameEn: 'Bitcoin / Tether', nameFa: 'بیت‌کوین (تتر)', category: 'crypto', unit: '\$', source: 'Binance', delay: '⚡ بلادرنگ', price: 67500.0, change24h: 2.45),
      WatchlistItem(symbol: 'ETHUSDT', exchange: 'binance', nameEn: 'Ethereum / Tether', nameFa: 'اتریوم (تتر)', category: 'crypto', unit: '\$', source: 'Binance', delay: '⚡ بلادرنگ', price: 2620.0, change24h: 1.15),
      WatchlistItem(symbol: 'GC=F', exchange: 'global_stocks', nameEn: 'Gold Futures', nameFa: 'انس طلای جهانی', category: 'commodity', unit: '\$', source: 'CME / Yahoo', delay: '⏱️ تأخیر ۱۵ دقیقه', price: 2655.40, change24h: 0.65),
      WatchlistItem(symbol: 'CL=F', exchange: 'global_stocks', nameEn: 'Crude Oil (WTI)', nameFa: 'نفت خام تگزاس (WTI)', category: 'commodity', unit: '\$', source: 'NYMEX / Yahoo', delay: '⏱️ تأخیر ۱۵ دقیقه', price: 74.85, change24h: -0.80),
      WatchlistItem(symbol: 'AAPL', exchange: 'global_stocks', nameEn: 'Apple Inc.', nameFa: 'سهام شرکت اپل', category: 'stock', unit: '\$', source: 'Yahoo Finance', delay: '⏱️ تأخیر ۱۵ دقیقه', price: 231.50, change24h: 0.95),
      WatchlistItem(symbol: '^GSPC', exchange: 'global_stocks', nameEn: 'S&P 500 Index', nameFa: 'شاخص بورس S&P 500', category: 'index', unit: 'pts', source: 'Yahoo Finance', delay: '⏱️ تأخیر ۱۵ دقیقه', price: 5780.20, change24h: 0.40),
      WatchlistItem(symbol: 'USD_FREE', exchange: 'iran_market', nameEn: 'Free US Dollar', nameFa: 'دلار آزاد تهران', category: 'iran_market', unit: 'تومان', source: 'TGJU / Bonbast', delay: '⚡ بلادرنگ', price: 64200.0, change24h: 0.30),
      WatchlistItem(symbol: 'CPI', exchange: 'global_stocks', nameEn: 'US Inflation (CPI)', nameFa: 'شاخص تورم آمریکا (CPI)', category: 'macro', unit: 'pts', source: 'Federal Reserve (FRED)', delay: '🏛️ ماهانه', price: 314.8, change24h: 0.20),
    ];
  }

  bool isWatchlisted(String symbol) {
    final sym = symbol.trim().toUpperCase();
    return _items.any((item) => item.symbol.toUpperCase() == sym);
  }

  Future<void> toggleWatchlist(WatchlistItem item) async {
    if (isWatchlisted(item.symbol)) {
      await removeFromWatchlist(item.symbol);
    } else {
      await addToWatchlist(item);
    }
  }

  Future<void> addToWatchlist(WatchlistItem item) async {
    final sym = item.symbol.trim().toUpperCase();
    _items.removeWhere((i) => i.symbol.toUpperCase() == sym);
    _items.insert(0, item);
    notifyListeners();
    await _save();
  }

  Future<void> removeFromWatchlist(String symbol) async {
    final sym = symbol.trim().toUpperCase();
    _items.removeWhere((i) => i.symbol.toUpperCase() == sym);
    notifyListeners();
    await _save();
  }

  Future<void> _save() async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/watchlist.json');
      final data = _items.map((e) => e.toJson()).toList();
      await file.writeAsString(jsonEncode(data));
    } catch (e) {
      debugPrint('⚠️ [WatchlistService] Error saving watchlist: $e');
    }
  }
}
