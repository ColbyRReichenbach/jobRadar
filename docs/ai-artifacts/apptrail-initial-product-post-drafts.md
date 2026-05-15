# AppTrail Initial Product Post Drafts

Working goal: introduce AppTrail as a product first, then set up follow-up technical posts on Gmail classification and evidence-grounded resume tailoring. The tone should be product-led, but the substance should make it obvious that the interesting work is in the systems behind the app.

## Recommended Draft: Product-System Version

I built AppTrail because my job search started breaking in the exact way I think a lot of recent grads recognize.

Not because I could not make a spreadsheet. I made plenty of them.

The problem was that the job search does not actually live in a spreadsheet. It lives across company career pages, LinkedIn, Greenhouse, Lever, Workday, job boards, Gmail, recruiter threads, calendar invites, notes, follow-ups, saved links, and a bunch of half-remembered context you only realize you lost when you need it again.

I would apply to a role, forget to update the tracker, get an application email three days later, lose the recruiter reply under job alerts, then try to remember which version of my resume I used. A month later the spreadsheet would be stale enough that starting over felt easier than cleaning it up.

So I started building AppTrail: a job-search operating system for people who need the process to have memory.

The simple version is that AppTrail gives you one workspace for:

- pipeline tracking
- Gmail sync
- recruiter conversations
- network/contact management
- interview tracking
- job search
- Chrome extension job capture
- resume/profile tooling
- opportunity research through Radar
- analytics and audit views

But the part I cared about most was not making a prettier tracker.

It was making the pages talk to each other.

That is where the product starts to feel different from a spreadsheet.

If you are browsing a role, the Chrome extension detects the job page, extracts the company, role, location, salary, source URL, and other metadata, then lets you save it without leaving the page. It has specific handling for common ATS surfaces like Greenhouse, Lever, Workday, Ashby, SmartRecruiters, iCIMS, Jobvite, BambooHR, Rippling, and generic career pages. The goal is not magic. The goal is removing the tiny bit of friction that causes trackers to rot.

Once a role is in the pipeline, it is not just a row. It can connect to contacts, source links, Gmail events, interviews, notes, and warm paths. If I have emailed someone at the company before, the job detail page can surface that as a warm connection instead of making me manually search my inbox.

Gmail is where the product gets more interesting.

AppTrail does not treat every email as the same kind of object. It separates application lifecycle emails from conversational recruiter/networking emails because they drive different product behavior.

An application confirmation, rejection, interview request, or offer belongs near the application workflow.

A recruiter reply belongs in conversations.

A job alert or marketing digest usually belongs nowhere.

That distinction matters because the downstream actions are different. An application email might update an application status or suggest adding a missing role to the pipeline. A conversation email might suggest adding the sender to your network. An interview email might become a calendar/interview suggestion.

The product flow I wanted was:

Find a role -> save it.

Apply -> let Gmail attach the follow-up emails.

Get an interview email -> suggest adding it to Calendar.

Talk to a recruiter -> suggest adding them to Network.

Look at an application -> see related emails, interviews, contacts, and source links.

Not because the app should silently do everything for you, but because it should notice the things you are probably about to type in manually.

That became a core product principle: AppTrail suggests, dedupes, links evidence, and asks for confirmation before creating important user-facing records.

For example, if Gmail finds an application-related email for a company that is not in your pipeline, the Inbox can show a suggested application. Accepting it creates or links the pipeline role, attaches the source emails, stores the decision, and records the evidence. If it is already a duplicate, the dedupe layer can link to the existing role instead of creating another copy.

If a conversation comes from a real human sender who is not already in your contacts, the Conversations and Network surfaces can suggest adding that person. Accepting the suggestion promotes the sender into a contact and links their previous emails.

If an email is classified as an interview request, Calendar can show it as an interview suggestion. Accepting it creates an interview record with whatever date, duration, interviewer, and location/link the system could extract, while still letting the user review the details.

