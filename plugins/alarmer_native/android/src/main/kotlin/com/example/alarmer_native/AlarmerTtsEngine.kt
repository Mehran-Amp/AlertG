package com.example.alarmer_native

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.speech.tts.TextToSpeech
import java.util.Locale

/**
 * Universal Native Text-To-Speech Engine for Alarmer.
 * Operates across Main Activity, Background Isolates, and Firebase Cloud Messaging Services.
 * Routes audio through USAGE_ALARM / STREAM_ALARM for maximum audibility,
 * and maintains a CPU WakeLock while speech is in progress.
 */
object AlarmerTtsEngine : TextToSpeech.OnInitListener {
    private var tts: TextToSpeech? = null
    private var isReady = false
    private val pendingQueue = mutableListOf<TtsRequest>()
    private var wakeLock: PowerManager.WakeLock? = null

    data class TtsRequest(val text: String, val langCode: String, val rate: Float, val pitch: Float)

    @Synchronized
    fun init(context: Context) {
        if (tts == null) {
            try {
                val mainLooper = android.os.Looper.getMainLooper()
                if (mainLooper != null) {
                    // UI + foreground service isolates: init on main looper
                    android.os.Handler(mainLooper).post {
                        try {
                            if (tts == null) {
                                tts = TextToSpeech(context.applicationContext, this)
                            }
                        } catch (_: Exception) {}
                    }
                } else {
                    // FCM background isolate: no main looper, init directly
                    tts = TextToSpeech(context.applicationContext, this)
                }
            } catch (_: Exception) {}
        }
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            isReady = true
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                    val attributes = AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                    tts?.setAudioAttributes(attributes)
                }
            } catch (_: Exception) {}
            tts?.language = Locale.US
            synchronized(pendingQueue) {
                for (req in pendingQueue) {
                    performSpeak(req.text, req.langCode, req.rate, req.pitch)
                }
                pendingQueue.clear()
            }
        }
    }

    fun speak(context: Context, text: String, langCode: String = "en", rate: Float = 1.0f, pitch: Float = 1.0f) {
        if (text.isEmpty()) return
        acquireWakeLock(context)
        init(context)

        // Wait up to 1.5s for onInit (FCM background isolate is slower to bind TTS)
        var waited = 0
        while ((!isReady || tts == null) && waited < 1500) {
            try {
                Thread.sleep(100)
                waited += 100
            } catch (_: Exception) {
                break
            }
        }

        if (isReady && tts != null) {
            performSpeak(text, langCode, rate, pitch)
        } else {
            synchronized(pendingQueue) {
                pendingQueue.add(TtsRequest(text, langCode, rate, pitch))
            }
        }
    }

    private fun performSpeak(text: String, langCode: String, rate: Float, pitch: Float) {
        try {
            val hasPersian = text.any { it in '\u0600'..'\u06FF' }
            val locale = if (hasPersian || langCode.lowercase() in listOf("fa", "fa-ir", "per")) {
                Locale("fa", "IR")
            } else when (langCode.lowercase()) {
                "ar" -> Locale("ar", "SA")
                "de" -> Locale.GERMAN
                "fr" -> Locale.FRENCH
                "es" -> Locale("es", "ES")
                "tr" -> Locale("tr", "TR")
                "zh" -> Locale.CHINESE
                "ru" -> Locale("ru", "RU")
                else -> Locale.US
            }

            tts?.setSpeechRate(rate)
            tts?.setPitch(pitch)

            val langResult = tts?.setLanguage(locale)
            if (langResult == TextToSpeech.LANG_MISSING_DATA || langResult == TextToSpeech.LANG_NOT_SUPPORTED) {
                tts?.setLanguage(Locale.US)
            }

            val utteranceId = "AlarmerSpeech_${System.currentTimeMillis()}"
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                val params = Bundle().apply {
                    putInt(TextToSpeech.Engine.KEY_PARAM_STREAM, AudioManager.STREAM_ALARM)
                    putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, 1.0f)
                }
                tts?.speak(text, TextToSpeech.QUEUE_ADD, params, utteranceId)
            } else {
                @Suppress("DEPRECATION")
                val params = HashMap<String, String>().apply {
                    put(TextToSpeech.Engine.KEY_PARAM_STREAM, AudioManager.STREAM_ALARM.toString())
                    put(TextToSpeech.Engine.KEY_PARAM_UTTERANCE_ID, utteranceId)
                }
                @Suppress("DEPRECATION")
                tts?.speak(text, TextToSpeech.QUEUE_ADD, params)
            }
        } catch (_: Exception) {}
    }

    private fun acquireWakeLock(context: Context) {
        try {
            if (wakeLock == null) {
                val pm = context.getSystemService(Context.POWER_SERVICE) as? PowerManager
                wakeLock = pm?.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "bitcoin_checker:tts_wake_lock")
            }
            wakeLock?.acquire(12000) // 12 seconds auto release
        } catch (_: Exception) {}
    }

    fun stop() {
        try {
            tts?.stop()
        } catch (_: Exception) {}
        try {
            if (wakeLock?.isHeld == true) {
                wakeLock?.release()
            }
        } catch (_: Exception) {}
    }

    fun shutdown() {
        try {
            tts?.stop()
            tts?.shutdown()
            tts = null
            isReady = false
        } catch (_: Exception) {}
        try {
            if (wakeLock?.isHeld == true) {
                wakeLock?.release()
            }
        } catch (_: Exception) {}
    }
}
