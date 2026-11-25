import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/tokens.dart';
import '../../alert_engine/models/alert_rule.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_quote.dart';
import '../theme/bourse_text.dart';
import '../utils/bourse_format.dart';
import '../widgets/bourse_daily_band_gauge.dart';
import '../widgets/bourse_quick_board.dart';
import '../widgets/bourse_state_badge.dart';
import 'bourse_alert_api.dart';
import 'bourse_alert_draft.dart';
import 'bourse_alert_text.dart';
import 'bourse_notification_options_card.dart';

/// Turns text typed by the user into a number: accepts Persian/Arabic digits, thousands
/// separators and the Persian decimal point. Returns null when it is not a number.
double? parseBourseAmount(String input) {
  final b = StringBuffer();
  for (final unit in input.runes) {
    final ch = String.fromCharCode(unit);
    if (unit >= 0x06F0 && unit <= 0x06F9) {
      b.write(unit - 0x06F0); // Persian digits
    } else if (unit >= 0x0660 && unit <= 0x0669) {
      b.write(unit - 0x0660); // Arabic-Indic digits
    } else if (ch == ',' || ch == '٬' || ch == ' ' || ch == '،') {
      continue; // separators
    } else if (ch == '٫') {
      b.write('.');
    } else {
      b.write(ch);
    }
  }
  final text = b.toString();
  if (text.isEmpty) return null;
  final v = double.tryParse(text);
  if (v == null || v.isNaN || v.isInfinite) return null;
  return v;
}

/// Unified Symbol + Alert Workspace for one Iranian Bourse instrument.
///
/// Combines a sticky live price & visual daily-band header, a compact tap-to-fill
/// market quick board (close, prev close, volume, ETF NAV + bubble %, best bid/ask,
/// and collapsible full metadata), the alert condition builder, collapsible notification
/// options, and a sticky bottom submit bar with live Persian rule summary.
///
/// Submitting creates the alert on the server first ([BourseAlertApi]); only when the server
/// accepts it is [onCreated] called to save it on the phone. If saving on the phone fails
/// the server copy is removed again, so both sides stay equal.
class BourseAlertFormPage extends StatefulWidget {
  final BourseQuote quote;

  /// Saves the accepted rule on the device. Throwing means "could not save".
  final Future<void> Function(AlertRule rule) onCreated;

  /// For tests; defaults to the app's own server connection.
  final BourseAlertApi? api;
  final bool persianDigits;

  /// Optional live quote refresh callback wired by [BourseSymbolWorkspacePage].
  final Future<void> Function()? onRefresh;
  final bool refreshing;
  final String? refreshError;

  const BourseAlertFormPage({
    super.key,
    required this.quote,
    required this.onCreated,
    this.api,
    this.persianDigits = false,
    this.onRefresh,
    this.refreshing = false,
    this.refreshError,
  });

  @override
  State<BourseAlertFormPage> createState() => _BourseAlertFormPageState();
}

class _BourseAlertFormPageState extends State<BourseAlertFormPage> {
  static const List<int> _quickPercents = [1, 2, 3, 5, 7, 10];
  static const List<double> _volumeMultipliers = [1.5, 2.0, 3.0];

  late final BourseAlertApi _api = widget.api ?? BourseAlertApi();
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _minQueueVolume = TextEditingController();
  final TextEditingController _upperAmount = TextEditingController();
  final TextEditingController _lowerAmount = TextEditingController();
  final TextEditingController _note = TextEditingController();
  final TextEditingController _upperNote = TextEditingController();
  final TextEditingController _lowerNote = TextEditingController();

  BourseAlertKind _kind = BourseAlertKind.price;
  AlertDirection _direction = AlertDirection.above;
  BothWayBehavior _bothWayBehavior = BothWayBehavior.oco;
  BoursePriceField _priceField = BoursePriceField.last;
  bool _recurring = false;

  // Notification & delivery options (matching other markets)
  String _selectedSound = 'alarm_siren';
  bool _soundEnabled = true;
  bool _vibrationEnabled = true;
  bool _flashEnabled = false;
  bool _ttsEnabled = false;

  bool _submitting = false;
  bool _triedSubmit = false;
  String? _error;

  @override
  void dispose() {
    _amount.dispose();
    _minQueueVolume.dispose();
    _upperAmount.dispose();
    _lowerAmount.dispose();
    _note.dispose();
    _upperNote.dispose();
    _lowerNote.dispose();
    super.dispose();
  }

  BourseAlertDraft get _draft => BourseAlertDraft.fromQuote(
        widget.quote,
        kind: _kind,
        direction: _direction,
        amount: parseBourseAmount(_amount.text),
        minQueueVolume: parseBourseAmount(_minQueueVolume.text),
        upperAmount: parseBourseAmount(_upperAmount.text),
        lowerAmount: parseBourseAmount(_lowerAmount.text),
        upperNote: _upperNote.text,
        lowerNote: _lowerNote.text,
        bothWayBehavior: _bothWayBehavior,
        note: _note.text,
        recurring: _recurring,
        priceField: _priceField,
      );

  /// The price is not a live one: market closed, no trade today or a stale feed.
  bool get _marketNotLive {
    final st = widget.quote.state;
    return st != BourseState.live && st != BourseState.unknown;
  }

  /// How far the alert price is from the last price, e.g. `4.67% بالاتر از آخرین قیمت`.
  String? _distanceText(double? target) {
    final last = widget.quote.price;
    if (target == null || last == null || last <= 0 || target <= 0) return null;
    final pct = (target - last) / last * 100;
    if (pct.isNaN || pct.isInfinite) return null;
    final text = BourseFormat.signedPercent(pct.abs(), persianDigits: widget.persianDigits).replaceFirst('+', '');
    return pct >= 0 ? BourseStrings.alertDistanceAbove(text) : BourseStrings.alertDistanceBelow(text);
  }

