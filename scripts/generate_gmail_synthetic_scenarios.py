from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_LABEL_FILE = Path(
    "audit/runs/gmail_labeling_sample/2026-05-12T20-40-container/label_queue_priority_policy_corrected.csv"
)
DEFAULT_OUTPUT_ROOT = Path("audit/runs/gmail_synthetic_scenarios")
PROMPT_VERSION = "gmail-synthetic-scenario-generator-v5"
LABEL_POLICY_VERSION = "gmail-route-policy-2026-05-12"

VALID_ROUTES = {
    "application_inbox",
    "conversation",
    "action_review",
    "filter",
    "opportunity_discovery",
}

VALID_SUBTYPES = {
    "application_received",
    "application_status_update",
    "interview_request",
    "rejection",
    "offer",
    "assessment_or_task",
    "document_request",
    "recruiter_outreach",
    "referral_or_networking",
    "job_alert",
    "job_board_promo",
    "career_fair_or_event",
    "company_newsletter",
    "marketing_promo",
    "system_notification",
    "finance_noise",
    "retail_noise",
    "school_or_alumni_update",
    "unknown_other",
}

ROUTE_ALLOWED_SUBTYPES = {
    "application_inbox": {
        "application_received",
        "application_status_update",
        "interview_request",
        "rejection",
        "offer",
        "assessment_or_task",
        "document_request",
    },
    "conversation": {
        "recruiter_outreach",
        "referral_or_networking",
    },
    "action_review": {
        "interview_request",
        "assessment_or_task",
        "document_request",
        "recruiter_outreach",
        "unknown_other",
    },
    "filter": {
        "job_alert",
        "job_board_promo",
        "career_fair_or_event",
        "company_newsletter",
        "marketing_promo",
        "system_notification",
        "finance_noise",
        "retail_noise",
        "school_or_alumni_update",
        "unknown_other",
    },
    "opportunity_discovery": {
        "job_alert",
        "job_board_promo",
        "career_fair_or_event",
        "company_newsletter",
        "unknown_other",
    },
}

VALID_ACTION_TYPES = {
    "",
    "reply_to_recruiter",
    "schedule_interview",
    "complete_assessment",
    "submit_document",
    "review_application_update",
}

REQUIRED_ROW_FIELDS = [
    "subject",
    "sender",
    "sender_domain",
    "body",
    "expected_route",
    "expected_subtype",
    "expected_action_required",
    "expected_action_type",
    "rationale",
    "difficulty",
    "scenario_family",
    "source_type",
    "source_dataset",
    "synthetic_family_id",
    "generation_prompt_version",
    "label_policy_version",
    "human_reviewed",
]

OUTPUT_COLUMNS = [
    *REQUIRED_ROW_FIELDS,
    "generation_mode",
    "training_eligible",
    "synthetic_example_notice",
]


SCENARIO_MATRIX = [
    {
        "scenario_family": "application_inbox/application_received",
        "expected_route": "application_inbox",
        "expected_subtype": "application_received",
        "expected_action_required": False,
        "expected_action_type": "",
        "target_count": 8,
        "difficulty": "easy",
        "risk_focus": "ATS confirmation should enter application inbox, not generic filter.",
    },
    {
        "scenario_family": "application_inbox/application_status_update",
        "expected_route": "application_inbox",
        "expected_subtype": "application_status_update",
        "expected_action_required": False,
        "expected_action_type": "",
        "target_count": 8,
        "difficulty": "medium",
        "risk_focus": "Lifecycle updates must not be filtered as job-board noise.",
    },
    {
        "scenario_family": "conversation/recruiter_outreach",
        "expected_route": "conversation",
        "expected_subtype": "recruiter_outreach",
        "expected_action_required": False,
        "expected_action_type": "",
        "target_count": 8,
        "difficulty": "medium",
        "risk_focus": "Human recruiter mail should not be collapsed into automated application events.",
    },
    {
        "scenario_family": "conversation/reply_needed",
        "expected_route": "conversation",
        "expected_subtype": "recruiter_outreach",
        "expected_action_required": True,
        "expected_action_type": "reply_to_recruiter",
        "target_count": 8,
        "difficulty": "hard",
        "risk_focus": "Reply-needed recruiter conversations are not interview scheduling unless a time selection is requested.",
    },
    {
        "scenario_family": "action_review/interview_scheduling",
        "expected_route": "action_review",
        "expected_subtype": "interview_request",
        "expected_action_required": True,
        "expected_action_type": "schedule_interview",
        "target_count": 8,
        "difficulty": "hard",
        "risk_focus": "Interview scheduling should be action-reviewed instead of auto-mutating status.",
    },
    {
        "scenario_family": "filter/job_alert",
        "expected_route": "filter",
        "expected_subtype": "job_alert",
        "expected_action_required": False,
        "expected_action_type": "",
        "target_count": 8,
        "difficulty": "easy",
        "risk_focus": "Bulk job alerts should not create application inbox events.",
    },
    {
        "scenario_family": "filter/job_board_promo",
        "expected_route": "filter",
        "expected_subtype": "job_board_promo",
        "expected_action_required": False,
        "expected_action_type": "",
        "target_count": 8,
        "difficulty": "medium",
        "risk_focus": "Recruiting-adjacent job-board wrappers should remain filtered.",
    },
    {
        "scenario_family": "filter/marketing_promo",
        "expected_route": "filter",
        "expected_subtype": "marketing_promo",
        "expected_action_required": False,
        "expected_action_type": "",
        "target_count": 8,
        "difficulty": "easy",
        "risk_focus": "Marketing language from tech or career domains is still not job-search workflow mail.",
    },
    {
        "scenario_family": "filter/hard_negative_job_mention",
        "expected_route": "filter",
        "expected_subtype": "unknown_other",
        "expected_action_required": False,
        "expected_action_type": "",
        "target_count": 8,
        "difficulty": "hard",
        "risk_focus": "Messages mentioning jobs, hiring, or careers can still be unrelated noise.",
    },
    {
        "scenario_family": "filter/platform_notification_wrapper",
        "expected_route": "filter",
        "expected_subtype": "job_board_promo",
        "expected_action_required": False,
        "expected_action_type": "",
        "target_count": 8,
        "difficulty": "hard",
        "risk_focus": "Ambiguous Handshake, LinkedIn, and platform notification wrappers should not be promoted.",
    },
]