Notifications are built around the same idea. They are not just generic banners. They carry action URLs back to the right surface: an email thread, a conversation, a contact, a calendar interview, a pipeline role, or a Radar report. The notification is supposed to move you to the next useful decision, not just tell you something happened.

Under the hood, this turned into a real product engineering problem.

The dashboard is React/Vite. The backend is FastAPI with Postgres, Redis, Celery workers, and SQLAlchemy/Alembic. Gmail polling, calendar sync, source-link processing, search indexing, Radar runs, follow-up checks, and digest work all run outside the main request path. The codebase has over 170 backend route declarations, 60+ database models, 50+ migrations, and a growing set of tests and audit artifacts.

The AI layer is deliberately not “LLM everywhere.”

For Gmail, local classification runs first. It decides whether a message should be filtered, treated as a conversation, attached to the application inbox, or sent to review. It records traces, matched features, confidence, route/subtype metadata, and preflight status. LLM adjudication is reserved for ambiguous cases that pass consent, redaction, prompt-injection, and size checks. If preflight fails, nothing gets sent to the model.

That Gmail classifier became the first engineering story I want to write about. I manually labeled real inbox rows, ran a TF-IDF + Logistic Regression model, saw 94% accuracy on a random split, and still decided not to ship it because source/account grouped evaluation showed it would fail on new inbox distributions. The production choice stayed more conservative: heuristics in production, LR in shadow, LLM only as a gated second pass.

Resume tooling exposed a different problem.

With Gmail, the big tradeoffs were cost, latency, privacy, and side effects.

With resume generation, the big tradeoff is factuality.

A model can make a resume sound better by quietly stretching the truth. It can claim you used a model, framework, metric, or business domain that sounds adjacent to your work but is not actually what you did. For a user-facing product, that is not an acceptable failure mode.

So the resume direction shifted. Instead of trying to fully rewrite resumes from a prompt, AppTrail is moving toward evidence-grounded assistance: ingest project/work evidence, retrieve the parts that match a job description, show which facts support which requirements, suggest bullets from verified evidence, and expose unsupported gaps instead of inventing fit.

Radar is the more experimental layer. The idea is to track companies, roles, sources, and opportunity signals over time. Some of that can come from internal product data, like saved applications, Gmail signals, source links, and user preferences. Some of it can come from research runs, but those runs need to be bounded: planned steps, fetched documents, extracted evidence, ranked evidence, report diffs, recommended actions, verification, and traceability. I do not want an unbounded agent roaming around making claims. I want a research workflow that can explain what it found and why it thinks it matters.

That is the theme across the whole product.

The interesting work is not getting AI to produce text.

It is deciding:

- what the system is allowed to see
- what it is allowed to create
- when it has to ask the user
- what evidence gets attached
- how duplicates are handled
- what can mutate product state
- how a wrong decision gets corrected later

AppTrail is still a work in progress. I am not positioning it as a polished public launch yet. I am still working through product kinks, deployment details, quality gates, and which features should be automatic versus assisted.

But I am going to start sharing the engineering behind it.

The next post will be about Gmail classification: how I went from heuristics, to manual labels, to a model that looked great under the wrong split, to a more honest production decision.

Then I will write about resume generation and why I shifted from “rewrite the whole resume” toward evidence-grounded suggestions.

The broader lesson so far is simple:

Applied AI product work is not just model choice.

It is product control.

The hard question is not “can the model answer?”

It is “what should the product do when the model is wrong?”

## Code-Read Workflow Map

This section is not meant to be posted directly. It is the codebase-grounded map behind the draft above.

