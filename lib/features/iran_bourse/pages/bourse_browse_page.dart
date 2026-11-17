import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_board.dart';
import '../services/iran_bourse_service.dart';
import '../utils/bourse_format.dart';
import '../widgets/bourse_board_row.dart';
import '../widgets/bourse_session_banner.dart';
import 'bourse_symbol_detail_page.dart';

/// Browse every Bourse symbol in categorized lists, like a stock app (IB-16c).
///
/// Prices are the last known ones when the market is closed; the banner says so.
/// Nothing here creates alerts: tapping a row calls [onSelected] (the alert flow, IB-16e) or,
/// without it, opens the symbol's detail page.
class BourseBrowsePage extends StatefulWidget {
  final IranBourseService? service;
  final void Function(BourseBoardItem item)? onSelected;
  final Duration debounce;
  final int pageSize;
  final bool persianDigits;

  const BourseBrowsePage({
    super.key,
    this.service,
    this.onSelected,
    this.debounce = const Duration(milliseconds: 400),
    this.pageSize = 50,
    this.persianDigits = false,
  });

  @override
  State<BourseBrowsePage> createState() => _BourseBrowsePageState();
}

class _BourseBrowsePageState extends State<BourseBrowsePage> {
  late final IranBourseService _service = widget.service ?? IranBourseService();
  final TextEditingController _search = TextEditingController();
  final ScrollController _scroll = ScrollController();
  Timer? _timer;
  int _seq = 0; // answers of older requests are ignored

  BourseGroup? _group; // null = default list (everything but options/futures)
  BourseSort _sort = BourseSort.value;
  bool _tradedOnly = false;

