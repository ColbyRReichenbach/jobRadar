"""Sprint 19: Twilio SMS sender for urgent alerts."""

import os
import logging

from backend.utils.retry import with_retry

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")

# Alert types that trigger SMS
URGENT_ALERT_TYPES = {"offer", "interview_request", "interview_reminder"}


async def send_sms(to_phone: str, message: str) -> dict:
    """Send an SMS via Twilio REST API."""
    import httpx

    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER]):
        logger.warning("Twilio credentials not configured, skipping SMS")
        return {"status": "skipped", "reason": "twilio_not_configured"}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"

    async def _send():
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                data={
                    "To": to_phone,
                    "From": TWILIO_FROM_NUMBER,
                    "Body": message,
                },
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            )
            resp.raise_for_status()
            return resp.json()

    try:
        result = await with_retry(_send)
        logger.info(f"SMS sent to {to_phone}: SID={result.get('sid')}")
        return {"status": "sent", "sid": result.get("sid")}
    except Exception as e:
        logger.error(f"Failed to send SMS to {to_phone}: {e}")
        return {"status": "failed", "error": str(e)}


def format_alert_sms(alert_type: str, title: str, body: str | None = None) -> str:
    """Format an alert into a short SMS message."""
    prefix = {
        "offer": "OFFER",
        "interview_request": "INTERVIEW",
        "interview_reminder": "REMINDER",
    }.get(alert_type, "ALERT")

    msg = f"[AppTrail {prefix}] {title}"
    if body:
        # Truncate to fit SMS limit
        remaining = 160 - len(msg) - 3  # " - " separator
        if remaining > 20:
            msg += f" - {body[:remaining]}"
    return msg[:160]


async def maybe_send_sms_for_alert(
    db, alert_type: str, title: str, body: str | None = None, user_id=None
) -> dict | None:
    """Check user preferences and send SMS if alert is urgent and SMS is enabled."""
    if alert_type not in URGENT_ALERT_TYPES:
        return None

    from sqlalchemy import select
    from backend.models import NotificationPreference

    # Find user's notification preferences
    stmt = select(NotificationPreference)
    if user_id:
        stmt = stmt.where(NotificationPreference.user_id == user_id)

    result = await db.execute(stmt)
    prefs = result.scalars().all()

    sent = []
    for pref in prefs:
        if pref.sms_enabled and pref.sms_phone:
            message = format_alert_sms(alert_type, title, body)
            result = await send_sms(pref.sms_phone, message)
            sent.append(result)

    return sent if sent else None
