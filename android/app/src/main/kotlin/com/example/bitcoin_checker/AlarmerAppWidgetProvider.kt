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

/**
 * Native Android Home Screen AppWidget Provider for Alarmer.
 * - Dynamic theme switching (Dark & Light)
 * - Scrollable ListView displaying ALL symbols in exact user custom order
 * - Interactive 'Check All' button with instant sync
 */
class AlarmerAppWidgetProvider : AppWidgetProvider() {

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action == ACTION_REFRESH_WIDGET) {
            updateAllWidgets(context)
            try {
                val launchIntent = Intent(context, MainActivity::class.java).apply {
                    action = "ACTION_CHECK_ALL_ALERTS"
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                }
                context.startActivity(launchIntent)
            } catch (_: Exception) {}
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

        fun updateAppWidget(
            context: Context,
            appWidgetManager: AppWidgetManager,
            appWidgetId: Int
        ) {
            try {
                val views = RemoteViews(context.packageName, R.layout.alarmer_appwidget_layout)

                // Tap on 'Check All' button
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

                // Read SharedPreferences state
                val prefs = context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
                val jsonStr = prefs.getString("flutter.widget_alerts_json", null)

                var isDark = true
                var primaryColor = 0xFF10B981.toInt()
                var textPrimaryColor = 0xFFF9FAFB.toInt()
                var textSecondaryColor = 0xFF9CA3AF.toInt()
                var borderColor = 0xFF374151.toInt()

                if (jsonStr != null && jsonStr.isNotEmpty()) {
                    try {
                        val root = JSONObject(jsonStr)
                        val activeCount = root.optInt("activeCount", 0)
                        val headerTitle = root.optString("title", "Alarmer Live")
                        val subtitle = root.optString("subtitle", "$activeCount active")
                        val footerText = root.optString("footerText", "Tap to open Alarmer")
                        val themeObj = root.optJSONObject("theme")

                        if (themeObj != null) {
                            isDark = themeObj.optInt("isDark", 1) == 1
                            primaryColor = themeObj.optLong("primary", if (isDark) 0xFF10B981 else 0xFF059669).toInt()
                            textPrimaryColor = themeObj.optLong("textPrimary", if (isDark) 0xFFF9FAFB else 0xFF111827).toInt()
                            textSecondaryColor = themeObj.optLong("textSecondary", if (isDark) 0xFF9CA3AF else 0xFF4B5563).toInt()
                            borderColor = themeObj.optLong("border", if (isDark) 0xFF374151 else 0xFFD1D5DB).toInt()
                        }

                        // Backgrounds
                        val bgRes = if (isDark) R.drawable.widget_background_dark else R.drawable.widget_background_light
                        val btnRes = if (isDark) R.drawable.widget_live_pill_dark else R.drawable.widget_live_pill_light

                        views.setInt(R.id.widget_root, "setBackgroundResource", bgRes)
                        views.setInt(R.id.widget_refresh_btn, "setBackgroundResource", btnRes)

                        views.setTextViewText(R.id.widget_header_title, headerTitle)
                        views.setTextColor(R.id.widget_header_title, textPrimaryColor)

                        views.setTextViewText(R.id.widget_subtitle, subtitle)
                        views.setTextColor(R.id.widget_subtitle, textSecondaryColor)

                        views.setTextViewText(R.id.widget_refresh_btn, "⟳ Check All")
                        views.setTextColor(R.id.widget_refresh_btn, primaryColor)

                        views.setTextViewText(R.id.widget_footer_text, footerText)
                        views.setTextColor(R.id.widget_footer_text, primaryColor)

                        views.setInt(R.id.widget_divider_1, "setBackgroundColor", borderColor)
                        views.setInt(R.id.widget_divider_2, "setBackgroundColor", borderColor)
                    } catch (_: Exception) {}
                }

                // Bind RemoteViewsService adapter for the scrollable ListView
                val serviceIntent = Intent(context, AlarmerWidgetService::class.java).apply {
                    putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
                    data = Uri.parse(toUri(Intent.URI_INTENT_SCHEME))
                }
                views.setRemoteAdapter(R.id.widget_listview, serviceIntent)
                views.setEmptyView(R.id.widget_listview, R.id.widget_empty_text)

                // Item click template
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
