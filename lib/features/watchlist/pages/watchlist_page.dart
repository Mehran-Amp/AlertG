import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../core/localization/app_strings.dart';
import '../../../core/services/google_auth_service.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/utils/crypto_icons.dart';
import '../../../core/utils/format_utils.dart';
import '../../alert_engine/models/alert_rule.dart';
import '../../alert_engine/repositories/json_alert_rule_repository.dart';
import '../../alert_engine/scheduler/scheduler_service.dart';
import '../../exchanges/registry/exchange_registry.dart';
import '../../settings/services/settings_service.dart';
import '../../widgets/alert_home_widget.dart';
import '../../widgets/server_status_button.dart';
import 'create_alert_flow.dart';

/// The Main Screen of Alarmer: Personal Price Alerts.
/// Highlights the latest checked price prominently (large and bold).
/// Supports full tap-to-edit and a 100% reliable in-app floating undo toast.
class TargetProgressState {
  final double progressFactor; // 0.0 to 1.0
  final Color? color;          // TradingView Green (0xFF089981), TradingView Red (0xFFF23645), or null
  final int percentageInt;     // 0 to 100

  const TargetProgressState({
    required this.progressFactor,
    required this.color,
    required this.percentageInt,
  });
}

TargetProgressState _computeTargetProgressState(AlertRule rule) {
  const Color tvGreen = Color(0xFF089981); // Official TradingView Bullish Green
  const Color tvRed = Color(0xFFF23645);   // Official TradingView Bearish Red

  final displayPrice = rule.currentDisplayPrice;
  final basePrice = rule.basePrice;

  if (displayPrice == null || displayPrice <= 0 || basePrice == null || basePrice <= 0) {
    return const TargetProgressState(progressFactor: 0.0, color: null, percentageInt: 0);
  }

  double progress = 0.0;
  Color? activeColor;

  switch (rule.conditionType) {
    case AlertConditionType.priceThreshold:
      if (rule.direction == AlertDirection.bothSides) {
        // Both-Way Channel / Resistance & Support
        final upper = rule.upperTargetPrice;
        final lower = rule.lowerTargetPrice;

        if (displayPrice > basePrice) {
          // Bullish movement towards upper resistance target
          activeColor = tvGreen;
          if (upper != null && upper > basePrice) {
            progress = (displayPrice - basePrice) / (upper - basePrice);
          } else if (upper != null && upper > 0) {
            progress = (displayPrice - basePrice) / upper;
          }
        } else if (displayPrice < basePrice) {
          // Bearish movement towards lower support target
          activeColor = tvRed;
          if (lower != null && lower < basePrice && basePrice > lower) {
            progress = (basePrice - displayPrice) / (basePrice - lower);
          } else if (lower != null && lower > 0) {
            progress = (basePrice - displayPrice) / basePrice;
          }
        } else {
          // No price movement -> Empty Layer 2
          progress = 0.0;
          activeColor = null;
        }
      } else if (rule.direction == AlertDirection.above) {
        // Single Target: Above
        final target = rule.targetPrice ?? 0.0;
        if (displayPrice > basePrice) {
          activeColor = tvGreen;
          if (target > basePrice) {
            progress = (displayPrice - basePrice) / (target - basePrice);
          } else if (target > 0) {
            progress = displayPrice / target;
          }
        } else {
          // Moving in opposite direction (downward) -> Empty Layer 2
          progress = 0.0;
          activeColor = null;
        }
      } else if (rule.direction == AlertDirection.below) {
        // Single Target: Below
        final target = rule.targetPrice ?? 0.0;
        if (displayPrice < basePrice) {
          activeColor = tvRed;
          if (basePrice > target && target > 0) {
            progress = (basePrice - displayPrice) / (basePrice - target);
          } else if (basePrice > 0) {
            progress = (basePrice - displayPrice) / basePrice;
          }
        } else {
          // Moving in opposite direction (upward) -> Empty Layer 2
          progress = 0.0;
          activeColor = null;
        }
      }
      break;

    case AlertConditionType.percentChange:
      final targetPct = rule.percent ?? 0.0;
      final actualPct = ((displayPrice - basePrice) / basePrice) * 100.0;

      if (rule.direction == AlertDirection.above) {
        if (actualPct > 0) {
          activeColor = tvGreen;
          progress = targetPct > 0 ? (actualPct / targetPct) : 0.0;
        } else {
          progress = 0.0;
          activeColor = null;
        }
      } else if (rule.direction == AlertDirection.below) {
        if (actualPct < 0) {
          activeColor = tvRed;
          progress = targetPct > 0 ? (actualPct.abs() / targetPct) : 0.0;
        } else {
          progress = 0.0;
          activeColor = null;
        }
      } else {
        // Both directions (% change)
        if (actualPct > 0) {
          activeColor = tvGreen;
          progress = targetPct > 0 ? (actualPct / targetPct) : 0.0;
        } else if (actualPct < 0) {
          activeColor = tvRed;
          progress = targetPct > 0 ? (actualPct.abs() / targetPct) : 0.0;
        } else {
          progress = 0.0;
          activeColor = null;
        }
      }
      break;

    case AlertConditionType.absolutePriceChange:
      final delta = rule.deltaAbsolute ?? 0.0;
      final diff = displayPrice - basePrice;

      if (rule.direction == AlertDirection.above) {
        if (diff > 0) {
          activeColor = tvGreen;
          progress = delta > 0 ? (diff / delta) : 0.0;
        } else {
          progress = 0.0;
          activeColor = null;
        }
      } else if (rule.direction == AlertDirection.below) {
        if (diff < 0) {
          activeColor = tvRed;
          progress = delta > 0 ? (diff.abs() / delta) : 0.0;
        } else {
          progress = 0.0;
          activeColor = null;
        }
      } else {
        if (diff > 0) {
          activeColor = tvGreen;
          progress = delta > 0 ? (diff / delta) : 0.0;
        } else if (diff < 0) {
          activeColor = tvRed;
          progress = delta > 0 ? (diff.abs() / delta) : 0.0;
        } else {
          progress = 0.0;
          activeColor = null;
        }
      }
      break;

    case AlertConditionType.volumeChange:
      activeColor = tvGreen;
      progress = 0.5;
      break;
  }

  final clampedProgress = progress.clamp(0.0, 1.0);
  final pctInt = (clampedProgress * 100).round();

  return TargetProgressState(
    progressFactor: clampedProgress,
    color: activeColor,
    percentageInt: pctInt,
  );
}