| Product surface | What it owns | How it connects |
| --- | --- | --- |
| Pipeline | Saved/applied/interviewing/offer/rejected jobs | Receives jobs from manual add, Chrome extension, job search saves, and Gmail application suggestions. Job detail can show emails, contacts, interviews, and warm connections. |
| Chrome extension | Job capture from browser pages | Detects common ATS/job pages, extracts job metadata, and sends reviewed captures into the backend. |
| Inbox | Application lifecycle and job-related updates | Shows non-conversation Gmail events, suggested applications, pipeline checks, user corrections, and interview creation from email. |
| Conversations | Recruiter/networking threads | Shows conversation-type Gmail events, reply drafting/sending, network suggestions, and correction paths back to inbox/filter. |
| Network | Contacts and relationship context | Accepts contacts from conversation-derived suggestions, shows email/application context, and supports warm-path discovery for applications. |
| Calendar | Interviews and prep workflow | Creates interviews manually, from Gmail suggestions, or calendar sync; links interviews to applications when available. |
| Notifications | Cross-surface action routing | Alerts carry action URLs back to inbox, conversations, calendar, pipeline, Radar, or related entities. |
| Job Search | Search and save-to-pipeline | Runs search/match previews, saves roles with duplicate checks, and can start source/Radar tracking from a result. |
| Source Intelligence | Safe public source extraction | Processes raw private URLs from Gmail/applications into sanitized public source intelligence when consent allows. |
| Radar | Opportunity signals and research workflows | Uses internal signals and optional bounded research runs with persisted steps, evidence, reports, diffs, actions, and feedback. |
| Profile/Resume | User profile and resume tooling | Stores profile/preferences/resume text; current resume direction is shifting toward evidence-grounded assistance. |
| Audit/Admin | Trust and debugging surfaces | Classifier audit, extraction reports, AI Ops, sync audit, traces, and generated artifacts support debugging and evaluation. |

Important code-backed product mechanics:

- Gmail sync skips obvious noise and user-blocklisted sender domains before storage.
- Classifier results that should not be stored still create classification traces.
- Application updates only mutate status when route/subtype policy allows it and an application match exists.
- Suggested applications group unmatched Gmail application events by company/role and require accept/dismiss.
- Network suggestions only come from conversation emails from likely human senders and require explicit acceptance.
- Interview suggestions come from `interview_request` Gmail events and require review before calendar creation.
- Action candidates store source, target, dedupe state, confidence, policy decision, and evidence.
- Alerts are deduped and preference-aware, and can route the user directly to the relevant workflow.
- Radar research mode is a bounded graph workflow, not an open-ended autonomous agent.

## Draft 1: Main LinkedIn Post

I built AppTrail because my job search got too messy to manage honestly.

Not messy in a dramatic way. Messy in the normal recent-grad way.

Applications spread across company career pages, LinkedIn, Greenhouse, Lever, Workday, and random job boards. A spreadsheet I kept rebuilding because I would stop updating it after a few weeks. Recruiter emails buried under newsletters and job alerts. Interview details sitting in Gmail. Follow-ups I meant to send, then forgot. Roles I applied to but could not remember where I found them.

At some point I realized the problem was not that I needed a better spreadsheet.

I needed an operating system for the job search.

So I started building AppTrail.

AppTrail is a job-search OS for people who are applying to enough roles that the process starts to break down. It brings the core workflow into one place:

- a pipeline for saved, applied, interviewing, offer, and rejected roles
- Gmail sync for application updates, recruiter conversations, and interview messages
- a conversation inbox for recruiter and networking threads
- a network/contact view tied back to companies and applications
- interview tracking, notes, and calendar sync
- job search and browser capture through a Chrome extension
- profile and resume tooling
- analytics and audit views for understanding what the system is doing
- Radar, an experimental research layer for surfacing opportunity signals and next actions

Anyone can make a job tracker. The part I cared about was making it behave like a connected product instead of a prettier spreadsheet.

That meant a lot of engineering behind the scenes.

The Chrome extension detects supported job pages, extracts job details, opens a side panel for review, and saves the role without forcing a context switch. It supports common ATS surfaces like Greenhouse, Lever, Workday, Ashby, SmartRecruiters, iCIMS, and others, with fallbacks for generic career pages. The goal is simple: if saving a job is annoying, users will not do it.

