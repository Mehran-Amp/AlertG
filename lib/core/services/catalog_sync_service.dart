import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'server_alert_service.dart';

/// Normalized Catalog Symbol Item
class CatalogItem {
  final String id;
  final String symbol;
  final String nameEn;
  final String nameFa;
  final String category; // 'stock', 'forex', 'bond', 'commodity', 'index', 'iran_market', 'macro', 'crypto'
  final String marketName;
  final String unit;
  final bool isActive;
  final DateTime? delistedAt;
  final String source;
  final double? price;
  final bool singleSource;
  final bool isDelayed;

  CatalogItem({
    required this.id,
    required this.symbol,
    required this.nameEn,
    required this.nameFa,
    required this.category,
    this.marketName = 'Global',
    this.unit = '\$',
    this.isActive = true,
    this.delistedAt,
    this.source = 'default',
    this.price,
    this.singleSource = true,
    this.isDelayed = false,
  });

  factory CatalogItem.fromJson(Map<String, dynamic> json) {
    final cat = (json['category'] as String? ?? 'stock').toLowerCase();
    return CatalogItem(
      id: json['id'] as String? ?? json['symbol'] as String? ?? '',
      symbol: (json['symbol'] as String? ?? json['id'] as String? ?? '').toUpperCase(),
      nameEn: json['nameEn'] as String? ?? json['name'] as String? ?? '',
      nameFa: json['nameFa'] as String? ?? json['name_fa'] as String? ?? '',
      category: cat,
      marketName: json['marketName'] as String? ?? json['market'] as String? ?? 'Global',
      unit: json['unit'] as String? ?? '\$',
      isActive: (json['is_active'] == 1 || json['is_active'] == true || json['is_active'] == null),
      delistedAt: json['delisted_at'] != null ? DateTime.tryParse(json['delisted_at'].toString()) : null,
      source: json['source'] as String? ?? json['source_provider'] as String? ?? 'Yahoo Finance',
      price: (json['price'] as num?)?.toDouble(),
      singleSource: json['single_source'] as bool? ?? (cat == 'bond' ? false : true),
      isDelayed: json['is_delayed'] as bool? ?? (cat == 'stock' || cat == 'index' || cat == 'macro'),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'symbol': symbol,
      'nameEn': nameEn,
      'nameFa': nameFa,
      'category': category,
      'marketName': marketName,
      'unit': unit,
      'is_active': isActive ? 1 : 0,
      'delisted_at': delistedAt?.toIso8601String(),
      'source': source,
      'price': price,
      'single_source': singleSource,
      'is_delayed': isDelayed,
    };
  }

  String get categoryFa {
    switch (category) {
      case 'crypto':
        return 'رمزارز';
      case 'iran_market':
        return 'بازار ایران و طلا/ارز';
      case 'stock':
        return 'سهام جهانی';
      case 'forex':
        return 'فارکس';
      case 'commodity':
        return 'کالا و کامودیتی';
      case 'index':
        return 'شاخص بورس';
      case 'macro':
        return 'شاخص کلان اقتصادی';
      case 'bond':
        return 'اوراق قرضه و بازدهی';
      default:
        return 'بازار مالی';
    }
  }

  String get singleSourceBadge => singleSource ? '⚠️ منبع محدود' : '🌐 چندمنبعی';

  String get delayBadge {
    if (isDelayed) return '⏱️ با تأخیر';
    return '⚡ بلادرنگ (Real-Time)';
  }

  String get sourceBadge {
    if (source.isNotEmpty && source != 'default') return source;
    if (category == 'macro' || category == 'bond') return 'Federal Reserve (FRED)';
    if (category == 'commodity') return 'CME / Yahoo Finance';
    if (category == 'forex') return 'Twelve Data / Yahoo';
    if (category == 'iran_market') return 'TSETMC / TGJU';
    return 'Yahoo Finance';
  }
}

/// CatalogSyncService manages offline local caching and delta sync for the symbols catalog.
class CatalogSyncService extends ChangeNotifier {
  static final CatalogSyncService instance = CatalogSyncService._internal();

  CatalogSyncService._internal();

  int _localVersion = 1;
  DateTime? _lastSyncAt;
  List<CatalogItem> _items = [];
  bool _isInitialized = false;
  bool _isSyncing = false;