class WatchlistPage extends StatefulWidget {
  const WatchlistPage({super.key});

  @override
  State<WatchlistPage> createState() => _WatchlistPageState();
}

class _WatchlistPageState extends State<WatchlistPage> {
  final Set<String> _checkingRuleUuids = {};
  AlertRule? _recentlyDeletedRule;
  Timer? _undoToastTimer;
  Timer? _countdownTimer;
  bool _isRefreshingAll = false;

  @override
  void initState() {
    super.initState();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    _undoToastTimer?.cancel();
    super.dispose();
  }

  Future<void> _refreshAllAlerts(
    BuildContext context,
    JsonAlertRuleRepository repository,
    SchedulerService scheduler,
    String lang,
  ) async {
    if (_isRefreshingAll) return;
    setState(() => _isRefreshingAll = true);
    final theme = Theme.of(context);
    final isFa = lang == 'fa' || lang == 'ar' || lang == 'ckb';

    try {
      final activeRules = repository.allRules.where((r) => r.isActive).toList();
      if (activeRules.isEmpty) {
        if (context.mounted) {
          ScaffoldMessenger.of(context).hideCurrentSnackBar();
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              content: Text(isFa ? 'هیچ هشدار فعالی برای بروزرسانی وجود ندارد.' : 'No active alerts to refresh.'),
              backgroundColor: theme.colorScheme.surfaceContainerHighest,
              duration: const Duration(seconds: 2),
            ),
          );
        }
        return;
      }

