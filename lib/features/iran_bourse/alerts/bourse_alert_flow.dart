import 'package:flutter/material.dart';

import '../../alert_engine/models/alert_rule.dart';
import '../models/bourse_instrument.dart';
import '../models/bourse_quote.dart';
import '../pages/bourse_search_page.dart';
import '../pages/bourse_symbol_detail_page.dart';
import '../services/iran_bourse_service.dart';
import 'bourse_alert_api.dart';
import 'bourse_alert_form_page.dart';

/// Route name of the flow's first page; used to close the whole flow after success.
const String bourseFlowRootRoute = 'iran_bourse_flow_root';

/// The Iranian Bourse "create alert" flow: search -> detail -> form (IB-11e).
///
/// It is self-contained: the shared create-alert page only opens it from one card and
/// closes itself when it reports success. [saveRule] stores the accepted rule on the device
/// (normally `repository.saveRule`); the form removes the server copy if that throws.
class BourseAlertFlow {
  /// Opens the flow. Completes with `true` when an alert was created, otherwise `null`.
  static Future<bool?> open(
    BuildContext context, {
    required Future<void> Function(AlertRule rule) saveRule,
    IranBourseService? service,
    BourseAlertApi? api,
  }) {
    return Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        settings: const RouteSettings(name: bourseFlowRootRoute),
        builder: (_) => BourseSearchPage(
          service: service,
          onSelected: (instrument) => _openDetail(context, instrument, saveRule, service, api),
        ),
      ),
    );
  }

  static void _openDetail(
    BuildContext context,
    BourseInstrument instrument,
    Future<void> Function(AlertRule rule) saveRule,
    IranBourseService? service,
    BourseAlertApi? api,
  ) {
    // The search page calls onSelected instead of opening the detail page itself.
    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (detailContext) => BourseSymbolDetailPage(
          instrumentId: instrument.id,
          title: instrument.displayTicker,
          service: service,
          onCreateAlert: (quote) => _openForm(detailContext, quote, saveRule, api),
        ),
      ),
    );
  }

  static Future<void> _openForm(
    BuildContext context,
    BourseQuote quote,
    Future<void> Function(AlertRule rule) saveRule,
    BourseAlertApi? api,
  ) async {
    final rule = await Navigator.of(context).push<AlertRule>(
      MaterialPageRoute<AlertRule>(
        builder: (_) => BourseAlertFormPage(quote: quote, api: api, onCreated: saveRule),
      ),
    );
    if (rule == null || !context.mounted) return;
    final nav = Navigator.of(context);
    nav.popUntil((r) => r.settings.name == bourseFlowRootRoute || r.isFirst);
    nav.maybePop(true); // closes the root page of the flow with success
  }
}