TEMPLATE_EXAMPLES = {
    "application_inbox/application_received": {
        "subject": "Application received for Data Platform Analyst",
        "sender": "Northwind Careers",
        "sender_domain": "careers.northwind.example",
        "body": "Thanks for applying to the Data Platform Analyst role. The recruiting team received your application and will review it soon.",
        "rationale": "Direct application receipt confirmation from a fictional careers system.",
    },
    "application_inbox/application_status_update": {
        "subject": "Update on your Product Data Engineer application",
        "sender": "Acme Recruiting",
        "sender_domain": "recruiting.acme.example",
        "body": "Your application remains under review. We will share the next step after the hiring team finishes evaluation.",
        "rationale": "Lifecycle status update for an existing fictional application.",
    },
    "conversation/recruiter_outreach": {
        "subject": "Following up about the analytics role",
        "sender": "Maya Chen",
        "sender_domain": "northstar.example",
        "body": "Thanks for speaking with me last week. I wanted to follow up on the analytics role and answer any questions.",
        "rationale": "Human recruiter conversation without an explicit scheduling action.",
    },
    "conversation/reply_needed": {
        "subject": "Quick question before I send your profile",
        "sender": "Jordan Rivera",
        "sender_domain": "tracebank.example",
        "body": "Could you reply with your preferred location and whether you are open to hybrid roles before I send your profile to the team?",
        "rationale": "Human recruiter needs a reply, but this is not an interview scheduling event.",
    },
    "action_review/interview_scheduling": {
        "subject": "Choose an interview time for the ML platform role",
        "sender": "Scheduling Team",
        "sender_domain": "schedule.example-ats.test",
        "body": "Please choose an interview time for the ML platform role using the scheduling link. The hiring manager has several slots available.",
        "rationale": "Scheduling request needs user action and should be reviewed.",
    },
    "filter/job_alert": {
        "subject": "18 new jobs match your profile",
        "sender": "Example Job Alerts",
        "sender_domain": "alerts.jobboard.example",
        "body": "Here are new open roles matching your saved search. View jobs, update preferences, or unsubscribe from alerts.",
        "rationale": "Bulk job alert should not become an application event.",
    },
    "filter/job_board_promo": {
        "subject": "Featured employers are hiring this week",
        "sender": "Campus Career Network",
        "sender_domain": "promo.careers.example",
        "body": "Explore featured employers, career fair sessions, and recommended job posts selected for students this week.",
        "rationale": "Recruiting-adjacent promotional wrapper.",
    },
    "filter/marketing_promo": {
        "subject": "New webinar: AI tools for modern teams",
        "sender": "Product Marketing",
        "sender_domain": "updates.vendor.example",
        "body": "Join our webinar and learn how teams are using AI tools. Register now to save your seat.",
        "rationale": "Marketing message with AI and work terms but no job-search workflow.",
    },
    "filter/hard_negative_job_mention": {
        "subject": "Your career dashboard weekly digest",
        "sender": "Account Notifications",
        "sender_domain": "notifications.platform.example",
        "body": "Your weekly digest includes profile views, saved jobs, and account tips. No action is required for an application.",
        "rationale": "Mentions jobs and career content but is a generic notification.",
    },
    "filter/platform_notification_wrapper": {
        "subject": "Someone viewed your profile",
        "sender": "Network Updates",
        "sender_domain": "notifications.network.example",
        "body": "A recruiter may have viewed your profile. Open the platform to see analytics, suggested jobs, and premium tips.",
        "rationale": "Ambiguous platform wrapper with recruiter/job terms should stay filtered.",
    },
}