The Gmail layer polls connected inboxes, classifies new messages, links application emails to the right role when it can, separates recruiter conversations from lifecycle updates, and records classifier traces so the system can be audited later. This ended up being one of the more interesting applied ML problems in the product. The first version looked good until I manually labeled real inbox data and found that job-board alerts were being mistaken for application updates. That led to a route-first classifier, privacy preflight checks, and a lot of evaluation work.

The backend is FastAPI, Postgres, Redis, and Celery. Background workers handle Gmail polling, follow-up checks, ATS/source verification, search indexing, weekly digest work, and Radar runs. The dashboard is a React/Vite app built more like a workstation than a landing page: pipeline, inbox, conversations, network, calendar, job search, Radar, analytics, profile, and settings.

I also spent a lot of time on the boring-but-important parts:

- Google OAuth with a one-time auth-code exchange
- access tokens kept out of local storage
- Gmail tokens encrypted at rest
- per-user extension API keys with narrower scope than dashboard sessions
- consent-aware AI and enrichment paths
- user-scoped search/retrieval
- AI call ledgers, model cards, eval artifacts, and admin-only audit surfaces
- deterministic rules first where a wrong model decision could mutate product state

That last point became a theme.

For Gmail classification, the tradeoff was latency, cost, and side-effect risk. It is better to keep most classification local and deterministic, then reserve LLM adjudication for ambiguous cases that pass redaction and preflight.

For resume generation, the tradeoff was different. Latency and cost still matter, but factuality matters more. I would rather wait a few more seconds and spend a little more if it means the product does not create a fake resume. That pushed the resume feature away from “rewrite my resume automatically” and toward an evidence-grounded assistant: retrieve supported facts from the user's real work, suggest honest bullets, and show unsupported gaps instead of inventing fit.

That is the part I want to write about next.

AppTrail is still a work in progress. I am not presenting this as a polished public launch yet. I am still working through product kinks, deployment details, and quality gates. But the engineering behind it has become the most interesting part of the build.

Over the next few posts I am going to break down the applied AI work behind the product:

1. Gmail classification: why a 94% random-split model was not good enough to ship.
2. Resume tailoring: why prompt-only resume rewriting is risky, and how evidence-grounded retrieval changes the product.
3. Radar: how I am thinking about source-grounded opportunity research without turning it into an unbounded agent.

The broader lesson so far: applied AI is not just picking the strongest model. It is deciding what the product is allowed to do when the model is wrong.

That is where the real engineering starts.

## Draft 2: More Personal / Less Technical

I built AppTrail because I got tired of losing track of my own job search.

I was applying through company sites, LinkedIn, Greenhouse, Workday, and random job boards. I had a spreadsheet that was useful for about three weeks, then stale enough that I wanted to start over. My Gmail inbox had application confirmations, rejections, job alerts, recruiter replies, interview links, and unrelated noise all mixed together.

The frustrating part was not any one task. It was the fact that the whole process had no memory.

Where did I apply?
Who replied?
Did I follow up?
Was that job still active?
Which version of my resume did I use?
Was that recruiter conversation tied to a specific application?

So I started building AppTrail: a job-search OS for people who need more than a spreadsheet.

The product brings the job search into one workspace:

- track roles through saved, applied, interviewing, offer, and rejected stages
- save jobs from the browser with a Chrome extension
- sync Gmail and separate real application updates from job-board noise
- keep recruiter conversations in one place
- manage contacts and warm paths
- track interviews, notes, and calendar events
- search for roles and save them into the pipeline
- use profile/resume data to support matching and tailoring
- experiment with Radar, a research layer for opportunity signals and next actions

What made the build interesting was not the UI. It was the systems work behind it.

Gmail classification had to be careful because a wrong label can change product state. A recruiter reply routed to “ignore” is a missed opportunity. A job alert routed to “application update” pollutes the pipeline. That pushed me toward a route-first classifier, manual labeling, evals, and a conservative LLM fallback only for ambiguous redacted cases.

