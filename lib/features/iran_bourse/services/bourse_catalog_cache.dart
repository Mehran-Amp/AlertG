import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import '../models/bourse_board.dart';
import 'iran_bourse_service.dart';

/// On-device catalog cache for Iranian Bourse symbols (`GET /api/iran-bourse/catalog`).
///
/// The full market catalog (~all instruments) is cached in memory and persisted on disk,
/// and only auto-refreshes **once per day after Tehran market close (19:00 UTC+03:30)**
/// or when the user explicitly pulls to refresh. Tab switches, sorting, traded-only filtering,
/// search, and paging run locally at 0ms with zero server requests.
class BourseCatalogCache {
  static const String cacheFileName = 'iran_bourse_catalog_v1.json';
  static const Duration _tehranOffset = Duration(hours: 3, minutes: 30);
  static const int _closeHourTehran = 19;

  static final BourseCatalogCache instance = BourseCatalogCache();

  final Future<Directory> Function() _directoryProvider;
  final DateTime Function() _nowUtc;

  List<BourseBoardItem> _items = const [];
  BourseSession _session = BourseSession.unknown;
  bool _serverStale = false;
  int? _asOf;
  DateTime? _syncedAtUtc;
  bool _diskLoaded = false;
  Future<BourseResult<void>>? _inFlight;

  BourseCatalogCache({
    Future<Directory> Function()? directoryProvider,
    DateTime Function()? nowUtc,
  })  : _directoryProvider = directoryProvider ?? getApplicationDocumentsDirectory,
        _nowUtc = nowUtc ?? (() => DateTime.now().toUtc());

  bool get hasItems => _items.isNotEmpty;
  DateTime? get syncedAtUtc => _syncedAtUtc;
  BourseSession get session => _session;
  bool get serverStale => _serverStale;
  int? get asOf => _asOf;
  List<BourseBoardItem> get items => _items;

  /// Latest 19:00 Tehran market-close timestamp (in UTC) at or before [nowUtc].
  static DateTime latestTehranCloseUtc(DateTime nowUtc) {
    final utc = nowUtc.toUtc();
    final tehran = utc.add(_tehranOffset);
    final todayCloseShifted = DateTime.utc(tehran.year, tehran.month, tehran.day, _closeHourTehran, 0);
    final closeShifted = !tehran.isBefore(todayCloseShifted)
        ? todayCloseShifted
        : todayCloseShifted.subtract(const Duration(days: 1));
    return closeShifted.subtract(_tehranOffset);
  }

  /// True when cached items exist and were synced at/after the latest 19:00 Tehran close.
  bool isFresh([DateTime? nowUtcOverride]) {
    if (_items.isEmpty || _syncedAtUtc == null) return false;
    final cutoff = latestTehranCloseUtc(nowUtcOverride ?? _nowUtc());
    return !_syncedAtUtc!.isBefore(cutoff);
  }

  /// Clears in-memory state (used by tests).
  @visibleForTesting
  void reset() {
    _items = const [];
    _session = BourseSession.unknown;
    _serverStale = false;
    _asOf = null;
    _syncedAtUtc = null;
    _diskLoaded = false;
    _inFlight = null;
  }

  /// Normalizes Arabic/Persian Yeh/Kaf, half-space, and whitespace to match backend `board.norm`.
  static String normalizeSearch(String? text) {
    if (text == null || text.isEmpty) return '';
    final normalized = text
        .replaceAll('ي', 'ی')
        .replaceAll('ك', 'ک')
        .replaceAll('ى', 'ی')
        .replaceAll('\u200C', ' ')
        .trim()
        .replaceAll(RegExp(r'\s+'), ' ');
    return normalized.toLowerCase();
  }

  Future<File?> _cacheFile() async {
    try {
      final dir = await _directoryProvider();
      return File('${dir.path}${Platform.pathSeparator}$cacheFileName');
    } catch (_) {
      return null;
    }
  }

  /// Loads previously saved catalog JSON from disk into memory if available.
  Future<void> loadFromDisk() async {
    if (_diskLoaded) return;
    _diskLoaded = true;
    final file = await _cacheFile();
    if (file == null) return;
    try {
      if (!await file.exists()) return;
      final raw = await file.readAsString();
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return;
      final syncedMs = decoded['synced_at_ms'];
      final rawItems = decoded['items'];
      if (rawItems is! List) return;
      final parsed = <BourseBoardItem>[];
      for (final row in rawItems) {
        final item = BourseBoardItem.tryParse(row);
        if (item != null) parsed.add(item);
      }
      if (parsed.isEmpty) return;
      _items = List<BourseBoardItem>.unmodifiable(parsed);
      _session = BourseSession.fromServer(decoded['session']);
      _serverStale = decoded['stale'] == true;
      _asOf = decoded['as_of'] is int ? decoded['as_of'] as int : null;
      _syncedAtUtc = syncedMs is int ? DateTime.fromMillisecondsSinceEpoch(syncedMs, isUtc: true) : null;
    } catch (_) {
      // Ignore corrupt or inaccessible cache file and fall back to network.
    }
  }

  Future<void> _saveToDisk() async {
    final file = await _cacheFile();
    if (file == null) return;
    try {
      await file.parent.create(recursive: true);
      final payload = jsonEncode({
        'version': 1,
        'synced_at_ms': _syncedAtUtc?.millisecondsSinceEpoch,
        'as_of': _asOf,
        'session': _sessionKey(_session),
        'stale': _serverStale,
        'items': _items.map((e) => e.toJson()).toList(),
      });
      await file.writeAsString(payload);
    } catch (_) {
      // Non-fatal in restricted or headless test environments.
    }
  }