SANITIZED_FEW_SHOT_POLICY_EXAMPLES = """## Sanitized Few-Shot Policy Examples

These are sanitized policy patterns derived from the human-labeled Gmail CSV. They do not copy real private email text.
Use them to understand boundaries before generating rows.

### Good Positive Patterns

`application_inbox/application_received`
- Subject pattern: "Thanks for your application to [FICTIONAL_COMPANY]"
- Body pattern: "We received your application for [ROLE]. Our recruiting team will review it and contact you about next steps."
- Why: Direct confirmation that the user already submitted an application.

`application_inbox/application_received`
- Subject pattern: "You applied to [FICTIONAL_COMPANY]"
- Body pattern: "Your application for [ROLE] was submitted. You can manage your candidate data in the application portal."
- Why: Even if a platform suggests similar jobs later, the primary message confirms a submitted application.

`application_inbox/application_status_update`
- Subject pattern: "Update on your [ROLE] application"
- Body pattern: "Your application remains under review. We will share the next step after the hiring team finishes evaluation."
- Why: Lifecycle update for an existing candidacy; no new user scheduling action is required.

`conversation/recruiter_outreach`
- Subject pattern: "Re: Interview format | [ROLE_OR_REQ_ID]"
- Body pattern: "Thanks for following up. I can answer questions about the interview format and next steps."
- Why: Human recruiter or candidate conversation; not an automated lifecycle notification.

`conversation/reply_needed`
- Subject pattern: "Quick question before I send your profile"
- Body pattern: "Could you reply with your preferred location and whether you are open to hybrid roles?"
- Why: Needs a reply to a recruiter, but it is not an interview scheduling link or time selection.

`action_review/interview_scheduling`
- Subject pattern: "Choose an interview time for [ROLE]"
- Body pattern: "Please use the scheduling link to select an interview slot or provide your availability."
- Why: User must act on the email to schedule or confirm an interview time.

`filter/job_alert`
- Subject pattern: "New [ROLE] at [FICTIONAL_COMPANY]"
- Body pattern: "A role matching your saved search was posted. View the job, apply, or update alert preferences."
- Why: Job recommendation or saved-search alert; the user has not applied yet.

`filter/job_board_promo`
- Subject pattern: "Show recruiters you are interested with [PLATFORM_FEATURE]"
- Body pattern: "Explore premium profile features, recruiter network suggestions, or platform engagement stats."
- Why: Job-adjacent platform promotion; not an application lifecycle event.

`filter/marketing_promo`
- Subject pattern: "New membership benefits / webinar / product offer"
- Body pattern: "Register, subscribe, purchase, or view promotional content unrelated to an active job process."
- Why: Consumer or vendor marketing; not job workflow mail.

`filter/unknown_other`
- Subject pattern: "Your weekly dashboard digest"
- Body pattern: "Profile views, account tips, generic career content, payment notices, or unrelated account updates."
- Why: May mention careers/jobs/accounts, but it is not actionable job-search lifecycle mail.

### Contrastive Near-Misses

Do not generate these under `application_inbox/application_received`:
- "Job Alert: [ROLE] openings" -> correct label: `filter/job_alert`
- "Weekly job opportunities digest" -> correct label: `filter/job_alert`
- "Special offer for job seekers" -> correct label: `filter/marketing_promo` or `filter/job_board_promo`
- "Company newsletter and latest updates" -> correct label: `filter/company_newsletter`
- "Interview request for [ROLE]" -> correct label: `action_review/interview_request` when scheduling/action is required
- "Status update on your application" -> correct label: `application_inbox/application_status_update`, not `application_received`

Do not generate these under `application_inbox/application_status_update`:
- "New jobs match your profile" -> correct label: `filter/job_alert`
- "Discover new openings" -> correct label: `filter/job_alert`
- "Schedule your interview / choose a time" -> correct label: `action_review/interview_request`
- "Exclusive promo for job seekers" -> correct label: `filter/marketing_promo` or `filter/job_board_promo`

Do not generate these under `action_review/interview_scheduling`:
- Generic career fair invitations without a specific interview schedule action -> `filter/career_fair_or_event`
- Application under-review updates without user action -> `application_inbox/application_status_update`
- Recruiter chat that asks a general question but no scheduling -> `conversation/recruiter_outreach`

Do not generate these under `filter/platform_notification_wrapper`:
- "Your application is under review" for a specific role the user applied to -> `application_inbox/application_status_update`
- "Choose an interview slot" for a specific application -> `action_review/interview_request`
"""

