import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../../alert_engine/models/alert_rule.dart';
import '../alerts/bourse_alert_api.dart';
import '../alerts/bourse_alert_form_page.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_quote.dart';
import '../services/iran_bourse_service.dart';
import '../theme/bourse_text.dart';

/// Unified Iranian Bourse Symbol + Alert Workspace.
///
/// Loads the live quote for [instrumentId] and immediately presents [BourseAlertFormPage]
/// with live market metrics, visual daily band gauge, top-of-book order strip, ETF NAV
/// bubble, and tap-to-fill target selection — eliminating the redundant Detail -> Form hop.
///
/// Pulling to refresh or tapping the AppBar refresh button updates the live quote in place
/// while preserving everything the user has typed into the alert builder.
class BourseSymbolWorkspacePage extends StatefulWidget {
  /// TSETMC instrument id. Always a String (rule N6).
  final String instrumentId;

  /// Initial title shown while the quote is loading.
  final String? title;

  /// Saves the accepted rule on the device. Throwing means "could not save".
  final Future<void> Function(AlertRule rule) onCreated;

  /// For tests; defaults to the app's own server connections.
  final IranBourseService? service;
  final BourseAlertApi? api;

  /// Optional periodic auto-refresh interval while the workspace is open.
  final Duration? autoRefresh;
  final bool persianDigits;

  const BourseSymbolWorkspacePage({
    super.key,
    required this.instrumentId,
    required this.onCreated,
    this.title,
    this.service,
    this.api,
    this.autoRefresh,
    this.persianDigits = false,
  });

  @override
  State<BourseSymbolWorkspacePage> createState() => _BourseSymbolWorkspacePageState();
}

class _BourseSymbolWorkspacePageState extends State<BourseSymbolWorkspacePage> {
  late final IranBourseService _service = widget.service ?? IranBourseService();

  BourseQuote? _quote;
  BourseFailure? _failure;
  BourseFailure? _refreshFailure;
  bool _loading = true;
  bool _refreshing = false;
  int _requestSeq = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    final every = widget.autoRefresh;
    if (every != null) {
      _timer = Timer.periodic(every, (_) => _load(isRefresh: true));
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load({bool isRefresh = false}) async {
    final seq = ++_requestSeq;
    if (isRefresh && mounted) {
      setState(() => _refreshing = true);
    }
    final res = await _service.quote(widget.instrumentId);
    if (!mounted || seq != _requestSeq) return;
    setState(() {
      _loading = false;
      _refreshing = false;
      if (res.isOk) {
        _quote = res.data;
        _failure = null;
        _refreshFailure = null;
      } else if (_quote == null) {
        _failure = res.failure;
      } else {
        _refreshFailure = res.failure;
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
    final quote = _quote;
    if (quote != null) {
      return BourseAlertFormPage(
        quote: quote,
        onCreated: widget.onCreated,
        api: widget.api,
        persianDigits: widget.persianDigits,
        onRefresh: () => _load(isRefresh: true),
        refreshing: _refreshing,
        refreshError: _refreshFailure != null ? BourseStrings.failureMessage(_refreshFailure!) : null,
      );
    }

    final theme = Theme.of(context);
    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          backgroundColor: theme.colorScheme.surface,
          elevation: 0,
          surfaceTintColor: Colors.transparent,
          iconTheme: IconThemeData(color: theme.colorScheme.onSurface),
          title: Text(widget.title ?? BourseStrings.title, style: BourseText.appBarTitle(context)),
        ),
        body: _loading ? _buildLoading() : _buildFailure(),
      ),
    );
  }

  Widget _buildLoading() {
    return const Center(child: CircularProgressIndicator(key: Key('bourse_loading')));
  }

  Widget _buildFailure() {
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
              style: BourseText.body(context),
            ),
            const SizedBox(height: AppTokens.space16),
            FilledButton(
              key: const Key('bourse_retry'),
              style: FilledButton.styleFrom(
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(BourseText.inputRadius),
                ),
              ),
              onPressed: _retry,
              child: const Text(BourseStrings.retry),
            ),
          ],
        ),
      ),
    );
  }
}