  final List<BourseBoardItem> _items = [];
  BourseBoardPage? _last;
  Map<BourseGroup, int> _counts = const {};
  bool _loading = true;
  bool _loadingMore = false;
  BourseFailure? _failure;
  bool _moreFailed = false;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _reload();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _search.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (!_scroll.hasClients) return;
    if (_scroll.position.extentAfter < 400) _loadMore();
  }

  Future<BourseResult<BourseBoardPage>> _fetch(int offset) => _service.board(
        group: _group,
        sort: _sort,
        traded: _tradedOnly ? true : null,
        q: _search.text.trim().isEmpty ? null : _search.text.trim(),
        offset: offset,
        limit: widget.pageSize,
      );

  Future<void> _reload({bool keepRows = false}) async {
    final my = ++_seq;
    setState(() {
      _loading = true;
      _failure = null;
      _moreFailed = false;
      if (!keepRows) _items.clear();
    });
    final res = await _fetch(0);
    if (!mounted || my != _seq) return;
    setState(() {
      _loading = false;
      _loadingMore = false;
      if (res.isOk) {
        final page = res.data!;
        _items
          ..clear()
          ..addAll(page.items);
        _last = page;
        _counts = page.groupCounts;
      } else {
        _failure = res.failure;
        _items.clear();
      }
    });
  }

  Future<void> _loadMore() async {
    final page = _last;
    if (page == null || !page.hasMore || _loading || _loadingMore || _moreFailed) return;
    final my = _seq;
    setState(() => _loadingMore = true);
    final res = await _fetch(page.nextOffset);
    if (!mounted || my != _seq) return;
    setState(() {
      _loadingMore = false;
      if (res.isOk) {
        final next = res.data!;
        final known = _items.map((e) => e.id).toSet();
        _items.addAll(next.items.where((e) => !known.contains(e.id)));
        _last = next;
        _counts = next.groupCounts;
      } else {
        _moreFailed = true;
      }
    });
  }

  void _setGroup(BourseGroup? g) {
    if (g == _group) return;
    _group = g;
    _reload();
  }

  void _onSearchChanged(String _) {
    _timer?.cancel();
    _timer = Timer(widget.debounce, _reload);
  }

  void _open(BourseBoardItem item) {
    final cb = widget.onSelected;
    if (cb != null) {
      cb(item);
      return;
    }
    Navigator.of(context).push<void>(MaterialPageRoute<void>(
      builder: (_) => BourseSymbolDetailPage(
        instrumentId: item.id,
        title: item.displayTicker,
        service: _service,
        persianDigits: widget.persianDigits,
      ),
    ));
  }

  String _tabLabel(BourseGroup? g) {
    final base = g == null ? BourseStrings.tabAll : BourseStrings.groupLabel(g);
    if (g == null || _counts.isEmpty) return base;
    final n = _counts[g];
    return n == null ? base : '$base (${BourseFormat.number(n, persianDigits: widget.persianDigits)})';
  }

  @override
  Widget build(BuildContext context) {
    final page = _last;
    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        appBar: AppBar(
          title: const Text(BourseStrings.marketCardTitle),
          actions: [
            PopupMenuButton<BourseSort>(
              key: const Key('bourse_sort_menu'),
              tooltip: BourseStrings.sortTitle,
              icon: const Icon(Icons.sort),
              initialValue: _sort,
              onSelected: (s) {
                if (s == _sort) return;
                _sort = s;
                _reload();
              },
              itemBuilder: (_) => [
                for (final s in BourseSort.values)
                  PopupMenuItem<BourseSort>(
                    key: Key('bourse_sort_${s.key}'),
                    value: s,
                    child: Text(BourseStrings.sortLabel(s)),
                  ),
              ],
            ),
          ],
        ),
        body: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                  AppTokens.space16, AppTokens.space8, AppTokens.space16, AppTokens.space4),
              child: TextField(
                key: const Key('bourse_board_search'),
                controller: _search,
                onChanged: _onSearchChanged,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  hintText: BourseStrings.browseSearchHint,
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
              ),
            ),
            SizedBox(
              height: 48,
              child: ListView(
                key: const Key('bourse_group_tabs'),
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: AppTokens.space12),
                children: [
                  for (final g in <BourseGroup?>[null, ...BourseGroup.values])
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: AppTokens.space4, vertical: AppTokens.space6),
                      child: ChoiceChip(
                        key: Key('bourse_tab_${g?.key ?? 'all'}'),
                        label: Text(_tabLabel(g)),
                        selected: _group == g,
                        onSelected: (_) => _setGroup(g),
                      ),
                    ),
                ],
              ),
            ),
            SwitchListTile(
              key: const Key('bourse_traded_only'),
              dense: true,
              contentPadding: const EdgeInsets.symmetric(horizontal: AppTokens.space16),
              title: const Text(BourseStrings.filterTradedOnly),
              value: _tradedOnly,
              onChanged: (v) {
                _tradedOnly = v;
                _reload();
              },
            ),
            if (page != null) BourseSessionBanner(session: page.session, stale: page.stale),
            Expanded(child: _body(page)),
          ],
        ),
      ),
    );
  }

  Widget _body(BourseBoardPage? page) {
    if (_loading && _items.isEmpty) {
      return const Center(child: CircularProgressIndicator(key: Key('bourse_board_loading')));
    }
    if (_failure != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppTokens.space16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(BourseStrings.failureMessage(_failure!), key: const Key('bourse_failure_text'), textAlign: TextAlign.center),
              const SizedBox(height: AppTokens.space12),
              OutlinedButton(
                key: const Key('bourse_retry'),
                onPressed: _reload,
                child: const Text(BourseStrings.retry),
              ),
            ],
          ),
        ),
      );
    }
    if (_items.isEmpty) {
      return const Center(child: Text(BourseStrings.browseEmpty, key: Key('bourse_board_empty')));
    }
    final session = page?.session ?? BourseSession.unknown;
    final footer = (_loadingMore || _moreFailed) ? 1 : 0;
    return RefreshIndicator(
      onRefresh: () => _reload(keepRows: true),
      child: ListView.builder(
        key: const Key('bourse_board_list'),
        controller: _scroll,
        physics: const AlwaysScrollableScrollPhysics(),
        itemCount: _items.length + footer,
        itemBuilder: (_, i) {
          if (i >= _items.length) {
            if (_moreFailed) {
              return TextButton(
                key: const Key('bourse_more_retry'),
                onPressed: () {
                  setState(() => _moreFailed = false);
                  _loadMore();
                },
                child: const Text(BourseStrings.browseLoadMoreFailed),
              );
            }
            return const Padding(
              padding: EdgeInsets.all(AppTokens.space16),
              child: Center(child: CircularProgressIndicator(key: Key('bourse_more_loading'))),
            );
          }
          final item = _items[i];
          return BourseBoardRow(
            item: item,
            session: session,
            persianDigits: widget.persianDigits,
            onTap: () => _open(item),
          );
        },
      ),
    );
  }
}