Resume tailoring had a completely different failure mode. The risk was not latency. The risk was hallucination. A normal prompt can rewrite a resume in a way that sounds great but quietly claims tools, models, or business domains the person did not actually use. That pushed the feature toward evidence-grounded suggestions instead of automatic rewriting.

Radar is the next frontier: can the product research opportunities and next actions without becoming an unbounded agent that makes unsupported claims?

That is the thread I am going to share over the next few posts.

AppTrail is still in progress, but the build has become a useful case study in applied AI product engineering:

Where should the model be allowed to decide?
Where should deterministic logic own the control path?
When is “I am not sure” the right product behavior?
What evidence would make a feature safe enough to ship?

Next post: the Gmail classifier, and why the model that hit 94% accuracy was not the model I trusted.

## Draft 3: More Technical / Engineering-Forward

I have been building AppTrail, a job-search OS for tracking applications, Gmail updates, recruiter conversations, contacts, interviews, job search, resume work, and opportunity research in one place.

The product started from a very ordinary pain point: I was applying to too many roles to keep the process straight in a spreadsheet.

But the interesting part has been the systems work underneath it.

The current architecture has three main entry points:

- React/Vite dashboard for the day-to-day workflow
- Chrome extension for browser-based job capture
- FastAPI backend with Postgres, Redis, and Celery workers for sync, classification, enrichment, search, and scheduled jobs

The dashboard is built around the actual job-search loop:

- Pipeline: saved/applied/interviewing/offer/rejected roles
- Inbox: application lifecycle emails and job-related updates
- Conversations: recruiter and networking threads
- Network: contacts, duplicates, outreach status, and email context
- Calendar: interviews, notes, calendar sync, and prep context
- Job Search: provider-backed search, match preview, and save-to-pipeline
- Radar: internal signals plus a research-report workflow for opportunity discovery
- Profile/Resume: parsed profile data, preferences, and resume tooling
- Admin/eval surfaces: classifier audit, extraction reports, AI Ops, and source intelligence

The Chrome extension handles the part most trackers ignore: capture at the moment the user is already looking at a role. It detects supported ATS/job pages, extracts job data through layered extraction, opens a side panel for review, and saves the role back to AppTrail. It also has platform detection, offline queueing, visit tracking, and submission detection.

The backend owns the side effects. Gmail polling, source verification, search indexing, follow-up checks, Radar dispatch, and weekly digest work all run outside the request path. That separation matters because the dashboard should not become responsible for long-running product behavior.

The AI layer is intentionally not “LLM everywhere.”

For Gmail, local deterministic classification runs first. The system decides route and subtype, records traces, and only considers LLM adjudication for ambiguous cases after preflight and redaction. If the preflight fails, nothing is sent to the model.

For resume tailoring, I started with prompt-only rewriting and found the failure mode was not bad writing. It was believable overclaiming. The model can make a resume sound aligned by quietly filling gaps. So the product direction shifted toward evidence-grounded suggestions: retrieve verified project facts, cite the evidence, suggest bullets, and show unsupported requirements.

For Radar, I am treating research as a bounded workflow rather than an autonomous agent. It has trackers, persisted runs, step traces, source/evidence persistence, report writing, verification, diffs, actions, and feedback.

The thing I keep learning is that the hard part is not getting a model to produce text.

The hard part is product control:

- What is the model allowed to see?
- What is it allowed to decide?
- What happens when it is uncertain?
- What gets persisted?
- What can mutate user state?
- How do you audit the decision later?

That is what AppTrail has become for me: a real product surface for testing applied AI, data engineering, retrieval, workflow automation, and evaluation under practical constraints.

I am going to start writing through the build in public.

First up: the Gmail classifier. It is a good example of why random-split accuracy can be misleading and why sometimes the best production decision is not the model with the highest easy metric.

## Draft 4: Short Announcement

I have been building AppTrail, a job-search OS for people who are applying to enough roles that spreadsheets start breaking down.