FAMILY_FEW_SHOT_EXAMPLES = {
    "application_inbox/application_received": """## Sanitized Few-Shot Policy Examples

Use only these examples for this scenario family.

Good `application_inbox/application_received` patterns:
- Subject: "Thanks for your application to [FICTIONAL_COMPANY]"
  Body: "We received your application for [ROLE]. Our recruiting team will review it and contact you about next steps."
- Subject: "You applied to [FICTIONAL_COMPANY]"
  Body: "Your application for [ROLE] was submitted. You can manage your candidate data in the application portal."

Near-misses to avoid:
- "Job Alert: [ROLE] openings" -> `filter/job_alert`
- "Weekly job opportunities digest" -> `filter/job_alert`
- "Special offer for job seekers" -> `filter/marketing_promo` or `filter/job_board_promo`
- "Company newsletter and latest updates" -> `filter/company_newsletter`
- "Interview request for [ROLE]" -> `action_review/interview_request`
- "Status update on your application" -> `application_inbox/application_status_update`
""",
    "application_inbox/application_status_update": """## Sanitized Few-Shot Policy Examples

Use only these examples for this scenario family.

Good `application_inbox/application_status_update` patterns:
- Subject: "Update on your [ROLE] application"
  Body: "Your application remains under review. We will share the next step after the hiring team finishes evaluation."
- Subject: "Your application status at [FICTIONAL_COMPANY]"
  Body: "The recruiting team is still reviewing your candidacy. No action is needed right now."

Near-misses to avoid:
- "New jobs match your profile" -> `filter/job_alert`
- "Discover new openings" -> `filter/job_alert`
- "Schedule your interview / choose a time" -> `action_review/interview_request`
- "Exclusive promo for job seekers" -> `filter/marketing_promo` or `filter/job_board_promo`
""",
    "conversation/recruiter_outreach": """## Sanitized Few-Shot Policy Examples

Use only these examples for this scenario family.

Good `conversation/recruiter_outreach` patterns:
- Subject: "Re: Interview format | [ROLE_OR_REQ_ID]"
  Body: "Thanks for following up. I can answer questions about the interview format and next steps."
- Subject: "Following up about the [ROLE] conversation"
  Body: "I wanted to reconnect and see whether you had questions after our last conversation."

Near-misses to avoid:
- Automated application received/status messages -> `application_inbox`
- A scheduling link requiring the user to choose a time -> `action_review/interview_request`
- Bulk recruiter platform notifications with no direct message -> `filter/job_board_promo`
""",
    "conversation/reply_needed": """## Sanitized Few-Shot Policy Examples

Use only these examples for this scenario family.

Good `conversation/reply_needed` patterns:
- Subject: "Quick question before I send your profile"
  Body: "Could you reply with your preferred location and whether you are open to hybrid roles?"
- Subject: "Can you confirm your current search preferences?"
  Body: "Please reply with your target roles and salary range so I can decide whether to submit you."

Near-misses to avoid:
- Calendar/scheduler/time-slot selection -> `action_review/interview_request`
- Application under-review status with no reply needed -> `application_inbox/application_status_update`
- Bulk job alert or job board digest -> `filter/job_alert`
""",
    "action_review/interview_scheduling": """## Sanitized Few-Shot Policy Examples

Use only these examples for this scenario family.

Good `action_review/interview_scheduling` patterns:
- Subject: "Choose an interview time for [ROLE]"
  Body: "Please use the scheduling link to select an interview slot or provide your availability."
- Subject: "Confirm your interview availability"
  Body: "Reply with two time windows or book through the calendar link by [DATE]."

Near-misses to avoid:
- Generic career fair invitations without a specific interview scheduling action -> `filter/career_fair_or_event`
- Application under-review updates without user action -> `application_inbox/application_status_update`
- Recruiter chat that asks a general question but no scheduling -> `conversation/recruiter_outreach`
""",
    "filter/job_alert": """## Sanitized Few-Shot Policy Examples

Use only these examples for this scenario family.

Good `filter/job_alert` patterns:
- Subject: "New [ROLE] at [FICTIONAL_COMPANY]"
  Body: "A role matching your saved search was posted. View the job, apply, or update alert preferences."
- Subject: "[N] new jobs match your search"
  Body: "Here are recommended jobs based on your profile or saved search."

Near-misses to avoid:
- "We received your application" -> `application_inbox/application_received`
- "Your application is under review" -> `application_inbox/application_status_update`
- "Your interview is scheduled" -> `action_review/interview_request`
""",
    "filter/job_board_promo": """## Sanitized Few-Shot Policy Examples

Use only these examples for this scenario family.

Good `filter/job_board_promo` patterns:
- Subject: "Show recruiters you are interested with [PLATFORM_FEATURE]"
  Body: "Explore premium profile features, recruiter network suggestions, or platform engagement stats."
- Subject: "Your profile got views this week"
  Body: "See profile analytics, suggested contacts, and tips to improve visibility."

Near-misses to avoid:
- Direct application confirmation -> `application_inbox/application_received`
- Direct application status update -> `application_inbox/application_status_update`
- Specific interview scheduling request -> `action_review/interview_request`
""",
    "filter/marketing_promo": """## Sanitized Few-Shot Policy Examples

Use only these examples for this scenario family.

Good `filter/marketing_promo` patterns:
- Subject: "New membership benefits / webinar / product offer"
  Body: "Register, subscribe, purchase, or view promotional content unrelated to an active job process."
- Subject: "Limited-time offer from [FICTIONAL_VENDOR]"
  Body: "Marketing copy for a consumer, SaaS, education, or services product."

Near-misses to avoid:
- Job recommendation digest -> `filter/job_alert`
- Direct recruiter message -> `conversation/recruiter_outreach`
- Application lifecycle message -> `application_inbox`
""",
    "filter/hard_negative_job_mention": """## Sanitized Few-Shot Policy Examples

Use only these examples for this scenario family.

Good `filter/hard_negative_job_mention` patterns:
- Subject: "Your weekly career dashboard digest"
  Body: "Profile views, saved search stats, generic career content, or account tips. No application or recruiter action exists."
- Subject: "Account update mentioning work preferences"
  Body: "Generic account or profile update that mentions jobs/careers but does not affect a specific candidacy."

Near-misses to avoid:
- "We received your application" -> `application_inbox/application_received`
- "Your application is under review" -> `application_inbox/application_status_update`
- "Your interview is scheduled" -> `action_review/interview_request`
""",
    "filter/platform_notification_wrapper": """## Sanitized Few-Shot Policy Examples

Use only these examples for this scenario family.

Good `filter/platform_notification_wrapper` patterns:
- Subject: "Someone viewed your profile"
  Body: "Open the platform to view analytics, suggested jobs, premium tips, or broad recruiter activity."
- Subject: "A recruiter may be interested in your profile"
  Body: "Notification wrapper with no direct message, no specific application, and no user scheduling action."

Near-misses to avoid:
- "Your application is under review" for a specific role -> `application_inbox/application_status_update`
- "Choose an interview slot" for a specific application -> `action_review/interview_request`
- Direct human recruiter message asking for a reply -> `conversation/recruiter_outreach`
""",
}


