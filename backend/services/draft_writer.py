"""Sprint 14: AI-drafted communications using Claude Sonnet.

Generates context-aware email drafts for follow-ups, introductions, and replies.
"""

import json
import logging
import os

import anthropic

from backend.utils.retry import with_retry

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

DRAFT_MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are an expert at writing professional job search emails.
Generate a draft email based on the context provided.

Rules:
1. Be concise and professional
2. Match the tone of any previous conversation (formal/casual)
3. Never sound desperate or pushy
4. Include specific details from the context (company name, role, conversation history)
5. Keep subject lines under 60 characters
6. Keep body under 150 words for follow-ups, 200 for introductions

Return ONLY valid JSON:
{
  "subject": "<email subject line>",
  "body": "<email body text>",
  "tone": "<formal|casual|neutral>"
}"""

DRAFT_TYPE_PROMPTS = {
    "follow_up": "Write a polite follow-up email for a job application. It's been {days_since} days since the last activity. Keep it brief and professional.",
    "introduction": "Write an introduction/networking email to {contact_name} at {company}. The user is interested in the {role} position. Make it warm but professional.",
    "reply": "Write a reply to the most recent message in this email thread. Be helpful and responsive.",
    "thank_you": "Write a thank-you email after an interview at {company} for the {role} position.",
}


async def generate_draft(
    draft_type: str,
    company: str = "",
    role: str = "",
    contact_name: str = "",
    contact_email: str = "",
    conversation_history: list[dict] | None = None,
    days_since: int = 0,
    additional_context: str = "",
) -> dict:
    """Generate an AI email draft.

    Returns dict with subject, body, tone.
    """
    # Build context prompt
    prompt_template = DRAFT_TYPE_PROMPTS.get(draft_type, DRAFT_TYPE_PROMPTS["follow_up"])
    type_prompt = prompt_template.format(
        days_since=days_since,
        contact_name=contact_name or "the contact",
        company=company or "the company",
        role=role or "the position",
    )

    # Build conversation context
    context_parts = [f"Draft type: {draft_type}"]
    if company:
        context_parts.append(f"Company: {company}")
    if role:
        context_parts.append(f"Role: {role}")
    if contact_name:
        context_parts.append(f"Contact: {contact_name}")
    if contact_email:
        context_parts.append(f"Contact email: {contact_email}")
    if additional_context:
        context_parts.append(f"Additional context: {additional_context}")

    if conversation_history:
        context_parts.append("\nConversation history (most recent first):")
        for msg in conversation_history[:5]:
            sender = "You" if msg.get("is_from_user") else msg.get("sender", "Unknown")
            context_parts.append(f"  [{sender}] {msg.get('subject', '')}: {msg.get('snippet', '')[:200]}")

    user_message = f"{type_prompt}\n\nContext:\n" + "\n".join(context_parts)

    try:
        response = await with_retry(
            client.messages.create,
            model=DRAFT_MODEL,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        text = response.content[0].text.strip()
        # Try to parse as JSON
        if text.startswith("{"):
            result = json.loads(text)
        else:
            # Extract JSON from response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(text[start:end])
            else:
                result = {
                    "subject": f"Re: {role} position at {company}" if role else "Following up",
                    "body": text,
                    "tone": "neutral",
                }

        return {
            "subject": result.get("subject", ""),
            "body": result.get("body", ""),
            "tone": result.get("tone", "neutral"),
            "draft_type": draft_type,
        }

    except Exception as e:
        logger.warning("Draft generation failed, returning template: %s", e)
        return _fallback_draft(draft_type, company, role, contact_name)


def _fallback_draft(
    draft_type: str,
    company: str = "",
    role: str = "",
    contact_name: str = "",
) -> dict:
    """Fallback template when LLM is unavailable."""
    templates = {
        "follow_up": {
            "subject": f"Following up on {role} application" if role else "Following up on my application",
            "body": f"Hi,\n\nI wanted to follow up on my application for the {role} position at {company}. I'm very excited about the opportunity and would love to discuss how my experience aligns with the role.\n\nPlease let me know if there are any updates or if you need any additional information from me.\n\nBest regards",
        },
        "introduction": {
            "subject": f"Introduction - interested in {role} at {company}" if role else "Introduction",
            "body": f"Hi {contact_name or 'there'},\n\nI came across {company}'s {role} position and I'm very interested. I'd love to learn more about the role and the team.\n\nWould you have a few minutes for a brief chat?\n\nBest regards",
        },
        "reply": {
            "subject": "Re: ",
            "body": "Thank you for getting back to me. ",
        },
        "thank_you": {
            "subject": f"Thank you - {role} interview at {company}" if role else "Thank you for the interview",
            "body": f"Hi {contact_name or 'there'},\n\nThank you for taking the time to interview me for the {role} position at {company}. I really enjoyed our conversation and learning more about the team.\n\nI'm very excited about the opportunity and look forward to hearing from you.\n\nBest regards",
        },
    }
    template = templates.get(draft_type, templates["follow_up"])
    return {
        "subject": template["subject"],
        "body": template["body"],
        "tone": "neutral",
        "draft_type": draft_type,
        "is_template": True,
    }