  int get localVersion => _localVersion;
  DateTime? get lastSyncAt => _lastSyncAt;
  List<CatalogItem> get items => _items;
  bool get isSyncing => _isSyncing;

  /// Loads cached catalog from disk on app start
  Future<void> initialize() async {
    if (_isInitialized) return;
    _isInitialized = true;

    try {
      final dir = await getApplicationDocumentsDirectory();
      final cacheFile = File('${dir.path}/catalog_cache.json');
      if (await cacheFile.exists()) {
        final content = await cacheFile.readAsString();
        final Map<String, dynamic> data = jsonDecode(content);
        _localVersion = data['catalog_version'] as int? ?? 1;
        if (data['last_sync_at'] != null) {
          _lastSyncAt = DateTime.tryParse(data['last_sync_at'].toString());
        }
        final list = data['symbols'] as List? ?? [];
        _items = list
            .whereType<Map<String, dynamic>>()
            .map((e) => CatalogItem.fromJson(e))
            .where((item) => item.isActive)
            .toList();
        debugPrint('📦 [CatalogCache] Loaded ${_items.length} cached symbols from disk (v$_localVersion)');
      }
    } catch (e) {
      debugPrint('⚠️ [CatalogCache] Error loading disk cache: $e');
    }

    // Seed defaults if empty
    if (_items.isEmpty) {
      _seedDefaultCatalog();
    }

    notifyListeners();

    // Fire background delta sync with server
    syncDelta();
  }

  /// Maximum number of symbols the app may ship as a hard-coded offline fallback.
  /// Everything else must come from the server catalog (/api/symbols/catalog + delta sync).
  static const int maxOfflineFallbackSymbols = 20;

  /// Minimal offline fallback used only when there is no disk cache yet and the server is unreachable.
  void _seedDefaultCatalog() {
    _items = [
      // Top Macro & Global
      CatalogItem(id: 'CPI', symbol: 'CPI', nameEn: 'Consumer Price Index (US CPI)', nameFa: 'شاخص تورم مصرف‌کننده آمریکا (CPI)', category: 'macro', unit: 'pts', source: 'FRED'),
      CatalogItem(id: 'FEDFUNDS', symbol: 'FEDFUNDS', nameEn: 'Federal Funds Effective Rate', nameFa: 'نرخ بهره فدرال رزرو آمریکا', category: 'macro', unit: '%', source: 'FRED'),
      CatalogItem(id: 'US10Y', symbol: 'US10Y', nameEn: 'US 10-Year Treasury Yield', nameFa: 'بازدهی اوراق ۱۰ ساله خزانه‌داری آمریکا', category: 'bond', unit: '%', source: 'Yahoo Finance'),
      CatalogItem(id: 'UNRATE', symbol: 'UNRATE', nameEn: 'US Unemployment Rate', nameFa: 'نرخ بیکاری آمریکا', category: 'macro', unit: '%', source: 'FRED'),
      CatalogItem(id: 'DX-Y.NYB', symbol: 'DX-Y.NYB', nameEn: 'US Dollar Index (DXY)', nameFa: 'شاخص قدرت دلار آمریکا (DXY)', category: 'macro', unit: 'pts', source: 'Yahoo Finance'),
      // Top Commodities
      CatalogItem(id: 'GC=F', symbol: 'GC=F', nameEn: 'Gold Futures (Ounce)', nameFa: 'انس طلای جهانی', category: 'commodity', unit: '\$', source: 'CME / Yahoo'),
      CatalogItem(id: 'SI=F', symbol: 'SI=F', nameEn: 'Silver Futures', nameFa: 'انس نقره جهانی', category: 'commodity', unit: '\$', source: 'CME / Yahoo'),
      CatalogItem(id: 'CL=F', symbol: 'CL=F', nameEn: 'Crude Oil (WTI)', nameFa: 'نفت خام تگزاس (WTI)', category: 'commodity', unit: '\$', source: 'NYMEX / Yahoo'),
      CatalogItem(id: 'BZ=F', symbol: 'BZ=F', nameEn: 'Brent Crude Oil', nameFa: 'نفت خام برنت دریای شمال', category: 'commodity', unit: '\$', source: 'ICE / Yahoo'),
      // Top Equities
      CatalogItem(id: 'AAPL', symbol: 'AAPL', nameEn: 'Apple Inc.', nameFa: 'سهام شرکت اپل', category: 'stock', unit: '\$', source: 'Yahoo Finance'),
      CatalogItem(id: 'MSFT', symbol: 'MSFT', nameEn: 'Microsoft Corp.', nameFa: 'سهام شرکت مایکروسافت', category: 'stock', unit: '\$', source: 'Yahoo Finance'),
      CatalogItem(id: 'NVDA', symbol: 'NVDA', nameEn: 'NVIDIA Corporation', nameFa: 'سهام شرکت انویدیا', category: 'stock', unit: '\$', source: 'Yahoo Finance'),
      CatalogItem(id: 'TSLA', symbol: 'TSLA', nameEn: 'Tesla Inc.', nameFa: 'سهام شرکت تسلا', category: 'stock', unit: '\$', source: 'Yahoo Finance'),
      CatalogItem(id: '^GSPC', symbol: '^GSPC', nameEn: 'S&P 500 Index', nameFa: 'شاخص ۵۰۰ شرکت برتر آمریکا (S&P 500)', category: 'index', unit: 'pts', source: 'Yahoo Finance'),
      CatalogItem(id: '^IXIC', symbol: '^IXIC', nameEn: 'Nasdaq Composite', nameFa: 'شاخص نزدک آمریکا', category: 'index', unit: 'pts', source: 'Yahoo Finance'),
      // Top Forex
      CatalogItem(id: 'EURUSD=X', symbol: 'EURUSD=X', nameEn: 'EUR / USD', nameFa: 'یورو به دلار آمریکا', category: 'forex', unit: '\$', source: 'Twelve Data'),
      CatalogItem(id: 'GBPUSD=X', symbol: 'GBPUSD=X', nameEn: 'GBP / USD', nameFa: 'پوند انگلیس به دلار آمریکا', category: 'forex', unit: '\$', source: 'Twelve Data'),
      CatalogItem(id: 'USDJPY=X', symbol: 'USDJPY=X', nameEn: 'USD / JPY', nameFa: 'دلار آمریکا به ین ژاپن', category: 'forex', unit: '¥', source: 'Twelve Data'),
    ];
    assert(_items.length <= maxOfflineFallbackSymbols, 'Offline fallback must stay <= 20 symbols');
  }

