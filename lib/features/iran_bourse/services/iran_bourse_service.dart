import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../../core/services/server_alert_service.dart';
import '../models/bourse_board.dart';
import '../models/bourse_instrument.dart';
import '../models/bourse_quote.dart';

/// Why a Bourse call did not produce data. The UI maps each value to a Persian message (IB-11b).
enum BourseFailure {
  /// Server answered 503 "not enabled": the Bourse is switched off (IRAN_BOURSE_ENABLED=false).
  disabled,

  /// Server answered 5xx for another reason (gateway or tunnel down, feed unavailable).
  unavailable,

  /// Unknown instrument id (HTTP 404).
  notFound,

  /// The request was rejected as malformed (HTTP 400/422) or the id has the wrong shape.
  badRequest,

  /// Missing or wrong API key (HTTP 401/403).
  unauthorized,

  /// No connection, timeout, or any transport error.
  network,

  /// The server answered but the body was not what this app version understands.
  badResponse,

  /// Alert creation: this user is not on the Bourse rollout list yet (HTTP 403).
  notAllowed,

  /// Alert creation: the instrument has no previous close, so a change alert is impossible.
  noPreviousClose,

  /// Alert creation: the server refused the alert for another reason (HTTP 400).
  rejected,
}

/// Result of one call. Exactly one of [data] / [failure] is set. Calls never throw.
class BourseResult<T> {
  final T? data;
  final BourseFailure? failure;

  /// Technical detail for logs (never shown to users as is).
  final String? message;
  final int? httpStatus;

  const BourseResult.ok(this.data)
      : failure = null,
        message = null,
        httpStatus = null;

  const BourseResult.fail(BourseFailure this.failure, {this.message, this.httpStatus})
      : data = null;

  bool get isOk => failure == null;
}

/// Answer of `GET /api/iran-bourse/symbols`.
class BourseSearchResult {
  /// The query as the server normalised it (Arabic ي/ك become Persian ی/ک).
  final String query;
  final List<BourseInstrument> items;

  /// True when the server's instrument list is old.
  final bool stale;

  const BourseSearchResult({required this.query, required this.items, required this.stale});
}

/// Talks to the AlertG server's Iranian Bourse API. It never calls TSETMC or the gateway.
///
/// All prices are Rial (IRR); instrument ids are Strings (rules D1 and N6).
class IranBourseService {
  static const int maxSearchLimit = 50;
  static const int maxQueryLength = 64;

  final http.Client? _client;
  final String Function() _baseUrl;
  final String Function() _apiKey;
  final Duration timeout;

  /// [client], [baseUrl] and [apiKey] exist for tests; the defaults use the app's own
  /// server settings (`ServerAlertService`).
  IranBourseService({
    http.Client? client,
    String Function()? baseUrl,
    String Function()? apiKey,
    this.timeout = const Duration(seconds: 10),
  })  : _client = client,
        _baseUrl = baseUrl ?? (() => ServerAlertService.effectiveBaseUrl),
        _apiKey = apiKey ?? (() => ServerAlertService.apiKey);

  /// Persian/English instrument search. An empty query returns an empty list without a request.
  Future<BourseResult<BourseSearchResult>> search(
    String query, {
    String? market,
    String? board,
    String? type,
    String? sector,
    bool? traded,
    int limit = 20,
  }) async {
    var q = query.trim();
    if (q.isEmpty) {
      return const BourseResult<BourseSearchResult>.ok(BourseSearchResult(query: '', items: [], stale: false));
    }
    if (q.length > maxQueryLength) q = q.substring(0, maxQueryLength);

    final safeLimit = limit < 1 ? 1 : (limit > maxSearchLimit ? maxSearchLimit : limit);
    final params = <String, String>{'q': q, 'limit': '$safeLimit'};
    void add(String key, String? value) {
      final v = value?.trim();
      if (v != null && v.isNotEmpty) params[key] = v;
    }

    add('market', market);
    add('board', board);
    add('type', type);
    add('sector', sector);
    if (traded == true) params['traded'] = 'true';

    final res = await _get('/api/iran-bourse/symbols', params);
    if (!res.isOk) return BourseResult<BourseSearchResult>.fail(res.failure!, message: res.message, httpStatus: res.httpStatus);

    final body = res.data!;
    final rawItems = body['items'];
    if (rawItems is! List) {
      return const BourseResult<BourseSearchResult>.fail(BourseFailure.badResponse, message: 'items is not a list');
    }
    final items = <BourseInstrument>[];
    for (final row in rawItems) {
      final parsed = BourseInstrument.tryParse(row);
      if (parsed != null) items.add(parsed); // unusable rows (no string id) are skipped
    }
    return BourseResult<BourseSearchResult>.ok(BourseSearchResult(
      query: body['query'] is String ? body['query'] as String : q,
      items: items,
      stale: body['stale'] == true,
    ));
  }

