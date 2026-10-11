package com.example.bitcoin_checker

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.speech.tts.TextToSpeech
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.util.Locale

/**
 * Main Activity for Alarmer.
 * Handles App Lifecycle, Background Minification, Widget State, Native Text-To-Speech (TTS),
 * and 1-Tap Direct OEM Autostart Launchers for Xiaomi, Samsung, Huawei, Oppo, Vivo, etc.
 */
class MainActivity : FlutterActivity(), TextToSpeech.OnInitListener {
    private val CHANNEL = "com.example.bitcoin_checker/app_lifecycle"
    private var tts: TextToSpeech? = null
    private var isTtsReady = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        try {
            tts = TextToSpeech(applicationContext, this)
        } catch (_: Exception) {}
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            isTtsReady = true
            tts?.language = Locale.US
        }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "speak" -> {
                    val text = call.argument<String>("text") ?: ""
                    val langCode = call.argument<String>("lang") ?: "en"
                    val rate = call.argument<Double>("rate") ?: 1.0
                    val pitch = call.argument<Double>("pitch") ?: 1.0

                    if (tts == null) {
                        try {
                            tts = TextToSpeech(applicationContext) { initStatus ->
                                if (initStatus == TextToSpeech.SUCCESS) {
                                    isTtsReady = true
                                    performSpeak(text, langCode, rate.toFloat(), pitch.toFloat())
                                }
                            }
                        } catch (_: Exception) {}
                    } else {
                        performSpeak(text, langCode, rate.toFloat(), pitch.toFloat())
                    }
                    result.success(true)
                }
                "stopSpeak" -> {
                    try {
                        tts?.stop()
                    } catch (_: Exception) {}
                    result.success(true)
                }
                "sendToBackground" -> {
                    val moved = moveTaskToBack(true)
                    result.success(moved)
                }
                "openAutostartSettings" -> {
                    val opened = openAutostartPermissionScreen()
                    result.success(opened)
                }
                "openAppSettings" -> {
                    try {
                        val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                            data = Uri.parse("package:$packageName")
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        }
                        startActivity(intent)
                        result.success(true)
                    } catch (_: Exception) {
                        result.success(false)
                    }
                }
                "openBatteryOptimizationSettings" -> {
                    try {
                        val intent = Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS).apply {
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        }
                        startActivity(intent)
                        result.success(true)
                    } catch (_: Exception) {
                        val opened = openAutostartPermissionScreen()
                        result.success(opened)
                    }
                }
                "updateWidgetList" -> {
                    val json = call.argument<String>("json") ?: ""
                    val prefs = getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
                    prefs.edit()
                        .putString("flutter.widget_alerts_json", json)
                        .apply()

                    AlarmerAppWidgetProvider.updateAllWidgets(this)
                    result.success(true)
                }
                "updateWidget" -> {
                    val symbol = call.argument<String>("symbol") ?: "BTC/USDT"
                    val price = call.argument<String>("price") ?: "$87,420.00"
                    val change = call.argument<String>("change") ?: "+3.52% ▲"
                    val exchange = call.argument<String>("exchange") ?: "Binance • Live"
                    val status = call.argument<String>("status") ?: "⚡ Active Alerts Monitored"

                    val prefs = getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
                    prefs.edit()
                        .putString("flutter.widget_symbol", symbol)
                        .putString("flutter.widget_price", price)
                        .putString("flutter.widget_change", change)
                        .putString("flutter.widget_exchange", exchange)
                        .putString("flutter.widget_status", status)
                        .apply()

                    AlarmerAppWidgetProvider.updateAllWidgets(this)
                    result.success(true)
                }
                else -> {
                    result.notImplemented()
                }
            }
        }
    }

    private fun openAutostartPermissionScreen(): Boolean {
        val intents = listOf(
            // Xiaomi / MIUI / HyperOS
            Intent().setComponent(ComponentName("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity")),
            Intent().setComponent(ComponentName("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartActivity")),
            Intent("miui.intent.action.OP_AUTO_START").addCategory(Intent.CATEGORY_DEFAULT),

            // Samsung
            Intent().setComponent(ComponentName("com.samsung.android.lool", "com.samsung.android.sm.ui.battery.BatteryActivity")),
            Intent().setComponent(ComponentName("com.samsung.android.sm", "com.samsung.android.sm.ui.battery.BatteryActivity")),
            Intent().setComponent(ComponentName("com.samsung.android.sm_cn", "com.samsung.android.sm.ui.battery.BatteryActivity")),

            // Huawei / Honor
            Intent().setComponent(ComponentName("com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity")),
            Intent().setComponent(ComponentName("com.huawei.systemmanager", "com.huawei.systemmanager.optimize.process.ProtectActivity")),
            Intent().setComponent(ComponentName("com.huawei.systemmanager", "com.huawei.systemmanager.appcontrol.activity.StartupAppControlActivity")),

            // Oppo / Realme / ColorOS
            Intent().setComponent(ComponentName("com.coloros.safecenter", "com.coloros.safecenter.permission.startup.StartupAppListActivity")),
            Intent().setComponent(ComponentName("com.coloros.safecenter", "com.coloros.safecenter.startupapp.StartupAppListActivity")),
            Intent().setComponent(ComponentName("com.oppo.safe", "com.oppo.safe.permission.startup.StartupAppListActivity")),
            Intent().setComponent(ComponentName("com.coloros.oppoguardelf", "com.coloros.powermanager.fuelgaard.PowerConsumptionActivity")),

            // Vivo / iQOO / FuntouchOS
            Intent().setComponent(ComponentName("com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity")),
            Intent().setComponent(ComponentName("com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.AddWhiteListActivity")),
            Intent().setComponent(ComponentName("com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.BgStartUpManager")),

            // OnePlus
            Intent().setComponent(ComponentName("com.oneplus.security", "com.oneplus.security.chainlaunch.view.ChainLaunchAppListAct")),

            // ASUS
            Intent().setComponent(ComponentName("com.asus.mobilemanager", "com.asus.mobilemanager.autostart.AutoStartActivity"))
        )

        for (intent in intents) {
            try {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                startActivity(intent)
                return true
            } catch (_: Exception) {}
        }

        // Generic Fallback: Application Details Settings page
        try {
            val fallback = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.parse("package:$packageName")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(fallback)
            return true
        } catch (_: Exception) {}

        return false
    }

    private fun performSpeak(text: String, langCode: String, rate: Float, pitch: Float) {
        if (text.isEmpty()) return
        try {
            val locale = when (langCode.lowercase()) {
                "fa" -> Locale("fa", "IR")
                "ar" -> Locale("ar", "SA")
                "de" -> Locale.GERMAN
                "fr" -> Locale.FRENCH
                "es" -> Locale("es", "ES")
                "tr" -> Locale("tr", "TR")
                "zh" -> Locale.CHINESE
                "ru" -> Locale("ru", "RU")
                "ckb" -> Locale("ar", "IQ")
                else -> Locale.US
            }

            tts?.setSpeechRate(rate)
            tts?.setPitch(pitch)

            val langResult = tts?.setLanguage(locale)
            if (langResult == TextToSpeech.LANG_MISSING_DATA || langResult == TextToSpeech.LANG_NOT_SUPPORTED) {
                // Fallback to English if device does not have target locale pack installed
                tts?.setLanguage(Locale.US)
            }

            // Use QUEUE_ADD so multiple concurrent notifications queue their speech sequentially without overlapping
            tts?.speak(text, TextToSpeech.QUEUE_ADD, null, "AlarmerSpeech_${System.currentTimeMillis()}")
        } catch (_: Exception) {}
    }

    override fun onDestroy() {
        try {
            tts?.stop()
            tts?.shutdown()
        } catch (_: Exception) {}
        super.onDestroy()
    }
}