def _load_local_env() -> None:
    """Load local dotenv values for standalone CLI runs without overriding shell env."""

    try:
        from dotenv import dotenv_values
    except Exception:
        return

    default_values = dict(dotenv_values(REPO_ROOT / ".env")) if (REPO_ROOT / ".env").exists() else {}
    environment = (
        os.environ.get("ENVIRONMENT")
        or default_values.get("ENVIRONMENT")
        or "development"
    ).strip().lower()

    merged_values = dict(default_values)
    local_path = REPO_ROOT / ".env.local"
    if environment != "production" and local_path.exists():
        for key, value in dict(dotenv_values(local_path)).items():
            if (
                key == "OPENAI_API_KEY"
                and not _clean_cell(value)
                and _clean_cell(merged_values.get(key))
            ):
                continue
            merged_values[key] = value

    for key, value in merged_values.items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _clean_cell(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_label(value: Any) -> str:
    cleaned = _clean_cell(value).lower()
    cleaned = re.sub(r"[\s-]+", "_", cleaned)
    cleaned = re.sub(r"[^a-z0-9_]+", "", cleaned)
    return re.sub(r"_+", "_", cleaned).strip("_")


def _bool_string(value: Any, *, default: str = "false") -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    cleaned = _normalize_label(value)
    if cleaned in {"yes", "true", "1", "y"}:
        return "true"
    if cleaned in {"no", "false", "0", "n"}:
        return "false"
    return default


def _read_seed_summary(path: Path) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labeled = [
        row
        for row in rows
        if _normalize_label(row.get("expected_route")) and _normalize_label(row.get("expected_subtype"))
    ]
    return {
        "source_file": str(path),
        "rows_total": len(rows),
        "rows_labeled": len(labeled),
        "expected_route_counts": dict(sorted(Counter(_normalize_label(row.get("expected_route")) for row in labeled).items())),
        "expected_subtype_counts": dict(sorted(Counter(_normalize_label(row.get("expected_subtype")) for row in labeled).items())),
        "account_role_counts": dict(sorted(Counter(_clean_cell(row.get("account_role")) for row in labeled).items())),
        "unique_sender_domains": len({_clean_cell(row.get("sender_domain")).lower() for row in labeled if _clean_cell(row.get("sender_domain"))}),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _scenario_rows_for_dry_run(source_dataset: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in SCENARIO_MATRIX:
        family = item["scenario_family"]
        template = TEMPLATE_EXAMPLES[family]
        rows.append(
            {
                "subject": template["subject"],
                "sender": template["sender"],
                "sender_domain": template["sender_domain"],
                "body": template["body"],
                "expected_route": item["expected_route"],
                "expected_subtype": item["expected_subtype"],
                "expected_action_required": _bool_string(item["expected_action_required"]),
                "expected_action_type": item["expected_action_type"],
                "rationale": template["rationale"],
                "difficulty": item["difficulty"],
                "scenario_family": family,
                "source_type": "synthetic_llm_generated",
                "source_dataset": source_dataset,
                "synthetic_family_id": _normalize_label(family),
                "generation_prompt_version": PROMPT_VERSION,
                "label_policy_version": LABEL_POLICY_VERSION,
                "human_reviewed": "false",
                "generation_mode": "dry_run_template",
                "training_eligible": "false",
                "synthetic_example_notice": "Deterministic dry-run template example; not LLM-generated and not training data.",
            }
        )
    return rows


def _schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "GmailSyntheticScenarioRows",
        "type": "object",
        "required": ["rows"],
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": REQUIRED_ROW_FIELDS,
                    "properties": {
                        "subject": {"type": "string", "minLength": 1},
                        "sender": {"type": "string", "minLength": 1},
                        "sender_domain": {"type": "string", "minLength": 1},
                        "body": {"type": "string", "minLength": 1},
                        "expected_route": {"type": "string", "enum": sorted(VALID_ROUTES)},
                        "expected_subtype": {"type": "string", "enum": sorted(VALID_SUBTYPES)},
                        "expected_action_required": {
                            "oneOf": [
                                {"type": "boolean"},
                                {"type": "string", "enum": ["true", "false"]},
                            ]
                        },
                        "expected_action_type": {"type": "string", "enum": sorted(VALID_ACTION_TYPES)},
                        "rationale": {"type": "string", "minLength": 1},
                        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                        "scenario_family": {"type": "string", "minLength": 1},
                        "source_type": {
                            "type": "string",
                            "enum": ["real_human", "real_llm_labeled", "synthetic_llm_generated"],
                        },
                        "source_dataset": {"type": "string", "minLength": 1},
                        "synthetic_family_id": {"type": "string", "minLength": 1},
                        "generation_prompt_version": {"type": "string", "minLength": 1},
                        "label_policy_version": {"type": "string", "minLength": 1},
                        "human_reviewed": {
                            "oneOf": [
                                {"type": "boolean"},
                                {"type": "string", "enum": ["true", "false"]},
                            ]
                        },
                    },
                },
            }
        },
    }


def _few_shot_policy_examples(scenarios: list[dict[str, Any]]) -> str:
    if len(scenarios) != 1:
        return SANITIZED_FEW_SHOT_POLICY_EXAMPLES
    family = str(scenarios[0].get("scenario_family", ""))
    return FAMILY_FEW_SHOT_EXAMPLES.get(family, SANITIZED_FEW_SHOT_POLICY_EXAMPLES)


