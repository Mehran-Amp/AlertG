import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/tokens.dart';
import '../../alert_engine/models/alert_rule.dart';
import '../localization/bourse_strings.dart';
import '../models/bourse_quote.dart';
import '../theme/bourse_text.dart';
import '../utils/bourse_format.dart';
import 'bourse_alert_api.dart';
import 'bourse_alert_draft.dart';
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

/// The unified alert form of one Bourse instrument (IB-11d-3 + unified alert UX).
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

  const BourseAlertFormPage({
    super.key,
    required this.quote,
    required this.onCreated,
    this.api,
    this.persianDigits = false,
  });

  @override
  State<BourseAlertFormPage> createState() => _BourseAlertFormPageState();
}

class _BourseAlertFormPageState extends State<BourseAlertFormPage> {
  static const List<int> _quickPercents = [1, 2, 3, 5, 7, 10];

  late final BourseAlertApi _api = widget.api ?? BourseAlertApi();
  final TextEditingController _amount = TextEditingController();
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
    }
  }

  String _plainInteger(num v) => v.round().toString();

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

  Widget _sectionCard(BuildContext context, {required Widget child}) {
    return Material(
      color: BourseText.cardColor(context),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(BourseText.cardRadius),
        side: BorderSide(color: BourseText.borderColor(context)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(AppTokens.space16),
        child: child,
      ),
    );
  }

  Widget _buildDailyLimitShortcuts(BuildContext context) {
    final up = widget.quote.upperLimit;
    final low = widget.quote.lowerLimit;
    if ((up == null || up <= 0) && (low == null || low <= 0)) return const SizedBox.shrink();

    final d = widget.persianDigits;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppTokens.space12),
      child: Row(
        children: [
          if (up != null && up > 0)
            Expanded(
              child: OutlinedButton(
                key: const Key('bourse_shortcut_upper_limit'),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                  side: BorderSide(color: AppTokens.positive.withValues(alpha: 0.45)),
                  backgroundColor: AppTokens.positive.withValues(alpha: 0.08),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
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
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text(
                      BourseStrings.shortcutUpperLimit,
                      style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: AppTokens.positive),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      BourseFormat.number(up, persianDigits: d),
                      textDirection: TextDirection.ltr,
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        fontFamily: 'monospace',
                        color: AppTokens.positive,
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
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                  side: BorderSide(color: AppTokens.negative.withValues(alpha: 0.45)),
                  backgroundColor: AppTokens.negative.withValues(alpha: 0.08),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
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
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text(
                      BourseStrings.shortcutLowerLimit,
                      style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: AppTokens.negative),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      BourseFormat.number(low, persianDigits: d),
                      textDirection: TextDirection.ltr,
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        fontFamily: 'monospace',
                        color: AppTokens.negative,
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = BourseText.accentColor(context);
    final d = widget.persianDigits;
    final draft = _draft;
    final amount = parseBourseAmount(_amount.text);
    final warning = draft.warning();
    final isPercent = _kind == BourseAlertKind.percentChange;
    final isChange = _kind != BourseAlertKind.price;
    final isTwoWayPrice = draft.isTwoWayPrice;
    final isBothChange = isChange && _direction == AlertDirection.bothSides;

    final preview = (!isTwoWayPrice && amount != null && amount > 0)
        ? (isPercent
            ? BourseFormat.signedPercent(amount, persianDigits: d).replaceFirst('+', '')
            : BourseFormat.rial(amount, persianDigits: d))
        : null;
    final target = draft.triggerPrice;
    final upperTarget = draft.upperTriggerPrice;
    final lowerTarget = draft.lowerTriggerPrice;
    final distance = _distanceText(target);
    final fullName = widget.quote.name.trim();
    final dailyBand = BourseFormat.range(widget.quote.lowerLimit, widget.quote.upperLimit, persianDigits: d);
    final hasDailyBand = dailyBand != BourseFormat.dash;

    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          backgroundColor: theme.colorScheme.surface,
          elevation: 0,
          surfaceTintColor: Colors.transparent,
          iconTheme: IconThemeData(color: theme.colorScheme.onSurface),
          title: Text(
            '${BourseStrings.createAlert} · ${draft.displayName}',
            style: BourseText.appBarTitle(context),
          ),
        ),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(AppTokens.space20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Card 1: Selected Symbol Summary & Daily Band
              _sectionCard(
                context,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            color: accent.withValues(alpha: 0.14),
                            shape: BoxShape.circle,
                          ),
                          alignment: Alignment.center,
                          child: Icon(Icons.candlestick_chart_rounded, size: 20, color: accent),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                draft.displayName,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: BourseText.header(context),
                              ),
                              if (fullName.isNotEmpty && fullName != draft.displayName) ...[
                                const SizedBox(height: 2),
                                Text(
                                  fullName,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: BourseText.caption(context),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppTokens.space12),
                    Text(
                      '${BourseStrings.lastPrice}: ${BourseFormat.rial(widget.quote.price, persianDigits: d)}',
                      key: const Key('bourse_form_last_price'),
                      style: BourseText.secondary(context).copyWith(fontWeight: FontWeight.w600),
                    ),
                    if (hasDailyBand) ...[
                      const SizedBox(height: 4),
                      Text(
                        '${BourseStrings.dailyBandLabel}: $dailyBand ${BourseFormat.rialWord}',
                        key: const Key('bourse_form_daily_band'),
                        style: BourseText.caption(context),
                      ),
                    ],
                    if (_marketNotLive)
                      Padding(
                        padding: const EdgeInsets.only(top: AppTokens.space12),
                        child: Container(
                          key: const Key('bourse_form_closed_note'),
                          padding: const EdgeInsets.all(AppTokens.space12),
                          decoration: BoxDecoration(
                            color: AppTokens.warningSubtle,
                            borderRadius: BorderRadius.circular(BourseText.inputRadius),
                            border: Border.all(color: AppTokens.warning.withAlpha(120)),
                          ),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Icon(Icons.info_outline_rounded, size: 18, color: BourseText.warningColor(context)),
                              const SizedBox(width: AppTokens.space8),
                              Expanded(
                                child: Text(
                                  BourseStrings.alertClosedNote(
                                      BourseFormat.rial(widget.quote.price, persianDigits: d)),
                                  style: BourseText.secondary(context).copyWith(fontSize: 12),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
              ),

              const SizedBox(height: AppTokens.space16),

              // Card 2: Condition, Direction, Target Amount & Price Basis
              _sectionCard(
                context,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.tune_rounded, size: 18, color: accent),
                        const SizedBox(width: 8),
                        Text(
                          BourseStrings.alertSectionCondition,
                          style: BourseText.sectionLabel(context).copyWith(fontSize: 13),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppTokens.space12),

                    // Condition kind selector
                    Wrap(
                      key: const Key('bourse_form_kind'),
                      spacing: AppTokens.space8,
                      runSpacing: AppTokens.space8,
                      children: [
                        for (final k in BourseAlertKind.values)
                          ChoiceChip(
                            key: Key('bourse_kind_${k.name}'),
                            label: Text(BourseStrings.alertKindLabel(k)),
                            selected: _kind == k,
                            showCheckmark: false,
                            labelStyle: TextStyle(
                              fontSize: 12,
                              fontWeight: _kind == k ? FontWeight.bold : FontWeight.normal,
                              color: _kind == k ? accent : BourseText.secondaryColor(context),
                            ),
                            selectedColor: accent.withValues(alpha: 0.15),
                            backgroundColor: theme.scaffoldBackgroundColor,
                            side: BorderSide(color: _kind == k ? accent : BourseText.borderColor(context)),
                            onSelected: _submitting ? null : (_) => setState(() {
                              _kind = k;
                              _error = null;
                            }),
                          ),
                      ],
                    ),
                    const SizedBox(height: AppTokens.space12),

                    // 3-way direction selector (Above / Below / Both Sides)
                    SegmentedButton<AlertDirection>(
                      key: const Key('bourse_form_direction'),
                      showSelectedIcon: false,
                      style: ButtonStyle(
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
                    const SizedBox(height: AppTokens.space16),

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
                                  label: Text(
                                    '${d ? BourseFormat.toPersianDigits('$p') : '$p'}٪',
                                  ),
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
                      const SizedBox(height: AppTokens.space12),
                    ],

                    // Daily limit shortcuts for price-level alerts
                    if (_kind == BourseAlertKind.price) _buildDailyLimitShortcuts(context),

                    // Target input(s)
                    if (isTwoWayPrice)
                      _buildTwoWayPriceInputs(context, theme, accent)
                    else
                      TextField(
                        key: const Key('bourse_form_amount'),
                        controller: _amount,
                        enabled: !_submitting,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        textDirection: TextDirection.ltr,
                        style: TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: BourseText.primaryColor(context),
                        ),
                        inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9۰-۹٠-٩.,٬٫،]'))],
                        decoration: BourseText.inputDecoration(
                          context,
                          labelText: _amountLabel,
                          hintText: isPercent ? 'مثلاً ۳' : BourseStrings.alertAmountHintRial,
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

                    // Price evaluation basis (Last trade vs Close price)
                    Padding(
                      padding: const EdgeInsets.only(top: AppTokens.space12),
                      child: Divider(height: 1, color: BourseText.borderColor(context)),
                    ),
                    const SizedBox(height: AppTokens.space12),
                    Text(
                      BourseStrings.priceFieldLabel,
                      style: BourseText.caption(context).copyWith(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: AppTokens.space8),
                    Wrap(
                      key: const Key('bourse_form_price_field'),
                      spacing: AppTokens.space8,
                      runSpacing: AppTokens.space8,
                      children: [
                        ChoiceChip(
                          key: const Key('bourse_price_field_last'),
                          label: const Text(BourseStrings.priceFieldLast),
                          selected: _priceField == BoursePriceField.last,
                          showCheckmark: false,
                          visualDensity: VisualDensity.compact,
                          labelStyle: TextStyle(
                            fontSize: 11.5,
                            fontWeight: _priceField == BoursePriceField.last ? FontWeight.bold : FontWeight.normal,
                            color:
                                _priceField == BoursePriceField.last ? accent : BourseText.secondaryColor(context),
                          ),
                          selectedColor: accent.withValues(alpha: 0.15),
                          backgroundColor: theme.scaffoldBackgroundColor,
                          side: BorderSide(
                            color: _priceField == BoursePriceField.last ? accent : BourseText.borderColor(context),
                          ),
                          onSelected:
                              _submitting ? null : (_) => setState(() => _priceField = BoursePriceField.last),
                        ),
                        ChoiceChip(
                          key: const Key('bourse_price_field_close'),
                          label: const Text(BourseStrings.priceFieldClose),
                          selected: _priceField == BoursePriceField.close,
                          showCheckmark: false,
                          visualDensity: VisualDensity.compact,
                          labelStyle: TextStyle(
                            fontSize: 11.5,
                            fontWeight: _priceField == BoursePriceField.close ? FontWeight.bold : FontWeight.normal,
                            color:
                                _priceField == BoursePriceField.close ? accent : BourseText.secondaryColor(context),
                          ),
                          selectedColor: accent.withValues(alpha: 0.15),
                          backgroundColor: theme.scaffoldBackgroundColor,
                          side: BorderSide(
                            color: _priceField == BoursePriceField.close ? accent : BourseText.borderColor(context),
                          ),
                          onSelected:
                              _submitting ? null : (_) => setState(() => _priceField = BoursePriceField.close),
                        ),
                      ],
                    ),
                  ],
                ),
              ),

              // Card 3: Note & Repeat Options (hidden when two-way price uses dedicated upper/lower notes & OCO/Dual)
              if (!isTwoWayPrice || !_marketNotLive) ...[
                const SizedBox(height: AppTokens.space16),
                _sectionCard(
                  context,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (!isTwoWayPrice) ...[
                        Row(
                          children: [
                            Icon(Icons.repeat_rounded, size: 18, color: accent),
                            const SizedBox(width: 8),
                            Text(
                              BourseStrings.alertSectionBehavior,
                              style: BourseText.sectionLabel(context).copyWith(fontSize: 13),
                            ),
                          ],
                        ),
                        const SizedBox(height: AppTokens.space12),
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
                          ).copyWith(fillColor: theme.scaffoldBackgroundColor),
                        ),
                        const SizedBox(height: AppTokens.space4),
                        SwitchListTile(
                          key: const Key('bourse_form_recurring'),
                          contentPadding: EdgeInsets.zero,
                          title: Text(BourseStrings.alertRecurring, style: BourseText.body(context)),
                          value: _recurring,
                          onChanged: _submitting ? null : (v) => setState(() => _recurring = v),
                        ),
                      ],
                      if (!_marketNotLive) ...[
                        if (!isTwoWayPrice) const SizedBox(height: AppTokens.space4),
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

              const SizedBox(height: AppTokens.space16),

              // Card 4: Notification & Alarm Delivery Options (Sound, Vibrate, Flash SOS, TTS)
              BourseNotificationOptionsCard(
                selectedSound: _selectedSound,
                soundEnabled: _soundEnabled,
                vibrationEnabled: _vibrationEnabled,
                flashEnabled: _flashEnabled,
                ttsEnabled: _ttsEnabled,
                enabled: !_submitting,
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

              if (_error != null && _triedSubmit)
                Padding(
                  padding: const EdgeInsets.only(top: AppTokens.space12),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppTokens.negative.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(BourseText.inputRadius),
                      border: Border.all(color: AppTokens.negative.withValues(alpha: 0.35)),
                    ),
                    child: Text(
                      _error!,
                      key: const Key('bourse_form_error'),
                      style: BourseText.secondary(context).copyWith(color: AppTokens.negative),
                    ),
                  ),
                ),

              const SizedBox(height: AppTokens.space20),

              FilledButton(
                key: const Key('bourse_form_submit'),
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(50),
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
}
