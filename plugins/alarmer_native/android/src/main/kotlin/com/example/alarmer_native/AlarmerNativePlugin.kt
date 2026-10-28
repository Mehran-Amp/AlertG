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

    // FLASH-1: SOS flash pattern state
    private var flashHandler: android.os.Handler? = null
    private var flashRunnable: Runnable? = null
    private var flashCameraId: String? = null

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

    // FLASH-1: SOS flash pattern (3 short, 3 long, 3 short, repeat)
    private fun startFlashSOS() {
        val ctx = context ?: return
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

        val pattern = longArrayOf(
            200, 200, 200, 200, 200, 1000,
            600, 200, 600, 200, 600, 1000,
            200, 200, 200, 200, 200, 2000
        )
        var index = 0
        var isOn = false
        val runnable = object : Runnable {
            override fun run() {
                try {
                    isOn = !isOn
                    cameraManager.setTorchMode(cameraId, isOn)
                } catch (e: Exception) {
                    stopFlashSOS()
                    return
                }
                index = (index + 1) % pattern.size
                handler.postDelayed(this, pattern[index])
            }
        }
        flashRunnable = runnable
        handler.post(runnable)
    }

    private fun stopFlashSOS() {
        flashRunnable?.let { flashHandler?.removeCallbacks(it) }
        flashRunnable = null
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