  /// Performs delta sync against backend server
  Future<bool> syncDelta() async {
    if (_isSyncing) return false;
    _isSyncing = true;
    notifyListeners();

    try {
      final baseUrl = ServerAlertService.effectiveBaseUrl;
      final uri = Uri.parse('$baseUrl/api/symbols/catalog').replace(
        queryParameters: {
          'since_version': _localVersion.toString(),
        },
      );

      final headers = <String, String>{
        'Content-Type': 'application/json',
      };
      final apiKey = ServerAlertService.apiKey;
      if (apiKey.isNotEmpty) {
        headers['X-API-Key'] = apiKey;
      }

      final response = await http.get(uri, headers: headers).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final Map<String, dynamic> body = jsonDecode(utf8.decode(response.bodyBytes));
        final status = body['status'] as String? ?? '';
        final isDelta = body['is_delta'] == true;
        final newVersion = body['catalog_version'] as int? ?? _localVersion;
        final syncTime = body['last_sync_at'] != null ? DateTime.tryParse(body['last_sync_at'].toString()) : DateTime.now();

        if (status == 'up_to_date') {
          debugPrint('🔄 [CatalogSync] Catalog is up to date at version $_localVersion');
          _lastSyncAt = syncTime;
        } else if (isDelta && status == 'delta_success') {
          // Apply Delta Changes
          final added = (body['added'] as List? ?? []).whereType<Map<String, dynamic>>().map((e) => CatalogItem.fromJson(e)).toList();
          final updated = (body['updated'] as List? ?? []).whereType<Map<String, dynamic>>().map((e) => CatalogItem.fromJson(e)).toList();
          final delistedSymbols = (body['delisted'] as List? ?? []).map((e) => e.toString().toUpperCase()).toSet();

          final map = {for (var item in _items) item.symbol: item};

          // Remove delisted
          for (final del in delistedSymbols) {
            map.remove(del);
          }
          // Update modified
          for (final up in updated) {
            map[up.symbol] = up;
          }
          // Insert added
          for (final add in added) {
            map[add.symbol] = add;
          }

          _items = map.values.where((item) => item.isActive).toList();
          _localVersion = newVersion;
          _lastSyncAt = syncTime;
          await _saveToDisk();
          debugPrint('✅ [CatalogSync] Applied delta: +${added.length}, ~${updated.length}, -${delistedSymbols.length}. Version: $_localVersion');
        } else {
          // Full catalog received
          final fullList = (body['symbols'] as List? ?? []).whereType<Map<String, dynamic>>().map((e) => CatalogItem.fromJson(e)).toList();
          if (fullList.isNotEmpty) {
            _items = fullList.where((item) => item.isActive).toList();
            _localVersion = newVersion;
            _lastSyncAt = syncTime;
            await _saveToDisk();
            debugPrint('✅ [CatalogSync] Full catalog refreshed with ${_items.length} symbols. Version: $_localVersion');
          }
        }
        _isSyncing = false;
        notifyListeners();
        return true;
      }
    } catch (e) {
      debugPrint('⚠️ [CatalogSync] Sync error (using local cache): $e');
    }

