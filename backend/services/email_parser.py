"""Gmail email body parser — handles multipart MIME, HTML stripping, and signature removal.

Fixes truncated email bodies by:
1. Requesting format=full from Gmail API
2. Recursively walking multipart MIME parts
3. Preferring text/plain, falling back to stripped text/html
4. Stripping signatures, footers, and quoted replies
"""

import base64
import re
from html.parser import HTMLParser


class _HTMLTextExtractor(HTMLParser):
    """Strip HTML tags and extract text content."""

    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False
        self._skip_tags = {"style", "script", "head"}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True
        if tag == "br":
            self._text.append("\n")
        if tag in ("p", "div", "tr", "li"):
            self._text.append("\n")

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False
        if tag in ("p", "div", "tr"):
            self._text.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._text.append(data)

    def get_text(self) -> str:
        return "".join(self._text)


def strip_html(html: str) -> str:
    """Convert HTML to plain text."""
    if not html:
        return ""
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(html)
        text = extractor.get_text()
    except Exception:
        # Fallback: crude tag removal
        text = re.sub(r"<[^>]+>", " ", html)

    # Clean up whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def strip_signature(text: str) -> str:
    """Remove email signatures and quoted replies."""
    if not text:
        return ""

    lines = text.split("\n")
    clean_lines = []

    for line in lines:
        stripped = line.strip()
        # Stop at common signature/reply markers
        if stripped in ("--", "---", "—"):
            break
        if stripped.startswith("On ") and stripped.endswith(" wrote:"):
            break
        if stripped.startswith(">"):
            continue  # Skip quoted text
        if re.match(r"^-{3,}$", stripped):
            break
        # Common footer patterns
        if any(marker in stripped.lower() for marker in [
            "unsubscribe", "view in browser", "email preferences",
            "this email was sent to", "confidentiality notice",
            "if you no longer wish", "manage your notifications",
        ]):
            break
        clean_lines.append(line)

    return "\n".join(clean_lines).strip()


def extract_body_from_payload(payload: dict) -> tuple[str, str]:
    """Recursively extract text/plain and text/html from Gmail API payload.

    Returns:
        (plain_text, html_text) — either or both may be empty
    """
    plain_text = ""
    html_text = ""

    mime_type = payload.get("mimeType", "")
    parts = payload.get("parts", [])

    if parts:
        # Multipart: recurse into parts
        for part in parts:
            pt, ht = extract_body_from_payload(part)
            if pt and not plain_text:
                plain_text = pt
            if ht and not html_text:
                html_text = ht
    else:
        # Leaf part — decode body
        data = payload.get("body", {}).get("data", "")
        if data:
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            if mime_type == "text/plain":
                plain_text = decoded
            elif mime_type == "text/html":
                html_text = decoded

    return plain_text, html_text


def parse_email_body(payload: dict) -> str:
    """Extract clean email body from Gmail API message payload.

    Prefers text/plain. Falls back to stripping HTML.
    Removes signatures, footers, and quoted replies.
    """
    plain_text, html_text = extract_body_from_payload(payload)

    body = plain_text if plain_text else strip_html(html_text)
    body = strip_signature(body)

    return body


def extract_sender_parts(from_header: str) -> tuple[str, str]:
    """Parse 'Display Name <email@domain.com>' into (name, email).

    Returns:
        (display_name, email_address)
    """
    if not from_header:
        return ("", "")

    match = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>$', from_header.strip())
    if match:
        return (match.group(1).strip(), match.group(2).strip())

    # No angle brackets — treat entire string as email
    if "@" in from_header:
        return ("", from_header.strip())

    return (from_header.strip(), "")
