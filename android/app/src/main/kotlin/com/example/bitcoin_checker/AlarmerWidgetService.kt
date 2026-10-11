package com.example.bitcoin_checker

import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import android.widget.RemoteViewsService
import org.json.JSONArray
import org.json.JSONObject

class AlarmerWidgetService : RemoteViewsService() {
    override fun onGetViewFactory(intent: Intent): RemoteViewsFactory {
        return AlarmerListRemoteViewsFactory(this.applicationContext, intent)
    }
}

class AlarmerListRemoteViewsFactory(
    private val context: Context,
    private val intent: Intent
) : RemoteViewsService.RemoteViewsFactory {

    private var items: JSONArray = JSONArray()
    private var isDark: Boolean = true
    private var textPrimaryColor: Int = 0xFFF9FAFB.toInt()
    private var priceColor: Int = 0xFFF59E0B.toInt()

    override fun onCreate() {
        loadData()
    }

    override fun onDataSetChanged() {
        loadData()
    }

    private fun loadData() {
        try {
            val prefs = context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
            val jsonStr = prefs.getString("flutter.widget_alerts_json", null)
            if (jsonStr != null && jsonStr.isNotEmpty()) {
                val root = JSONObject(jsonStr)
                items = root.optJSONArray("items") ?: JSONArray()
                val themeObj = root.optJSONObject("theme")
                isDark = themeObj?.optInt("isDark", 1) == 1
                textPrimaryColor = themeObj?.optLong("textPrimary", if (isDark) 0xFFF9FAFB else 0xFF111827)?.toInt()
                    ?: if (isDark) 0xFFF9FAFB.toInt() else 0xFF111827.toInt()
                priceColor = themeObj?.optLong("price", if (isDark) 0xFFF59E0B else 0xFFD97706)?.toInt()
                    ?: if (isDark) 0xFFF59E0B.toInt() else 0xFFD97706.toInt()
            } else {
                items = JSONArray()
            }
        } catch (_: Exception) {
            items = JSONArray()
        }
    }

    override fun onDestroy() {}

    override fun getCount(): Int = items.length()

    override fun getViewAt(position: Int): RemoteViews {
        val rowView = RemoteViews(context.packageName, R.layout.alarmer_widget_row_item)
        if (position < 0 || position >= items.length()) {
            return rowView
        }

        try {
            val item = items.getJSONObject(position)
            val symbol = item.optString("symbol", "—")
            val price = item.optString("price", "—")
            val badge = item.optString("badge", "—")
            val isDone = item.optBoolean("isDone", false)
            val isPositive = item.optBoolean("isPositive", true)

            val rowRes = if (isDark) R.drawable.widget_row_bg_dark else R.drawable.widget_row_bg_light
            rowView.setInt(R.id.item_root, "setBackgroundResource", rowRes)

            rowView.setTextViewText(R.id.item_symbol, symbol)
            rowView.setTextColor(R.id.item_symbol, textPrimaryColor)

            rowView.setTextViewText(R.id.item_price, price)
            rowView.setTextColor(R.id.item_price, priceColor)

            rowView.setTextViewText(R.id.item_badge, badge)

            if (isDone) {
                rowView.setInt(R.id.item_badge, "setBackgroundResource", if (isDark) R.drawable.badge_done_dark else R.drawable.badge_done_light)
                rowView.setTextColor(R.id.item_badge, if (isDark) 0xFFE3B341.toInt() else 0xFFD97706.toInt())
            } else if (isPositive) {
                rowView.setInt(R.id.item_badge, "setBackgroundResource", if (isDark) R.drawable.badge_green_dark else R.drawable.badge_green_light)
                rowView.setTextColor(R.id.item_badge, if (isDark) 0xFF3FB950.toInt() else 0xFF16A34A.toInt())
            } else {
                rowView.setInt(R.id.item_badge, "setBackgroundResource", if (isDark) R.drawable.badge_red_dark else R.drawable.badge_red_light)
                rowView.setTextColor(R.id.item_badge, if (isDark) 0xFFF85149.toInt() else 0xFFDC2626.toInt())
            }

            // Fill-in Intent so clicking on any row launches the app
            val fillInIntent = Intent().apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            }
            rowView.setOnClickFillInIntent(R.id.item_root, fillInIntent)
        } catch (_: Exception) {}

        return rowView
    }

    override fun getLoadingView(): RemoteViews? = null
    override fun getViewTypeCount(): Int = 1
    override fun getItemId(position: Int): Long = position.toLong()
    override fun hasStableIds(): Boolean = true
}
