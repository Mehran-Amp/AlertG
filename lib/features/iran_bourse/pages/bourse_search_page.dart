import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_filters.dart';
import '../models/bourse_instrument.dart';
import '../services/iran_bourse_service.dart';
import '../theme/bourse_text.dart';
import '../utils/bourse_format.dart';
import 'bourse_symbol_detail_page.dart';

/// Persian search for Bourse instruments with market / type filters.
///
/// Tapping a result calls [onSelected] when given (used by the alert flow in IB-11d/e);
/// otherwise it opens the detail page.
class BourseSearchPage extends StatefulWidget {
  /// For tests; defaults to the app's own server connection.
  final IranBourseService? service;
  final void Function(BourseInstrument instrument)? onSelected;

  /// Wait after the last keystroke before searching.
  final Duration debounce;

  final bool persianDigits;

  const BourseSearchPage({
    super.key,
    this.service,
    this.onSelected,
    this.debounce = const Duration(milliseconds: 300),
    this.persianDigits = false,
  });

  @override
  State<BourseSearchPage> createState() => _BourseSearchPageState();
}

class _BourseSearchPageState extends State<BourseSearchPage> {
  late final IranBourseService _service = widget.service ?? IranBourseService();
  final TextEditingController _controller = TextEditingController();
  Timer? _debounce;
  int _seq = 0; // only the newest request may update the screen

  String _query = '';
  String? _market;
  String? _type;
  bool _onlyTraded = false;

  BourseFilterOptions _options = BourseFilterOptions.empty;
  BourseSearchResult? _result;
  BourseFailure? _failure;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _loadOptions();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  Future<void> _loadOptions() async {
    final res = await _service.classification();
    if (!mounted || !res.isOk) return; // filters simply stay empty; search still works
    setState(() => _options = BourseFilterOptions.fromClassification(res.data));
  }

  void _onQueryChanged(String text) {
    _query = text.trim();
    _debounce?.cancel();
    if (_query.isEmpty) {
      _seq++; // drop any answer still on its way
      setState(() {
        _result = null;
        _failure = null;
        _loading = false;
      });
      return;
    }
    _debounce = Timer(widget.debounce, _search);
  }

  void _onFilterChanged() {
    _debounce?.cancel();
    if (_query.isNotEmpty) _search();
  }

  Future<void> _search() async {
    final q = _query;
    if (q.isEmpty) return;
    final seq = ++_seq;
    setState(() {
      _loading = true;
      _failure = null;
    });
    final res = await _service.search(
      q,
      market: _market,
      type: _type,
      traded: _onlyTraded ? true : null,
    );
    if (!mounted || seq != _seq) return;
    setState(() {
      _loading = false;
      if (res.isOk) {
        _result = res.data;
        _failure = null;
      } else {
        _result = null;
        _failure = res.failure;
      }
    });
  }