It combines:

- application pipeline tracking
- Gmail sync and classification
- recruiter conversation management
- contact/network tracking
- interview notes and calendar sync
- Chrome extension job capture
- job search and source intelligence
- resume/profile tooling
- Radar, an experimental opportunity research layer

The reason I built it is simple: I was tired of losing track of applications, recruiter emails, follow-ups, and job pages across inboxes, tabs, and spreadsheets.

The reason I kept building it is more interesting: it became a real applied AI systems problem.

Gmail classification is not just a label problem because wrong labels can mutate application state.

Resume tailoring is not just a writing problem because polished output can still hallucinate a person's experience.

Opportunity research is not just an agent problem because source quality and verification matter more than autonomous behavior.

I am still working through product and deployment kinks, so this is not a broad public launch yet. But I am going to start sharing the engineering behind the build.

Next post: how I evaluated the Gmail classifier, why a 94% accuracy model was misleading, and why the production decision ended up being more conservative.

## Carousel / Thread Outline

### Slide 1
I built a job-search OS because spreadsheets kept failing me.

### Slide 2
The problem was not tracking one application.
The problem was keeping the whole search connected:

- applications
- Gmail
- recruiter threads
- contacts
- interviews
- job pages
- follow-ups
- resume versions

### Slide 3
AppTrail is the workspace I wanted:

- Pipeline
- Inbox
- Conversations
- Network
- Calendar
- Job Search
- Resume/Profile
- Radar

### Slide 4
The Chrome extension captures jobs where they happen.

It detects supported job pages, extracts job details, opens a side panel, and saves the role without forcing a context switch.

### Slide 5
Gmail sync turns inbox chaos into product signals.

Application confirmations, rejections, recruiter messages, interview links, and job alerts all need different product behavior.

### Slide 6
The first ML lesson:

classification accuracy is not the product metric.

The real question is:
what happens downstream when the classifier is wrong?

### Slide 7
Resume tailoring exposed a different tradeoff.

For Gmail, latency and side effects mattered most.
For resumes, factuality mattered more.

A fake polished resume is worse than a slower honest assistant.

### Slide 8
So the product direction shifted:

not “generate my resume”

but:

“show me what my real work supports, suggest bullets, and show unsupported gaps.”

### Slide 9
Radar is the next hard feature:

can the product research opportunities and next actions without becoming an unbounded agent?

### Slide 10
I am going to write through the build:

1. Gmail classification
2. Evidence-grounded resume tailoring
3. Radar and source-grounded opportunity research

The theme: applied AI is product control, not just model choice.

## Safe Claims To Use

- AppTrail is a work-in-progress job-search OS, not a polished public launch yet.
- The dashboard has pipeline, inbox, conversations, network, calendar, job search, Radar, analytics, profile, settings, and admin/eval surfaces.
- The Chrome extension detects and extracts jobs from supported ATS/job pages and saves them to the backend.
- Gmail sync/classification is implemented with deterministic routing, traces, and bounded LLM adjudication for ambiguous preflight-safe cases.
- Resume tailoring exists in the product, and the current research direction is shifting it toward evidence-grounded suggestions instead of automatic rewriting.
- Radar has internal signal behavior and a research-report workflow, but broad product claims should stay careful because source quality and verification are still active work.
- The backend uses FastAPI, Postgres, Redis, Celery workers, Google OAuth, encrypted Gmail tokens, and per-user extension API keys.

## Claims To Avoid Or Qualify

- Do not say AppTrail is fully launched publicly unless that becomes true.
- Do not say Radar autonomously finds perfect roles; say it is experimental / research-oriented / bounded.
- Do not say resume tailoring never hallucinates; say the product direction is designed to reduce unsupported claims through evidence grounding and review.
- Do not say Gmail classification is solved; say it is evaluated, conservative, and improving.
- Do not say the job search covers every provider perfectly; it supports layered extraction/search paths and verified-source work is still evolving.
