package com.example.bitcoin_checker

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.RemoteViews
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.text.DecimalFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs

/**
 * Native Android Home Screen AppWidget Provider for Alarmer Pro.
 * - Fixed Obsidian Dark Luxury aesthetic
 * - 2-Line Rich Financial Cards with readable Persian/English names, exchange & target price, and proximity bar
 * - Silent Background Refresh ('⟳') that fetches live prices directly from the server without opening the app
 * - Quick Add ('＋') and Header Brand / Card tap to open the app
 */
class AlarmerAppWidgetProvider : AppWidgetProvider() {

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        when (intent.action) {
            ACTION_REFRESH_WIDGET -> {
                // Silent background refresh WITHOUT launching MainActivity!
                setRefreshingState(context, true)
                val pendingResult = goAsync()
                Thread {
                    try {
                        refreshPricesInBackground(context)
                    } catch (_: Exception) {
                    } finally {
                        updateAllWidgets(context)
                        try {
                            pendingResult.finish()
                        } catch (_: Exception) {}
                    }
                }.start()
            }
            ACTION_WIDGET_DATA_UPDATED -> {
                updateAllWidgets(context)
            }
        }
    }

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        for (appWidgetId in appWidgetIds) {
            updateAppWidget(context, appWidgetManager, appWidgetId)
        }
    }

    companion object {
        const val ACTION_REFRESH_WIDGET = "com.example.bitcoin_checker.ACTION_REFRESH_WIDGET"
        const val ACTION_WIDGET_DATA_UPDATED = "com.example.bitcoin_checker.ACTION_WIDGET_DATA_UPDATED"

        private fun setRefreshingState(context: Context, refreshing: Boolean) {
            try {
                val appWidgetManager = AppWidgetManager.getInstance(context)
                val componentName = ComponentName(context, AlarmerAppWidgetProvider::class.java)
                val appWidgetIds = appWidgetManager.getAppWidgetIds(componentName)
                if (appWidgetIds != null && appWidgetIds.isNotEmpty()) {
                    for (appWidgetId in appWidgetIds) {
                        val views = RemoteViews(context.packageName, R.layout.alarmer_appwidget_layout)
                        views.setTextViewText(
                            R.id.widget_refresh_btn,
                            if (refreshing) "⟳ ..." else "⟳ بروزرسانی"
                        )
                        appWidgetManager.partiallyUpdateAppWidget(appWidgetId, views)
                    }
                }
            } catch (_: Exception) {}
        }

        /**
         * Silently fetches latest prices from server API for all widget items in background
         * and updates FlutterSharedPreferences without opening the app.
         */
        private fun refreshPricesInBackground(context: Context) {
            val prefs = context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
            val jsonStr = prefs.getString("flutter.widget_alerts_json", null) ?: return
            if (jsonStr.isEmpty()) return

            val root = JSONObject(jsonStr)
            val serverUrl = root.optString("serverUrl", "https://aisocialfeed.com").trimEnd('/')
            val items = root.optJSONArray("items") ?: return

            var updatedAny = false
            for (i in 0 until items.length()) {
                val item = items.optJSONObject(i) ?: continue
                val rawExchange = item.optString("exchangeId", "").lowercase(Locale.ROOT)
                val rawSymbol = item.optString("rawSymbol", "")
                if (rawExchange.isEmpty() || rawSymbol.isEmpty()) continue

                val apiExchange = when (rawExchange) {
                    "iran_domestic" -> "iran_market"
                    "iran_bourse" -> "tse"
                    else -> rawExchange
                }

                val livePrice = fetchLivePriceFromServer(serverUrl, apiExchange, rawSymbol)
                if (livePrice != null && livePrice > 0.0) {
                    updatedAny = true
                    val isIranAsset = item.optBoolean("isIranAsset", apiExchange in listOf("iran_market", "tse", "tabdeal", "kifpool"))
                    val counterCurrency = item.optString("counterCurrency", if (isIranAsset) "TMN" else "USDT")
                    item.put("price", formatPriceForWidget(livePrice, counterCurrency, isIranAsset))

                    val isDone = item.optBoolean("isDone", false)
                    if (!isDone) {
                        val basePrice = item.optDouble("basePrice", 0.0)
                        val targetPrice = item.optDouble("targetPrice", 0.0)
                        val percentRule = item.optDouble("percent", 0.0)
                        val conditionType = item.optString("conditionType", "priceThreshold")
                        val direction = item.optString("direction", "above")

                        var diffPct = 0.0
                        if (basePrice > 0.0 && abs(livePrice - basePrice) > 0.0001) {
                            diffPct = ((livePrice - basePrice) / basePrice) * 100.0
                        } else if (conditionType == "priceThreshold" && targetPrice > 0.0) {
                            diffPct = ((targetPrice - livePrice) / livePrice) * 100.0
                        } else if (percentRule > 0.0) {
                            diffPct = if (direction == "below") -percentRule else percentRule
                        }

                        val isUp = diffPct >= 0.0
                        item.put("isPositive", isUp)
                        item.put("isNegative", !isUp)

                        // Calculate distance to target & proximity (0..100)
                        var isNearTarget = false
                        if (targetPrice > 0.0) {
                            val distPct = (abs(targetPrice - livePrice) / livePrice) * 100.0
                            isNearTarget = distPct <= 1.0
                            val prox = if (basePrice > 0.0 && abs(targetPrice - basePrice) > 0.0001) {
                                val totalDist = abs(targetPrice - basePrice)
                                val remDist = abs(targetPrice - livePrice)
                                (((totalDist - remDist) / totalDist) * 100.0).toInt().coerceIn(8, 99)
                            } else {
                                (100.0 - (distPct * 12.0)).toInt().coerceIn(10, 99)
                            }
                            item.put("proximity", prox)
                        }
                        item.put("isNearTarget", isNearTarget)

                        val sign = if (isUp) "+" else ""
                        val arrow = if (isUp) "▲" else "▼"
                        val pctStr = String.format(Locale.US, "%s%.2f%% %s", sign, diffPct, arrow)
                        item.put("badge", if (isNearTarget) "🔥 $pctStr" else pctStr)
                    }
                }
            }

            val timeNow = SimpleDateFormat("HH:mm", Locale.US).format(Date())
            val activeCount = root.optInt("activeCount", items.length())
            val hitCount = root.optInt("hitCount", 0)
            val subtitle = if (hitCount > 0) {
                "$activeCount فعال • $hitCount زده‌شده • $timeNow"
            } else {
                "$activeCount آلارم فعال • بروزرسانی $timeNow"
            }
            root.put("subtitle", subtitle)
            root.put("lastUpdated", timeNow)

            if (updatedAny || items.length() >= 0) {
                prefs.edit().putString("flutter.widget_alerts_json", root.toString()).apply()
            }
        }

        private fun fetchLivePriceFromServer(serverUrl: String, exchange: String, symbol: String): Double? {
            var conn: HttpURLConnection? = null
            return try {
                val encodedSym = Uri.encode(symbol)
                val url = URL("$serverUrl/api/price/$exchange/$encodedSym")
                conn = (url.openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"
                    connectTimeout = 4500
                    readTimeout = 4500
                    setRequestProperty("Accept", "application/json")
                }
                if (conn.responseCode == 200) {
                    val reader = BufferedReader(InputStreamReader(conn.inputStream))
                    val response = reader.use { it.readText() }
                    val json = JSONObject(response)
                    val price = json.optDouble("price", -1.0)
                    if (!price.isNaN() && price > 0.0) price else null
                } else {
                    null
                }
            } catch (_: Exception) {
                null
            } finally {
                try {
                    conn?.disconnect()
                } catch (_: Exception) {}
            }
        }

        private fun formatPriceForWidget(price: Double, counterCurrency: String, isIranAsset: Boolean): String {
            val upperCurr = counterCurrency.uppercase(Locale.ROOT)
            val isToman = isIranAsset || upperCurr == "TMN" || upperCurr == "IRT" || upperCurr.contains("تومان")
            return if (isToman) {
                val df = DecimalFormat("#,###")
                "${df.format(price.toLong())} تومان"
            } else {
                val prefix = if (upperCurr == "USD" || upperCurr == "USDT" || upperCurr == "USDC") "$" else ""
                val formatted = when {
                    price >= 1000.0 -> DecimalFormat("#,##0.00").format(price)
                    price >= 1.0 -> DecimalFormat("#,##0.00##").format(price)
                    price >= 0.01 -> DecimalFormat("0.0000").format(price)
                    else -> DecimalFormat("0.000000").format(price)
                }
                if (prefix.isNotEmpty()) "$prefix$formatted" else "$formatted $upperCurr"
            }
        }

        fun updateAppWidget(
            context: Context,
            appWidgetManager: AppWidgetManager,
            appWidgetId: Int
        ) {
            try {
                val views = RemoteViews(context.packageName, R.layout.alarmer_appwidget_layout)

                // 1. Silent Background Refresh Button ('⟳ بروزرسانی') -> Broadcast only, does NOT open app!
                val refreshIntent = Intent(context, AlarmerAppWidgetProvider::class.java).apply {
                    action = ACTION_REFRESH_WIDGET
                }
                val refreshPendingIntent = PendingIntent.getBroadcast(
                    context,
                    1,
                    refreshIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
                views.setOnClickPendingIntent(R.id.widget_refresh_btn, refreshPendingIntent)

                // 2. Open App Intent on Header Brand, Quick Add ('＋'), Footer, and Empty State
                val openAppIntent = Intent(context, MainActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                }
                val openAppPendingIntent = PendingIntent.getActivity(
                    context,
                    3,
                    openAppIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
                views.setOnClickPendingIntent(R.id.widget_header_brand, openAppPendingIntent)
                views.setOnClickPendingIntent(R.id.widget_add_btn, openAppPendingIntent)
                views.setOnClickPendingIntent(R.id.widget_footer_text, openAppPendingIntent)
                views.setOnClickPendingIntent(R.id.widget_empty_text, openAppPendingIntent)

                // Read SharedPreferences state
                val prefs = context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
                val jsonStr = prefs.getString("flutter.widget_alerts_json", null)

                views.setInt(R.id.widget_root, "setBackgroundResource", R.drawable.widget_background_dark)
                views.setInt(R.id.widget_refresh_btn, "setBackgroundResource", R.drawable.widget_live_pill_dark)
                views.setInt(R.id.widget_add_btn, "setBackgroundResource", R.drawable.widget_add_pill_dark)

                if (jsonStr != null && jsonStr.isNotEmpty()) {
                    try {
                        val root = JSONObject(jsonStr)
                        val activeCount = root.optInt("activeCount", 0)
                        val headerTitle = root.optString("title", "Alarmer Pro")
                        val subtitle = root.optString("subtitle", "$activeCount آلارم فعال")
                        val footerText = root.optString("footerText", "برای مدیریت آلارم‌ها ضربه بزنید")
                        val refreshText = root.optString("refreshText", "⟳ بروزرسانی")

                        views.setTextViewText(R.id.widget_header_title, headerTitle)
                        views.setTextColor(R.id.widget_header_title, 0xFFF8FAFC.toInt())

                        views.setTextViewText(R.id.widget_subtitle, subtitle)
                        views.setTextColor(R.id.widget_subtitle, 0xFF94A3B8.toInt())

                        views.setTextViewText(R.id.widget_refresh_btn, refreshText)
                        views.setTextColor(R.id.widget_refresh_btn, 0xFF10B981.toInt())

                        views.setTextViewText(R.id.widget_footer_text, footerText)
                        views.setTextColor(R.id.widget_footer_text, 0xFF64748B.toInt())
                    } catch (_: Exception) {}
                }

                // Bind RemoteViewsService adapter for the scrollable ListView
                val serviceIntent = Intent(context, AlarmerWidgetService::class.java).apply {
                    putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
                    data = Uri.parse(toUri(Intent.URI_INTENT_SCHEME))
                }
                views.setRemoteAdapter(R.id.widget_listview, serviceIntent)
                views.setEmptyView(R.id.widget_listview, R.id.widget_empty_text)

                // Item click template (tapping any row opens MainActivity)
                val itemClickIntent = Intent(context, MainActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                }
                val itemClickPendingIntent = PendingIntent.getActivity(
                    context,
                    2,
                    itemClickIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
                views.setPendingIntentTemplate(R.id.widget_listview, itemClickPendingIntent)

                // Push update and notify dataset changed
                appWidgetManager.updateAppWidget(appWidgetId, views)
                appWidgetManager.notifyAppWidgetViewDataChanged(appWidgetId, R.id.widget_listview)
            } catch (_: Exception) {}
        }

        fun updateAllWidgets(context: Context) {
            try {
                val appWidgetManager = AppWidgetManager.getInstance(context)
                val componentName = ComponentName(context, AlarmerAppWidgetProvider::class.java)
                val appWidgetIds = appWidgetManager.getAppWidgetIds(componentName)
                if (appWidgetIds != null && appWidgetIds.isNotEmpty()) {
                    for (appWidgetId in appWidgetIds) {
                        updateAppWidget(context, appWidgetManager, appWidgetId)
                    }
                    appWidgetManager.notifyAppWidgetViewDataChanged(appWidgetIds, R.id.widget_listview)
                }
            } catch (_: Exception) {}
        }
    }
}
