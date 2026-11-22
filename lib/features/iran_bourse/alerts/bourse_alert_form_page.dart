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

/// The alert form of one Bourse instrument (IB-11d-3).
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
  late final BourseAlertApi _api = widget.api ?? BourseAlertApi();
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _note = TextEditingController();

  BourseAlertKind _kind = BourseAlertKind.price;
  AlertDirection _direction = AlertDirection.above;
  bool _recurring = false;
  bool _submitting = false;
  bool _triedSubmit = false;
  String? _error;

  @override
  void dispose() {
    _amount.dispose();
    _note.dispose();
    super.dispose();
  }

  BourseAlertDraft get _draft => BourseAlertDraft.fromQuote(
        widget.quote,
        kind: _kind,
        direction: _direction,
        amount: parseBourseAmount(_amount.text),
        note: _note.text,
        recurring: _recurring,
      );

  /// The price is not a live one: market closed, no trade today or a stale feed.
  bool get _marketNotLive {
    final st = widget.quote.state;
    return st != BourseState.live && st != BourseState.unknown;
  }

  /// How far the alert price is from the last price, e.g. `+4.7% بالاتر از آخرین قیمت`.
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

    final rule = draft.toRule();
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = BourseText.accentColor(context);
    final draft = _draft;
    final amount = parseBourseAmount(_amount.text);
    final warning = draft.warning();
    final isPercent = _kind == BourseAlertKind.percentChange;
    final isChange = _kind != BourseAlertKind.price;
    final preview = (amount != null && amount > 0)
        ? (isPercent
            ? BourseFormat.signedPercent(amount, persianDigits: widget.persianDigits).replaceFirst('+', '')
            : BourseFormat.rial(amount, persianDigits: widget.persianDigits))
        : null;
    final target = draft.triggerPrice;
    final distance = _distanceText(target);
    final fullName = widget.quote.name.trim();

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
              // Section 1: Selected Symbol Summary Card
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
                      '${BourseStrings.lastPrice}: ${BourseFormat.rial(widget.quote.price, persianDigits: widget.persianDigits)}',
                      key: const Key('bourse_form_last_price'),
                      style: BourseText.secondary(context).copyWith(fontWeight: FontWeight.w600),
                    ),
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
                                      BourseFormat.rial(widget.quote.price, persianDigits: widget.persianDigits)),
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

              // Section 2: Condition, Direction & Amount
              _sectionCard(
                context,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
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
                            onSelected: _submitting ? null : (_) => setState(() => _kind = k),
                          ),
                      ],
                    ),
                    const SizedBox(height: AppTokens.space12),
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
                            value: AlertDirection.above, label: Text(BourseStrings.directionAbove)),
                        ButtonSegment<AlertDirection>(
                            value: AlertDirection.below, label: Text(BourseStrings.directionBelow)),
                      ],
                      selected: {_direction},
                      onSelectionChanged: _submitting ? null : (s) => setState(() => _direction = s.first),
                    ),
                    const SizedBox(height: AppTokens.space16),
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
                        hintText: isPercent ? null : BourseStrings.alertAmountHintRial,
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
                    if (isChange && target != null)
                      Padding(
                        padding: const EdgeInsets.only(top: AppTokens.space4),
                        child: Text(
                          '≈ ${BourseFormat.rial(target.round(), persianDigits: widget.persianDigits)}',
                          key: const Key('bourse_form_target'),
                          style: BourseText.secondary(context),
                        ),
                      ),
                    if (distance != null)
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
                  ],
                ),
              ),

              const SizedBox(height: AppTokens.space16),

              // Section 3: Note & Repeat Options
              _sectionCard(
                context,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
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
                    if (!_marketNotLive) ...[
                      const SizedBox(height: AppTokens.space4),
                      Text(
                        BourseStrings.alertOnlyLiveNote,
                        key: const Key('bourse_form_only_live_note'),
                        style: BourseText.caption(context),
                      ),
                    ],
                  ],
                ),
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
