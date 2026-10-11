import os
import time
import html
import asyncio
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
import firebase_admin

from app.config import APP_VERSION, SERVICE_ACCOUNT_FILE
from app.security import ADMIN_DEP, API_DEP, _validate_market_args
from app.state import METRICS, RECENT_DIAGNOSTICS, FAILED_SYMBOLS
from app.storage import ALERTS_DB
from app.markets.base import fetch_price_with_trace
from app.markets.limiter import get_all_providers_status
from app.engine.sync import get_last_sync_info
from app.markets.kill_switch import get_active_kill_switches, is_provider_killed, is_category_killed
from app.notifier import get_exchange_display_name, send_fcm_notification_async
from app.notifier.outbox import OUTBOX
import app.state as state
import app.storage as storage

router = APIRouter()

@router.get("/api/outbox", dependencies=ADMIN_DEP)
async def view_outbox():
    now = time.time()
    return {
        "pending": len(OUTBOX),
        "entries": [
            {
                "id": e["id"][:8],
                "alert_id": e.get("alert_id"),
                "attempts": e.get("attempts", 0),
                "last_error": e.get("last_error", ""),
                "age_seconds": int(now - e.get("created_at", now)),
                "next_attempt_in": max(0, int(e.get("next_attempt_at", now) - now)),
            }
            for e in OUTBOX.values()
        ],
    }

