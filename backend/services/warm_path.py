"""Sprint 9: Discover warm connections at target companies via email history."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import WarmConnection


async def discover_warm_paths(
    db: AsyncSession,
    company_domain: str,
    gmail_service=None,
    user_id=None,
) -> list[dict]:
    """Scan Gmail for prior interactions with people at the given company domain.

    If gmail_service is None (test/no-gmail mode), returns existing stored connections.
    """
    # Check for already-discovered connections
    stmt = select(WarmConnection).where(WarmConnection.company_domain == company_domain)
    if user_id:
        stmt = stmt.where(WarmConnection.user_id == user_id)
    result = await db.execute(stmt)
    existing = result.scalars().all()
    if existing:
        return [_serialize(c) for c in existing]

    if not gmail_service:
        return []

    # Query Gmail for interactions with this domain
    try:
        query = f"from:*@{company_domain} OR to:*@{company_domain}"
        messages_response = gmail_service.users().messages().list(
            userId="me", q=query, maxResults=100
        ).execute()
        messages = messages_response.get("messages", [])
    except Exception:
        return []

    # Aggregate contacts from email headers
    contact_map: dict[str, dict] = {}
    for msg_meta in messages[:50]:  # cap at 50 to avoid rate limits
        try:
            msg = gmail_service.users().messages().get(
                userId="me", id=msg_meta["id"], format="metadata",
                metadataHeaders=["From", "To", "Date"],
            ).execute()
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

            from_header = headers.get("from", "")
            to_header = headers.get("to", "")
            date_str = headers.get("date", "")

            # Parse date
            from email.utils import parsedate_to_datetime
            try:
                msg_date = parsedate_to_datetime(date_str)
                if msg_date.tzinfo is None:
                    msg_date = msg_date.replace(tzinfo=timezone.utc)
            except Exception:
                msg_date = datetime.now(timezone.utc)

            # Extract email addresses containing the target domain
            import re
            all_addrs = re.findall(r'[\w.+-]+@[\w.-]+', f"{from_header} {to_header}")
            for addr in all_addrs:
                if company_domain in addr.lower():
                    addr_lower = addr.lower()
                    if addr_lower not in contact_map:
                        # Try to extract name from "Name <email>" format
                        name = None
                        name_match = re.search(r'"?([^"<]+)"?\s*<' + re.escape(addr), f"{from_header} {to_header}", re.IGNORECASE)
                        if name_match:
                            name = name_match.group(1).strip()

                        contact_map[addr_lower] = {
                            "email": addr_lower,
                            "name": name,
                            "count": 0,
                            "last_date": msg_date,
                        }
                    contact_map[addr_lower]["count"] += 1
                    if msg_date > contact_map[addr_lower]["last_date"]:
                        contact_map[addr_lower]["last_date"] = msg_date
        except Exception:
            continue

    # Store discovered connections
    connections = []
    for addr, info in contact_map.items():
        conn = WarmConnection(
            user_id=user_id,
            company_domain=company_domain,
            contact_email=info["email"],
            contact_name=info["name"],
            email_count=info["count"],
            last_interaction_at=info["last_date"],
        )
        db.add(conn)
        connections.append(conn)

    if connections:
        await db.commit()
        for c in connections:
            await db.refresh(c)

    return [_serialize(c) for c in connections]


def _serialize(conn: WarmConnection) -> dict:
    return {
        "id": str(conn.id),
        "company_domain": conn.company_domain,
        "contact_email": conn.contact_email,
        "contact_name": conn.contact_name,
        "email_count": conn.email_count,
        "last_interaction_at": conn.last_interaction_at.isoformat() if conn.last_interaction_at else None,
        "discovered_at": conn.discovered_at.isoformat() if conn.discovered_at else None,
    }
