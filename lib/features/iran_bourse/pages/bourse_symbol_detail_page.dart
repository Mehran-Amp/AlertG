import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_quote.dart';
import '../services/iran_bourse_service.dart';
import '../theme/bourse_text.dart';
import '../widgets/bourse_quote_card.dart';

/// Detail page of one Bourse instrument (a [BourseQuoteCard] with loading and error states).
///
/// The "create alert" button appears only when [onCreateAlert] is given (wired in IB-11d/e).
class BourseSymbolDetailPage extends StatefulWidget {
  /// TSETMC instrument id. Always a String (rule N6).
  final String instrumentId;

  /// Shown in the app bar; falls back to the generic Bourse title.
  final String? title;

  /// For tests; defaults to the app's own server connection.
  final IranBourseService? service;

  /// Called with the loaded quote when the user taps "create alert".
  final void Function(BourseQuote quote)? onCreateAlert;

  /// When set, the quote is refreshed on this interval while the page is open.
  final Duration? autoRefresh;

  final bool persianDigits;

  const BourseSymbolDetailPage({
    super.key,
    required this.instrumentId,
    this.title,
    this.service,
    this.onCreateAlert,
    this.autoRefresh,
    this.persianDigits = false,
  });

  @override
  State<BourseSymbolDetailPage> createState() => _BourseSymbolDetailPageState();
}

class _BourseSymbolDetailPageState extends State<BourseSymbolDetailPage> {
  late final IranBourseService _service = widget.service ?? IranBourseService();

  BourseQuote? _quote;
  BourseFailure? _failure; // set only while there is no quote to show
  BourseFailure? _refreshFailure; // a refresh failed but an older quote is still shown
  bool _loading = true;
  int _requestSeq = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    final every = widget.autoRefresh;
    if (every != null) {
      _timer = Timer.periodic(every, (_) => _load());
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    final seq = ++_requestSeq;
    final res = await _service.quote(widget.instrumentId);
    if (!mounted || seq != _requestSeq) return;
    setState(() {
      _loading = false;
      if (res.isOk) {
        _quote = res.data;
        _failure = null;
        _refreshFailure = null;
      } else if (_quote == null) {
        _failure = res.failure;
      } else {
        _refreshFailure = res.failure; // keep showing the last good quote
      }
    });
  }

  void _retry() {
    setState(() {
      _loading = true;
      _failure = null;
    });
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        appBar: AppBar(title: Text(widget.title ?? BourseStrings.title)),
        body: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    final quote = _quote;
    if (quote != null) {
      final refreshFailure = _refreshFailure;
      return RefreshIndicator(
        onRefresh: () async {
          await _load();
        },
        child: ListView(
          padding: const EdgeInsets.all(AppTokens.space16),
          children: [
            if (refreshFailure != null)
              Padding(
                padding: const EdgeInsets.only(bottom: AppTokens.space12),
                child: Text(
                  BourseStrings.failureMessage(refreshFailure),
                  key: const Key('bourse_refresh_failure'),
                  style: BourseText.secondary(context).copyWith(color: BourseText.warningColor(context)),
                ),
              ),
            BourseQuoteCard(quote: quote, persianDigits: widget.persianDigits),
            if (widget.onCreateAlert != null) ...[
              const SizedBox(height: AppTokens.space16),
              FilledButton(
                key: const Key('bourse_create_alert'),
                onPressed: () => widget.onCreateAlert!(quote),
                child: const Text(BourseStrings.createAlert),
              ),
            ],
          ],
        ),
      );
    }

    if (_loading) {
      return const Center(child: CircularProgressIndicator(key: Key('bourse_loading')));
    }

    final failure = _failure ?? BourseFailure.badResponse;
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
              onPressed: _retry,
              child: const Text(BourseStrings.retry),
            ),
          ],
        ),
      ),
    );
  }
}
