import httpx
from app.notifier.safety import is_safe_webhook_url_async
from app.state import METRICS

async def send_webhook_alert(client: httpx.AsyncClient, webhook_url: str, payload: dict):
    if not webhook_url:
        return
    if not await is_safe_webhook_url_async(webhook_url):
        print("⚠️ [Webhook Blocked] Unsafe or unresolvable webhook URL.")
        return
    try:
        await client.post(webhook_url, json=payload, timeout=4.0, follow_redirects=False)
        METRICS["webhook_sent"] += 1
    except Exception as e:
        print(f"⚠️ [Webhook Dispatch Error] {e}")
