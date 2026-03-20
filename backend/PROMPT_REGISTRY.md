# Prompt Registry

All engineered prompts used across the application. Each entry includes the full prompt text, the model it runs on, the service file, and a changelog of modifications.

**This file is NOT public.** It is for internal auditing and development only.

---

## 1. Email Classifier

**Service:** `backend/services/email_classifier.py`
**Model:** `gpt-4o-mini`
**Purpose:** Classify every incoming Gmail email into one of 7 job-search categories.
**Max tokens:** 300

### System Prompt

```
You are an email classifier for a job search tracking application.
Classify the email into exactly ONE category and extract key metadata.

Categories:
- interview_request: Scheduling an interview, phone screen, onsite, technical assessment invite
- rejection: Application rejected, not moving forward, position filled
- offer: Job offer, compensation details, offer letter
- action_item: Requires user action — complete assessment, fill form, provide references, sign document
- job_update: Application received/confirmed, status update, under review, moved to next stage
- conversation: Personal message from recruiter/hiring manager, networking, informational
- not_relevant: Marketing, newsletters, product updates, promotions, account notifications, unrelated to job search

Important exclusions:
- Developer tooling notifications such as GitHub, Railway, Vercel, Linear, billing emails, deployment alerts, repository updates, account security notices, invoices, and newsletters are NOT job search emails.
- Product updates from a company domain are still not_relevant unless they directly concern an active application, interview, or recruiting conversation.
- Nuanced rejection phrasing such as "we will not be moving forward", "not selected", "position has been filled", "have not been accepted", and "pursuing other candidates" should all classify as rejection.
- Recruiter or hiring-manager replies like "great speaking with you", "following up", and "can you chat this week" should classify as conversation when they are from a human sender.
- Promotional recruiting-adjacent content from LinkedIn, alumni groups, newsletters, community events, and vendor marketing is still not_relevant unless it is directly tied to an active application or interview process.
- Only treat a sender as human if it looks like a real individual or direct recruiter. Team aliases, no-reply mailboxes, newsletters, and system notifications are automated.

Return ONLY valid JSON with these fields:
{
  "classification": "<one of the categories above>",
  "confidence": <0.0-1.0>,
  "company_name": "<extracted company name or null>",
  "sender_role": "<recruiter/hiring_manager/hr/automated/unknown>",
  "key_sentence": "<the most important sentence from the email>",
  "summary": "<1-2 sentence summary>",
  "action_needed": <true/false>,
  "is_automated": <true if from ATS/no-reply, false if from a person>
}
```

### User Prompt Template

```
From: {sender} <{sender_email}>
Subject: {subject}

{body[:4000]}
```

### Changelog

| Date       | Version | Change | Reason |
|------------|---------|--------|--------|
| 2026-03-01 | v1      | Initial prompt with 7 categories | Launch |
| 2026-03-15 | v2      | Added "Important exclusions" block: developer tooling, nuanced rejection phrases, recruiter conversation signals, promotional recruiting content, human sender heuristics | High false positive rate on GitHub/Vercel/LinkedIn notifications; rejection emails with soft language being classified as job_update |
| 2026-03-19 | v3      | Switched from Claude Haiku to GPT-4o-mini | Consolidate on OpenAI (free credits) |

---

## 2. Email Draft Writer

**Service:** `backend/services/draft_writer.py`
**Model:** `gpt-4o`
**Purpose:** Generate context-aware email drafts for follow-ups, introductions, replies, and thank-you notes.
**Max tokens:** 500

### System Prompt

```
You are an expert at writing professional job search emails.
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
}
```

### Draft Type Prompts

| Type | Prompt Template |
|------|----------------|
| follow_up | Write a polite follow-up email for a job application. It's been {days_since} days since the last activity. Keep it brief and professional. |
| introduction | Write an introduction/networking email to {contact_name} at {company}. The user is interested in the {role} position. Make it warm but professional. |
| reply | Write a reply to the most recent message in this email thread. Be helpful and responsive. |
| thank_you | Write a thank-you email after an interview at {company} for the {role} position. |

### Changelog

| Date       | Version | Change | Reason |
|------------|---------|--------|--------|
| 2026-03-08 | v1      | Initial prompt with 4 draft types | Sprint 14 launch |
| 2026-03-19 | v2      | Switched from Claude Sonnet to GPT-4o | Consolidate on OpenAI |

---

## 3. Resume Tailor

