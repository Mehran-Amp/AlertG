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

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        context = binding.applicationContext
        channel = MethodChannel(binding.binaryMessenger, "com.example.bitcoin_checker/app_lifecycle")
        channel?.setMethodCallHandler(this)
        context?.let { ctx ->
            AlarmerTtsEngine.init(ctx)
        }
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel?.setMethodCallHandler(null)
        channel = null
        context = null
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
            else -> {
                result.notImplemented()
            }
        }
    }
}