  void _open(BourseInstrument instrument) {
    final select = widget.onSelected;
    if (select != null) {
      select(instrument);
      return;
    }
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => BourseSymbolDetailPage(
        instrumentId: instrument.id,
        title: instrument.displayTicker,
        service: _service,
        persianDigits: widget.persianDigits,
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        appBar: AppBar(title: const Text(BourseStrings.title)),
        body: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                  AppTokens.space16, AppTokens.space12, AppTokens.space16, AppTokens.space8),
              child: TextField(
                key: const Key('bourse_search_field'),
                controller: _controller,
                onChanged: _onQueryChanged,
                textInputAction: TextInputAction.search,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  hintText: BourseStrings.searchHint,
                  border: OutlineInputBorder(),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppTokens.space16),
              child: Row(
                children: [
                  Expanded(
                    child: _dropdown(
                      const Key('bourse_market_filter'),
                      BourseStrings.filterMarket,
                      _market,
                      _options.markets,
                      (v) {
                        setState(() => _market = v);
                        _onFilterChanged();
                      },
                    ),
                  ),
                  const SizedBox(width: AppTokens.space12),
                  Expanded(
                    child: _dropdown(
                      const Key('bourse_type_filter'),
                      BourseStrings.filterType,
                      _type,
                      _options.types,
                      (v) {
                        setState(() => _type = v);
                        _onFilterChanged();
                      },
                    ),
                  ),
                ],
              ),
            ),
            SwitchListTile(
              key: const Key('bourse_traded_switch'),
              dense: true,
              title: const Text(BourseStrings.filterOnlyTraded),
              value: _onlyTraded,
              onChanged: (v) {
                setState(() => _onlyTraded = v);
                _onFilterChanged();
              },
            ),
            if (_loading) const LinearProgressIndicator(key: Key('bourse_search_progress')),
            Expanded(child: _buildContent()),
          ],
        ),
      ),
    );
  }

  Widget _dropdown(
    Key key,
    String label,
    String? value,
    List<BourseFilterOption> options,
    ValueChanged<String?> onChanged,
  ) {
    return DropdownButton<String?>(
      key: key,
      isExpanded: true,
      value: value,
      hint: Text(label),
      items: [
        DropdownMenuItem<String?>(
          value: null,
          child: Text('$label: ${BourseStrings.filterAll}'),
        ),
        for (final o in options)
          DropdownMenuItem<String?>(
            value: o.code,
            child: Text(o.label, overflow: TextOverflow.ellipsis),
          ),
      ],
      onChanged: options.isEmpty ? null : onChanged,
    );
  }

  Widget _buildContent() {
    final failure = _failure;
    if (failure != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppTokens.space24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                BourseStrings.failureMessage(failure),
                key: const Key('bourse_failure_text'),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppTokens.space16),
              FilledButton(
                key: const Key('bourse_retry'),
                onPressed: _search,
                child: const Text(BourseStrings.retry),
              ),
            ],
          ),
        ),
      );
    }

    final result = _result;
    if (result == null) {
      if (_loading) return const Center(child: CircularProgressIndicator());
      return Center(
        child: Text(
          BourseStrings.searchEmptyPrompt,
          key: const Key('bourse_prompt'),
          style: BourseText.secondary(context),
        ),
      );
    }

    if (result.items.isEmpty) {
      return const Center(
        child: Text(BourseStrings.searchNoResults, key: Key('bourse_no_results')),
      );
    }

    return ListView(
      children: [
        if (result.stale)
          const Padding(
            padding: EdgeInsets.all(AppTokens.space12),
            child: Text(BourseStrings.searchStaleNote, key: Key('bourse_stale_note')),
          ),
        for (final item in result.items) _tile(context, item),
      ],
    );
  }

  Widget _tile(BuildContext context, BourseInstrument i) {
    final d = widget.persianDigits;
    final subtitleParts = <String>[
      if (i.name.isNotEmpty && i.name != i.displayTicker) i.name,
      if (i.typeLabel != null) i.typeLabel!,
    ];
    final hasPrice = i.last != null && i.last! > 0;
    final pct = i.lastChangePct;
    final pctColor = (pct == null || pct == 0)
        ? BourseText.secondaryColor(context)
        : (pct > 0 ? AppTokens.positive : AppTokens.negative);

    return ListTile(
      key: ValueKey('bourse_item_${i.id}'),
      title: Text(i.displayTicker),
      subtitle: subtitleParts.isEmpty
          ? null
          : Text(subtitleParts.join(' · '), maxLines: 2, overflow: TextOverflow.ellipsis),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            BourseFormat.rial(hasPrice ? i.last : null, persianDigits: d),
            textDirection: TextDirection.ltr,
          ),
          Text(
            BourseFormat.signedPercent(pct, persianDigits: d),
            textDirection: TextDirection.ltr,
            style: TextStyle(color: pctColor, fontSize: 12),
          ),
        ],
      ),
      onTap: () => _open(i),
    );
  }
}