def _prompt_pack(seed_summary: dict[str, Any], scenario_matrix: list[dict[str, Any]] | None = None) -> str:
    scenarios = scenario_matrix or SCENARIO_MATRIX
    scenario_json = json.dumps(scenarios, indent=2, sort_keys=True)
    schema_json = json.dumps(_schema(), indent=2, sort_keys=True)
    summary_json = json.dumps(seed_summary, indent=2, sort_keys=True)
    route_subtype_json = json.dumps(
        {route: sorted(subtypes) for route, subtypes in sorted(ROUTE_ALLOWED_SUBTYPES.items())},
        indent=2,
        sort_keys=True,
    )
    target_total = sum(int(item.get("target_count", 0)) for item in scenarios)
    return f"""# Gmail Synthetic Scenario Prompt Pack

Prompt version: `{PROMPT_VERSION}`
Label policy version: `{LABEL_POLICY_VERSION}`

## Boundary

Real human-labeled rows are truth data. Synthetic rows are only training and stress-test expansion.
Do not treat synthetic-only performance as production evidence. Do not include private real email text in the prompt.
Only aggregate label counts and sanitized policy examples are included.

## Seed Summary

The generator receives aggregate label counts and sanitized policy examples only:

```json
{summary_json}
```

## Scenario Matrix

```json
{scenario_json}
```

## Strict Label Vocabulary

Use only these production route labels. Do not invent route names:

```json
{json.dumps(sorted(VALID_ROUTES), indent=2)}
```

Use only these production subtype labels. Do not invent subtype names:

```json
{json.dumps(sorted(VALID_SUBTYPES), indent=2)}
```

Use only these route/subtype pairings:

```json
{route_subtype_json}
```

{_few_shot_policy_examples(scenarios)}

## Output Schema

Return only a JSON object matching this schema:

```json
{schema_json}
```

## Instructions

- Generate exactly `{target_total}` rows total.
- For each scenario family, generate exactly its `target_count` number of unique rows.
- Generate only rows for the scenario families shown in this prompt. Do not add contrast examples from other families.
- Generate fictional Gmail-like examples only. Do not use real companies, real people, real email addresses, or copied source text.
- Do not use placeholders such as Company X, Company Y, Example Corp, John Doe, Jane Doe, candidate@example.com, or test@example.com.
- Use specific invented company/recruiter/platform names and plausible but fictional sender domains.
- Preserve the exact `expected_route`, `expected_subtype`, `expected_action_required`, and `expected_action_type` values from the scenario family. Do not infer or alter labels.
- The email text must semantically match the assigned route/subtype. For example:
  - `application_inbox/application_received` must be a direct confirmation for a job the user already applied to. It must not be a job alert, recommendation digest, career newsletter, promo, or "new openings" email.
  - `application_inbox/application_status_update` must update an existing candidacy/application. It must not advertise roles the user has not applied to.
  - `action_review/interview_request` must contain an interview scheduling or time-selection action.
  - `filter/job_alert` and `filter/job_board_promo` must remain bulk/recommendation/promotional messages, not application lifecycle messages.
- Do not create hard negatives unless the scenario family itself starts with `filter/`.
- For `application_inbox` scenarios, forbidden cues include: job alert, weekly job digest, recommended jobs, new openings, special offer, promo, unsubscribe-only footer, and career coaching offer.
- For `action_review/interview_scheduling`, every row must include an explicit user action to schedule, choose a slot, provide availability, use a calendar link, or confirm an interview time.
- For `filter` scenarios, do not use direct application lifecycle language such as "we received your application", "your application is under review", "schedule your interview", or "choose a time" unless the text clearly says it is only a platform ad or generic example unrelated to the user's own application.
- Vary wording, sender domains, body length, subject style, notification wrapper text, recruiter tone, and difficulty.
- Include messy real-inbox artifacts such as signatures, forwarded context, boilerplate, vague subjects, notification wrappers, and unsubscribe/footer text when appropriate.
- Keep each row grounded in the label policy and include a short rationale.
"""


def _body_signature(row: dict[str, Any]) -> str:
    text = f"{row.get('subject', '')} {row.get('body', '')}".lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _near_duplicate(a: str, b: str) -> bool:
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if not a_tokens or not b_tokens:
        return False
    overlap = len(a_tokens & b_tokens) / max(len(a_tokens), len(b_tokens))
    return overlap >= 0.86


def _semantic_warnings(row: dict[str, Any]) -> list[str]:
    route = row.get("expected_route")
    subtype = row.get("expected_subtype")
    text = f"{row.get('subject', '')} {row.get('body', '')}".lower()
    subject = str(row.get("subject", "")).lower()
    warnings: list[str] = []
    alert_or_promo_cues = [
        "job alert",
        "weekly job",
        "job opportunities digest",
        "job postings",
        "job digest",
        "recommended jobs",
        "new openings",
        "discover new job",
        "special offer",
        "exclusive offer",
        "career coaching",
        "company newsletter",
        "newsletter",
        "promotion",
        "promo",
        "unsubscribe",
    ]
    lifecycle_or_action_cues = [
        "thank you for applying",
        "thanks for applying",
        "thanks for your application",
        "we received your application",
        "application has been received",
        "your application is under review",
        "special update on your application",
        "schedule an interview",
        "interview scheduled",
        "your interview is scheduled",
        "your interview for",
        "choose a time",
        "calendar link",
    ]
    scheduling_cues = [
        "schedule",
        "interview",
        "choose",
        "availability",
        "calendar",
        "slot",
        "time",
    ]
    if route == "application_inbox" and any(cue in text for cue in alert_or_promo_cues):
        warnings.append("application_inbox_text_looks_like_alert_or_promo")
    if subtype == "application_received":
        received_cues = [
            "application received",
            "received your application",
            "thanks for your application",
            "thanks for applying",
            "you applied",
            "application confirmation",
        ]
        wrong_received_subject_cues = [
            "interview request",
            "interview scheduling",
            "schedule your interview",
            "choose an interview",
            "status update",
            "application status",
            "under review",
            "in review",
            "newsletter",
            "promotion",
            "promo",
        ]
        if not any(cue in text for cue in received_cues):
            warnings.append("application_received_missing_direct_receipt_cue")
        if any(cue in subject for cue in wrong_received_subject_cues):
            warnings.append("application_received_subject_matches_other_subtype")
    if subtype == "application_status_update":
        status_cues = [
            "status",
            "update",
            "under review",
            "still reviewing",
            "next step",
            "application",
        ]
        scheduling_cues = ["schedule", "choose", "calendar", "interview slot", "interview time"]
        if not any(cue in text for cue in status_cues):
            warnings.append("application_status_update_missing_status_cue")
        if any(cue in text for cue in scheduling_cues):
            warnings.append("application_status_update_contains_scheduling_action")
    if route == "conversation":
        bulk_or_event_cues = [
            "job alert",
            "weekly job",
            "job digest",
            "job postings",
            "new openings",
            "career fair",
            "recommended jobs",
        ]
        scheduling_subject_cues = [
            "interview scheduling",
            "choose your interview",
            "schedule your interview",
            "interview time",
            "calendar link",
        ]
        if any(cue in text for cue in bulk_or_event_cues):
            warnings.append("conversation_text_looks_like_bulk_alert_or_event")
        if any(cue in subject for cue in scheduling_subject_cues):
            warnings.append("conversation_subject_looks_like_scheduling_action")
    if route == "filter" and any(cue in text for cue in lifecycle_or_action_cues):
        warnings.append("filter_text_looks_like_lifecycle_or_action")
    if route == "action_review" and not any(cue in text for cue in scheduling_cues):
        warnings.append("action_review_text_missing_scheduling_cue")
    return warnings


