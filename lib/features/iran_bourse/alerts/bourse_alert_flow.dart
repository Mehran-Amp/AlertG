import 'package:flutter/material.dart';

import '../../alert_engine/models/alert_rule.dart';
import '../models/bourse_board.dart';
import '../pages/bourse_browse_page.dart';
import '../pages/bourse_symbol_workspace_page.dart';
import '../services/iran_bourse_service.dart';
import 'bourse_alert_api.dart';

/// Route name of the flow's first page; used to close the whole flow after success.
const String bourseFlowRootRoute = 'iran_bourse_flow_root';

/// The Iranian Bourse "create alert" flow: browse list (with search) -> unified Symbol + Alert workspace.
///
/// It is self-contained: the shared create-alert page only opens it from one card and
/// closes itself when it reports success. [saveRule] stores the accepted rule on the device
/// (normally `repository.saveRule`); the workspace removes the server copy if that throws.
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
        builder: (browseContext) => BourseBrowsePage(
          service: service,
          onSelected: (item) => _openWorkspace(browseContext, item, saveRule, service, api),
        ),
      ),
    );
  }

  /// Opens the unified Symbol + Alert workspace directly for a symbol chosen from an embedded browse list.
  /// Completes with `true` when an alert was created, otherwise `null`.
  static Future<bool?> openDetail(
    BuildContext context, {
    required BourseBoardItem item,
    required Future<void> Function(AlertRule rule) saveRule,
    IranBourseService? service,
    BourseAlertApi? api,
  }) async {
    final rule = await Navigator.of(context).push<AlertRule>(
      MaterialPageRoute<AlertRule>(
        settings: const RouteSettings(name: bourseFlowRootRoute),
        builder: (_) => BourseSymbolWorkspacePage(
          instrumentId: item.id,
          title: item.displayTicker,
          service: service,
          api: api,
          onCreated: saveRule,
        ),
      ),
    );
    return rule != null ? true : null;
  }

  static Future<void> _openWorkspace(
    BuildContext context,
    BourseBoardItem item,
    Future<void> Function(AlertRule rule) saveRule,
    IranBourseService? service,
    BourseAlertApi? api,
  ) async {
    final rule = await Navigator.of(context).push<AlertRule>(
      MaterialPageRoute<AlertRule>(
        builder: (_) => BourseSymbolWorkspacePage(
          instrumentId: item.id,
          title: item.displayTicker,
          service: service,
          api: api,
          onCreated: saveRule,
        ),
      ),
    );
    if (rule == null || !context.mounted) return;
    final nav = Navigator.of(context);
    nav.popUntil((r) => r.settings.name == bourseFlowRootRoute || r.isFirst);
    nav.maybePop(true); // closes the root page of the flow with success
  }
}