  String get _amountLabel {
    switch (_kind) {
      case BourseAlertKind.price:
        return BourseStrings.alertPriceLabel;
      case BourseAlertKind.percentChange:
        return BourseStrings.alertAmountPercent;
      case BourseAlertKind.absoluteChange:
        return BourseStrings.alertAmountAbsolute;
      case BourseAlertKind.volumeAbove:
        return BourseStrings.alertAmountVolume;
      case BourseAlertKind.queueBuy:
      case BourseAlertKind.queueSell:
        return BourseStrings.queueMinVolumeLabel;
    }
  }

  String _plainInteger(num v) => v.round().toString();

  /// Populates target price when the user taps any price tile in [BourseQuickBoard].
  void _fillTargetPrice(num price) {
    if (_submitting || price <= 0) return;
    final text = _plainInteger(price);
    final last = widget.quote.price;
    setState(() {
      _kind = BourseAlertKind.price;
      _error = null;
      if (_direction == AlertDirection.bothSides) {
        if (last != null && last > 0 && price < last) {
          _lowerAmount.text = text;
        } else {
          _upperAmount.text = text;
        }
      } else {
        _amount.text = text;
        if (last != null && last > 0) {
          _direction = price < last ? AlertDirection.below : AlertDirection.above;
        }
      }
    });
  }

