import 'package:flutter/material.dart';

import '../../../core/services/tts_service.dart';
import '../../../core/theme/tokens.dart';
import '../../settings/services/sound_manager.dart';
import '../localization/bourse_strings.dart';
import '../theme/bourse_text.dart';

/// Quick notification presets for one-tap mobile configuration.
enum BourseNotifPreset {
  standard,
  soundOnly,
  vibrateOnly,
  silent,
}

/// Unified notification & alarm delivery card for Bourse alerts:
/// quick profile chips, alarm sound picker with audition, sound/vibration/SOS-flash toggles,
/// and TTS voice announcer with test button.
///
/// Important: [SoundManager] is only touched on user tap (never inside [build] or [initState])
/// so headless widget tests run cleanly without platform audio plugins.
class BourseNotificationOptionsCard extends StatefulWidget {
  final String selectedSound;
  final bool soundEnabled;
  final bool vibrationEnabled;
  final bool flashEnabled;
  final bool ttsEnabled;
  final bool enabled;
  final bool collapsible;
  final bool initiallyExpanded;
  final ValueChanged<String> onSoundChanged;
  final ValueChanged<bool> onSoundEnabledChanged;
  final ValueChanged<bool> onVibrationEnabledChanged;
  final ValueChanged<bool> onFlashEnabledChanged;
  final ValueChanged<bool> onTtsEnabledChanged;
  final void Function({
    required bool soundEnabled,
    required bool vibrationEnabled,
    required bool flashEnabled,
    required bool ttsEnabled,
  }) onApplyPreset;

  const BourseNotificationOptionsCard({
    super.key,
    required this.selectedSound,
    required this.soundEnabled,
    required this.vibrationEnabled,
    required this.flashEnabled,
    required this.ttsEnabled,
    required this.onSoundChanged,
    required this.onSoundEnabledChanged,
    required this.onVibrationEnabledChanged,
    required this.onFlashEnabledChanged,
    required this.onTtsEnabledChanged,
    required this.onApplyPreset,
    this.enabled = true,
    this.collapsible = false,
    this.initiallyExpanded = true,
  });

  @override
  State<BourseNotificationOptionsCard> createState() => _BourseNotificationOptionsCardState();
}

class _BourseNotificationOptionsCardState extends State<BourseNotificationOptionsCard> {
  String? _playingSoundId;
  late bool _expanded = widget.initiallyExpanded;

  @override
  void dispose() {
    if (_playingSoundId != null) {
      try {
        SoundManager().stop();
      } catch (_) {}
    }
    super.dispose();
  }

  BourseNotifPreset? get _activePreset {
    if (widget.flashEnabled || widget.ttsEnabled) return null;
    if (widget.soundEnabled && widget.vibrationEnabled) return BourseNotifPreset.standard;
    if (widget.soundEnabled && !widget.vibrationEnabled) return BourseNotifPreset.soundOnly;
    if (!widget.soundEnabled && widget.vibrationEnabled) return BourseNotifPreset.vibrateOnly;
    return BourseNotifPreset.silent;
  }

  void _selectPreset(BourseNotifPreset preset) {
    switch (preset) {
      case BourseNotifPreset.standard:
        widget.onApplyPreset(soundEnabled: true, vibrationEnabled: true, flashEnabled: false, ttsEnabled: false);
        break;
      case BourseNotifPreset.soundOnly:
        widget.onApplyPreset(soundEnabled: true, vibrationEnabled: false, flashEnabled: false, ttsEnabled: false);
        break;
      case BourseNotifPreset.vibrateOnly:
        widget.onApplyPreset(soundEnabled: false, vibrationEnabled: true, flashEnabled: false, ttsEnabled: false);
        break;
      case BourseNotifPreset.silent:
        widget.onApplyPreset(soundEnabled: false, vibrationEnabled: false, flashEnabled: false, ttsEnabled: false);
        break;
    }
  }

  String _presetLabel(BourseNotifPreset preset) {
    switch (preset) {
      case BourseNotifPreset.standard:
        return BourseStrings.notifPresetStandard;
      case BourseNotifPreset.soundOnly:
        return BourseStrings.notifPresetSoundOnly;
      case BourseNotifPreset.vibrateOnly:
        return BourseStrings.notifPresetVibrateOnly;
      case BourseNotifPreset.silent:
        return BourseStrings.notifPresetSilent;
    }
  }

