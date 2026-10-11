import 'dart:io';
import 'dart:math';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import '../../../core/localization/app_strings.dart';

class AlarmSoundPreset {
  final String id;
  final String titleFa;
  final String titleEn;
  final String icon;
  final int baseFreq;
  final int secondaryFreq;
  final double durationSec;

  const AlarmSoundPreset({
    required this.id,
    required this.titleFa,
    required this.titleEn,
    required this.icon,
    required this.baseFreq,
    required this.secondaryFreq,
    this.durationSec = 2.5,
  });

  String getTitle(String lang) {
    return AppStrings.get('sound_${id}_title', lang);
  }
}

/// High-Performance Audio Engine for Market Alerts
/// Features native asset-based playback + local synthesis fail-safe.
class SoundManager {
  static final SoundManager _instance = SoundManager._internal();
  factory SoundManager() => _instance;
  SoundManager._internal();

  final AudioPlayer _player = AudioPlayer();
  bool _isPlaying = false;
  String? _currentlyPlayingId;

  static const List<AlarmSoundPreset> presets = [
    AlarmSoundPreset(
      id: 'alarm_siren',
      titleFa: '🚨 آژیر اضطراری نوسان (Siren)',
      titleEn: 'Emergency Market Siren',
      icon: '🚨',
      baseFreq: 880,
      secondaryFreq: 1760,
      durationSec: 3.0,
    ),
    AlarmSoundPreset(
      id: 'radar_pulse',
      titleFa: '📡 پالس رادار و تارگت (Radar)',
      titleEn: 'Radar Target Pulse',
      icon: '📡',
      baseFreq: 1200,
      secondaryFreq: 600,
      durationSec: 2.5,
    ),
    AlarmSoundPreset(
      id: 'cyber_chime',
      titleFa: '⚡ چایم سایبری بایننس (Cyber)',
      titleEn: 'Cyber Trading Chime',
      icon: '⚡',
      baseFreq: 1046,
      secondaryFreq: 1318,
      durationSec: 2.0,
    ),
    AlarmSoundPreset(
      id: 'crystal_ping',
      titleFa: '💎 پینگ کریستالی شفاف (Crystal)',
      titleEn: 'Crystal Clear Ping',
      icon: '💎',
      baseFreq: 1568,
      secondaryFreq: 2093,
      durationSec: 1.8,
    ),
    AlarmSoundPreset(
      id: 'bullish_rise',
      titleFa: '📈 صعود شارپ و بولیش (Ascend)',
      titleEn: 'Bullish Price Surge',
      icon: '📈',
      baseFreq: 523,
      secondaryFreq: 1046,
      durationSec: 2.5,
    ),
    AlarmSoundPreset(
      id: 'coin_drop',
      titleFa: '🪙 صدای تراکنش و سکه (Coin)',
      titleEn: 'Digital Coin Drop',
      icon: '🪙',
      baseFreq: 1400,
      secondaryFreq: 1800,
      durationSec: 1.5,
    ),
    AlarmSoundPreset(
      id: 'alert_horn',
      titleFa: '🎺 شیپور اعلام خطر (Horn)',
      titleEn: 'Market Alert Horn',
      icon: '🎺',
      baseFreq: 440,
      secondaryFreq: 660,
      durationSec: 3.0,
    ),
    AlarmSoundPreset(
      id: 'classic_bell',
      titleFa: '⏰ زنگ کلاسیک وال‌استریت (Bell)',
      titleEn: 'Wall Street Bell',
      icon: '⏰',
      baseFreq: 784,
      secondaryFreq: 988,
      durationSec: 2.0,
    ),
  ];

  bool isSoundPlaying(String id) => _isPlaying && _currentlyPlayingId == id;