@router.get("/status", dependencies=ADMIN_DEP)
@router.get("/api/status", dependencies=ADMIN_DEP)
def get_status_dashboard(format: Optional[str] = None, accept: Optional[str] = Header(None)):
    """Live Dark-Themed Web Monitoring Dashboard & JSON Status API"""
    uptime_sec = int(time.time() - METRICS.get("start_time", time.time()))
    uptime_min = int(uptime_sec / 60)
    active_count = len([a for a in storage.ALERTS_DB if a.is_active])
    total_count = len(storage.ALERTS_DB)
    cache_hits = METRICS.get("cache_hits", 0)
    cache_misses = METRICS.get("cache_misses", 0)
    cache_total = cache_hits + cache_misses
    cache_ratio = round((cache_hits / max(1, cache_total)) * 100, 1)

    providers_status = get_all_providers_status()
    last_sync = get_last_sync_info()
    failing_list = list(FAILED_SYMBOLS.values())
    kill_switches = get_active_kill_switches()

    wants_json = (format == "json") or (isinstance(accept, str) and "application/json" in accept and format != "html")
    if wants_json:
        return JSONResponse({
            "status": "online",
            "uptime_seconds": uptime_sec,
            "engine": f"SignalAlert Enterprise Engine v{APP_VERSION}",
            "metrics": METRICS,
            "providers": providers_status,
            "last_catalog_sync": last_sync,
            "failing_symbols": {
                "count": len(failing_list),
                "items": failing_list
            },
            "kill_switches": kill_switches,
            "active_alerts_count": active_count,
            "total_alerts_count": total_count,
        })

    # Kill switch banner
    kill_banner = ""
    if kill_switches.get("any_active"):
        kp = ", ".join(kill_switches.get("providers_killed", [])) or "None"
        kc = ", ".join(kill_switches.get("categories_killed", [])) or "None"
        kill_banner = f"""
        <div style="background: #ef444422; border: 1px solid #ef444466; border-radius: 10px; padding: 12px 16px; margin-bottom: 20px; color: #fca5a5;">
            <strong>⚠️ [سوئیچ‌های قطع اضطراری فعال (Active Kill Switches)]:</strong><br>
            <span>📡 ارائه‌دهندگان مسدود: <code>{html.escape(kp)}</code> | 🏷️ دسته‌های مسدود: <code>{html.escape(kc)}</code></span>
        </div>
        """

    # Provider Rows HTML
    prov_rows = ""
    for p_id, p_info in providers_status.items():
        st = p_info["health"]
        if st == "HEALTHY":
            badge = '<span style="background:#10b98125;color:#10b981;padding:3px 8px;border-radius:6px;font-weight:bold;font-size:11px;">HEALTHY</span>'
        elif st == "DEGRADED":
            badge = '<span style="background:#f59e0b25;color:#f59e0b;padding:3px 8px;border-radius:6px;font-weight:bold;font-size:11px;">DEGRADED</span>'
        elif st == "KILLED":
            badge = '<span style="background:#8b5cf625;color:#c084fc;padding:3px 8px;border-radius:6px;font-weight:bold;font-size:11px;">KILLED (SWITCH)</span>'
        else:
            badge = '<span style="background:#ef444425;color:#ef4444;padding:3px 8px;border-radius:6px;font-weight:bold;font-size:11px;">OUTAGE</span>'

        pct = p_info.get("quota_percentage", 0.0)
        bar_color = "#ef4444" if pct >= 80 else ("#f59e0b" if pct >= 50 else "#10b981")
        warn_tag = ' <span style="color:#ef4444;font-weight:bold;">⚠️ &gt;80%</span>' if p_info.get("quota_warning") else ''

        prov_rows += f"""
        <tr>
            <td><b>{html.escape(p_info.get('name', p_id))}</b><br><small style="color:#64748b;">{html.escape(p_id)}</small></td>
            <td>{badge}</td>
            <td style="font-family:monospace;">{p_info.get('requests', 0):,}</td>
            <td><span style="color:#10b981;">{p_info.get('success', 0)}</span> / <span style="color:#ef4444;">{p_info.get('errors', 0)}</span></td>
            <td style="font-family:monospace;color:#f59e0b;">{p_info.get('rate_limits_429', 0)}</td>
            <td style="min-width:180px;">
                <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">
                    <span>{p_info.get('quota_used', 0):,} / {p_info.get('quota_limit', 0):,}{warn_tag}</span>
                    <span style="font-weight:bold;color:{bar_color};">{pct}%</span>
                </div>
                <div style="background:#1e293b;border-radius:4px;height:6px;overflow:hidden;">
                    <div style="background:{bar_color};width:{min(100.0, pct)}%;height:100%;"></div>
                </div>
            </td>
        </tr>
        """

    # Failing Symbols Rows HTML
    if failing_list:
        failing_rows = "".join(f"""
        <tr>
            <td style="font-weight:bold;font-family:monospace;color:#fca5a5;">{html.escape(str(f.get('symbol', '')))}</td>
            <td>{html.escape(str(f.get('exchange', '')))}</td>
            <td><span style="background:#334155;padding:2px 6px;border-radius:4px;font-size:11px;">{html.escape(str(f.get('category', 'crypto')))}</span></td>
            <td style="color:#ef4444;font-size:12px;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{html.escape(str(f.get('error', 'Unknown')))}</td>
            <td style="font-family:monospace;text-align:center;">{f.get('attempts', 1)}</td>
            <td style="font-size:11px;color:#94a3b8;">{int(time.time() - f.get('failed_at', time.time()))}s ago</td>
        </tr>
        """ for f in failing_list[:20])
    else:
        failing_rows = '<tr><td colspan="6" style="text-align:center;color:#10b981;padding:16px;">✅ تمامی نمادها بدون خطا دریافت شدند (No Failing Symbols)</td></tr>'

    sync_st_color = "#10b981" if last_sync.get("status") == "HEALTHY" else "#ef4444"
    sync_err_html = f'<div style="color:#ef4444;margin-top:6px;font-size:12px;">⚠️ آخرین خطا: <code>{html.escape(str(last_sync.get("last_error")))}</code></div>' if last_sync.get("last_error") else ''

    page = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SignalAlert Engine Monitor & Status</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b0f19; color: #e2e8f0; margin: 0; padding: 24px; }}
            .container {{ max-width: 1050px; margin: 0 auto; }}
            .header {{ display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 24px; }}
            .status-badge {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; padding: 6px 12px; border-radius: 9999px; font-weight: bold; font-size: 13px; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
            .card {{ background: #131b2e; border: 1px solid #1e293b; border-radius: 12px; padding: 16px; }}
            .card-title {{ font-size: 12px; color: #94a3b8; text-transform: uppercase; font-weight: bold; margin-bottom: 8px; }}
            .card-value {{ font-size: 24px; font-weight: 900; color: #f8fafc; font-family: monospace; }}
            .section-title {{ font-size: 16px; font-weight: bold; color: #f8fafc; margin: 24px 0 12px; display: flex; align-items: center; justify-content: space-between; }}
            .table-wrap {{ background: #131b2e; border: 1px solid #1e293b; border-radius: 12px; padding: 16px; overflow-x: auto; margin-bottom: 24px; }}
            table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }}
            th, td {{ padding: 10px 12px; border-bottom: 1px solid #1e293b; }}
            th {{ color: #94a3b8; font-weight: 600; font-size: 12px; }}
            .badge-active {{ color: #10b981; font-weight: bold; }}
            .badge-done {{ color: #f59e0b; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div>
                    <h2 style="margin:0; color:#38bdf8;">⚡ SignalAlert Enterprise Monitor & Observability</h2>
                    <p style="margin:4px 0 0; color:#64748b; font-size:13px;">High-Precision 24/7 Engine & Provider Health Center</p>
                </div>
                <div class="status-badge">● ONLINE ({uptime_min}m uptime)</div>
            </div>

            {kill_banner}

            <div class="grid">
                <div class="card">
                    <div class="card-title">Active Alerts</div>
                    <div class="card-value">{active_count} <span style="font-size:14px;color:#64748b;">/ {total_count}</span></div>
                </div>
                <div class="card">
                    <div class="card-title">Total Evaluated</div>
                    <div class="card-value">{METRICS.get("total_checks", 0):,}</div>
                </div>
                <div class="card">
                    <div class="card-title">Cache Hit Ratio</div>
                    <div class="card-value">{cache_ratio}%</div>
                </div>
                <div class="card">
                    <div class="card-title">FCM Push Sent</div>
                    <div class="card-value" style="color:#10b981;">{METRICS.get("fcm_success", 0)}</div>
                </div>
            </div>

            <!-- Provider Health & Quotas -->
            <div class="section-title">
                <span>📡 Provider Health & Quotas (سلامت و سهمیه سرویس‌دهنده‌ها)</span>
                <span style="font-size:12px;color:#64748b;">هشدار خودکار روی ۸۰٪ سهمیه</span>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Provider</th>
                            <th>Status</th>
                            <th>Requests</th>
                            <th>Success / Error</th>
                            <th>429 Rate Limits</th>
                            <th>Quota Usage & Limit</th>
                        </tr>
                    </thead>
                    <tbody>
                        {prov_rows}
                    </tbody>
                </table>
            </div>

            <!-- Last Catalog Sync Card -->
            <div class="section-title">
                <span>📦 Weekly Catalog Sync Status (آخرین وضعیت همگام‌سازی کاتالوگ)</span>
                <span style="font-size:12px;color:{sync_st_color};font-weight:bold;">● {last_sync.get("status")}</span>
            </div>
            <div class="card" style="margin-bottom:24px;">
                <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:16px;">
                    <div>
                        <div class="card-title">Catalog Version</div>
                        <div style="font-size:18px;font-weight:bold;color:#38bdf8;">Version {last_sync.get("version", 1)}</div>
                    </div>
                    <div>
                        <div class="card-title">Active Symbols</div>
                        <div style="font-size:18px;font-weight:bold;color:#10b981;">{last_sync.get("active_symbols", 0):,}</div>
                    </div>
                    <div>
                        <div class="card-title">Soft Delisted</div>
                        <div style="font-size:18px;font-weight:bold;color:#94a3b8;">{last_sync.get("delisted_symbols", 0):,}</div>
                    </div>
                    <div>
                        <div class="card-title">Total Sync Runs</div>
                        <div style="font-size:18px;font-weight:bold;color:#f8fafc;">{last_sync.get("total_syncs", 0)}</div>
                    </div>
                    <div>
                        <div class="card-title">Last Sync Timestamp</div>
                        <div style="font-size:13px;font-family:monospace;color:#94a3b8;margin-top:4px;">{last_sync.get("last_sync_at") or "Not run yet"}</div>
                    </div>
                </div>
                {sync_err_html}
            </div>

            <!-- Failing Symbols -->
            <div class="section-title">
                <span>⚠️ Failing Symbols (نمادهای خطادار اخیر)</span>
                <span style="font-size:12px;color:#fca5a5;">تعداد کل: {len(failing_list)}</span>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Exchange</th>
                            <th>Category</th>
                            <th>Error Details</th>
                            <th>Attempts</th>
                            <th>Failed At</th>
                        </tr>
                    </thead>
                    <tbody>
                        {failing_rows}
                    </tbody>
                </table>
            </div>

            <!-- Registered Alert Rules -->
            <div class="section-title">
                <span>🔔 Live Registered Alert Rules ({len(storage.ALERTS_DB)})</span>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Exchange</th>
                            <th>Target</th>
                            <th>Condition</th>
                            <th>Interval</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(f'''
                        <tr>
                            <td style="font-weight:bold; font-family:monospace;">{html.escape(a.symbol)}</td>
                            <td>{html.escape(get_exchange_display_name(a.exchange))}</td>
                            <td style="font-family:monospace; color:#38bdf8;">{a.target_price:,.2f}</td>
                            <td>{"🟢 Above" if a.condition.upper() == "ABOVE" else "🔴 Below"}</td>
                            <td>{a.check_interval_seconds}s</td>
                            <td class="{'badge-active' if a.is_active else 'badge-done'}">{'Active' if a.is_active else 'Triggered (Done)'}</td>
                        </tr>
                        ''' for a in storage.ALERTS_DB[:25]) if storage.ALERTS_DB else '<tr><td colspan="6" style="text-align:center;color:#64748b;padding:24px;">No alerts registered on server yet.</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=page)

@router.get("/api/debug/inspect/{exchange}/{symbol}", dependencies=ADMIN_DEP)
@router.get("/debug/inspect/{exchange}/{symbol}", dependencies=ADMIN_DEP)
async def inspect_market_source(exchange: str, symbol: str):
    """Deeply tests and traces every API endpoint without code duplication"""
    if state.http_client is None:
        raise HTTPException(status_code=503, detail="Server initializing...")

    _validate_market_args(exchange, symbol)
    start_time = time.time()
    final_price, traces = await fetch_price_with_trace(state.http_client, exchange, symbol, collect_all_traces=True)
    elapsed_total = round((time.time() - start_time) * 1000, 2)

    report = {
        'status': 'OK' if final_price is not None else 'FAILED',
        'exchange': exchange,
        'symbol': symbol,
        'resolved_price': final_price,
        'total_duration_ms': elapsed_total,
        'timestamp': datetime.utcnow().isoformat(),
        'traces': traces,
        'recommendation': 'Price resolved successfully.' if final_price else f'Unable to fetch {symbol} on {exchange}. Verify symbol code.'
    }

    RECENT_DIAGNOSTICS.insert(0, report)
    if len(RECENT_DIAGNOSTICS) > 50:
        RECENT_DIAGNOSTICS.pop()

    return report

@router.get("/api/debug/logs", dependencies=ADMIN_DEP)
@router.get("/debug/logs", dependencies=ADMIN_DEP)
def get_debug_logs():
    return {"count": len(RECENT_DIAGNOSTICS), "logs": RECENT_DIAGNOSTICS}

PROBE_TARGETS = [
    # Iran Markets
    {"id": "tsetmc_web", "name": "TSETMC Web (تارنمای قدیمی بورس)", "cat": "iran", "url": "http://old.tsetmc.com/tsev2/data/MarketWatchPlus.aspx", "extractor": lambda d: None},
    {"id": "tsetmc_main", "name": "TSETMC Main (درگاه اصلی بورس تهران)", "cat": "iran", "url": "https://tsetmc.com", "extractor": lambda d: None},
    {"id": "ice_cbi", "name": "ICE (مرکز مبادله ارز و طلای ایران)", "cat": "iran", "url": "https://ice.ir", "extractor": lambda d: None},
    {"id": "nobitex_stats", "name": "Nobitex Stats (آمار بازار نوبیتکس)", "cat": "iran", "url": "https://apiv2.nobitex.ir/market/stats", "extractor": lambda d: float(d.get('stats', {}).get('usdt-rls', {}).get('latest', 0)) / 10.0 if isinstance(d, dict) else None},
    {"id": "tabdeal_depth", "name": "Tabdeal Depth (دفتر سفارشات تبدیل)", "cat": "iran", "url": "https://api1.tabdeal.org/r/api/v1/depth?symbol=USDTIRT", "extractor": lambda d: float(d.get('bids', [[0]])[0][0]) if isinstance(d, dict) and d.get('bids') else None},
    {"id": "wallex_markets", "name": "Wallex Markets (مارکت والکس)", "cat": "iran", "url": "https://api.wallex.ir/v1/markets", "extractor": lambda d: float(d.get('result', {}).get('symbols', {}).get('USDTTMN', {}).get('stats', {}).get('lastPrice', 0)) if isinstance(d, dict) else None},
    {"id": "bitpin_markets", "name": "Bitpin Markets (مارکت بیت‌پین)", "cat": "iran", "url": "https://api.bitpin.org/v1/mkt/markets/", "extractor": lambda d: float(d.get('results', [{}])[0].get('price', 0)) if isinstance(d, dict) and d.get('results') else None},
    {"id": "tetherland", "name": "Tetherland (نرخ مستقیم تتر)", "cat": "iran", "url": "https://api.tetherland.com/currencies", "extractor": lambda d: float(d.get('data', {}).get('currencies', {}).get('USDT', {}).get('price', 0)) if isinstance(d, dict) else None},
    {"id": "bonbast", "name": "Bonbast (دلار آزاد و سکه)", "cat": "iran", "url": "https://bonbast.com", "extractor": lambda d: None},

    # DEX Providers
    {"id": "dexscreener_token", "name": "DexScreener Tokens (توکن On-Chain)", "cat": "dex", "url": "https://api.dexscreener.com/latest/dex/tokens/0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "extractor": lambda d: float(d.get('pairs', [{}])[0].get('priceUsd', 0)) if isinstance(d, dict) and d.get('pairs') else None},
    {"id": "dexscreener_search", "name": "DexScreener Search (جستجوی صرافی غیرمتمرکز)", "cat": "dex", "url": "https://api.dexscreener.com/latest/dex/search?q=WBNB", "extractor": lambda d: float(d.get('pairs', [{}])[0].get('priceUsd', 0)) if isinstance(d, dict) and d.get('pairs') else None},
    {"id": "geckoterminal_simple", "name": "GeckoTerminal Simple (قیمت WETH)", "cat": "dex", "url": "https://api.geckoterminal.com/api/v2/simple/networks/eth/token_price/0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", "extractor": lambda d: float(next(iter(d.get('data', {}).get('attributes', {}).get('token_prices', {}).values()), 0)) if isinstance(d, dict) else None},
    {"id": "geckoterminal_networks", "name": "GeckoTerminal Networks (شبکه‌های فعال)", "cat": "dex", "url": "https://api.geckoterminal.com/api/v2/networks", "extractor": lambda d: None},

    # Asian Indices & Global Macro
    {"id": "nikkei225", "name": "Nikkei 225 (^N225 - ژاپن)", "cat": "macro", "url": "https://query1.finance.yahoo.com/v8/finance/chart/%5EN225?interval=1m&range=1d", "extractor": lambda d: float(d.get('chart', {}).get('result', [{}])[0].get('meta', {}).get('regularMarketPrice', 0)) if isinstance(d, dict) else None},
    {"id": "nifty50", "name": "NIFTY 50 (^NSEI - هند)", "cat": "macro", "url": "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1m&range=1d", "extractor": lambda d: float(d.get('chart', {}).get('result', [{}])[0].get('meta', {}).get('regularMarketPrice', 0)) if isinstance(d, dict) else None},
    {"id": "kospi", "name": "KOSPI (^KS11 - کره جنوبی)", "cat": "macro", "url": "https://query1.finance.yahoo.com/v8/finance/chart/%5EKS11?interval=1m&range=1d", "extractor": lambda d: float(d.get('chart', {}).get('result', [{}])[0].get('meta', {}).get('regularMarketPrice', 0)) if isinstance(d, dict) else None},
    {"id": "sp500", "name": "S&P 500 (^GSPC - آمریکا)", "cat": "macro", "url": "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1m&range=1d", "extractor": lambda d: float(d.get('chart', {}).get('result', [{}])[0].get('meta', {}).get('regularMarketPrice', 0)) if isinstance(d, dict) else None},
    {"id": "gold_spot", "name": "Gold Spot (GC=F - طلا و انس)", "cat": "macro", "url": "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d", "extractor": lambda d: float(d.get('chart', {}).get('result', [{}])[0].get('meta', {}).get('regularMarketPrice', 0)) if isinstance(d, dict) else None},
    {"id": "tbill_13w", "name": "US 13-Week T-Bill (^IRX - اوراق خزانه‌داری)", "cat": "macro", "url": "https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX?interval=1m&range=1d", "extractor": lambda d: float(d.get('chart', {}).get('result', [{}])[0].get('meta', {}).get('regularMarketPrice', 0)) if isinstance(d, dict) else None},

    # Global Crypto Exchanges
    {"id": "binance", "name": "Binance Spot (BTC/USDT)", "cat": "crypto", "url": "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", "extractor": lambda d: float(d.get('price', 0)) if isinstance(d, dict) else None},
    {"id": "mexc", "name": "MEXC Spot (BTC/USDT)", "cat": "crypto", "url": "https://api.mexc.com/api/v3/ticker/price?symbol=BTCUSDT", "extractor": lambda d: float(d.get('price', 0)) if isinstance(d, dict) else None},
    {"id": "kucoin", "name": "KuCoin Spot (BTC/USDT)", "cat": "crypto", "url": "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=BTC-USDT", "extractor": lambda d: float(d.get('data', {}).get('price', 0)) if isinstance(d, dict) else None},
    {"id": "gateio", "name": "Gate.io Spot (BTC/USDT)", "cat": "crypto", "url": "https://api.gateio.ws/api/v4/spot/tickers?currency_pair=BTC_USDT", "extractor": lambda d: float(d[0].get('last', 0)) if isinstance(d, list) and d else None},
    {"id": "coinex", "name": "CoinEx Spot (BTC/USDT)", "cat": "crypto", "url": "https://api.coinex.com/v1/market/ticker?market=BTCUSDT", "extractor": lambda d: float(d.get('data', {}).get('ticker', {}).get('last', 0)) if isinstance(d, dict) else None},
    {"id": "bitstamp", "name": "Bitstamp Spot (BTC/USD)", "cat": "crypto", "url": "https://www.bitstamp.net/api/v2/ticker/btcusd/", "extractor": lambda d: float(d.get('last', 0)) if isinstance(d, dict) else None},
    {"id": "gemini", "name": "Gemini Spot (BTC/USD)", "cat": "crypto", "url": "https://api.gemini.com/v1/pubticker/btcusd", "extractor": lambda d: float(d.get('last', 0)) if isinstance(d, dict) else None},
    {"id": "htx", "name": "HTX / Huobi Spot (BTC/USDT)", "cat": "crypto", "url": "https://api.huobi.pro/market/detail/merged?symbol=btcusdt", "extractor": lambda d: float(d.get('tick', {}).get('close', 0)) if isinstance(d, dict) else None},
    {"id": "bitmex", "name": "BitMEX Instrument (XBTUSD)", "cat": "crypto", "url": "https://www.bitmex.com/api/v1/instrument?symbol=XBTUSD", "extractor": lambda d: float(d[0].get('lastPrice', 0)) if isinstance(d, list) and d else None},
]

@router.get("/api/admin/probe", dependencies=ADMIN_DEP)
@router.get("/admin/probe", dependencies=ADMIN_DEP)
async def admin_probe_market_sources(format: Optional[str] = None, accept: Optional[str] = Header(None)):
    """
    Comprehensive Admin Probe Endpoint (Phase 6):
    Probes all market data sources (Iran Markets, DEX, Asian Indices, Crypto)
    and returns a status matrix: HEALTHY, SLOW, BLOCKED_OR_ERROR, SUSPICIOUS_PRICE
    """
    if state.http_client is None:
        raise HTTPException(status_code=503, detail="Server initializing...")

    req_headers = {'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) SignalAlertProbe/{APP_VERSION}'}

    async def _probe_single(target):
        # Check kill switch before making network request
        if is_provider_killed(target['id']) or is_category_killed(target['cat']):
            return {
                'id': target['id'],
                'name': target['name'],
                'category': target['cat'],
                'url': target['url'],
                'status': 'KILLED',
                'status_fa': 'غیرفعال (Kill Switch)',
                'http_code': 503,
                'latency_ms': 0.0,
                'sample_price': None,
                'error': 'Disabled by Kill Switch'
            }

        t0 = time.time()
        url = target['url']
        try:
            res = await state.http_client.get(url, headers=req_headers, timeout=3.5)
            latency = round((time.time() - t0) * 1000, 1)
            code = res.status_code

            if code == 200:
                sample_p = None
                try:
                    data = res.json()
                    sample_p = target['extractor'](data)
                except Exception:
                    pass

                status = 'HEALTHY'
                status_fa = 'سالم'

                if sample_p is not None and sample_p <= 0:
                    status = 'SUSPICIOUS_PRICE'
                    status_fa = 'قیمت مشکوک'
                elif latency > 1200:
                    status = 'SLOW'
                    status_fa = 'کند'

                return {
                    'id': target['id'],
                    'name': target['name'],
                    'category': target['cat'],
                    'url': url,
                    'status': status,
                    'status_fa': status_fa,
                    'http_code': code,
                    'latency_ms': latency,
                    'sample_price': sample_p,
                    'error': None
                }
            elif code in [403, 429]:
                return {
                    'id': target['id'],
                    'name': target['name'],
                    'category': target['cat'],
                    'url': url,
                    'status': 'BLOCKED_OR_ERROR',
                    'status_fa': 'بلاک / محدود',
                    'http_code': code,
                    'latency_ms': round((time.time() - t0) * 1000, 1),
                    'sample_price': None,
                    'error': f'HTTP {code} Geo-blocked/Rate-limited'
                }
            else:
                return {
                    'id': target['id'],
                    'name': target['name'],
                    'category': target['cat'],
                    'url': url,
                    'status': 'BLOCKED_OR_ERROR',
                    'status_fa': 'خطا',
                    'http_code': code,
                    'latency_ms': round((time.time() - t0) * 1000, 1),
                    'sample_price': None,
                    'error': f'HTTP {code}'
                }
        except Exception as e:
            return {
                'id': target['id'],
                'name': target['name'],
                'category': target['cat'],
                'url': url,
                'status': 'BLOCKED_OR_ERROR',
                'status_fa': 'بلاک / تایم‌اوت',
                'http_code': 0,
                'latency_ms': round((time.time() - t0) * 1000, 1),
                'sample_price': None,
                'error': f'{type(e).__name__}: {str(e)[:60]}'
            }

    results = await asyncio.gather(*[_probe_single(t) for t in PROBE_TARGETS])

    healthy_c = sum(1 for r in results if r['status'] == 'HEALTHY')
    slow_c = sum(1 for r in results if r['status'] == 'SLOW')
    blocked_c = sum(1 for r in results if r['status'] == 'BLOCKED_OR_ERROR')
    suspicious_c = sum(1 for r in results if r['status'] == 'SUSPICIOUS_PRICE')
    killed_c = sum(1 for r in results if r['status'] == 'KILLED')

    providers_status = get_all_providers_status()
    last_sync = get_last_sync_info()
    failing_list = list(FAILED_SYMBOLS.values())
    kill_switches = get_active_kill_switches()

    probe_report = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'server_location': 'Belgium (europe-west1 / Google Cloud)',
        'summary': {
            'total_sources': len(results),
            'healthy': healthy_c,
            'slow': slow_c,
            'blocked_or_error': blocked_c,
            'suspicious_price': suspicious_c,
            'killed': killed_c
        },
        'results': results,
        'providers': providers_status,
        'last_catalog_sync': last_sync,
        'failing_symbols': {
            'count': len(failing_list),
            'items': failing_list
        },
        'kill_switches': kill_switches
    }

    wants_html = (format == 'html') or (isinstance(accept, str) and 'text/html' in accept)
    if wants_html:
        rows_html = ""
        for r in results:
            st = r['status']
            if st == 'HEALTHY':
                badge = '<span style="background:#d1fae5;color:#065f46;padding:4px 8px;border-radius:6px;font-weight:bold;">✅ سالم (HEALTHY)</span>'
            elif st == 'SLOW':
                badge = '<span style="background:#fef3c7;color:#92400e;padding:4px 8px;border-radius:6px;font-weight:bold;">⏱ کند (SLOW)</span>'
            elif st == 'SUSPICIOUS_PRICE':
                badge = '<span style="background:#fee2e2;color:#991b1b;padding:4px 8px;border-radius:6px;font-weight:bold;">⚠️ قیمت مشکوک</span>'
            elif st == 'KILLED':
                badge = '<span style="background:#ede9fe;color:#6d28d9;padding:4px 8px;border-radius:6px;font-weight:bold;">🛑 غیرفعال (Kill Switch)</span>'
            else:
                badge = '<span style="background:#f3f4f6;color:#1f2937;padding:4px 8px;border-radius:6px;font-weight:bold;">🚫 بلاک / خطا</span>'

            price_str = f"{r['sample_price']:,.2f}" if r['sample_price'] else "—"
            err_str = f"<small style='color:#ef4444;'>{html.escape(r['error'])}</small>" if r['error'] else "—"

            rows_html += f"""
            <tr>
                <td><b>{html.escape(r['name'])}</b><br><small style="color:#6b7280;">{html.escape(r['category'].upper())}</small></td>
                <td>{badge}</td>
                <td>{r['latency_ms']} ms</td>
                <td><b>{price_str}</b></td>
                <td><small style="color:#4b5563;">{r['http_code']}</small></td>
                <td>{err_str}</td>
            </tr>
            """

        # Provider quota rows for probe
        prov_probe_rows = ""
        for p_id, p_info in providers_status.items():
            st_color = "#10b981" if p_info['health'] == 'HEALTHY' else ("#ef4444" if p_info['health'] in ('OUTAGE_OR_BLOCKED', 'OUTAGE') else "#f59e0b")
            warn_badge = ' <span style="color:#ef4444;font-weight:bold;">⚠️ سهمیه بالای ۸۰٪</span>' if p_info.get('quota_warning') else ''
            prov_probe_rows += f"""
            <tr>
                <td><b>{html.escape(p_info.get('name', p_id))}</b></td>
                <td><span style="color:{st_color};font-weight:bold;">{p_info['health']}</span></td>
                <td>{p_info.get('requests', 0):,}</td>
                <td>{p_info.get('quota_used', 0):,} / {p_info.get('quota_limit', 0):,} ({p_info.get('quota_percentage', 0.0)}%){warn_badge}</td>
            </tr>
            """

        # Kill Switch Banner HTML
        kill_probe_banner = ""
        if kill_switches.get("any_active"):
            kp = ", ".join(kill_switches.get("providers_killed", [])) or "None"
            kc = ", ".join(kill_switches.get("categories_killed", [])) or "None"
            kill_probe_banner = f"""
            <div style="background: #fef2f2; border: 1px solid #f87171; border-radius: 8px; padding: 12px 16px; margin-bottom: 20px; color: #991b1b;">
                <strong>⚠️ سوئیچ‌های قطع اضطراری فعال (Active Kill Switches):</strong><br>
                <span>سرویس‌دهنده‌ها: <code>{html.escape(kp)}</code> | دسته‌ها: <code>{html.escape(kc)}</code></span>
            </div>
            """

        # Failing symbols rows for probe
        if failing_list:
            failing_probe_rows = "".join(f"""
            <tr>
                <td><b>{html.escape(str(f.get('symbol', '')))}</b> ({html.escape(str(f.get('exchange', '')))})</td>
                <td>{html.escape(str(f.get('category', '')))}</td>
                <td style="color:#dc2626;">{html.escape(str(f.get('error', '')))}</td>
                <td>{f.get('attempts', 1)} بار</td>
            </tr>
            """ for f in failing_list[:15])
        else:
            failing_probe_rows = '<tr><td colspan="4" style="text-align:center;color:#166534;padding:12px;">✅ تمامی نمادها بدون خطا فعال هستند</td></tr>'

        html_content = f"""
        <!DOCTYPE html>
        <html dir="rtl" lang="fa">
        <head>
            <meta charset="utf-8">
            <title>ارزیابی پایش و مشاهده‌پذیری منابع بازار - SignalAlert Probe</title>
            <style>
                body {{ font-family: system-ui, -apple-system, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 24px; }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 12px; padding: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
                h1 {{ margin-top: 0; font-size: 24px; color: #1e293b; }}
                h2 {{ font-size: 18px; color: #334155; margin: 24px 0 12px; }}
                .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }}
                .card {{ padding: 16px; border-radius: 8px; text-align: center; }}
                .card-total {{ background: #eff6ff; color: #1e40af; }}
                .card-healthy {{ background: #f0fdf4; color: #166534; }}
                .card-slow {{ background: #fffbeb; color: #854d0e; }}
                .card-blocked {{ background: #fef2f2; color: #991b1b; }}
                .card-killed {{ background: #f5f3ff; color: #6b21a8; }}
                .card-num {{ font-size: 26px; font-weight: bold; margin-top: 4px; }}
                table {{ width: 100%; border-collapse: collapse; text-align: right; margin-bottom: 24px; }}
                th, td {{ padding: 10px 14px; border-bottom: 1px solid #e2e8f0; font-size: 13px; }}
                th {{ background: #f1f5f9; color: #475569; font-weight: 600; }}
                tr:hover {{ background: #f8fafc; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📊 مانیتورینگ مشاهده‌پذیری منابع بازار (SignalAlert Admin Probe)</h1>
                <p style="color:#64748b; margin-bottom: 20px;">
                    سرور اصلی: <b>Belgium (europe-west1 / Google Cloud)</b> | زمان ثبت: <b>{probe_report['timestamp']}</b>
                </p>

                {kill_probe_banner}

                <div class="summary">
                    <div class="card card-total">کل منابع<div class="card-num">{len(results)}</div></div>
                    <div class="card card-healthy">سالم (HEALTHY)<div class="card-num">{healthy_c}</div></div>
                    <div class="card card-slow">کند (SLOW)<div class="card-num">{slow_c}</div></div>
                    <div class="card card-blocked">بلاک / خطا<div class="card-num">{blocked_c}</div></div>
                    <div class="card card-blocked" style="background:#fee2e2; color:#991b1b;">قیمت مشکوک<div class="card-num">{suspicious_c}</div></div>
                    <div class="card card-killed">غیرفعال (Kill)<div class="card-num">{killed_c}</div></div>
                </div>

                <h2>📡 سلامت و سهمیه سرویس‌دهنده‌ها (Providers Health & Quotas)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>سرویس‌دهنده</th>
                            <th>وضعیت سلامت</th>
                            <th>درخواست‌ها</th>
                            <th>مصرف سهمیه مجاز</th>
                        </tr>
                    </thead>
                    <tbody>
                        {prov_probe_rows}
                    </tbody>
                </table>

                <h2>📦 آخرین همگام‌سازی کاتالوگ (Last Catalog Sync)</h2>
                <div style="background:#f1f5f9;border-radius:8px;padding:14px;margin-bottom:24px;display:flex;justify-content:space-around;font-size:13px;">
                    <div>نسخه کاتالوگ: <b>نسخه {last_sync.get('version', 1)}</b></div>
                    <div>نمادهای فعال: <b style="color:#166534;">{last_sync.get('active_symbols', 0):,}</b></div>
                    <div>حذف‌شده (Soft Delisted): <b>{last_sync.get('delisted_symbols', 0):,}</b></div>
                    <div>وضعیت: <b style="color:{'#166534' if last_sync.get('status') == 'HEALTHY' else '#dc2626'};">{last_sync.get('status')}</b></div>
                    <div>زمان آخرین سنک: <b>{last_sync.get('last_sync_at') or 'اجرا نشده'}</b></div>
                </div>

                <h2>⚠️ نمادهای خطادار (Failing Symbols)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>نماد و صرافی</th>
                            <th>دسته</th>
                            <th>علت خطا</th>
                            <th>تعداد تلاش</th>
                        </tr>
                    </thead>
                    <tbody>
                        {failing_probe_rows}
                    </tbody>
                </table>

                <h2>🔍 وضعیت لحظه‌ای پایگاه‌های قیمت (Market Probe Targets)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>منبع داده</th>
                            <th>وضعیت</th>
                            <th>زمان پاسخ (Latency)</th>
                            <th>نمونه قیمت استخراجی</th>
                            <th>کد HTTP</th>
                            <th>جزئیات خطا / علت</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)

    return probe_report

@router.get("/api/test/push", dependencies=API_DEP)
@router.post("/api/test/push", dependencies=API_DEP)
async def test_push_notification(fcm_token: Optional[str] = None, title: Optional[str] = None, body: Optional[str] = None):
    token_to_use = fcm_token
    if not token_to_use:
        for a in storage.ALERTS_DB:
            if a.fcm_token and not any(k in a.fcm_token.lower() for k in ['sample', 'pending', 'device_token_']):
                token_to_use = a.fcm_token
                break

    test_title = title or "🔔 [SignalAlert Live Connection]"
    test_body = body or "✅ App is successfully connected to the server! Live push notification channel is online."

    if not token_to_use:
        return {
            "success": False,
            "error": "No real FCM device token found. Please open mobile app or pass ?fcm_token=YOUR_TOKEN",
            "firebase_initialized": bool(firebase_admin._apps),
            "service_account_key_found": os.path.exists(SERVICE_ACCOUNT_FILE),
            "active_alerts_count": len(storage.ALERTS_DB),
            "timestamp": datetime.utcnow().isoformat()
        }

    sent_ok, sent_msg = await send_fcm_notification_async(
        fcm_token=token_to_use,
        title=test_title,
        body=test_body,
        data_payload={
            "alert_id": f"test_ping_{int(time.time())}",
            "symbol": "BTC/USDT",
            "price": "68500",
            "note": "تست اتصال زنده سرور",
            "sound_enabled": "true",
            "vibration_enabled": "true",
            "tts_enabled": "true",
            "sound": "alarm_siren",
            "type": "test_ping",
            "timestamp": str(time.time()),
            "source": "api_test_endpoint"
        }
    )

    return {
        "success": sent_ok,
        "details": sent_msg,
        "fcm_token_used": "..." + token_to_use[-6:],
        "firebase_initialized": bool(firebase_admin._apps),
        "service_account_key_found": os.path.exists(SERVICE_ACCOUNT_FILE),
        "title_sent": test_title,
        "body_sent": test_body,
        "timestamp": datetime.utcnow().isoformat()
    }


# -------------------------------------------------------------------------
# Catalog Sync, Rollback & Snapshot Management (Phase 7 - v2.10.0)
# -------------------------------------------------------------------------
@router.get("/api/admin/catalog/status", dependencies=ADMIN_DEP)
@router.get("/admin/catalog/status", dependencies=ADMIN_DEP)
def get_admin_catalog_status():
    from app.engine.sync import load_catalog, list_catalog_snapshots
    cat = load_catalog()
    active_symbols = [s for s in cat.get("symbols", []) if s.get("is_active", 1)]
    soft_deleted = [s for s in cat.get("symbols", []) if not s.get("is_active", 1)]
    return {
        "status": "success",
        "catalog_version": cat.get("catalog_version", 1),
        "last_sync_at": cat.get("last_sync_at"),
        "total_symbols": len(cat.get("symbols", [])),
        "total_active": len(active_symbols),
        "total_soft_deleted": len(soft_deleted),
        "available_snapshots": len(list_catalog_snapshots()),
        "admin_alerts_count": METRICS.get("catalog_sync_admin_alerts", 0),
        "last_error": METRICS.get("last_catalog_sync_error", None)
    }


@router.get("/api/admin/catalog/snapshots", dependencies=ADMIN_DEP)
@router.get("/admin/catalog/snapshots", dependencies=ADMIN_DEP)
def get_admin_catalog_snapshots():
    from app.engine.sync import list_catalog_snapshots
    return {
        "status": "success",
        "snapshots": list_catalog_snapshots()
    }


@router.post("/api/admin/catalog/sync", dependencies=ADMIN_DEP)
@router.post("/admin/catalog/sync", dependencies=ADMIN_DEP)
async def trigger_admin_catalog_sync(dry_run: bool = False, ignore_safety: bool = False):
    from app.engine.sync import run_weekly_catalog_sync, CatalogSafetyCeilingExceededError
    try:
        report = await run_weekly_catalog_sync(dry_run=dry_run, ignore_safety=ignore_safety)
        return {
            "success": True,
            "report": report
        }
    except CatalogSafetyCeilingExceededError as ce:
        raise HTTPException(status_code=400, detail=str(ce))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Catalog sync failed: {str(e)}")


@router.post("/api/admin/catalog/rollback", dependencies=ADMIN_DEP)
@router.post("/admin/catalog/rollback", dependencies=ADMIN_DEP)
def trigger_admin_catalog_rollback(version: Optional[int] = None):
    from app.engine.sync import rollback_catalog
    try:
        restored = rollback_catalog(target_version=version)
        return {
            "success": True,
            "restored_version": restored.get("catalog_version"),
            "total_active": restored.get("total_active"),
            "last_sync_at": restored.get("last_sync_at")
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/admin/features", dependencies=ADMIN_DEP)
@router.get("/admin/features", dependencies=ADMIN_DEP)
def get_features_status(user_id: Optional[str] = None):
    """Inspects active feature flags and beta user group status."""
    from app.engine.features import get_all_feature_flags
    return get_all_feature_flags(user_id=user_id)


@router.post("/api/admin/features", dependencies=ADMIN_DEP)
@router.post("/admin/features", dependencies=ADMIN_DEP)
def toggle_feature_flag(flag: str, enabled: Optional[bool] = None):
    """Sets or clears a dynamic runtime override for a feature flag."""
    from app.engine.features import set_feature_override, get_all_feature_flags
    set_feature_override(flag, enabled)
    return {
        "success": True,
        "message": f"Feature flag '{flag}' set to {enabled}",
        "status": get_all_feature_flags()
    }