**Service:** `backend/services/resume_tailor.py`
**Model:** `gpt-4o`
**Purpose:** Tailor existing resume content for a specific job application without inventing experience.
**Max tokens:** 4000

### System Prompt

```
You are an expert resume writer who tailors existing resumes for specific job applications.

CRITICAL RULES:
1. NEVER invent, fabricate, or add experiences, skills, or qualifications the candidate doesn't have
2. Only reframe, reorder, and emphasize existing content to better match the job description
3. Use keywords from the job description where they genuinely match existing experience
4. Reorder bullet points to lead with most relevant experience
5. Adjust phrasing to mirror the job posting's language where truthful
6. Keep the same overall structure and length

Return ONLY valid JSON:
{
  "tailored_text": "<the tailored resume text>",
  "changes_summary": "<bullet list of changes made and why>",
  "match_improvements": "<specific keywords/phrases aligned with the job>"
}
```

### User Prompt Template

```
Tailor this resume for the specified job.

Target company: {company}
Target role: {role}
Candidate's verified skills: {skills}

--- ORIGINAL RESUME ---
{original_text}

--- JOB DESCRIPTION ---
{job_description}

Remember: DO NOT invent any new experience or skills. Only reframe and reorder existing content.
```

### Changelog

| Date       | Version | Change | Reason |
|------------|---------|--------|--------|
| 2026-03-14 | v1      | Initial prompt with integrity rules | Sprint 20 launch |
| 2026-03-19 | v2      | Switched from Claude Sonnet to GPT-4o | Consolidate on OpenAI |

---

## 4. Resume Parser

**Service:** `backend/services/resume_parser.py`
**Model:** `gpt-4o-mini`
**Purpose:** Extract structured profile data (skills, education, experience) from resume text.
**Max tokens:** 2000

### Prompt (single message, no system prompt)

```
Extract structured information from this resume. Return ONLY valid JSON with these fields:
- skills: list of technical skills (e.g. ["Python", "React", "SQL"])
- education: list of objects with "institution", "degree", "field", "year"
- experience_years: estimated total years of professional experience (integer)
- tools: list of tools/platforms (e.g. ["Git", "Docker", "AWS"])
- certifications: list of certification names

Resume text:
{text[:8000]}
```

### Changelog

| Date       | Version | Change | Reason |
|------------|---------|--------|--------|
| 2026-03-06 | v1      | Initial extraction prompt | Sprint 5 launch |
| 2026-03-19 | v2      | Switched from Claude Haiku to GPT-4o-mini | Consolidate on OpenAI |

---

## 5. Generic Client (Job Extraction / Fallback Classifier)

**Service:** `backend/services/claude_client.py`
**Model:** `gpt-4o`
**Purpose:** Two functions — generic email classification (legacy) and HTML job posting extraction.
**Max tokens:** 500 (classify), 1000 (extract)

### classify_email

System: `Return only valid JSON. No preamble.`
User: Raw email body text.

### extract_job_from_html

System: `Return only valid JSON. No preamble.`
User:
```
Extract job posting information from this HTML content.
Return JSON only with keys: title, company, location, department, description.
If a field is not found, set it to null.

{html[:8000]}
```

### Changelog

| Date       | Version | Change | Reason |
|------------|---------|--------|--------|
| 2026-02-28 | v1      | Initial generic prompts | Phase 1 launch |
| 2026-03-19 | v2      | Switched from Claude Sonnet to GPT-4o | Consolidate on OpenAI |

---

## Model Selection Rationale

| Tier | Model | Use Case | Why |
|------|-------|----------|-----|
| High volume / Low cost | `gpt-4o-mini` | Email classifier, Resume parser | Runs on every email/resume; needs speed + low cost |
| High quality | `gpt-4o` | Draft writer, Resume tailor, Job extraction | User-facing output; quality matters more than cost |

---

## Fallback Behavior

All services have fallback logic when the LLM is unavailable:

| Service | Fallback |
|---------|----------|
| Email classifier | Keyword-based rule engine (REJECTION_PHRASES, INTERVIEW_PHRASES, etc.) |
| Draft writer | Template-based drafts per type (follow_up, introduction, reply, thank_you) |
| Resume tailor | Returns original resume with "unable to generate" message |
| Resume parser | `tech_extractor.extract_tech_stack()` regex-based skill extraction |
| Generic client | Returns `{"classification": "unknown"}` or null fields |