  AlarmSoundPreset get _currentSoundPreset => SoundManager.presets.firstWhere(
        (p) => p.id == widget.selectedSound,
        orElse: () => SoundManager.presets.first,
      );

  Future<void> _togglePreview(String soundId, [void Function(VoidCallback)? setModalState]) async {
    final wasPlaying = _playingSoundId == soundId;
    try {
      if (wasPlaying) {
        await SoundManager().stop();
      } else {
        await SoundManager().playPreset(soundId);
      }
    } catch (_) {
      // Ignore platform audio failures in headless test environments.
    }
    if (!mounted) return;
    final next = wasPlaying ? null : soundId;
    setState(() => _playingSoundId = next);
    setModalState?.call(() {});
  }

  Future<void> _stopPreview() async {
    if (_playingSoundId == null) return;
    try {
      await SoundManager().stop();
    } catch (_) {}
    if (mounted) {
      setState(() => _playingSoundId = null);
    }
  }

  void _openSoundPicker(BuildContext context) {
    if (!widget.enabled) return;
    final theme = Theme.of(context);
    final accent = BourseText.accentColor(context);

    showModalBottomSheet<void>(
      context: context,
      backgroundColor: theme.colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) => Directionality(
          textDirection: TextDirection.rtl,
          child: SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          Icon(Icons.music_note_rounded, size: 20, color: accent),
                          const SizedBox(width: 8),
                          Text(
                            BourseStrings.notifSelectSoundTitle,
                            style: BourseText.header(context),
                          ),
                        ],
                      ),
                      IconButton(
                        icon: Icon(Icons.close_rounded, color: BourseText.mutedColor(context)),
                        onPressed: () {
                          _stopPreview();
                          Navigator.pop(ctx);
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Flexible(
                    child: ListView.separated(
                      shrinkWrap: true,
                      itemCount: SoundManager.presets.length,
                      separatorBuilder: (_, __) => Divider(height: 1, color: BourseText.borderColor(context)),
                      itemBuilder: (context, index) {
                        final preset = SoundManager.presets[index];
                        final isSelected = widget.selectedSound == preset.id;
                        final isPlaying = _playingSoundId == preset.id;

                        return InkWell(
                          key: Key('bourse_sound_option_${preset.id}'),
                          borderRadius: BorderRadius.circular(BourseText.inputRadius),
                          onTap: () {
                            widget.onSoundChanged(preset.id);
                            setModalState(() {});
                          },
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                            decoration: BoxDecoration(
                              color: isSelected ? accent.withValues(alpha: 0.1) : Colors.transparent,
                              borderRadius: BorderRadius.circular(BourseText.inputRadius),
                              border: isSelected ? Border.all(color: accent.withValues(alpha: 0.35)) : null,
                            ),
                            child: Row(
                              children: [
                                Text(preset.icon, style: const TextStyle(fontSize: 20)),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Text(
                                    preset.titleFa,
                                    style: BourseText.body(context).copyWith(
                                      fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                                    ),
                                  ),
                                ),
                                IconButton(
                                  icon: Icon(
                                    isPlaying ? Icons.stop_circle_rounded : Icons.play_circle_filled_rounded,
                                    color: isPlaying ? AppTokens.negative : accent,
                                    size: 26,
                                  ),
                                  onPressed: () => _togglePreview(preset.id, setModalState),
                                ),
                                if (isSelected)
                                  Icon(Icons.check_circle_rounded, color: accent, size: 20),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 12),
                  FilledButton(
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(44),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(BourseText.inputRadius),
                      ),
                    ),
                    onPressed: () {
                      _stopPreview();
                      Navigator.pop(ctx);
                    },
                    child: const Text(BourseStrings.notifConfirmSound),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    ).whenComplete(_stopPreview);
  }

  String _summaryText(AlarmSoundPreset currentSound) {
    final parts = <String>[];
    if (widget.soundEnabled) {
      parts.add(currentSound.titleFa);
      parts.add(widget.vibrationEnabled
          ? BourseStrings.notifPresetStandard
          : BourseStrings.notifPresetSoundOnly);
    } else if (widget.vibrationEnabled) {
      parts.add(BourseStrings.notifPresetVibrateOnly);
    } else {
      parts.add(BourseStrings.notifPresetSilent);
    }
    if (widget.flashEnabled) parts.add('SOS');
    if (widget.ttsEnabled) parts.add('TTS');
    return parts.join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = BourseText.accentColor(context);
    final activePreset = _activePreset;
    final currentSound = _currentSoundPreset;
    final isPlaying = _playingSoundId == currentSound.id;
    final showBody = !widget.collapsible || _expanded;

    return Material(
      key: const Key('bourse_form_notif_card'),
      color: BourseText.cardColor(context),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(BourseText.cardRadius),
        side: BorderSide(color: BourseText.borderColor(context)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.collapsible)
            InkWell(
              key: const Key('bourse_notif_expand'),
              onTap: () => setState(() => _expanded = !_expanded),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: AppTokens.space16, vertical: 12),
                child: Row(
                  children: [
                    Icon(Icons.notifications_active_outlined, size: 18, color: accent),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            BourseStrings.alertSectionNotification,
                            style: BourseText.sectionLabel(context).copyWith(fontSize: 12.5),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            _summaryText(currentSound),
                            key: const Key('bourse_notif_summary'),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: BourseText.caption(context),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      _expanded ? BourseStrings.notifCollapse : BourseStrings.notifEdit,
                      style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold, color: accent),
                    ),
                    const SizedBox(width: 2),
                    Icon(
                      _expanded ? Icons.keyboard_arrow_up_rounded : Icons.keyboard_arrow_down_rounded,
                      size: 18,
                      color: accent,
                    ),
                  ],
                ),
              ),
            ),
          if (showBody)
            Padding(
              padding: widget.collapsible
                  ? const EdgeInsets.fromLTRB(AppTokens.space16, 0, AppTokens.space16, AppTokens.space16)
                  : const EdgeInsets.all(AppTokens.space16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (!widget.collapsible) ...[
                    Row(
                      children: [
                        Icon(Icons.notifications_active_outlined, size: 18, color: accent),
                        const SizedBox(width: 8),
                        Text(
                          BourseStrings.alertSectionNotification,
                          style: BourseText.sectionLabel(context).copyWith(fontSize: 13),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppTokens.space12),
                  ] else ...[
                    Divider(height: 1, color: BourseText.borderColor(context)),
                    const SizedBox(height: AppTokens.space12),
                  ],

            // 1. Quick notification profile chips
            Wrap(
              key: const Key('bourse_notif_presets'),
              spacing: AppTokens.space8,
              runSpacing: AppTokens.space8,
              children: [
                for (final preset in BourseNotifPreset.values)
                  ChoiceChip(
                    key: Key('bourse_notif_preset_${preset.name}'),
                    label: Text(_presetLabel(preset)),
                    selected: activePreset == preset,
                    showCheckmark: false,
                    visualDensity: VisualDensity.compact,
                    labelStyle: TextStyle(
                      fontSize: 11.5,
                      fontWeight: activePreset == preset ? FontWeight.bold : FontWeight.normal,
                      color: activePreset == preset ? accent : BourseText.secondaryColor(context),
                    ),
                    selectedColor: accent.withValues(alpha: 0.15),
                    backgroundColor: theme.scaffoldBackgroundColor,
                    side: BorderSide(color: activePreset == preset ? accent : BourseText.borderColor(context)),
                    onSelected: widget.enabled ? (_) => _selectPreset(preset) : null,
                  ),
              ],
            ),
            const SizedBox(height: AppTokens.space12),

            // 2. Alarm sound selector with audition
            Opacity(
              opacity: widget.soundEnabled ? 1.0 : 0.5,
              child: InkWell(
                key: const Key('bourse_form_sound_picker'),
                onTap: (widget.enabled && widget.soundEnabled) ? () => _openSoundPicker(context) : null,
                borderRadius: BorderRadius.circular(BourseText.inputRadius),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: theme.scaffoldBackgroundColor,
                    borderRadius: BorderRadius.circular(BourseText.inputRadius),
                    border: Border.all(
                      color: widget.soundEnabled
                          ? accent.withValues(alpha: 0.35)
                          : BourseText.borderColor(context),
                    ),
                  ),
                  child: Row(
                    children: [
                      Text(currentSound.icon, style: const TextStyle(fontSize: 20)),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              BourseStrings.notifSoundTitle,
                              style: BourseText.caption(context),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              widget.soundEnabled ? currentSound.titleFa : BourseStrings.notifSoundMuted,
                              key: const Key('bourse_form_sound_name'),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: BourseText.body(context).copyWith(
                                fontSize: 12.5,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                      ),
                      if (widget.soundEnabled) ...[
                        IconButton(
                          key: const Key('bourse_form_sound_preview'),
                          visualDensity: VisualDensity.compact,
                          icon: Icon(
                            isPlaying ? Icons.stop_circle_rounded : Icons.play_circle_filled_rounded,
                            color: isPlaying ? AppTokens.negative : accent,
                            size: 24,
                          ),
                          onPressed: widget.enabled ? () => _togglePreview(currentSound.id) : null,
                        ),
                        FilledButton.tonal(
                          style: FilledButton.styleFrom(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                            minimumSize: Size.zero,
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                          ),
                          onPressed: widget.enabled ? () => _openSoundPicker(context) : null,
                          child: const Text(
                            BourseStrings.notifChangeSound,
                            style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: AppTokens.space8),

            // 3. Physical delivery toggles (Sound, Vibration, SOS Flash)
            SwitchListTile(
              key: const Key('bourse_form_sound_enabled'),
              dense: true,
              contentPadding: EdgeInsets.zero,
              secondary: Icon(Icons.volume_up_rounded, size: 20, color: BourseText.secondaryColor(context)),
              title: Text(BourseStrings.notifSoundToggle, style: BourseText.body(context)),
              value: widget.soundEnabled,
              onChanged: widget.enabled ? widget.onSoundEnabledChanged : null,
            ),
            SwitchListTile(
              key: const Key('bourse_form_vibration_enabled'),
              dense: true,
              contentPadding: EdgeInsets.zero,
              secondary: Icon(Icons.vibration_rounded, size: 20, color: BourseText.secondaryColor(context)),
              title: Text(BourseStrings.notifVibrateToggle, style: BourseText.body(context)),
              value: widget.vibrationEnabled,
              onChanged: widget.enabled ? widget.onVibrationEnabledChanged : null,
            ),
            SwitchListTile(
              key: const Key('bourse_form_flash_enabled'),
              dense: true,
              contentPadding: EdgeInsets.zero,
              secondary: Icon(Icons.flashlight_on_rounded, size: 20, color: BourseText.secondaryColor(context)),
              title: Text(BourseStrings.notifFlashToggle, style: BourseText.body(context)),
              value: widget.flashEnabled,
              onChanged: widget.enabled ? widget.onFlashEnabledChanged : null,
            ),

            const SizedBox(height: AppTokens.space8),

            // 4. Dedicated TTS Voice Announcer box
            Material(
              color: theme.scaffoldBackgroundColor,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(BourseText.inputRadius),
                side: BorderSide(
                  color: widget.ttsEnabled ? accent.withValues(alpha: 0.45) : BourseText.borderColor(context),
                ),
              ),
              clipBehavior: Clip.antiAlias,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    SwitchListTile(
                      key: const Key('bourse_form_tts_enabled'),
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      secondary: Icon(
                        Icons.record_voice_over_rounded,
                        size: 20,
                        color: widget.ttsEnabled ? accent : BourseText.mutedColor(context),
                      ),
                      title: Text(
                        BourseStrings.notifTtsTitle,
                        style: BourseText.body(context).copyWith(fontWeight: FontWeight.w600),
                      ),
                      subtitle: Text(
                        BourseStrings.notifTtsSubtitle,
                        style: BourseText.caption(context),
                      ),
                      value: widget.ttsEnabled,
                      onChanged: widget.enabled ? widget.onTtsEnabledChanged : null,
                    ),
                    if (widget.ttsEnabled) ...[
                      const SizedBox(height: 4),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: OutlinedButton.icon(
                          key: const Key('bourse_form_tts_test'),
                          onPressed: widget.enabled
                              ? () {
                                  try {
                                    TtsService.instance.testVoice();
                                  } catch (_) {}
                                }
                              : null,
                          icon: const Icon(Icons.volume_up_rounded, size: 14),
                          label: const Text(BourseStrings.notifTtsTest, style: TextStyle(fontSize: 11)),
                          style: OutlinedButton.styleFrom(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            visualDensity: VisualDensity.compact,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    ],
      ),
    );
  }
}