  /// Plays synthesized audio with 100% Android/iOS hardware speaker compatibility
  Future<void> playPreset(String soundId, {double volume = 1.0, bool loop = false}) async {
    try {
      await stop();

      final preset = presets.firstWhere(
        (p) => p.id == soundId,
        orElse: () => presets.first,
      );

      // Trigger immediate tactile haptic
      await HapticFeedback.mediumImpact();

      // Configure AudioContext for direct alarm speaker routing
      await _player.setAudioContext(AudioContext(
        android: const AudioContextAndroid(
          isSpeakerphoneOn: true,
          stayAwake: true,
          contentType: AndroidContentType.music,
          usageType: AndroidUsageType.alarm,
          audioFocus: AndroidAudioFocus.gainTransientExclusive,
        ),
        iOS: AudioContextIOS(
          category: AVAudioSessionCategory.playback,
          options: const {
            AVAudioSessionOptions.duckOthers,
          },
        ),
      ));

      await _player.setVolume(volume.clamp(0.1, 1.0));
      if (loop) {
        await _player.setReleaseMode(ReleaseMode.loop);
      } else {
        await _player.setReleaseMode(ReleaseMode.release);
      }

      _isPlaying = true;
      _currentlyPlayingId = soundId;

      try {
        // 1. Try bundled asset playback
        await _player.play(AssetSource('sounds/${preset.id}.wav'));
      } catch (assetErr) {
        debugPrint('Asset playback error: $assetErr, trying file synthesis...');
        // 2. Fallback to temp file synthesis
        final tempDir = await getTemporaryDirectory();
        final soundFile = File('${tempDir.path}/alarmer_${preset.id}.wav');
        if (!await soundFile.exists()) {
          final wavBytes = _generateWavBytes(
            freq1: preset.baseFreq,
            freq2: preset.secondaryFreq,
            durationSeconds: preset.durationSec,
          );
          await soundFile.writeAsBytes(wavBytes, flush: true);
        }
        await _player.play(DeviceFileSource(soundFile.path));
      }

      _player.onPlayerComplete.listen((_) {
        _isPlaying = false;
        _currentlyPlayingId = null;
      });
    } catch (e) {
      debugPrint('Error in SoundManager: $e');
      try {
        await SystemSound.play(SystemSoundType.alert);
      } catch (_) {}
      _isPlaying = false;
      _currentlyPlayingId = null;
    }
  }

  Future<void> stop() async {
    try {
      await _player.stop();
    } catch (_) {}
    _isPlaying = false;
    _currentlyPlayingId = null;
  }

  /// Generates pristine CD-Quality (44.1kHz 16-bit Mono) WAV PCM Audio Buffer
  static Uint8List _generateWavBytes({
    required int freq1,
    required int freq2,
    required double durationSeconds,
    int sampleRate = 44100,
  }) {
    final numSamples = (durationSeconds * sampleRate).toInt();
    final dataSize = numSamples * 2;
    final fileSize = 44 + dataSize;

    final buffer = ByteData(fileSize);

    // RIFF chunk descriptor
    buffer.setUint8(0, 0x52); // 'R'
    buffer.setUint8(1, 0x49); // 'I'
    buffer.setUint8(2, 0x46); // 'F'
    buffer.setUint8(3, 0x46); // 'F'
    buffer.setUint32(4, fileSize - 8, Endian.little);
    buffer.setUint8(8, 0x57);  // 'W'
    buffer.setUint8(9, 0x41);  // 'A'
    buffer.setUint8(10, 0x56); // 'V'
    buffer.setUint8(11, 0x45); // 'E'

    // 'fmt ' subchunk
    buffer.setUint8(12, 0x66); // 'f'
    buffer.setUint8(13, 0x6D); // 'm'
    buffer.setUint8(14, 0x74); // 't'
    buffer.setUint8(15, 0x20); // ' '
    buffer.setUint32(16, 16, Endian.little);
    buffer.setUint16(20, 1, Endian.little);
    buffer.setUint16(22, 1, Endian.little);
    buffer.setUint32(24, sampleRate, Endian.little);
    buffer.setUint32(28, sampleRate * 2, Endian.little);
    buffer.setUint16(32, 2, Endian.little);
    buffer.setUint16(34, 16, Endian.little);

    // 'data' subchunk
    buffer.setUint8(36, 0x64); // 'd'
    buffer.setUint8(37, 0x61); // 'a'
    buffer.setUint8(38, 0x74); // 't'
    buffer.setUint8(39, 0x61); // 'a'
    buffer.setUint32(40, dataSize, Endian.little);

    int offset = 44;
    for (int i = 0; i < numSamples; i++) {
      final t = i / sampleRate;
      final currentFreq = ((t * 5).toInt() % 2 == 0) ? freq1 : freq2;
      final wave = (sin(2 * pi * currentFreq * t) + 0.3 * sin(4 * pi * currentFreq * t)) / 1.3;
      final pulsePhase = (t * 5) - (t * 5).floor();
      final env = (sin(pi * pulsePhase)).clamp(0.0, 1.0);
      final sample = (wave * 30000 * env).toInt().clamp(-32768, 32767);
      buffer.setInt16(offset, sample, Endian.little);
      offset += 2;
    }

    return buffer.buffer.asUint8List();
  }
}