      if (context.mounted) {
        ScaffoldMessenger.of(context).hideCurrentSnackBar();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            content: Row(
              children: [
                SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2, color: theme.colorScheme.primary),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    isFa
                        ? 'در حال استعلام هوشمند قیمت‌ها (با سرور پشتیبان)... لطفا شکیبا باشید.'
                        : 'Smart fetching live prices via exchange & server proxy...',
                    style: const TextStyle(fontSize: 12),
                  ),
                ),
              ],
            ),
            backgroundColor: theme.colorScheme.surfaceContainerHighest,
            duration: const Duration(seconds: 4),
          ),
        );
      }

      int successCount = 0;
      for (final rule in activeRules) {
        final ok = await scheduler.checkRuleNow(rule);
        if (ok) successCount++;
      }

      if (context.mounted) {
        ScaffoldMessenger.of(context).hideCurrentSnackBar();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            content: Text(
              isFa
                  ? 'بروزرسانی دقیق نرخ‌ها انجام شد ($successCount از ${activeRules.length} نماد با موفقیت به‌روزرسانی شدند)'
                  : 'Successfully verified $successCount of ${activeRules.length} symbols.',
            ),
            backgroundColor: theme.colorScheme.primary,
            duration: const Duration(seconds: 2),
          ),
        );
      }
    } catch (_) {
    } finally {
      if (mounted) {
        setState(() => _isRefreshingAll = false);
      }
    }
  }

  Future<void> _openCreateFlow() async {
    final settingsService = context.read<SettingsService>();
    final settings = settingsService.settings;
    final lang = settings.language;

    // Ensure user has connected Google Account for cloud sync and telegram integration
    if (!settings.isSignedInWithGoogle) {
      final signedIn = await GoogleAuthService.promptGoogleSignIn(context, settingsService, lang);
      if (!signedIn) {
        return; // User cancelled login dialog
      }
    }

    if (!mounted) return;
    final registry = context.read<ExchangeRegistry>();
    final repository = context.read<JsonAlertRuleRepository>();

    CreateAlertFlow.open(
      context,
      registry: registry,
      repository: repository,
    );
  }

  void _openEditFlow(AlertRule rule) {
    final registry = context.read<ExchangeRegistry>();
    final repository = context.read<JsonAlertRuleRepository>();

    CreateAlertFlow.open(
      context,
      registry: registry,
      repository: repository,
      initialRule: rule,
    );
  }

  void _onRuleDismissed(AlertRule rule, JsonAlertRuleRepository repository) {
    _undoToastTimer?.cancel();
    repository.deleteRule(rule.uuid);
    setState(() {
      _recentlyDeletedRule = rule;
    });

    _undoToastTimer = Timer(const Duration(milliseconds: 3800), () {
      if (mounted) {
        setState(() {
          _recentlyDeletedRule = null;
        });
      }
    });
  }

  void _undoDelete(JsonAlertRuleRepository repository) {
    if (_recentlyDeletedRule != null) {
      _undoToastTimer?.cancel();
      repository.saveRule(_recentlyDeletedRule!);
      setState(() {
        _recentlyDeletedRule = null;
      });
    }
  }

  void _dismissUndoToast() {
    _undoToastTimer?.cancel();
    setState(() {
      _recentlyDeletedRule = null;
    });
  }

  Future<void> _manualCheck(AlertRule rule, SchedulerService scheduler, String lang) async {
    setState(() => _checkingRuleUuids.add(rule.uuid));
    try {
      final success = await scheduler.checkRuleNow(rule);
      if (mounted) {
        final theme = Theme.of(context);
        ScaffoldMessenger.of(context).hideCurrentSnackBar();
        if (success) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              content: Text('${AppStrings.get('check_price_done', lang)}${rule.pair.displayName}'),
              backgroundColor: theme.colorScheme.surfaceContainerHighest,
              duration: const Duration(seconds: 2),
            ),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              content: Text(AppStrings.get('offline_error', lang)),
              backgroundColor: theme.colorScheme.surfaceContainerHighest,
              duration: const Duration(seconds: 3),
            ),
          );
        }
      }
    } finally {
      if (mounted) {
        setState(() => _checkingRuleUuids.remove(rule.uuid));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final repository = context.read<JsonAlertRuleRepository>();
    final scheduler = context.read<SchedulerService>();
    final settingsService = context.watch<SettingsService>();
    final lang = settingsService.settings.language;
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: theme.colorScheme.surface,
        elevation: 0,
        titleSpacing: 16,
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(AppTokens.space6),
              decoration: BoxDecoration(
                color: theme.colorScheme.primary.withValues(alpha: 0.15),
                borderRadius: AppTokens.borderSmall,
              ),
              child: Icon(Icons.alarm_on_rounded, color: theme.colorScheme.primary, size: 20),
            ),
            const SizedBox(width: 8),
            Flexible(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    AppStrings.get('my_alerts', lang),
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: theme.colorScheme.onSurface,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    AppStrings.get('smart_alerts_desc', lang),
                    style: TextStyle(
                      fontSize: 10,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          ServerStatusButton(lang: lang),
          IconButton(
            icon: _isRefreshingAll
                ? SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.2,
                      color: theme.colorScheme.primary,
                    ),
                  )
                : Icon(
                    Icons.sync_rounded,
                    size: 24,
                    color: theme.colorScheme.primary,
                  ),
            tooltip: lang == 'fa' ? 'به‌روزرسانی آنی تمامی نمادها' : 'Refresh All Symbols',
            onPressed: _isRefreshingAll
                ? null
                : () => _refreshAllAlerts(context, repository, scheduler, lang),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
            child: ElevatedButton.icon(
              onPressed: _openCreateFlow,
              icon: const Icon(Icons.add_rounded, size: 18),
              label: Text(
                AppStrings.get('new_alert', lang),
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: theme.colorScheme.primary,
                foregroundColor: Colors.white,
                elevation: 0,
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 0),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
            ),
          ),
        ],
      ),
      body: Stack(
        children: [
          StreamBuilder<List<AlertRule>>(
            stream: repository.watchAllRules(),
            builder: (context, snapshot) {
              final rules = snapshot.data ?? repository.allRules;

              if (rules.isEmpty) {
                return _buildEmptyState(lang, theme);
              }

              return ReorderableListView.builder(
                padding: const EdgeInsets.fromLTRB(
                  AppTokens.space16,
                  AppTokens.space12,
                  AppTokens.space16,
                  80.0,
                ),
                itemCount: rules.length,
                onReorder: (oldIndex, newIndex) {
                  repository.reorderRules(oldIndex, newIndex);
                },
                itemBuilder: (context, index) {
                  final rule = rules[index];
                  return Padding(
                    key: ValueKey(rule.uuid),
                    padding: const EdgeInsets.only(bottom: AppTokens.space12),
                    child: _buildAlertCard(rule, repository, scheduler, lang),
                  );
                },
              );
            },
          ),

          // 100% Reliable In-App Floating Undo Toast
          AnimatedPositioned(
            duration: const Duration(milliseconds: 280),
            curve: Curves.easeOutCubic,
            left: 16,
            right: 16,
            bottom: _recentlyDeletedRule != null ? 20 : -100,
            child: _buildUndoToast(lang, theme, repository),
          ),
        ],
      ),
    );
  }

  Widget _buildUndoToast(String lang, ThemeData theme, JsonAlertRuleRepository repository) {
    if (_recentlyDeletedRule == null) return const SizedBox.shrink();

    final ruleName = _recentlyDeletedRule!.pair.displayName;

    return Material(
      elevation: 10,
      borderRadius: BorderRadius.circular(14),
      color: theme.colorScheme.surfaceContainerHighest,
      shadowColor: Colors.black.withValues(alpha: 0.35),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: theme.dividerColor),
        ),
        child: Row(
          children: [
            const Icon(Icons.delete_outline_rounded, color: AppTokens.negative, size: 22),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                '${AppStrings.get('alert_deleted_msg', lang)}$ruleName',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: theme.colorScheme.onSurface,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            TextButton.icon(
              onPressed: () => _undoDelete(repository),
              icon: Icon(Icons.undo_rounded, size: 16, color: theme.colorScheme.primary),
              label: Text(
                AppStrings.get('undo_action', lang),
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                  color: theme.colorScheme.primary,
                ),
              ),
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                backgroundColor: theme.colorScheme.primary.withValues(alpha: 0.12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
            const SizedBox(width: 4),
            IconButton(
              icon: Icon(Icons.close_rounded, size: 18, color: theme.colorScheme.onSurface.withValues(alpha: 0.5)),
              onPressed: _dismissUndoToast,
              visualDensity: VisualDensity.compact,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAlertCard(
    AlertRule rule,
    JsonAlertRuleRepository repository,
    SchedulerService scheduler,
    String lang,
  ) {
    final theme = Theme.of(context);
    final isTriggeredOneShot = rule.isTriggered && rule.triggerMode == TriggerMode.oneShot;
    final isChecking = _checkingRuleUuids.contains(rule.uuid);
    final textMuted = theme.colorScheme.onSurface.withValues(alpha: 0.45);

    final displayPrice = rule.currentDisplayPrice;
    final basePrice = rule.basePrice;

    double? changePercent;
    if (displayPrice != null && basePrice != null && basePrice > 0) {
      changePercent = ((displayPrice - basePrice) / basePrice) * 100.0;
    }

    // Compute Target Progress State (TradingView Green/Red two-layer bar)
    final progState = _computeTargetProgressState(rule);

    return Dismissible(
      key: Key(rule.uuid),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: AppTokens.space20),
        decoration: BoxDecoration(
          color: AppTokens.negative,
          borderRadius: BorderRadius.circular(18),
        ),
        child: const Icon(Icons.delete_sweep_rounded, color: Colors.white, size: 26),
      ),
      onDismissed: (_) => _onRuleDismissed(rule, repository),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(18),
        child: InkWell(
          onTap: () => _openEditFlow(rule),
          borderRadius: BorderRadius.circular(18),
          child: Directionality(
            textDirection: TextDirection.ltr,
            child: SizedBox(
              height: 184,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      theme.colorScheme.surface,
                      theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
                    ],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(
                    color: isTriggeredOneShot
                        ? AppTokens.warning.withValues(alpha: 0.75)
                        : (rule.isActive
                            ? theme.colorScheme.primary.withValues(alpha: 0.25)
                            : theme.dividerColor),
                    width: isTriggeredOneShot ? 1.5 : 1.1,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.12),
                      blurRadius: 10,
                      offset: const Offset(0, 3),
                    ),
                  ],
                ),
                child: Builder(
                  builder: (context) {
                    const cardLang = 'en';
                    final prevPrice = rule.previousPrice ?? basePrice;
                    final showPrevious = prevPrice != null &&
                        displayPrice != null &&
                        (prevPrice - displayPrice).abs() > 1e-8;

                    return Column(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // === ROW 1: Hero Asset + Dedicated Wide Title & Exchange + Switch ===
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.all(2),
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: theme.colorScheme.primary.withValues(alpha: 0.3),
                                  width: 1.2,
                                ),
                              ),
                              child: CryptoIcons.buildLogo(rule.baseCurrency, size: 32),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Row(
                                    children: [
                                      Flexible(
                                        child: Text(
                                          rule.pair.displayName,
                                          style: TextStyle(
                                            fontWeight: FontWeight.w800,
                                            fontSize: 14,
                                            color: rule.isActive ? theme.colorScheme.onSurface : textMuted,
                                          ),
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                      if (rule.customNote != null && rule.customNote!.trim().isNotEmpty) ...[
                                        const SizedBox(width: 4),
                                        Icon(Icons.edit_note_rounded, size: 14, color: theme.colorScheme.primary),
                                      ],
                                    ],
                                  ),
                                  const SizedBox(height: 2),
                                  Row(
                                    children: [
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                                        decoration: BoxDecoration(
                                          color: theme.colorScheme.surfaceContainerHighest,
                                          borderRadius: BorderRadius.circular(4),
                                        ),
                                        child: Text(
                                          _getExchangeDisplayName(rule.exchangeId, cardLang).toUpperCase(),
                                          maxLines: 1,
                                          softWrap: false,
                                          overflow: TextOverflow.ellipsis,
                                          style: TextStyle(
                                            fontSize: 8.5,
                                            fontWeight: FontWeight.bold,
                                            color: rule.isActive ? theme.colorScheme.primary : textMuted,
                                            letterSpacing: 0.3,
                                          ),
                                        ),
                                      ),
                                      const SizedBox(width: 5),
                                      Flexible(
                                        child: Text(
                                          rule.marketSymbol.isNotEmpty ? rule.marketSymbol : rule.baseCurrency,
                                          style: TextStyle(
                                            fontSize: 9.5,
                                            fontFamily: 'monospace',
                                            fontWeight: FontWeight.w600,
                                            color: textMuted,
                                          ),
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 6),
                            Transform.scale(
                              scale: 0.78,
                              child: isTriggeredOneShot
                                  ? IconButton(
                                      icon: const Icon(Icons.replay_rounded, color: AppTokens.warning),
                                      onPressed: () => repository.rearmRule(rule.uuid),
                                    )
                                  : Switch(
                                      value: rule.isActive,
                                      activeThumbColor: Colors.white,
                                      activeTrackColor: theme.colorScheme.primary,
                                      onChanged: (val) => repository.saveRule(rule.copyWith(isActive: val)),
                                    ),
                            ),
                          ],
                        ),

                        // === ROW 2: Price Metrics Bar (Live Price & 24h Change Badge) ===
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                SizedBox(
                                  height: 12,
                                  child: showPrevious
                                      ? FittedBox(
                                          fit: BoxFit.scaleDown,
                                          alignment: Alignment.centerLeft,
                                          child: Text(
                                            FormatUtils.formatPrice(prevPrice, currencySymbol: rule.counterCurrency, lang: cardLang),
                                            maxLines: 1,
                                            style: TextStyle(
                                              fontSize: 10,
                                              fontWeight: FontWeight.w600,
                                              fontFamily: 'monospace',
                                              decoration: TextDecoration.lineThrough,
                                              color: textMuted,
                                            ),
                                          ),
                                        )
                                      : const SizedBox.shrink(),
                                ),
                                FittedBox(
                                  fit: BoxFit.scaleDown,
                                  alignment: Alignment.centerLeft,
                                  child: Text(
                                    displayPrice != null
                                        ? FormatUtils.formatPrice(displayPrice, currencySymbol: rule.counterCurrency, lang: cardLang)
                                        : '---',
                                    maxLines: 1,
                                    style: TextStyle(
                                      fontSize: 19,
                                      fontWeight: FontWeight.w900,
                                      fontFamily: 'monospace',
                                      letterSpacing: -0.2,
                                      color: rule.isActive
                                          ? (changePercent != null && changePercent > 0.005
                                              ? theme.colorScheme.primary
                                              : (changePercent != null && changePercent < -0.005
                                                  ? AppTokens.negative
                                                  : theme.colorScheme.onSurface))
                                          : textMuted,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            if (isTriggeredOneShot)
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                                decoration: BoxDecoration(
                                  color: AppTokens.warning.withValues(alpha: 0.15),
                                  borderRadius: BorderRadius.circular(6),
                                  border: Border.all(color: AppTokens.warning.withValues(alpha: 0.3)),
                                ),
                                child: const Text(
                                  '✅ Done',
                                  maxLines: 1,
                                  style: TextStyle(fontSize: 9.5, fontWeight: FontWeight.bold, color: AppTokens.warning),
                                ),
                              )
                            else if (changePercent != null)
                              Builder(builder: (context) {
                                final cp = changePercent!;
                                final isZero = cp.abs() < 0.005;
                                final isPositive = cp > 0.005;
                                final badgeColor = isZero ? textMuted : (isPositive ? AppTokens.positive : AppTokens.negative);
                                final badgeBg = isZero
                                    ? theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.6)
                                    : badgeColor.withValues(alpha: 0.12);
                                final prefix = isZero ? '• ' : (isPositive ? '▲ +' : '▼ ');

                                return Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: badgeBg,
                                    borderRadius: BorderRadius.circular(6),
                                  ),
                                  child: Text(
                                    '$prefix${cp.abs().toStringAsFixed(2)}%',
                                    maxLines: 1,
                                    style: TextStyle(
                                      fontSize: 9.5,
                                      fontWeight: FontWeight.bold,
                                      fontFamily: 'monospace',
                                      color: badgeColor,
                                    ),
                                  ),
                                );
                              })
                            else
                              const SizedBox(height: 16),
                          ],
                        ),

                        // === ROW 3: Target Proximity Progress Strip ===
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
                          decoration: BoxDecoration(
                            color: isTriggeredOneShot
                                ? AppTokens.warning.withValues(alpha: 0.08)
                                : theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                              color: isTriggeredOneShot
                                  ? AppTokens.warning.withValues(alpha: 0.25)
                                  : (progState.color != null && progState.percentageInt >= 85
                                      ? progState.color!.withValues(alpha: 0.35)
                                      : theme.colorScheme.primary.withValues(alpha: 0.12)),
                              width: 1,
                            ),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Row(
                                children: [
                                  Icon(
                                    rule.conditionType == AlertConditionType.priceThreshold
                                        ? Icons.gps_fixed_rounded
                                        : Icons.trending_up_rounded,
                                    size: 11.5,
                                    color: isTriggeredOneShot
                                        ? AppTokens.warning
                                        : (progState.color ?? theme.colorScheme.primary),
                                  ),
                                  const SizedBox(width: 4),
                                  Expanded(
                                    child: Text(
                                      _buildConditionSummary(rule, cardLang),
                                      style: TextStyle(
                                        fontSize: 9.5,
                                        fontWeight: FontWeight.bold,
                                        color: rule.isActive ? theme.colorScheme.onSurface : textMuted,
                                      ),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                  const SizedBox(width: 6),
                                  Text(
                                    isTriggeredOneShot ? 'Done' : '${progState.percentageInt}%',
                                    style: TextStyle(
                                      fontSize: 9,
                                      fontWeight: FontWeight.bold,
                                      fontFamily: 'monospace',
                                      color: isTriggeredOneShot ? AppTokens.warning : (progState.color ?? textMuted),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 4),
                              ClipRRect(
                                borderRadius: BorderRadius.circular(2),
                                child: Stack(
                                  children: [
                                    Container(
                                      height: 3,
                                      width: double.infinity,
                                      color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.8),
                                    ),
                                    if (progState.color != null && progState.progressFactor > 0)
                                      FractionallySizedBox(
                                        widthFactor: progState.progressFactor,
                                        child: Container(
                                          height: 3,
                                          color: isTriggeredOneShot ? AppTokens.warning : progState.color,
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),

                        // === ROW 4: Footer Utilities & Check Action ===
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.7),
                                borderRadius: BorderRadius.circular(5),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(Icons.timer_outlined, size: 10, color: theme.colorScheme.primary),
                                  const SizedBox(width: 3),
                                  Text(
                                    _formatInterval(rule.checkIntervalSeconds, cardLang),
                                    style: TextStyle(
                                      fontSize: 9,
                                      fontWeight: FontWeight.w600,
                                      color: theme.colorScheme.primary,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 5),
                            if (rule.ttsEnabled)
                              Icon(Icons.record_voice_over_rounded, size: 11.5, color: theme.colorScheme.primary.withValues(alpha: 0.75)),
                            if (rule.soundEnabled)
                              Padding(
                                padding: const EdgeInsets.only(left: 3),
                                child: Icon(Icons.volume_up_rounded, size: 11.5, color: theme.colorScheme.onSurface.withValues(alpha: 0.55)),
                              ),
                            const Spacer(),
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.hourglass_bottom_rounded,
                                  size: 10,
                                  color: rule.isActive ? theme.colorScheme.primary : textMuted,
                                ),
                                const SizedBox(width: 2.5),
                                Text(
                                  _formatNextCheckTime(rule, cardLang),
                                  style: TextStyle(
                                    fontSize: 9,
                                    fontWeight: FontWeight.w500,
                                    color: rule.isActive ? theme.colorScheme.onSurface.withValues(alpha: 0.7) : textMuted,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(width: 6),
                            InkWell(
                              onTap: isChecking ? null : () => _manualCheck(rule, scheduler, lang),
                              borderRadius: BorderRadius.circular(5),
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2.5),
                                decoration: BoxDecoration(
                                  color: theme.colorScheme.primary.withValues(alpha: 0.12),
                                  borderRadius: BorderRadius.circular(5),
                                  border: Border.all(color: theme.colorScheme.primary.withValues(alpha: 0.28)),
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    if (isChecking)
                                      SizedBox(
                                        width: 9,
                                        height: 9,
                                        child: CircularProgressIndicator(strokeWidth: 1.5, color: theme.colorScheme.primary),
                                      )
                                    else
                                      Icon(Icons.sync_rounded, size: 10.5, color: theme.colorScheme.primary),
                                    const SizedBox(width: 2.5),
                                    Text(
                                      AppStrings.get('check_now', cardLang),
                                      style: TextStyle(
                                        fontSize: 9,
                                        fontWeight: FontWeight.bold,
                                        color: theme.colorScheme.primary,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    );
                  },
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildEmptyState(String lang, ThemeData theme) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppTokens.space32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(AppTokens.space24),
              decoration: BoxDecoration(
                color: theme.colorScheme.primary.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.add_alert_rounded,
                size: 56,
                color: theme.colorScheme.primary,
              ),
            ),
            const SizedBox(height: AppTokens.space20),
            Text(
              AppStrings.get('empty_alerts_title', lang),
              style: TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.bold,
                color: theme.colorScheme.onSurface,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppTokens.space8),
            Text(
              AppStrings.get('empty_alerts_desc', lang),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 12.5,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                height: 1.5,
              ),
            ),
            const SizedBox(height: AppTokens.space24),
            ElevatedButton.icon(
              onPressed: _openCreateFlow,
              icon: const Icon(Icons.add_rounded, size: 20),
              label: Text(
                AppStrings.get('create_first_alert', lang),
                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: theme.colorScheme.primary,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatNextCheckTime(AlertRule rule, String lang) {
    final isFa = AppStrings.isRtl(lang);
    if (!rule.isActive) {
      return isFa ? 'غیرفعال' : 'Inactive';
    }

    final now = DateTime.now();
    final lastTime = rule.lastCheckedAt ?? rule.createdAt;
    
    // Smooth cyclic interval calculation matching central server scheduler
    final elapsedSecs = now.difference(lastTime).inSeconds;
    final interval = rule.checkIntervalSeconds > 0 ? rule.checkIntervalSeconds : 10;
    
    final mod = elapsedSecs % interval;
    final remainingSecs = mod == 0 ? 0 : (interval - mod);

    if (remainingSecs == 0) {
      return '⚡';
    }

    final diff = Duration(seconds: remainingSecs);

    if (diff.inHours >= 1) {
      final h = diff.inHours;
      final m = diff.inMinutes % 60;
      if (m == 0) {
        return isFa ? '$h ساعت تا پایش' : 'In ${h}h';
      }
      return isFa ? '$h ساعت و $m دقیقه تا پایش' : 'In ${h}h ${m}m';
    } else if (diff.inMinutes >= 1) {
      final m = diff.inMinutes;
      final s = diff.inSeconds % 60;
      if (s == 0) {
        return isFa ? '$m دقیقه تا پایش' : 'In ${m}m';
      }
      return isFa ? '$m دقیقه و $s ثانیه تا پایش' : 'In ${m}m ${s}s';
    } else {
      return isFa ? '${diff.inSeconds} ثانیه تا پایش' : 'In ${diff.inSeconds}s';
    }
  }

  String _formatInterval(int seconds, String lang) {
    if (seconds < 60) {
      return '$seconds s';
    } else if (seconds < 3600) {
      final m = seconds ~/ 60;
      return '$m ${AppStrings.get('minutes', lang)}';
    } else {
      final h = seconds ~/ 3600;
      return '$h ${AppStrings.get('hours', lang)}';
    }
  }

  String _getExchangeDisplayName(String exchangeId, String lang) {
    switch (exchangeId) {
      case 'global_stocks':
      case 'GLOBALSTOKS':
      case 'GLOBAL_STOCKS':
      case 'Global Stocks':
        return 'GL-ST';
      case 'iran_market':
      case 'IRAN_MARKET':
        return 'IR_M';
      case 'binance':
        return 'Binance';
      case 'nobitex':
        return 'Nobitex';
      case 'wallex':
        return 'Wallex';
      case 'tabdeal':
        return 'Tabdeal';
      case 'bitbarg':
        return 'Bitbarg';
      case 'abantether':
        return 'AbanTether';
      case 'ramzinex':
        return 'Ramzinex';
      case 'tetherland':
        return 'TetherLand';
      case 'sarmayex':
        return 'Sarmayex';
      case 'exir':
        return 'Exir';
      case 'kcex':
        return 'KCEX';
      case 'lbank':
        return 'LBank';
      case 'ourbit':
        return 'Ourbit';
      case 'xt':
        return 'XT.COM';
      case 'toobit':
        return 'Toobit';
      case 'coinbase':
        return 'Coinbase';
      case 'kucoin':
        return 'KuCoin';
      case 'okx':
        return 'OKX';
      case 'bybit':
        return 'Bybit';
      case 'mexc':
        return 'MEXC';
      case 'gateio':
        return 'Gate.io';
      case 'bingx':
        return 'BingX';
      case 'bitget':
        return 'Bitget';
      case 'kraken':
        return 'Kraken';
      case 'coinmarketcap':
        return 'CoinMarketCap';
      case 'coingecko':
        return 'CoinGecko';
      default:
        return exchangeId.toUpperCase();
    }
  }

  String _buildConditionSummary(AlertRule rule, String lang) {
    final isFa = AppStrings.isRtl(lang);
    switch (rule.conditionType) {
      case AlertConditionType.priceThreshold:
        if (rule.direction == AlertDirection.bothSides) {
          final up = FormatUtils.formatPrice(rule.upperTargetPrice ?? 0, currencySymbol: rule.counterCurrency, lang: lang);
          final down = FormatUtils.formatPrice(rule.lowerTargetPrice ?? 0, currencySymbol: rule.counterCurrency, lang: lang);
          return isFa ? '▲ بالا: $up | ▼ پایین: $down' : '▲ Up: $up | ▼ Down: $down';
        }
        final String dirStr;
        if (rule.direction == AlertDirection.above) {
          dirStr = lang == 'ckb' ? 'بەرزبوونەوە بۆ سەرووی' : (isFa ? 'صعود به بالای' : 'Crosses above');
        } else if (rule.direction == AlertDirection.below) {
          dirStr = lang == 'ckb' ? 'دابەزین بۆ خوارەوەی' : (isFa ? 'سقوط به زیر' : 'Drops below');
        } else {
          dirStr = lang == 'ckb' ? 'گەیشتن بە' : (isFa ? 'رسیدن به' : 'Reaches');
        }
        return '$dirStr ${FormatUtils.formatPrice(rule.targetPrice ?? 0, currencySymbol: rule.counterCurrency, lang: lang)}';

      case AlertConditionType.percentChange:
        final p = rule.percent ?? 0;
        final String dirStr;
        if (rule.direction == AlertDirection.above) {
          dirStr = lang == 'ckb' ? 'بەرزبوونەوەی' : (isFa ? 'رشد حداقل' : 'Surges by +');
        } else if (rule.direction == AlertDirection.below) {
          dirStr = lang == 'ckb' ? 'دابەزینی' : (isFa ? 'افت حداقل' : 'Drops by -');
        } else {
          dirStr = lang == 'ckb' ? 'جووڵە' : (isFa ? 'نوسان' : 'Moves ±');
        }
        return '$dirStr ${p.toStringAsFixed(1)}%';

      case AlertConditionType.absolutePriceChange:
        return '${lang == 'ckb' ? "گۆڕانکاری" : (isFa ? "تغییر" : "Changes by")} ${FormatUtils.formatPrice(rule.deltaAbsolute ?? 0, currencySymbol: rule.counterCurrency, lang: lang)}';

      case AlertConditionType.volumeChange:
        return '${lang == 'ckb' ? "هەڵکشانی قەبارە" : (isFa ? "جهش حجم" : "Volume jump")} ${(rule.volumePercent ?? 0).toStringAsFixed(1)}%';
    }
  }
}