  Future<void> _submit() async {
    if (_submitting) return;
    final draft = _draft;
    final problem = draft.validate();
    if (problem != null) {
      setState(() {
        _triedSubmit = true;
        _error = BourseStrings.alertProblem(problem);
      });
      return;
    }

    setState(() {
      _submitting = true;
      _triedSubmit = true;
      _error = null;
    });

    final rule = draft.toRule(
      customSound: _selectedSound,
      soundEnabled: _soundEnabled,
      vibrationEnabled: _vibrationEnabled,
      flashEnabled: _flashEnabled,
      ttsEnabled: _ttsEnabled,
    );
    final res = await _api.create(rule);
    if (!mounted) return;
    if (!res.isOk) {
      setState(() {
        _submitting = false;
        _error = BourseStrings.failureMessage(res.failure!);
      });
      return;
    }

    try {
      await widget.onCreated(rule);
    } catch (_) {
      await _api.remove(rule.uuid); // undo: never leave an alert only on the server
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _error = BourseStrings.alertSaveFailed;
      });
      return;
    }
    if (!mounted) return;
    setState(() => _submitting = false);
    Navigator.of(context).maybePop(rule);
  }

  Widget _sectionCard(BuildContext context, {required Widget child, EdgeInsets? padding}) {
    return Material(
      color: BourseText.cardColor(context),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(BourseText.cardRadius),
        side: BorderSide(color: BourseText.borderColor(context)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: padding ?? const EdgeInsets.all(AppTokens.space12),
        child: child,
      ),
    );
  }

  Widget _buildStickyPriceStrip(
    BuildContext context, {
    required double? target,
    required double? upperTarget,
    required double? lowerTarget,
    required bool isDual,
  }) {
    final theme = Theme.of(context);
    final d = widget.persianDigits;
    final pct = widget.quote.changePct;
    final queueLabel = widget.quote.queueLabel;

    final Color pctColor;
    if (pct != null && pct > 0) {
      pctColor = AppTokens.positive;
    } else if (pct != null && pct < 0) {
      pctColor = AppTokens.negative;
    } else {
      pctColor = BourseText.secondaryColor(context);
    }

    final bool hasLimits = widget.quote.lowerLimit != null &&
        widget.quote.upperLimit != null &&
        widget.quote.lowerLimit! > 0 &&
        widget.quote.upperLimit! > widget.quote.lowerLimit!;

    return Container(
      key: const Key('bourse_workspace_sticky_header'),
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(AppTokens.space16, 6, AppTokens.space16, 8),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border(bottom: BorderSide(color: BourseText.borderColor(context))),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${BourseStrings.lastPrice}: ${BourseFormat.rial(widget.quote.price, persianDigits: d)}',
                  key: const Key('bourse_form_last_price'),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: BourseText.body(context).copyWith(
                    fontWeight: FontWeight.bold,
                    fontSize: 13.5,
                  ),
                ),
              ),
              if (queueLabel != null) ...[
                const SizedBox(width: 6),
                Container(
                  key: const Key('bourse_workspace_queue_badge'),
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                  decoration: BoxDecoration(
                    color: (queueLabel.contains('خرید') ? AppTokens.positive : AppTokens.negative)
                        .withValues(alpha: 0.14),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    queueLabel,
                    style: TextStyle(
                      fontSize: 10.5,
                      fontWeight: FontWeight.bold,
                      color: queueLabel.contains('خرید') ? AppTokens.positive : AppTokens.negative,
                    ),
                  ),
                ),
              ],
              if (pct != null) ...[
                const SizedBox(width: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                  decoration: BoxDecoration(
                    color: pctColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    BourseFormat.signedPercent(pct, persianDigits: d),
                    textDirection: TextDirection.ltr,
                    style: TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 11.5,
                      fontWeight: FontWeight.bold,
                      color: pctColor,
                    ),
                  ),
                ),
              ],
            ],
          ),
          if (hasLimits) ...[
            const SizedBox(height: 6),
            BourseDailyBandGauge(
              quote: widget.quote,
              targetPrice: isDual ? null : target,
              upperTargetPrice: isDual ? upperTarget : null,
              lowerTargetPrice: isDual ? lowerTarget : null,
              persianDigits: d,
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildConditionGrid(BuildContext context, ThemeData theme, Color accent) {
    const row1 = [
      BourseAlertKind.price,
      BourseAlertKind.percentChange,
      BourseAlertKind.absoluteChange,
    ];
    const row2 = [
      BourseAlertKind.queueBuy,
      BourseAlertKind.queueSell,
      BourseAlertKind.volumeAbove,
    ];

    Widget chipFor(BourseAlertKind k) {
      final selected = _kind == k;
      return Expanded(
        child: ChoiceChip(
          key: Key('bourse_kind_${k.name}'),
          label: SizedBox(
            width: double.infinity,
            child: Text(
              BourseStrings.alertKindShortLabel(k),
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          selected: selected,
          showCheckmark: false,
          visualDensity: VisualDensity.compact,
          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
          labelPadding: EdgeInsets.zero,
          labelStyle: TextStyle(
            fontSize: 11.5,
            fontWeight: selected ? FontWeight.bold : FontWeight.w500,
            color: selected ? accent : BourseText.secondaryColor(context),
          ),
          selectedColor: accent.withValues(alpha: 0.15),
          backgroundColor: theme.scaffoldBackgroundColor,
          side: BorderSide(color: selected ? accent : BourseText.borderColor(context)),
          onSelected: _submitting
              ? null
              : (_) => setState(() {
                    _kind = k;
                    _error = null;
                  }),
        ),
      );
    }

    return Column(
      key: const Key('bourse_form_kind'),
      children: [
        Row(
          children: [
            for (int i = 0; i < row1.length; i++) ...[
              if (i > 0) const SizedBox(width: 6),
              chipFor(row1[i]),
            ],
          ],
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            for (int i = 0; i < row2.length; i++) ...[
              if (i > 0) const SizedBox(width: 6),
              chipFor(row2[i]),
            ],
          ],
        ),
      ],
    );
  }

  Widget _buildDailyLimitShortcuts(BuildContext context) {
    final up = widget.quote.upperLimit;
    final low = widget.quote.lowerLimit;
    if ((up == null || up <= 0) && (low == null || low <= 0)) return const SizedBox.shrink();

    final d = widget.persianDigits;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppTokens.space8),
      child: Row(
        children: [
          if (up != null && up > 0)
            Expanded(
              child: OutlinedButton(
                key: const Key('bourse_shortcut_upper_limit'),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                  minimumSize: const Size(0, 34),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  side: BorderSide(color: AppTokens.positive.withValues(alpha: 0.45)),
                  backgroundColor: AppTokens.positive.withValues(alpha: 0.08),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(9)),
                ),
                onPressed: _submitting
                    ? null
                    : () => setState(() {
                          final text = _plainInteger(up);
                          if (_direction == AlertDirection.bothSides) {
                            _upperAmount.text = text;
                          } else {
                            _amount.text = text;
                            _direction = AlertDirection.above;
                          }
                          _error = null;
                        }),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Text(
                      BourseStrings.bandCeilShort,
                      style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: AppTokens.positive),
                    ),
                    const SizedBox(width: 4),
                    Flexible(
                      child: Text(
                        BourseFormat.number(up, persianDigits: d),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textDirection: TextDirection.ltr,
                        style: const TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                          fontFamily: 'monospace',
                          color: AppTokens.positive,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          if (up != null && up > 0 && low != null && low > 0) const SizedBox(width: AppTokens.space8),
          if (low != null && low > 0)
            Expanded(
              child: OutlinedButton(
                key: const Key('bourse_shortcut_lower_limit'),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                  minimumSize: const Size(0, 34),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  side: BorderSide(color: AppTokens.negative.withValues(alpha: 0.45)),
                  backgroundColor: AppTokens.negative.withValues(alpha: 0.08),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(9)),
                ),
                onPressed: _submitting
                    ? null
                    : () => setState(() {
                          final text = _plainInteger(low);
                          if (_direction == AlertDirection.bothSides) {
                            _lowerAmount.text = text;
                          } else {
                            _amount.text = text;
                            _direction = AlertDirection.below;
                          }
                          _error = null;
                        }),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Text(
                      BourseStrings.bandFloorShort,
                      style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: AppTokens.negative),
                    ),
                    const SizedBox(width: 4),
                    Flexible(
                      child: Text(
                        BourseFormat.number(low, persianDigits: d),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textDirection: TextDirection.ltr,
                        style: const TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                          fontFamily: 'monospace',
                          color: AppTokens.negative,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildVolumeShortcuts(BuildContext context, ThemeData theme, Color accent) {
    final todayVol = widget.quote.volume;
    if (todayVol == null || todayVol <= 0) return const SizedBox.shrink();
    final d = widget.persianDigits;
    final currentAmount = parseBourseAmount(_amount.text);

    return Padding(
      padding: const EdgeInsets.only(bottom: AppTokens.space8),
      child: Row(
        key: const Key('bourse_volume_multipliers'),
        children: [
          for (int i = 0; i < _volumeMultipliers.length; i++) ...[
            if (i > 0) const SizedBox(width: 6),
            Builder(builder: (context) {
              final mult = _volumeMultipliers[i];
              final targetVol = (todayVol * mult).round();
              final multStr = mult == mult.roundToDouble() ? '${mult.toInt()}' : '$mult';
              final keySuffix = (mult * 10).round();
              final selected = currentAmount != null && (currentAmount.round() - targetVol).abs() == 0;
              return Expanded(
                child: ChoiceChip(
                  key: Key('bourse_vol_mult_$keySuffix'),
                  label: SizedBox(
                    width: double.infinity,
                    child: Text(
                      BourseStrings.volumeMultiplier(d ? BourseFormat.toPersianDigits(multStr) : multStr),
                      textAlign: TextAlign.center,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  selected: selected,
                  showCheckmark: false,
                  visualDensity: VisualDensity.compact,
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  labelStyle: TextStyle(
                    fontSize: 11,
                    fontWeight: selected ? FontWeight.bold : FontWeight.w500,
                    color: selected ? accent : BourseText.secondaryColor(context),
                  ),
                  selectedColor: accent.withValues(alpha: 0.15),
                  backgroundColor: theme.scaffoldBackgroundColor,
                  side: BorderSide(color: selected ? accent : BourseText.borderColor(context)),
                  onSelected: _submitting
                      ? null
                      : (_) => setState(() {
                            _amount.text = targetVol.toString();
                            _error = null;
                          }),
                ),
              );
            }),
          ],
        ],
      ),
    );
  }

  Widget _buildTwoWayPriceInputs(BuildContext context, ThemeData theme, Color accent) {
    final numberFormatters = [FilteringTextInputFormatter.allow(RegExp(r'[0-9۰-۹٠-٩.,٬٫،]'))];
    return Column(
      key: const Key('bourse_form_two_way_price'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // OCO vs Dual-Active behavior selector
        Text(
          BourseStrings.bothWayBehaviorLabel,
          style: BourseText.caption(context).copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: AppTokens.space8),
        SegmentedButton<BothWayBehavior>(
          key: const Key('bourse_form_both_way_behavior'),
          showSelectedIcon: false,
          style: ButtonStyle(
            shape: WidgetStatePropertyAll(
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(BourseText.inputRadius)),
            ),
            side: WidgetStatePropertyAll(BorderSide(color: BourseText.borderColor(context))),
          ),
          segments: const [
            ButtonSegment<BothWayBehavior>(
              value: BothWayBehavior.oco,
              label: Text(BourseStrings.bothWayOcoTitle, style: TextStyle(fontSize: 11.5)),
            ),
            ButtonSegment<BothWayBehavior>(
              value: BothWayBehavior.dualActive,
              label: Text(BourseStrings.bothWayDualTitle, style: TextStyle(fontSize: 11.5)),
            ),
          ],
          selected: {_bothWayBehavior},
          onSelectionChanged: _submitting ? null : (s) => setState(() => _bothWayBehavior = s.first),
        ),
        const SizedBox(height: 4),
        Text(
          _bothWayBehavior == BothWayBehavior.oco
              ? BourseStrings.bothWayOcoDesc
              : BourseStrings.bothWayDualDesc,
          style: BourseText.caption(context),
        ),
        const SizedBox(height: AppTokens.space12),

        // Upper target (Resistance)
        Row(
          children: [
            const Icon(Icons.arrow_upward_rounded, size: 16, color: AppTokens.positive),
            const SizedBox(width: 6),
            Text(
              BourseStrings.upperTargetTitle,
              style: BourseText.sectionLabel(context).copyWith(color: AppTokens.positive),
            ),
          ],
        ),
        const SizedBox(height: AppTokens.space8),
        TextField(
          key: const Key('bourse_form_upper_amount'),
          controller: _upperAmount,
          enabled: !_submitting,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          textDirection: TextDirection.ltr,
          style: TextStyle(
            fontFamily: 'monospace',
            fontSize: 15,
            fontWeight: FontWeight.bold,
            color: BourseText.primaryColor(context),
          ),
          inputFormatters: numberFormatters,
          decoration: BourseText.inputDecoration(
            context,
            labelText: BourseStrings.upperPriceLabel,
            hintText: BourseStrings.alertAmountHintRial,
          ).copyWith(fillColor: theme.scaffoldBackgroundColor),
          onChanged: (_) => setState(() => _error = null),
        ),
        const SizedBox(height: AppTokens.space8),
        TextField(
          key: const Key('bourse_form_upper_note'),
          controller: _upperNote,
          enabled: !_submitting,
          maxLength: 120,
          style: BourseText.body(context),
          decoration: BourseText.inputDecoration(
            context,
            labelText: BourseStrings.upperNoteLabel,
            prefixIcon: Icon(Icons.edit_note_rounded, size: 18, color: BourseText.mutedColor(context)),
          ).copyWith(fillColor: theme.scaffoldBackgroundColor, counterText: ''),
        ),

        Padding(
          padding: const EdgeInsets.symmetric(vertical: AppTokens.space12),
          child: Divider(height: 1, color: BourseText.borderColor(context)),
        ),

        // Lower target (Support)
        Row(
          children: [
            const Icon(Icons.arrow_downward_rounded, size: 16, color: AppTokens.negative),
            const SizedBox(width: 6),
            Text(
              BourseStrings.lowerTargetTitle,
              style: BourseText.sectionLabel(context).copyWith(color: AppTokens.negative),
            ),
          ],
        ),
        const SizedBox(height: AppTokens.space8),
        TextField(
          key: const Key('bourse_form_lower_amount'),
          controller: _lowerAmount,
          enabled: !_submitting,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          textDirection: TextDirection.ltr,
          style: TextStyle(
            fontFamily: 'monospace',
            fontSize: 15,
            fontWeight: FontWeight.bold,
            color: BourseText.primaryColor(context),
          ),
          inputFormatters: numberFormatters,
          decoration: BourseText.inputDecoration(
            context,
            labelText: BourseStrings.lowerPriceLabel,
            hintText: BourseStrings.alertAmountHintRial,
          ).copyWith(fillColor: theme.scaffoldBackgroundColor),
          onChanged: (_) => setState(() => _error = null),
        ),
        const SizedBox(height: AppTokens.space8),
        TextField(
          key: const Key('bourse_form_lower_note'),
          controller: _lowerNote,
          enabled: !_submitting,
          maxLength: 120,
          style: BourseText.body(context),
          decoration: BourseText.inputDecoration(
            context,
            labelText: BourseStrings.lowerNoteLabel,
            prefixIcon: Icon(Icons.edit_note_rounded, size: 18, color: BourseText.mutedColor(context)),
          ).copyWith(fillColor: theme.scaffoldBackgroundColor, counterText: ''),
        ),
      ],
    );
  }

  String? _liveSummary(BourseAlertDraft draft, bool persianDigits) {
    if (draft.validate() != null) return null;
    final desc = bourseAlertDescription(draft.toRule(), persianDigits: persianDigits);
    return '${draft.displayName} · $desc';
  }

  Widget _buildStickyBottomBar(BuildContext context, ThemeData theme, BourseAlertDraft draft, bool d) {
    final summary = _liveSummary(draft, d);
    final showError = _error != null && _triedSubmit;

    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border(top: BorderSide(color: BourseText.borderColor(context))),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(AppTokens.space16, 8, AppTokens.space16, 10),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (showError)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                    decoration: BoxDecoration(
                      color: AppTokens.negative.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: AppTokens.negative.withValues(alpha: 0.35)),
                    ),
                    child: Text(
                      _error!,
                      key: const Key('bourse_form_error'),
                      style: BourseText.secondary(context).copyWith(
                        fontSize: 12,
                        color: AppTokens.negative,
                      ),
                    ),
                  ),
                )
              else if (summary != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    children: [
                      Icon(Icons.notifications_active_rounded, size: 14, color: BourseText.accentColor(context)),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          summary,
                          key: const Key('bourse_form_live_summary'),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: BourseText.caption(context).copyWith(
                            fontSize: 11.5,
                            fontWeight: FontWeight.w600,
                            color: BourseText.primaryColor(context),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              FilledButton(
                key: const Key('bourse_form_submit'),
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(46),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(BourseText.inputRadius),
                  ),
                ),
                onPressed: _submitting ? null : _submit,
                child: _submitting
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, key: Key('bourse_form_busy')),
                      )
                    : const Text(
                        BourseStrings.alertSubmit,
                        style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = BourseText.accentColor(context);
    final d = widget.persianDigits;
    final draft = _draft;
    final amount = parseBourseAmount(_amount.text);
    final minQueueVol = parseBourseAmount(_minQueueVolume.text);
    final warning = draft.warning();
    final isQueue = draft.isQueue;
    final isVolume = draft.isVolume;
    final isPriceBased = draft.isPriceBased;
    final isPercent = _kind == BourseAlertKind.percentChange;
    final isChange = _kind == BourseAlertKind.percentChange || _kind == BourseAlertKind.absoluteChange;
    final isTwoWayPrice = draft.isTwoWayPrice;
    final isBothChange = isChange && _direction == AlertDirection.bothSides;

    final preview = (!isTwoWayPrice && !isQueue && amount != null && amount > 0)
        ? (isPercent
            ? BourseFormat.signedPercent(amount, persianDigits: d).replaceFirst('+', '')
            : (isVolume
                ? '${BourseFormat.number(amount.round(), persianDigits: d)} سهم'
                : BourseFormat.rial(amount, persianDigits: d)))
        : null;
    final target = draft.triggerPrice;
    final upperTarget = draft.upperTriggerPrice;
    final lowerTarget = draft.lowerTriggerPrice;
    final distance = _distanceText(target);
    final fullName = widget.quote.name.trim();

    // Queue top-of-book helper volume if available
    final BourseOrderLevel? relevantQueueLevel =
        _kind == BourseAlertKind.queueBuy ? widget.quote.bestBid : widget.quote.bestAsk;

    final scrollContent = SingleChildScrollView(
      physics: widget.onRefresh != null ? const AlwaysScrollableScrollPhysics() : null,
      padding: const EdgeInsets.fromLTRB(AppTokens.space16, 10, AppTokens.space16, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.refreshError != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(
                widget.refreshError!,
                key: const Key('bourse_refresh_failure'),
                style: BourseText.caption(context).copyWith(color: BourseText.warningColor(context)),
              ),
            ),

          if (_marketNotLive)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Container(
                key: const Key('bourse_form_closed_note'),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(
                  color: AppTokens.warningSubtle,
                  borderRadius: BorderRadius.circular(BourseText.inputRadius),
                  border: Border.all(color: AppTokens.warning.withAlpha(120)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.info_outline_rounded, size: 16, color: BourseText.warningColor(context)),
                    const SizedBox(width: AppTokens.space8),
                    Expanded(
                      child: Text(
                        BourseStrings.alertClosedNote(
                          BourseFormat.rial(widget.quote.price, persianDigits: d),
                        ),
                        style: BourseText.secondary(context).copyWith(fontSize: 11.5),
                      ),
                    ),
                  ],
                ),
              ),
            ),

          // Live Tap-to-Fill Symbol Quick Board + Order Book + ETF NAV Bubble + Collapsible Details
          BourseQuickBoard(
            quote: widget.quote,
            persianDigits: d,
            onFillPrice: _submitting ? null : _fillTargetPrice,
          ),

          const SizedBox(height: 10),

          // Condition, Direction, Target Amount & Price Basis
          _sectionCard(
            context,
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Icon(Icons.tune_rounded, size: 17, color: accent),
                    const SizedBox(width: 6),
                    Text(
                      BourseStrings.alertSectionCondition,
                      style: BourseText.sectionLabel(context).copyWith(fontSize: 12.5),
                    ),
                  ],
                ),
                const SizedBox(height: 10),

                // Symmetric 2x3 condition kind grid
                _buildConditionGrid(context, theme, accent),
                const SizedBox(height: 10),

                // 3-way direction selector (only for price-based kinds)
                if (isPriceBased) ...[
                  SegmentedButton<AlertDirection>(
                    key: const Key('bourse_form_direction'),
                    showSelectedIcon: false,
                    style: ButtonStyle(
                      visualDensity: VisualDensity.compact,
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      shape: WidgetStatePropertyAll(
                        RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(BourseText.inputRadius),
                        ),
                      ),
                      side: WidgetStatePropertyAll(BorderSide(color: BourseText.borderColor(context))),
                    ),
                    segments: const [
                      ButtonSegment<AlertDirection>(
                        value: AlertDirection.above,
                        label: Text(BourseStrings.directionAbove, style: TextStyle(fontSize: 12)),
                      ),
                      ButtonSegment<AlertDirection>(
                        value: AlertDirection.below,
                        label: Text(BourseStrings.directionBelow, style: TextStyle(fontSize: 12)),
                      ),
                      ButtonSegment<AlertDirection>(
                        value: AlertDirection.bothSides,
                        label: Text(BourseStrings.directionBothSides, style: TextStyle(fontSize: 12)),
                      ),
                    ],
                    selected: {_direction},
                    onSelectionChanged: _submitting
                        ? null
                        : (s) => setState(() {
                              _direction = s.first;
                              _error = null;
                            }),
                  ),
                  const SizedBox(height: 10),
                ],

                // Quick percent chips tailored for Tehran Bourse volatility bands
                if (isPercent) ...[
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      key: const Key('bourse_quick_percents'),
                      children: [
                        for (final p in _quickPercents)
                          Padding(
                            padding: const EdgeInsets.only(left: 6),
                            child: ChoiceChip(
                              key: Key('bourse_quick_pct_$p'),
                              label: Text('${d ? BourseFormat.toPersianDigits('$p') : '$p'}٪'),
                              selected: amount != null && (amount - p).abs() < 1e-6,
                              showCheckmark: false,
                              visualDensity: VisualDensity.compact,
                              labelStyle: TextStyle(
                                fontSize: 11.5,
                                fontWeight: (amount != null && (amount - p).abs() < 1e-6)
                                    ? FontWeight.bold
                                    : FontWeight.normal,
                                color: (amount != null && (amount - p).abs() < 1e-6)
                                    ? accent
                                    : BourseText.secondaryColor(context),
                              ),
                              selectedColor: accent.withValues(alpha: 0.15),
                              backgroundColor: theme.scaffoldBackgroundColor,
                              side: BorderSide(
                                color: (amount != null && (amount - p).abs() < 1e-6)
                                    ? accent
                                    : BourseText.borderColor(context),
                              ),
                              onSelected: _submitting
                                  ? null
                                  : (_) => setState(() {
                                        _amount.text = p.toString();
                                        _error = null;
                                      }),
                            ),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                ],

                // Daily limit shortcuts for price-level alerts
                if (_kind == BourseAlertKind.price) _buildDailyLimitShortcuts(context),

                // Quick volume multiplier chips for volume alerts
                if (isVolume) _buildVolumeShortcuts(context, theme, accent),

                // Target input(s)
                if (isQueue) ...[
                  Container(
                    key: const Key('bourse_form_queue_note'),
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: (_kind == BourseAlertKind.queueBuy ? AppTokens.positive : AppTokens.negative)
                          .withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(BourseText.inputRadius),
                      border: Border.all(
                        color: (_kind == BourseAlertKind.queueBuy ? AppTokens.positive : AppTokens.negative)
                            .withValues(alpha: 0.35),
                      ),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                          _kind == BourseAlertKind.queueBuy
                              ? Icons.trending_up_rounded
                              : Icons.trending_down_rounded,
                          size: 18,
                          color: _kind == BourseAlertKind.queueBuy ? AppTokens.positive : AppTokens.negative,
                        ),
                        const SizedBox(width: AppTokens.space8),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                _kind == BourseAlertKind.queueBuy
                                    ? BourseStrings.queueBuyNote
                                    : BourseStrings.queueSellNote,
                                style: BourseText.secondary(context).copyWith(fontSize: 12),
                              ),
                              if (relevantQueueLevel != null && relevantQueueLevel.volume > 0) ...[
                                const SizedBox(height: 4),
                                Text(
                                  BourseStrings.currentQueueTopHint(
                                    _kind == BourseAlertKind.queueBuy
                                        ? BourseStrings.bestBidLabel
                                        : BourseStrings.bestAskLabel,
                                    BourseFormat.number(relevantQueueLevel.volume, persianDigits: d),
                                  ),
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600,
                                    color: _kind == BourseAlertKind.queueBuy
                                        ? AppTokens.positive
                                        : AppTokens.negative,
                                  ),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    key: const Key('bourse_form_min_queue_volume'),
                    controller: _minQueueVolume,
                    enabled: !_submitting,
                    keyboardType: TextInputType.number,
                    textDirection: TextDirection.ltr,
                    style: TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                      color: BourseText.primaryColor(context),
                    ),
                    inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9۰-۹٠-٩,٬،]'))],
                    decoration: BourseText.inputDecoration(
                      context,
                      labelText: BourseStrings.queueMinVolumeLabel,
                      hintText: BourseStrings.queueMinVolumeHint,
                    ).copyWith(fillColor: theme.scaffoldBackgroundColor),
                    onChanged: (_) => setState(() => _error = null),
                  ),
                  if (minQueueVol != null && minQueueVol > 0)
                    Padding(
                      padding: const EdgeInsets.only(top: AppTokens.space8),
                      child: Text(
                        '${BourseFormat.number(minQueueVol.round(), persianDigits: d)} سهم',
                        key: const Key('bourse_form_queue_vol_preview'),
                        style: BourseText.secondary(context).copyWith(fontWeight: FontWeight.w600),
                      ),
                    ),
                ] else if (isTwoWayPrice)
                  _buildTwoWayPriceInputs(context, theme, accent)
                else
                  TextField(
                    key: const Key('bourse_form_amount'),
                    controller: _amount,
                    enabled: !_submitting,
                    keyboardType: isVolume
                        ? TextInputType.number
                        : const TextInputType.numberWithOptions(decimal: true),
                    textDirection: TextDirection.ltr,
                    style: TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: BourseText.primaryColor(context),
                    ),
                    inputFormatters: [
                      FilteringTextInputFormatter.allow(
                        isVolume ? RegExp(r'[0-9۰-۹٠-٩,٬،]') : RegExp(r'[0-9۰-۹٠-٩.,٬٫،]'),
                      ),
                    ],
                    decoration: BourseText.inputDecoration(
                      context,
                      labelText: _amountLabel,
                      hintText: isPercent
                          ? 'مثلاً ۳'
                          : (isVolume ? BourseStrings.alertVolumeHint : BourseStrings.alertAmountHintRial),
                    ).copyWith(fillColor: theme.scaffoldBackgroundColor),
                    onChanged: (_) => setState(() => _error = null),
                  ),

                if (preview != null)
                  Padding(
                    padding: const EdgeInsets.only(top: AppTokens.space8),
                    child: Text(
                      preview,
                      key: const Key('bourse_form_preview'),
                      style: BourseText.secondary(context).copyWith(fontWeight: FontWeight.w600),
                    ),
                  ),

                // Live dual target preview for two-way percent / Rial change
                if (isBothChange && (upperTarget != null || lowerTarget != null))
                  Padding(
                    padding: const EdgeInsets.only(top: AppTokens.space8),
                    child: Container(
                      key: const Key('bourse_form_both_targets'),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: theme.scaffoldBackgroundColor,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: BourseText.borderColor(context)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (upperTarget != null)
                            Text(
                              BourseStrings.bothSidesPreviewUpper(
                                BourseFormat.rial(upperTarget.round(), persianDigits: d),
                              ),
                              style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: AppTokens.positive,
                              ),
                            ),
                          if (lowerTarget != null) ...[
                            const SizedBox(height: 2),
                            Text(
                              BourseStrings.bothSidesPreviewLower(
                                BourseFormat.rial(lowerTarget.round(), persianDigits: d),
                              ),
                              style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: AppTokens.negative,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),

                if (isChange && !isBothChange && target != null)
                  Padding(
                    padding: const EdgeInsets.only(top: AppTokens.space4),
                    child: Text(
                      '≈ ${BourseFormat.rial(target.round(), persianDigits: d)}',
                      key: const Key('bourse_form_target'),
                      style: BourseText.secondary(context),
                    ),
                  ),
                if (!isTwoWayPrice && distance != null)
                  Padding(
                    padding: const EdgeInsets.only(top: AppTokens.space4),
                    child: Text(
                      distance,
                      key: const Key('bourse_form_distance'),
                      style: BourseText.secondary(context),
                    ),
                  ),
                if (warning != null)
                  Padding(
                    padding: const EdgeInsets.only(top: AppTokens.space8),
                    child: Text(
                      BourseStrings.alertWarning(warning),
                      key: const Key('bourse_form_warning'),
                      style: BourseText.secondary(context).copyWith(color: BourseText.warningColor(context)),
                    ),
                  ),
                if (isChange)
                  Padding(
                    padding: const EdgeInsets.only(top: AppTokens.space8),
                    child: Text(BourseStrings.alertDailyBaseNote, style: BourseText.caption(context)),
                  ),

                if (isVolume) ...[
                  if (widget.quote.volume != null && widget.quote.volume! > 0)
                    Padding(
                      padding: const EdgeInsets.only(top: AppTokens.space8),
                      child: Text(
                        BourseStrings.alertVolumeTodayHint(
                          BourseFormat.number(widget.quote.volume!, persianDigits: d),
                        ),
                        key: const Key('bourse_form_today_volume'),
                        style: BourseText.caption(context),
                      ),
                    ),
                  Padding(
                    padding: const EdgeInsets.only(top: AppTokens.space4),
                    child: Text(BourseStrings.alertVolumeNote, style: BourseText.caption(context)),
                  ),
                ],

                // Price evaluation basis (Last trade vs Close price) — only for price-based alerts
                if (isPriceBased) ...[
                  Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Divider(height: 1, color: BourseText.borderColor(context)),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Text(
                        BourseStrings.priceFieldLabel,
                        style: BourseText.caption(context).copyWith(fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Wrap(
                          key: const Key('bourse_form_price_field'),
                          alignment: WrapAlignment.end,
                          spacing: 6,
                          runSpacing: 6,
                          children: [
                            ChoiceChip(
                              key: const Key('bourse_price_field_last'),
                              label: const Text(BourseStrings.priceFieldLast),
                              selected: _priceField == BoursePriceField.last,
                              showCheckmark: false,
                              visualDensity: VisualDensity.compact,
                              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              labelStyle: TextStyle(
                                fontSize: 11,
                                fontWeight:
                                    _priceField == BoursePriceField.last ? FontWeight.bold : FontWeight.normal,
                                color: _priceField == BoursePriceField.last
                                    ? accent
                                    : BourseText.secondaryColor(context),
                              ),
                              selectedColor: accent.withValues(alpha: 0.15),
                              backgroundColor: theme.scaffoldBackgroundColor,
                              side: BorderSide(
                                color: _priceField == BoursePriceField.last
                                    ? accent
                                    : BourseText.borderColor(context),
                              ),
                              onSelected: _submitting
                                  ? null
                                  : (_) => setState(() => _priceField = BoursePriceField.last),
                            ),
                            ChoiceChip(
                              key: const Key('bourse_price_field_close'),
                              label: const Text(BourseStrings.priceFieldClose),
                              selected: _priceField == BoursePriceField.close,
                              showCheckmark: false,
                              visualDensity: VisualDensity.compact,
                              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              labelStyle: TextStyle(
                                fontSize: 11,
                                fontWeight:
                                    _priceField == BoursePriceField.close ? FontWeight.bold : FontWeight.normal,
                                color: _priceField == BoursePriceField.close
                                    ? accent
                                    : BourseText.secondaryColor(context),
                              ),
                              selectedColor: accent.withValues(alpha: 0.15),
                              backgroundColor: theme.scaffoldBackgroundColor,
                              side: BorderSide(
                                color: _priceField == BoursePriceField.close
                                    ? accent
                                    : BourseText.borderColor(context),
                              ),
                              onSelected: _submitting
                                  ? null
                                  : (_) => setState(() => _priceField = BoursePriceField.close),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),

          // Behavior & Note card
          if (!isTwoWayPrice || !_marketNotLive) ...[
            const SizedBox(height: 10),
            _sectionCard(
              context,
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (!isTwoWayPrice) ...[
                    Row(
                      children: [
                        Icon(Icons.repeat_rounded, size: 17, color: accent),
                        const SizedBox(width: 6),
                        Text(
                          BourseStrings.alertSectionBehavior,
                          style: BourseText.sectionLabel(context).copyWith(fontSize: 12.5),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    TextField(
                      key: const Key('bourse_form_note'),
                      controller: _note,
                      enabled: !_submitting,
                      maxLength: 120,
                      style: BourseText.body(context),
                      decoration: BourseText.inputDecoration(
                        context,
                        labelText: BourseStrings.alertNoteLabel,
                        prefixIcon: Icon(
                          Icons.sticky_note_2_outlined,
                          size: 18,
                          color: BourseText.mutedColor(context),
                        ),
                      ).copyWith(fillColor: theme.scaffoldBackgroundColor, counterText: ''),
                    ),
                    const SizedBox(height: 4),
                    SwitchListTile(
                      key: const Key('bourse_form_recurring'),
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      title: Text(BourseStrings.alertRecurring, style: BourseText.body(context)),
                      value: _recurring,
                      onChanged: _submitting ? null : (v) => setState(() => _recurring = v),
                    ),
                  ],
                  if (!_marketNotLive) ...[
                    if (!isTwoWayPrice) const SizedBox(height: 4),
                    Text(
                      BourseStrings.alertOnlyLiveNote,
                      key: const Key('bourse_form_only_live_note'),
                      style: BourseText.caption(context),
                    ),
                  ],
                ],
              ),
            ),
          ],

          const SizedBox(height: 10),

          // Collapsible Notification & Alarm Delivery Options (Sound, Vibrate, Flash SOS, TTS)
          BourseNotificationOptionsCard(
            selectedSound: _selectedSound,
            soundEnabled: _soundEnabled,
            vibrationEnabled: _vibrationEnabled,
            flashEnabled: _flashEnabled,
            ttsEnabled: _ttsEnabled,
            enabled: !_submitting,
            collapsible: true,
            initiallyExpanded: false,
            onSoundChanged: (s) => setState(() => _selectedSound = s),
            onSoundEnabledChanged: (v) => setState(() => _soundEnabled = v),
            onVibrationEnabledChanged: (v) => setState(() => _vibrationEnabled = v),
            onFlashEnabledChanged: (v) => setState(() => _flashEnabled = v),
            onTtsEnabledChanged: (v) => setState(() => _ttsEnabled = v),
            onApplyPreset: ({
              required bool soundEnabled,
              required bool vibrationEnabled,
              required bool flashEnabled,
              required bool ttsEnabled,
            }) =>
                setState(() {
              _soundEnabled = soundEnabled;
              _vibrationEnabled = vibrationEnabled;
              _flashEnabled = flashEnabled;
              _ttsEnabled = ttsEnabled;
            }),
          ),
        ],
      ),
    );

    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          backgroundColor: theme.colorScheme.surface,
          elevation: 0,
          surfaceTintColor: Colors.transparent,
          toolbarHeight: 52,
          iconTheme: IconThemeData(color: theme.colorScheme.onSurface),
          titleSpacing: 0,
          title: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                draft.displayName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: BourseText.appBarTitle(context).copyWith(fontSize: 15.5),
              ),
              if (fullName.isNotEmpty && fullName != draft.displayName)
                Text(
                  fullName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: BourseText.caption(context).copyWith(fontSize: 10.5),
                ),
            ],
          ),
          actions: [
            Center(
              child: Padding(
                padding: EdgeInsets.only(left: widget.onRefresh == null ? 12 : 4),
                child: BourseStateBadge(state: widget.quote.state),
              ),
            ),
            if (widget.onRefresh != null)
              IconButton(
                key: const Key('bourse_workspace_refresh'),
                tooltip: BourseStrings.refreshTooltip,
                onPressed: widget.refreshing ? null : () => widget.onRefresh!(),
                icon: widget.refreshing
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.refresh_rounded, size: 20),
              ),
          ],
        ),
        body: Column(
          children: [
            _buildStickyPriceStrip(
              context,
              target: target,
              upperTarget: upperTarget,
              lowerTarget: lowerTarget,
              isDual: isTwoWayPrice || isBothChange,
            ),
            Expanded(
              child: widget.onRefresh != null
                  ? RefreshIndicator(
                      onRefresh: widget.onRefresh!,
                      child: scrollContent,
                    )
                  : scrollContent,
            ),
          ],
        ),
        bottomNavigationBar: _buildStickyBottomBar(context, theme, draft, d),
      ),
    );
  }
}