def validate_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    semantic_warnings: list[dict[str, Any]] = []
    signatures: list[str] = []
    exact_duplicates = 0
    near_duplicates = 0
    for index, row in enumerate(rows, start=1):
        reasons: list[str] = []
        action_required = _bool_string(row.get("expected_action_required")) == "true"
        for field in REQUIRED_ROW_FIELDS:
            if field not in row:
                reasons.append(f"missing_{field}")
                continue
            if field == "expected_action_type" and not action_required:
                continue
            if _clean_cell(row.get(field)) == "":
                reasons.append(f"missing_{field}")
        if row.get("expected_route") not in VALID_ROUTES:
            reasons.append("invalid_expected_route")
        if row.get("expected_subtype") not in VALID_SUBTYPES:
            reasons.append("invalid_expected_subtype")
        allowed_subtypes = ROUTE_ALLOWED_SUBTYPES.get(row.get("expected_route"), set())
        if row.get("expected_route") in VALID_ROUTES and row.get("expected_subtype") not in allowed_subtypes:
            reasons.append("invalid_route_subtype_pair")
        if _bool_string(row.get("expected_action_required"), default="") not in {"true", "false"}:
            reasons.append("invalid_expected_action_required")
        if row.get("expected_action_type", "") not in VALID_ACTION_TYPES:
            reasons.append("invalid_expected_action_type")
        if not action_required and _clean_cell(row.get("expected_action_type")):
            reasons.append("unexpected_action_type_without_required_action")
        if _bool_string(row.get("human_reviewed"), default="") != "false":
            reasons.append("human_reviewed_must_be_false_for_generated_rows")
        warnings = _semantic_warnings(row)
        if warnings:
            semantic_warnings.append(
                {
                    "row_index": index,
                    "scenario_family": row.get("scenario_family"),
                    "expected_route": row.get("expected_route"),
                    "subject": row.get("subject"),
                    "warnings": warnings,
                }
            )
            reasons.extend(f"semantic_warning:{warning}" for warning in warnings)
        signature = _body_signature(row)
        if signature in signatures:
            exact_duplicates += 1
            reasons.append("duplicate_subject_body")
        elif any(_near_duplicate(signature, existing) for existing in signatures):
            near_duplicates += 1
            reasons.append("near_duplicate_subject_body")
        if reasons:
            rejected.append({"row_index": index, "reasons": reasons, "scenario_family": row.get("scenario_family")})
            continue
        signatures.append(signature)
        accepted.append(row)

    body_lengths = [len(row["body"]) for row in accepted]
    summary = {
        "rows_input": len(rows),
        "rows_accepted": len(accepted),
        "rows_rejected": len(rejected),
        "rejected_rows": rejected,
        "semantic_warning_count": len(semantic_warnings),
        "semantic_warnings": semantic_warnings,
        "duplicate_rate": round((exact_duplicates + near_duplicates) / len(rows), 6) if rows else 0,
        "exact_duplicate_count": exact_duplicates,
        "near_duplicate_count": near_duplicates,
        "counts_by_route_subtype": dict(
            sorted(Counter(f"{row['expected_route']}/{row['expected_subtype']}" for row in accepted).items())
        ),
        "counts_by_scenario_family": dict(sorted(Counter(row["scenario_family"] for row in accepted).items())),
        "unique_sender_domains": len({row["sender_domain"] for row in accepted}),
        "body_length": {
            "min": min(body_lengths) if body_lengths else 0,
            "max": max(body_lengths) if body_lengths else 0,
            "mean": round(mean(body_lengths), 2) if body_lengths else 0,
        },
        "training_eligible_count": sum(1 for row in accepted if str(row.get("training_eligible")).lower() == "true"),
    }
    return accepted, summary


