import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_board.dart';
import '../services/iran_bourse_service.dart';
import '../theme/bourse_text.dart';
import '../utils/bourse_format.dart';
import '../widgets/bourse_board_row.dart';
import '../widgets/bourse_session_banner.dart';
import 'bourse_symbol_detail_page.dart';

/// Browse every Bourse symbol in categorized lists, like a stock app (IB-16c).
///
/// Prices are the last known ones when the market is closed; the banner says so.
/// Nothing here creates alerts: tapping a row calls [onSelected] (the alert flow, IB-16e) or,
/// without it, opens the symbol's detail page.
///
/// When [embedded] is true, renders only the browse body (no Scaffold/AppBar) so it can live
/// inside the unified Iran Market tabbed hub without a nested header.
class BourseBrowsePage extends StatefulWidget {
  final IranBourseService? service;
  final void Function(BourseBoardItem item)? onSelected;
  final Duration debounce;
  final int pageSize;
  final bool persianDigits;
  final bool embedded;

  const BourseBrowsePage({
    super.key,
    this.service,
    this.onSelected,
    this.debounce = const Duration(milliseconds: 400),
    this.pageSize = 50,
    this.persianDigits = false,
    this.embedded = false,
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

  Widget _buildSortMenu(BuildContext context) {
    final theme = Theme.of(context);
    return PopupMenuButton<BourseSort>(
      key: const Key('bourse_sort_menu'),
      tooltip: BourseStrings.sortTitle,
      icon: Icon(Icons.sort_rounded, color: theme.colorScheme.onSurface),
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
    );
  }

  Widget _buildContent(BuildContext context, BourseBoardPage? page) {
    final theme = Theme.of(context);
    final accent = BourseText.accentColor(context);
    return Column(
      children: [
        Padding(
          padding: EdgeInsets.fromLTRB(
            AppTokens.space16,
            widget.embedded ? AppTokens.space4 : AppTokens.space12,
            AppTokens.space16,
            AppTokens.space8,
          ),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  key: const Key('bourse_board_search'),
                  controller: _search,
                  onChanged: _onSearchChanged,
                  style: TextStyle(fontSize: 13, color: theme.colorScheme.onSurface),
                  decoration: BourseText.inputDecoration(
                    context,
                    hintText: BourseStrings.browseSearchHint,
                    prefixIcon: Icon(
                      Icons.search,
                      size: 20,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ).copyWith(
                    contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  ),
                ),
              ),
              if (widget.embedded) ...[
                const SizedBox(width: 8),
                Container(
                  height: 44,
                  width: 44,
                  decoration: BoxDecoration(
                    color: BourseText.cardColor(context),
                    borderRadius: BorderRadius.circular(BourseText.inputRadius),
                    border: Border.all(color: BourseText.borderColor(context)),
                  ),
                  child: _buildSortMenu(context),
                ),
              ],
            ],
          ),
        ),
        SizedBox(
          height: 44,
          child: ListView(
            key: const Key('bourse_group_tabs'),
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: AppTokens.space16),
            children: [
              for (final g in <BourseGroup?>[null, ...BourseGroup.values])
                Padding(
                  padding: const EdgeInsets.only(left: 6),
                  child: ChoiceChip(
                    key: Key('bourse_tab_${g?.key ?? 'all'}'),
                    label: Text(_tabLabel(g)),
                    selected: _group == g,
                    showCheckmark: false,
                    labelStyle: TextStyle(
                      fontSize: 11,
                      fontWeight: _group == g ? FontWeight.bold : FontWeight.normal,
                      color: _group == g ? accent : BourseText.secondaryColor(context),
                    ),
                    selectedColor: accent.withValues(alpha: 0.15),
                    backgroundColor: BourseText.cardColor(context),
                    side: BorderSide(color: _group == g ? accent : BourseText.borderColor(context)),
                    onSelected: (_) => _setGroup(g),
                  ),
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(AppTokens.space16, AppTokens.space4, AppTokens.space16, AppTokens.space4),
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            child: FilterChip(
              key: const Key('bourse_traded_only'),
              selected: _tradedOnly,
              visualDensity: VisualDensity.compact,
              label: const Text(BourseStrings.filterTradedOnly),
              labelStyle: TextStyle(
                fontSize: 11,
                fontWeight: _tradedOnly ? FontWeight.bold : FontWeight.normal,
                color: _tradedOnly ? accent : BourseText.secondaryColor(context),
              ),
              selectedColor: accent.withValues(alpha: 0.15),
              backgroundColor: BourseText.cardColor(context),
              side: BorderSide(color: _tradedOnly ? accent : BourseText.borderColor(context)),
              onSelected: (v) {
                _tradedOnly = v;
                _reload();
              },
            ),
          ),
        ),
        if (page != null) BourseSessionBanner(session: page.session, stale: page.stale),
        Expanded(child: _body(page)),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final page = _last;
    final content = _buildContent(context, page);
    if (widget.embedded) {
      return Directionality(
        textDirection: TextDirection.rtl,
        child: content,
      );
    }
    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          backgroundColor: theme.colorScheme.surface,
          elevation: 0,
          surfaceTintColor: Colors.transparent,
          iconTheme: IconThemeData(color: theme.colorScheme.onSurface),
          title: Text(BourseStrings.marketCardTitle, style: BourseText.appBarTitle(context)),
          actions: [_buildSortMenu(context)],
        ),
        body: content,
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
                style: OutlinedButton.styleFrom(
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(BourseText.inputRadius)),
                ),
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
      child: ListView.separated(
        key: const Key('bourse_board_list'),
        controller: _scroll,
        padding: const EdgeInsets.fromLTRB(AppTokens.space16, AppTokens.space6, AppTokens.space16, AppTokens.space16),
        physics: const AlwaysScrollableScrollPhysics(),
        itemCount: _items.length + footer,
        separatorBuilder: (_, __) => const SizedBox(height: AppTokens.space8),
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
