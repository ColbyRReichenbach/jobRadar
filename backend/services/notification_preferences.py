from __future__ import annotations

from typing import Any

from backend.models import NotificationPreference


DEFAULT_NOTIFICATION_PREFERENCES: dict[str, Any] = {
    "sms_enabled": False,
    "sms_phone": None,
    "weekly_digest_enabled": False,
    "browser_notifications_enabled": False,
    "inbox_updates_enabled": True,
    "conversations_enabled": True,
    "network_enabled": True,
    "interviews_enabled": True,
    "followups_enabled": True,
    "listings_enabled": True,
    "quiet_hours_enabled": False,
    "quiet_hours_start": None,
    "quiet_hours_end": None,
}


ALERT_TYPE_TO_PREFERENCE: dict[str, str] = {
    "conversation_message": "conversations_enabled",
    "network_contact": "network_enabled",
    "interview_request": "interviews_enabled",
    "offer": "inbox_updates_enabled",
    "rejection": "inbox_updates_enabled",
    "action_item": "inbox_updates_enabled",
    "job_update": "inbox_updates_enabled",
    "email_update": "inbox_updates_enabled",
    "follow_up": "followups_enabled",
    "dead_listing": "listings_enabled",
    "weekly_digest": "weekly_digest_enabled",
}


def serialize_notification_preferences(pref: NotificationPreference | None) -> dict[str, Any]:
    payload = dict(DEFAULT_NOTIFICATION_PREFERENCES)
    if pref is None:
        return payload

    payload.update(
        {
            "id": str(pref.id),
            "sms_enabled": pref.sms_enabled,
            "sms_phone": pref.sms_phone,
            "weekly_digest_enabled": pref.weekly_digest_enabled,
            "browser_notifications_enabled": pref.browser_notifications_enabled,
            "inbox_updates_enabled": pref.inbox_updates_enabled,
            "conversations_enabled": pref.conversations_enabled,
            "network_enabled": pref.network_enabled,
            "interviews_enabled": pref.interviews_enabled,
            "followups_enabled": pref.followups_enabled,
            "listings_enabled": pref.listings_enabled,
            "quiet_hours_enabled": pref.quiet_hours_enabled,
            "quiet_hours_start": pref.quiet_hours_start,
            "quiet_hours_end": pref.quiet_hours_end,
            "created_at": pref.created_at.isoformat() if pref.created_at else None,
            "updated_at": pref.updated_at.isoformat() if pref.updated_at else None,
        }
    )
    return payload


def is_alert_enabled(pref: NotificationPreference | None, alert_type: str) -> bool:
    if pref is None:
        return True
    preference_field = ALERT_TYPE_TO_PREFERENCE.get(alert_type)
    if not preference_field:
        return True
    return bool(getattr(pref, preference_field, True))