    _isSyncing = false;
    notifyListeners();
    return false;
  }

  Future<void> _saveToDisk() async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      final cacheFile = File('${dir.path}/catalog_cache.json');
      final data = {
        'catalog_version': _localVersion,
        'last_sync_at': _lastSyncAt?.toIso8601String(),
        'symbols': _items.map((e) => e.toJson()).toList(),
      };
      await cacheFile.writeAsString(jsonEncode(data));
    } catch (e) {
      debugPrint('⚠️ [CatalogCache] Error saving cache to disk: $e');
    }
  }

  /// Fast Offline Search supporting English & Persian text normalizations
  List<CatalogItem> searchOffline(String query, {String? categoryTab}) {
    final cleanQuery = _normalizePersianText(query.trim().toLowerCase());

    return _items.where((item) {
      // Category tab filtering
      if (categoryTab != null && categoryTab != 'all') {
        if (categoryTab == 'crypto') {
          if (item.category != 'crypto') return false;
        } else if (categoryTab == 'iran') {
          if (item.category != 'iran_market') return false;
        } else if (categoryTab == 'stocks') {
          if (item.category != 'stock') return false;
        } else if (categoryTab == 'forex') {
          if (item.category != 'forex') return false;
        } else if (categoryTab == 'commodities') {
          if (item.category != 'commodity') return false;
        } else if (categoryTab == 'indices') {
          if (item.category != 'index') return false;
        } else if (categoryTab == 'macro') {
          if (item.category != 'macro' && item.category != 'bond') return false;
        }
      }

      if (cleanQuery.isEmpty) return true;

      final symMatch = item.symbol.toLowerCase().contains(cleanQuery);
      final enMatch = item.nameEn.toLowerCase().contains(cleanQuery);
      final faNorm = _normalizePersianText(item.nameFa.toLowerCase());
      final faMatch = faNorm.contains(cleanQuery);

      return symMatch || enMatch || faMatch;
    }).toList();
  }

  /// Helper to normalize Persian/Arabic letters & half-spaces for robust search
  static String _normalizePersianText(String text) {
    return text
        .replaceAll('\u200c', '') // remove zero-width non-joiner
        .replaceAll('ي', 'ی')
        .replaceAll('ك', 'ک')
        .replaceAll('آ', 'ا')
        .replaceAll('أ', 'ا')
        .replaceAll('إ', 'ا')
        .replaceAll('ؤ', 'و')
        .replaceAll('ة', 'ه');
  }

  /// Fetch full rich symbol details from backend (market status, hours, schedule)
  Future<Map<String, dynamic>?> fetchSymbolDetail(String symbol, {String exchange = 'global_stocks'}) async {
    try {
      final baseUrl = ServerAlertService.effectiveBaseUrl;
      final uri = Uri.parse('$baseUrl/api/symbols/detail').replace(
        queryParameters: {
          'symbol': symbol,
          'exchange': exchange,
        },
      );

      final headers = <String, String>{
        'Content-Type': 'application/json',
      };
      final apiKey = ServerAlertService.apiKey;
      if (apiKey.isNotEmpty) {
        headers['X-API-Key'] = apiKey;
      }

      final response = await http.get(uri, headers: headers).timeout(const Duration(seconds: 6));
      if (response.statusCode == 200) {
        return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>?;
      }
    } catch (_) {}
    return null;
  }
}
