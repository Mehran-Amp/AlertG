package com.example.alarmer_native

import android.content.Context
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * Registers the com.example.bitcoin_checker/app_lifecycle channel on every
 * FlutterEngine (main UI, FCM background, foreground service). This is what
 * MainActivity used to do, but only for its own engine.
 */
class AlarmerNativePlugin : FlutterPlugin, MethodChannel.MethodCallHandler {
    private var channel: MethodChannel? = null
    private var context: Context? = null

    // FLASH-3: SOS flash pattern state (native, survives FCM isolate teardown)
    private var flashHandler: android.os.Handler? = null
    private var flashRunnable: Runnable? = null
    private var flashStopRunnable: Runnable? = null
    private var flashCameraId: String? = null

    // FLASH-3: hard ceiling — never flash longer than 10s, even if Dart dies.
    private val FLASH_HARD_CEILING_MS = 10_000L

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        context = binding.applicationContext
        channel = MethodChannel(binding.binaryMessenger, "com.example.bitcoin_checker/app_lifecycle")
        channel?.setMethodCallHandler(this)
        context?.let { ctx ->
            // Delay TTS init slightly so the engine is fully bound in FCM isolates
            android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
                AlarmerTtsEngine.init(ctx)
            }, 500)
        }
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel?.setMethodCallHandler(null)
        channel = null
        context = null
        // FLASH-3: never leave the torch on when the engine goes away.
        stopFlashSOS()
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "speak" -> {
                val text = call.argument<String>("text") ?: ""
                val langCode = call.argument<String>("lang") ?: "en"
                val rate = (call.argument<Double>("rate") ?: 1.0).toFloat()
                val pitch = (call.argument<Double>("pitch") ?: 1.0).toFloat()
                context?.let { ctx ->
                    AlarmerTtsEngine.speak(ctx, text, langCode, rate, pitch)
                }
                result.success(true)
            }
            "stopSpeak" -> {
                AlarmerTtsEngine.stop()
                result.success(true)
            }
            "playAlarm" -> {
                val soundName = call.argument<String>("sound") ?: "alarm_siren"
                val vibrate = call.argument<Boolean>("vibrate") ?: true
                val volume = (call.argument<Double>("volume") ?: 1.0).toFloat()
                context?.let { ctx ->
                    AlarmerAlertPlayer.playAlarm(ctx, soundName, vibrate, volume)
                }
                result.success(true)
            }
            "vibrate" -> {
                context?.let { ctx ->
                    AlarmerAlertPlayer.triggerVibration(ctx)
                }
                result.success(true)
            }
            "stopAlarm" -> {
                AlarmerAlertPlayer.stop(context)
                AlarmerTtsEngine.stop()
                result.success(true)
            }
            "startFlashSOS" -> {
                startFlashSOS()
                result.success(true)
            }
            "stopFlashSOS" -> {
                stopFlashSOS()
                result.success(true)
            }
            else -> {
                result.notImplemented()
            }
        }
    }

    // FLASH-3: SOS flash pattern (3 short, 3 long, 3 short, repeat),
    // self-terminating after FLASH_HARD_CEILING_MS. This runs entirely on the
    // native side, so it survives the Dart isolate being torn down (FCM
    // background handler, app swiped from recents).
    private fun startFlashSOS() {
        val ctx = context ?: return
        // Restart cleanly: cancel any in-flight pattern and torch state.
        stopFlashSOS()

        val cameraManager = ctx.getSystemService(android.content.Context.CAMERA_SERVICE)
                as? android.hardware.camera2.CameraManager ?: return
        val cameraId = try {
            cameraManager.cameraIdList.firstOrNull { id ->
                val chars = cameraManager.getCameraCharacteristics(id)
                chars.get(android.hardware.camera2.CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
            }
        } catch (e: Exception) { null } ?: return

        flashCameraId = cameraId
        val handler = android.os.Handler(android.os.Looper.getMainLooper())
        flashHandler = handler

        // SOS pattern: 3 short (200ms), 3 long (600ms), 3 short (200ms).
        // Values alternate ON/OFF; the first entry is the first ON duration.
        val pattern = longArrayOf(
            200, 200, 200, 200, 200, 1000,
            600, 200, 600, 200, 600, 1000,
            200, 200, 200, 200, 200, 2000
        )
        var index = 0
        var isOn = true
        // First ON is immediate, so the torch lights up right away.
        try { cameraManager.setTorchMode(cameraId, true) } catch (_: Exception) { stopFlashSOS(); return }

        val runnable = object : Runnable {
            override fun run() {
                try {
                    index = (index + 1) % pattern.size
                    isOn = !isOn
                    cameraManager.setTorchMode(cameraId, isOn)
                    handler.postDelayed(this, pattern[index])
                } catch (e: Exception) {
                    stopFlashSOS()
                }
            }
        }
        flashRunnable = runnable
        // We already turned the torch on; schedule the first OFF transition.
        handler.postDelayed(runnable, pattern[0])

        // FLASH-3: hard ceiling — force stop after 10s no matter what.
        val stopRunnable = Runnable {
            stopFlashSOS()
        }
        flashStopRunnable = stopRunnable
        handler.postDelayed(stopRunnable, FLASH_HARD_CEILING_MS)
    }

    private fun stopFlashSOS() {
        flashRunnable?.let { flashHandler?.removeCallbacks(it) }
        flashRunnable = null
        flashStopRunnable?.let { flashHandler?.removeCallbacks(it) }
        flashStopRunnable = null
        flashHandler = null
        flashCameraId?.let { id ->
            try {
                val ctx = context ?: return@let
                val cameraManager = ctx.getSystemService(android.content.Context.CAMERA_SERVICE)
                        as? android.hardware.camera2.CameraManager
                cameraManager?.setTorchMode(id, false)
            } catch (_: Exception) {}
        }
        flashCameraId = null
    }
}