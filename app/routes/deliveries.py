from fastapi import APIRouter, HTTPException

from app.security import API_DEP
from app.notifier import journal
from app.state import METRICS
from app.notifier import outbox
router = APIRouter()


@router.post("/api/deliveries/{delivery_id}/ack", dependencies=API_DEP)
async def ack_delivery(delivery_id: str):
    """Phase 2: the app confirms the banner was really shown.

    Always returns 200 so a repeated / stale ack is harmless.
    """
    clean_id = (delivery_id or "").strip()
    if not clean_id:
        raise HTTPException(status_code=400, detail="delivery_id is required.")

    # Capture the state BEFORE record_acked so a repeated ack is not counted twice.
    prev_state = journal.get_status(clean_id)
    acked = journal.record_acked(clean_id)
    if acked and prev_state != "acked":
        METRICS["fcm_acked"] = METRICS.get("fcm_acked", 0) + 1
    if acked:
        await outbox.on_delivery_acked(clean_id)
    return {"status": "acked" if acked else "unknown"}