def _normalise_generated_rows(
    rows: list[dict[str, Any]],
    *,
    scenario: dict[str, Any] | None = None,
    training_eligible: bool = False,
) -> list[dict[str, Any]]:
    normalized_rows = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        row = dict(row)
        if scenario:
            row["scenario_family"] = scenario["scenario_family"]
            row["expected_route"] = scenario["expected_route"]
            row["expected_subtype"] = scenario["expected_subtype"]
            row["expected_action_required"] = _bool_string(scenario["expected_action_required"], default="")
            row["expected_action_type"] = scenario["expected_action_type"]
            row.setdefault("difficulty", scenario["difficulty"])
        row.setdefault("source_type", "synthetic_llm_generated")
        row.setdefault("source_dataset", "gmail_synthetic_scenarios")
        row.setdefault("generation_prompt_version", PROMPT_VERSION)
        row.setdefault("label_policy_version", LABEL_POLICY_VERSION)
        row.setdefault("human_reviewed", False)
        row.setdefault(
            "synthetic_family_id",
            f"{_normalize_label(row.get('scenario_family'))}_{index:03d}",
        )
        row["generation_mode"] = "llm_generate"
        row["training_eligible"] = "true" if training_eligible else "false"
        row["synthetic_example_notice"] = (
            ""
            if training_eligible
            else "LLM-generated synthetic row; requires human or critic review before training use."
        )
        row["expected_action_required"] = _bool_string(row.get("expected_action_required"), default="")
        row["human_reviewed"] = "false"
        normalized_rows.append(row)
    return normalized_rows


def _call_openai_json_rows(client: Any, *, seed_summary: dict[str, Any], scenarios: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    prompt = _prompt_pack(seed_summary, scenarios)
    try:
        response = client.chat.completions.create(
            model=os.getenv("GMAIL_SYNTHETIC_GENERATOR_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "Generate schema-valid fictional Gmail classifier scenario rows."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            response_format={"type": "json_object"},
        )
    except Exception as exc:  # pragma: no cover - network/provider guard
        return [], f"LLM generation failed: {type(exc).__name__}: {exc}"
    content = response.choices[0].message.content or "{}"
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        return [], f"LLM returned invalid JSON: {exc}"
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return [], "LLM JSON did not include a rows array"
    return [row for row in rows if isinstance(row, dict)], "generated"


def _openai_generate_rows(seed_summary: dict[str, Any], *, training_eligible: bool = False) -> tuple[list[dict[str, Any]], str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return [], "OPENAI_API_KEY is not configured"
    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover - local dependency guard
        return [], f"openai package unavailable: {type(exc).__name__}: {exc}"

    client = OpenAI(api_key=api_key)
    generated_rows: list[dict[str, Any]] = []
    statuses: list[str] = []
    for scenario in SCENARIO_MATRIX:
        rows, status = _call_openai_json_rows(client, seed_summary=seed_summary, scenarios=[scenario])
        statuses.append(f"{scenario['scenario_family']}:{status}:{len(rows)}")
        generated_rows.extend(_normalise_generated_rows(rows, scenario=scenario, training_eligible=training_eligible))
    if not generated_rows:
        return [], "; ".join(statuses) or "LLM returned no rows"
    return generated_rows, "generated_by_scenario_family; " + "; ".join(statuses)


def main() -> None:
    _load_local_env()

    parser = argparse.ArgumentParser(description="Generate offline Gmail synthetic scenario artifacts.")
    parser.add_argument("--seed-csv", default=str(SEED_LABEL_FILE))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--timestamp", default=_timestamp())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run-template", action="store_true", help="Write prompt/schema/template examples without LLM calls.")
    mode.add_argument("--generate", action="store_true", help="Call configured LLM if available; fall back to dry-run artifacts.")
    parser.add_argument(
        "--mark-training-eligible",
        action="store_true",
        help="Mark LLM-generated rows as training eligible. Use only after explicit review/approval.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_root) / args.timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    seed_path = Path(args.seed_csv)
    seed_summary = _read_seed_summary(seed_path)
    source_dataset = f"seed:{seed_path.name}"

    rows: list[dict[str, Any]]
    generation_status: str
    if args.generate:
        rows, generation_status = _openai_generate_rows(seed_summary, training_eligible=args.mark_training_eligible)
        if not rows:
            rows = _scenario_rows_for_dry_run(source_dataset)
            generation_status = f"{generation_status}; wrote dry-run template examples instead"
    else:
        rows = _scenario_rows_for_dry_run(source_dataset)
        generation_status = "dry_run_template"

    accepted, validation_summary = validate_rows(rows)

    _write_csv(output_dir / "scenario_matrix.csv", SCENARIO_MATRIX, list(SCENARIO_MATRIX[0]))
    (output_dir / "generation_schema.json").write_text(json.dumps(_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "prompt_pack.md").write_text(_prompt_pack(seed_summary), encoding="utf-8")
    _write_jsonl(output_dir / "synthetic_scenarios.jsonl", accepted)
    _write_csv(output_dir / "synthetic_scenarios.csv", accepted, OUTPUT_COLUMNS)

    validation_summary = {
        **validation_summary,
        "artifact": "gmail_synthetic_scenarios",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation_status": generation_status,
        "prompt_version": PROMPT_VERSION,
        "label_policy_version": LABEL_POLICY_VERSION,
        "seed_summary": seed_summary,
        "output_dir": str(output_dir),
    }
    (output_dir / "validation_summary.json").write_text(
        json.dumps(validation_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "generation_status": generation_status,
                "rows_accepted": validation_summary["rows_accepted"],
                "training_eligible_count": validation_summary["training_eligible_count"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