  static String _sessionKey(BourseSession session) {
    switch (session) {
      case BourseSession.open:
        return 'OPEN';
      case BourseSession.closed:
        return 'CLOSED';
      case BourseSession.stale:
        return 'STALE';
      case BourseSession.unknown:
        return 'UNKNOWN';
    }
  }

  /// Ensures cached catalog is ready.
  ///
  /// - Loads from disk once if memory is empty.
  /// - Skips network entirely if [forceRefresh] is false and cache is fresh (post latest 19:00 Tehran).
  /// - If passive daily refresh fails over network while stale disk cache exists, keeps stale items usable.
  /// - If [forceRefresh] is true and network fails, keeps existing items intact and returns failure.
  Future<BourseResult<void>> ensureLoaded({
    required IranBourseService service,
    bool forceRefresh = false,
  }) async {
    await loadFromDisk();
    if (!forceRefresh && isFresh()) {
      return const BourseResult<void>.ok(null);
    }
    if (!forceRefresh && _inFlight != null) {
      return _inFlight!;
    }

    final future = _fetchAndStore(service: service, forceRefresh: forceRefresh);
    _inFlight = future;
    try {
      return await future;
    } finally {
      if (identical(_inFlight, future)) {
        _inFlight = null;
      }
    }
  }

  Future<BourseResult<void>> _fetchAndStore({
    required IranBourseService service,
    required bool forceRefresh,
  }) async {
    final res = await service.catalog();
    if (res.isOk && res.data != null) {
      final page = res.data!;
      _items = List<BourseBoardItem>.unmodifiable(page.items);
      _session = page.session;
      _serverStale = page.stale;
      _asOf = page.asOf;
      _syncedAtUtc = _nowUtc().toUtc();
      await _saveToDisk();
      return const BourseResult<void>.ok(null);
    }
    if (!forceRefresh && _items.isNotEmpty) {
      // Offline / transient network error with an older local catalog: keep browsing locally.
      return const BourseResult<void>.ok(null);
    }
    return BourseResult<void>.fail(
      res.failure ?? BourseFailure.unavailable,
      message: res.message,
      httpStatus: res.httpStatus,
    );
  }

  /// Queries the in-memory catalog with parity to backend `BourseBoard.query`.
  BourseBoardPage query({
    BourseGroup? group,
    bool? traded,
    String? q,
    BourseSort sort = BourseSort.value,
    bool? ascending,
    int offset = 0,
    int limit = 50,
  }) {
    final safeLimit = limit < 1 ? 1 : (limit > 200 ? 200 : limit);
    final safeOffset = offset < 0 ? 0 : offset;
    final desc = ascending != null ? !ascending : (sort != BourseSort.name);
    final nq = normalizeSearch(q);

    final counts = <BourseGroup, int>{for (final g in BourseGroup.values) g: 0};
    final filtered = <BourseBoardItem>[];

    for (final item in _items) {
      counts[item.group] = (counts[item.group] ?? 0) + 1;

      if (group != null) {
        if (item.group != group) continue;
      } else if (item.group == BourseGroup.derivatives) {
        continue; // Default "همه" list excludes options/futures, matching server `board.py`.
      }
      if (traded == true && !item.traded) continue;
      if (nq.isNotEmpty) {
        final inTicker = normalizeSearch(item.ticker).contains(nq);
        final inName = normalizeSearch(item.name).contains(nq);
        if (!inTicker && !inName) continue;
      }
      filtered.add(item);
    }

    final present = <BourseBoardItem>[];
    final missing = <BourseBoardItem>[];
    for (final item in filtered) {
      if (_hasSortValue(item, sort)) {
        present.add(item);
      } else {
        missing.add(item);
      }
    }

    present.sort((a, b) {
      final cmp = _comparePresent(a, b, sort);
      return desc ? -cmp : cmp;
    });

    final ordered = <BourseBoardItem>[...present, ...missing];
    final start = safeOffset > ordered.length ? ordered.length : safeOffset;
    final end = (start + safeLimit) > ordered.length ? ordered.length : (start + safeLimit);
    final pageItems = ordered.sublist(start, end);

    return BourseBoardPage(
      items: pageItems,
      total: ordered.length,
      offset: start,
      limit: safeLimit,
      session: _session,
      stale: _serverStale,
      asOf: _asOf,
      sort: sort.key,
      descending: desc,
      groupCounts: counts,
    );
  }

  static bool _hasSortValue(BourseBoardItem item, BourseSort sort) {
    switch (sort) {
      case BourseSort.name:
        return true;
      case BourseSort.value:
        return item.value != null;
      case BourseSort.volume:
        return item.volume != null;
      case BourseSort.change:
        return item.changePct != null;
      case BourseSort.price:
        return item.price != null;
    }
  }

  static int _comparePresent(BourseBoardItem a, BourseBoardItem b, BourseSort sort) {
    int cmp;
    switch (sort) {
      case BourseSort.name:
        cmp = normalizeSearch(a.displayTicker).compareTo(normalizeSearch(b.displayTicker));
        break;
      case BourseSort.value:
        cmp = (a.value!).compareTo(b.value!);
        break;
      case BourseSort.volume:
        cmp = (a.volume!).compareTo(b.volume!);
        break;
      case BourseSort.change:
        cmp = (a.changePct!).compareTo(b.changePct!);
        break;
      case BourseSort.price:
        cmp = (a.price!).compareTo(b.price!);
        break;
    }
    if (cmp != 0) return cmp;
    return a.id.compareTo(b.id);
  }
}
