package com.example.bitcoin_checker

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager

/**
 * Universal Native Alert Audio & Vibration Player for Alarmer.
 * Plays high-priority audible alarms on STREAM_ALARM (alarm speaker channel)
 * and triggers physical hardware vibration even on lockscreen or in background.
 */
object AlarmerAlertPlayer {
    private var mediaPlayer: MediaPlayer? = null
    private var wakeLock: PowerManager.WakeLock? = null

    fun playAlarm(
        context: Context,
        soundName: String = "alarm_siren",
        vibrate: Boolean = true,
        volume: Float = 1.0f
    ) {
        acquireWakeLock(context)

        // 1. Trigger hardware vibration
        if (vibrate) {
            triggerVibration(context)
        }

        // 2. Play audible alarm on STREAM_ALARM
        try {
            stopSoundOnly()

            val cleanSound = soundName.replace(".wav", "").replace(".mp3", "").lowercase().trim()
            val resId = context.resources.getIdentifier(cleanSound, "raw", context.packageName).let {
                if (it != 0) it else context.resources.getIdentifier("alarm_siren", "raw", context.packageName)
            }

            if (resId != 0) {
                val player = MediaPlayer()
                mediaPlayer = player

                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                    player.setAudioAttributes(
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_ALARM)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                            .build()
                    )
                } else {
                    @Suppress("DEPRECATION")
                    player.setAudioStreamType(AudioManager.STREAM_ALARM)
                }

                val uri = Uri.parse("android.resource://${context.packageName}/$resId")
                player.setDataSource(context, uri)
                val safeVol = volume.coerceIn(0.1f, 1.0f)
                player.setVolume(safeVol, safeVol)
                player.isLooping = false

                player.setOnCompletionListener { mp ->
                    try {
                        mp.release()
                    } catch (_: Exception) {}
                    if (mediaPlayer == mp) {
                        mediaPlayer = null
                    }
                    releaseWakeLock()
                }

                player.setOnErrorListener { mp, _, _ ->
                    try {
                        mp.release()
                    } catch (_: Exception) {}
                    if (mediaPlayer == mp) {
                        mediaPlayer = null
                    }
                    releaseWakeLock()
                    true
                }

                player.prepare()
                player.start()
            }
        } catch (e: Exception) {
            android.util.Log.e("AlarmerAlertPlayer", "Error playing alarm sound: $e")
        }
    }

    fun triggerVibration(context: Context) {
        try {
            val pattern = longArrayOf(0, 500, 200, 500, 200, 500)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vibratorManager = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
                val vibrator = vibratorManager?.defaultVibrator ?: context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
                vibrator?.vibrate(VibrationEffect.createWaveform(pattern, -1))
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val vibrator = context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
                vibrator?.vibrate(VibrationEffect.createWaveform(pattern, -1))
            } else {
                @Suppress("DEPRECATION")
                val vibrator = context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
                @Suppress("DEPRECATION")
                vibrator?.vibrate(pattern, -1)
            }
        } catch (e: Exception) {
            android.util.Log.e("AlarmerAlertPlayer", "Error triggering vibration: $e")
        }
    }

    fun stop(context: Context? = null) {
        stopSoundOnly()
        try {
            context?.let { ctx ->
                val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    val vibratorManager = ctx.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
                    vibratorManager?.defaultVibrator ?: ctx.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
                } else {
                    ctx.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
                }
                vibrator?.cancel()
            }
        } catch (_: Exception) {}
        releaseWakeLock()
    }

    private fun stopSoundOnly() {
        try {
            mediaPlayer?.let { mp ->
                if (mp.isPlaying) {
                    mp.stop()
                }
                mp.release()
            }
            mediaPlayer = null
        } catch (_: Exception) {}
    }

    private fun acquireWakeLock(context: Context) {
        try {
            if (wakeLock == null) {
                val pm = context.getSystemService(Context.POWER_SERVICE) as? PowerManager
                wakeLock = pm?.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "bitcoin_checker:alert_audio_lock")
            }
            wakeLock?.acquire(15000) // 15 seconds auto release
        } catch (_: Exception) {}
    }

    private fun releaseWakeLock() {
        try {
            if (wakeLock?.isHeld == true) {
                wakeLock?.release()
            }
        } catch (_: Exception) {}
    }
}