  /// One page of the categorized browse list (IB-16). Without [group] the server returns
  /// everything except options and futures. The first call after a server start can take a
  /// few seconds because the server loads the whole market once, hence the longer timeout.
  Future<BourseResult<BourseBoardPage>> board({
    BourseGroup? group,
    String? market,
    String? sector,
    String? type,
    bool? traded,
    String? q,
    BourseSort sort = BourseSort.value,
    bool? ascending,
    int offset = 0,
    int limit = 50,
    Duration boardTimeout = const Duration(seconds: 30),
  }) async {
    final params = <String, String>{
      'sort': sort.key,
      'limit': '${limit < 1 ? 1 : (limit > 100 ? 100 : limit)}',
      'offset': '${offset < 0 ? 0 : (offset > 100000 ? 100000 : offset)}',
    };
    void add(String key, String? value) {
      final v = value?.trim();
      if (v != null && v.isNotEmpty) params[key] = v;
    }

    if (group != null) params['group'] = group.key;
    add('market', market);
    add('sector', sector);
    add('type', type);
    var query = q?.trim();
    if (query != null && query.length > maxQueryLength) query = query.substring(0, maxQueryLength);
    add('q', query);
    if (traded != null) params['traded'] = traded ? 'true' : 'false';
    if (ascending != null) params['order'] = ascending ? 'asc' : 'desc';

    final res = await _get('/api/iran-bourse/board', params, boardTimeout);
    if (!res.isOk) {
      return BourseResult<BourseBoardPage>.fail(res.failure!, message: res.message, httpStatus: res.httpStatus);
    }
    final page = BourseBoardPage.tryParse(res.data);
    if (page == null) {
      return const BourseResult<BourseBoardPage>.fail(BourseFailure.badResponse, message: 'not a board answer');
    }
    return BourseResult<BourseBoardPage>.ok(page);
  }

  /// Full projected market catalog for on-device daily caching (`GET /api/iran-bourse/catalog`).
  Future<BourseResult<BourseBoardPage>> catalog({
    Duration catalogTimeout = const Duration(seconds: 30),
  }) async {
    final res = await _get('/api/iran-bourse/catalog', null, catalogTimeout);
    if (!res.isOk) {
      return BourseResult<BourseBoardPage>.fail(
        res.failure!,
        message: res.message,
        httpStatus: res.httpStatus,
      );
    }
    final page = BourseBoardPage.tryParse(res.data);
    if (page == null) {
      return const BourseResult<BourseBoardPage>.fail(
        BourseFailure.badResponse,
        message: 'not a catalog answer',
      );
    }
    return BourseResult<BourseBoardPage>.ok(page);
  }

  /// The gateway's classification tables (market / board / type / sector codes), as raw JSON.
  /// The filter UI (IB-11c) builds its options from this.
  Future<BourseResult<Map<String, dynamic>>> classification() async {
    final res = await _get('/api/iran-bourse/classification');
    if (!res.isOk) return BourseResult<Map<String, dynamic>>.fail(res.failure!, message: res.message, httpStatus: res.httpStatus);
    final c = res.data!['classification'];
    if (c is! Map) {
      return const BourseResult<Map<String, dynamic>>.fail(BourseFailure.badResponse, message: 'classification is not an object');
    }
    return BourseResult<Map<String, dynamic>>.ok(Map<String, dynamic>.from(c));
  }

  /// One quote. [instrumentId] must be 12-20 digits, otherwise no request is sent.
  Future<BourseResult<BourseQuote>> quote(String instrumentId) async {
    final id = instrumentId.trim();
    if (!BourseInstrument.isValidId(id)) {
      return const BourseResult<BourseQuote>.fail(BourseFailure.badRequest, message: 'instrument id must be 12-20 digits');
    }
    final res = await _get('/api/iran-bourse/quote/$id');
    if (!res.isOk) return BourseResult<BourseQuote>.fail(res.failure!, message: res.message, httpStatus: res.httpStatus);
    final q = BourseQuote.tryParse(res.data);
    if (q == null) {
      return const BourseResult<BourseQuote>.fail(BourseFailure.badResponse, message: 'quote has no valid string symbol');
    }
    return BourseResult<BourseQuote>.ok(q);
  }

  // ---- transport -------------------------------------------------------------------------

  Future<BourseResult<Map<String, dynamic>>> _get(String path, [Map<String, String>? query, Duration? timeoutOverride]) async {
    try {
      var base = _baseUrl().trim();
      while (base.endsWith('/')) {
        base = base.substring(0, base.length - 1);
      }
      var uri = Uri.parse('$base$path');
      if (query != null && query.isNotEmpty) uri = uri.replace(queryParameters: query);

      final headers = <String, String>{'Accept': 'application/json'};
      final key = _apiKey();
      if (key.isNotEmpty) headers['X-API-Key'] = key;

      final client = _client;
      final response = await (client != null
              ? client.get(uri, headers: headers)
              : http.get(uri, headers: headers))
          .timeout(timeoutOverride ?? timeout);
      return _decode(response);
    } on TimeoutException {
      return const BourseResult<Map<String, dynamic>>.fail(BourseFailure.network, message: 'timeout');
    } catch (e) {
      return BourseResult<Map<String, dynamic>>.fail(BourseFailure.network, message: '$e');
    }
  }

  BourseResult<Map<String, dynamic>> _decode(http.Response response) {
    final status = response.statusCode;
    dynamic decoded;
    try {
      decoded = jsonDecode(utf8.decode(response.bodyBytes));
    } catch (_) {
      decoded = null;
    }

    if (status == 200) {
      if (decoded is Map) {
        return BourseResult<Map<String, dynamic>>.ok(Map<String, dynamic>.from(decoded));
      }
      return BourseResult<Map<String, dynamic>>.fail(BourseFailure.badResponse, message: 'body is not a JSON object', httpStatus: status);
    }

    final detail = (decoded is Map && decoded['detail'] is String) ? decoded['detail'] as String : null;
    BourseFailure failure;
    if (status == 503) {
      failure = (detail != null && detail.toLowerCase().contains('not enabled'))
          ? BourseFailure.disabled
          : BourseFailure.unavailable;
    } else if (status == 404) {
      failure = BourseFailure.notFound;
    } else if (status == 400 || status == 422) {
      failure = BourseFailure.badRequest;
    } else if (status == 401 || status == 403) {
      failure = BourseFailure.unauthorized;
    } else if (status >= 500) {
      failure = BourseFailure.unavailable;
    } else {
      failure = BourseFailure.badResponse;
    }
    return BourseResult<Map<String, dynamic>>.fail(failure, message: detail ?? 'http $status', httpStatus: status);
  }
}
