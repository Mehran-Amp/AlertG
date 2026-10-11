import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../core/localization/app_strings.dart';
import '../../../core/theme/tokens.dart';
import '../../settings/services/settings_service.dart';

enum PollingUnit { seconds, minutes, hours }

/// Individual polling interval selector with unit segmented control and quick presets.
class IntervalPicker extends StatefulWidget {
  final int initialSeconds;
  final ValueChanged<int> onIntervalChanged;

  const IntervalPicker({
    super.key,
    this.initialSeconds = 60, // 1m default
    required this.onIntervalChanged,
  });

  @override
  State<IntervalPicker> createState() => _IntervalPickerState();
}

class _IntervalPickerState extends State<IntervalPicker> {
  late TextEditingController _valueController;
  late PollingUnit _unit;

  @override
  void initState() {
    super.initState();
    _initFromSeconds(widget.initialSeconds);
  }

  void _initFromSeconds(int secs) {
    if (secs >= 3600 && secs % 3600 == 0) {
      _unit = PollingUnit.hours;
      _valueController = TextEditingController(text: (secs ~/ 3600).toString());
    } else if (secs >= 60 && secs % 60 == 0) {
      _unit = PollingUnit.minutes;
      _valueController = TextEditingController(text: (secs ~/ 60).toString());
    } else {
      _unit = PollingUnit.seconds;
      _valueController = TextEditingController(text: secs.toString());
    }
  }

  @override
  void dispose() {
    _valueController.dispose();
    super.dispose();
  }

  void _notifyChange() {
    final val = int.tryParse(_valueController.text.trim()) ?? 10;
    final mult = _unit == PollingUnit.hours
        ? 3600
        : (_unit == PollingUnit.minutes ? 60 : 1);
    final totalSeconds = (val * mult).clamp(5, 86400); // 5s minimum
    widget.onIntervalChanged(totalSeconds);
  }

  void _applyPreset(int secs) {
    setState(() {
      _initFromSeconds(secs);
    });
    _notifyChange();
  }

  @override
  Widget build(BuildContext context) {
    final lang = context.watch<SettingsService>().settings.language;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              AppStrings.get('frequency', lang),
              style: AppTokens.caption.copyWith(color: AppTokens.textSecondary, fontWeight: FontWeight.w600),
            ),
            Text(
              'Min: 5 sec',
              style: AppTokens.caption.copyWith(color: AppTokens.textMuted),
            ),
          ],
        ),
        const SizedBox(height: AppTokens.space8),

        // Value Input + Segmented Unit Control
        Row(
          children: [
            Expanded(
              flex: 4,
              child: TextField(
                controller: _valueController,
                keyboardType: TextInputType.number,
                onChanged: (_) => _notifyChange(),
                style: AppTokens.monoNumbers,
                decoration: InputDecoration(
                  labelText: AppStrings.get('frequency', lang),
                  filled: true,
                  fillColor: AppTokens.surface,
                  border: const OutlineInputBorder(borderRadius: AppTokens.borderMedium),
                ),
              ),
            ),
            const SizedBox(width: AppTokens.space8),
            Expanded(
              flex: 6,
              child: SegmentedButton<PollingUnit>(
                segments: [
                  ButtonSegment(value: PollingUnit.seconds, label: Text(AppStrings.get('seconds', lang))),
                  ButtonSegment(value: PollingUnit.minutes, label: Text(AppStrings.get('minutes', lang))),
                  ButtonSegment(value: PollingUnit.hours, label: Text(AppStrings.get('hours', lang))),
                ],
                selected: {_unit},
                onSelectionChanged: (selected) {
                  setState(() => _unit = selected.first);
                  _notifyChange();
                },
                style: ButtonStyle(
                  backgroundColor: WidgetStateProperty.resolveWith((states) {
                    if (states.contains(WidgetState.selected)) {
                      return AppTokens.surfaceElevated;
                    }
                    return AppTokens.surface;
                  }),
                  foregroundColor: WidgetStateProperty.resolveWith((states) {
                    if (states.contains(WidgetState.selected)) {
                      return AppTokens.textPrimary;
                    }
                    return AppTokens.textMuted;
                  }),
                ),
              ),
            ),
          ],
        ),

        const SizedBox(height: AppTokens.space8),

        // Quick Presets
        Wrap(
          spacing: AppTokens.space6,
          runSpacing: AppTokens.space6,
          children: [
            _presetChip('10s', 10),
            _presetChip('30s', 30),
            _presetChip('1m', 60),
            _presetChip('5m', 300),
            _presetChip('15m', 900),
            _presetChip('1h', 3600),
            _presetChip('4h', 14400),
          ],
        ),
      ],
    );
  }

  Widget _presetChip(String label, int seconds) {
    return ActionChip(
      label: Text(label),
      onPressed: () => _applyPreset(seconds),
      backgroundColor: AppTokens.surface,
      side: const BorderSide(color: AppTokens.borderSubtle),
      labelStyle: const TextStyle(fontSize: 12, color: AppTokens.primary, fontWeight: FontWeight.w600),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    );
  }
}
