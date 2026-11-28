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
            val subtitle = item.optString("subtitle", "")
            val price = item.optString("price", "—")
            val badge = item.optString("badge", "—")
            val isDone = item.optBoolean("isDone", false)
            val isNearTarget = item.optBoolean("isNearTarget", false)
            val isPositive = item.optBoolean("isPositive", true)
            val proximity = item.optInt("proximity", if (isDone) 100 else 35).coerceIn(4, 100)

            // Fixed Obsidian Dark Luxury Card Background
            val rowRes = if (isDone) R.drawable.widget_row_bg_done else R.drawable.widget_row_bg_dark
            rowView.setInt(R.id.item_root, "setBackgroundResource", rowRes)

            // Left Vertical Accent Bar
            val accentRes = when {
                isDone || isNearTarget -> R.drawable.widget_accent_gold
                isPositive -> R.drawable.widget_accent_green
                else -> R.drawable.widget_accent_red
            }
            rowView.setInt(R.id.item_accent_bar, "setBackgroundResource", accentRes)

            // Line 1: Symbol & Live Price
            rowView.setTextViewText(R.id.item_symbol, symbol)
            rowView.setTextColor(
                R.id.item_symbol,
                if (isDone) 0xFFFBBF24.toInt() else 0xFFF8FAFC.toInt()
            )

            rowView.setTextViewText(R.id.item_price, price)
            rowView.setTextColor(R.id.item_price, 0xFFF8FAFC.toInt())

            // Line 2: Exchange + Target Subtitle & Status Badge
            rowView.setTextViewText(R.id.item_subtitle, if (subtitle.isNotEmpty()) subtitle else "Active Alert")
            rowView.setTextColor(R.id.item_subtitle, 0xFF94A3B8.toInt())

            rowView.setTextViewText(R.id.item_badge, badge)

            when {
                isDone || isNearTarget -> {
                    rowView.setInt(R.id.item_badge, "setBackgroundResource", R.drawable.badge_done_dark)
                    rowView.setTextColor(R.id.item_badge, 0xFFFBBF24.toInt())
                }
                isPositive -> {
                    rowView.setInt(R.id.item_badge, "setBackgroundResource", R.drawable.badge_green_dark)
                    rowView.setTextColor(R.id.item_badge, 0xFF10B981.toInt())
                }
                else -> {
                    rowView.setInt(R.id.item_badge, "setBackgroundResource", R.drawable.badge_red_dark)
                    rowView.setTextColor(R.id.item_badge, 0xFFF43F5E.toInt())
                }
            }

            // Target Proximity Micro-Bar
            rowView.setProgressBar(R.id.item_proximity_bar, 100, proximity, false)

            // Fill-in Intent so clicking on any card row launches the app
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
