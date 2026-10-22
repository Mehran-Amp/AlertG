from fastapi import APIRouter, HTTPException

from app.security import API_DEP
from app.notifier import journal
from app.state import METRICS
from app.notifier import outbox
router = APIRouter()


@router.post("/api/deliveries/{delivery_id}/ack", dependencies=API_DEP)
@router.post("/deliveries/{delivery_id}/ack", dependencies=API_DEP)
async def ack_delivery(delivery_id: str):
    """Phase 2: the app confirms the banner was really shown.

    Always returns 200 so a repeated / stale ack is harmless.
    """
    clean_id = (delivery_id or "").strip()
    if not clean_id:
        raise HTTPException(status_code=400, detail="delivery_id is required.")

    known = clean_id in journal.JOURNAL
    acked = journal.record_acked(clean_id)
    if acked:
        await outbox.on_delivery_acked(clean_id)
    if acked and known and journal.get_status(clean_id) == "acked":
        # Only count the first ack for this delivery.
        METRICS["fcm_acked"] = METRICS.get("fcm_acked", 0) + 1
    return {"status": "acked" if acked else "unknown"}