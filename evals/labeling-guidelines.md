# Email Classifier Labeling Guidelines

These guidelines make the email classifier eval reproducible.

## Binary Decision

`expected_job_related=true` when the email is directly tied to a job search workflow:

- application confirmation
- application status update
- interview scheduling
- assessment or form action
- offer
- rejection
- recruiter or hiring-manager conversation

`expected_job_related=false` when the email is not directly tied to an active opportunity:

- newsletters
- product updates
- GitHub, Railway, Vercel, billing, or security notifications
- community events
- generic career advice
- marketing from recruiting-adjacent vendors

## Classification Labels

- `job_update`: application received, under review, candidate portal update, next-stage status update.
- `interview_request`: schedule screen, technical interview, onsite, final round, hiring-manager chat.
- `action_item`: assessment, references, background check, form completion, availability confirmation.
- `offer`: written offer, compensation details, benefits package, offer letter.
- `rejection`: not selected, not moving forward, role filled, pursuing other candidates.
- `conversation`: human recruiter or hiring manager message that is not one of the above categories.
- `not_relevant`: unrelated or recruiting-adjacent but not tied to an opportunity.

## Stage Labels

- `applied`: application confirmation or status update.
- `interview`: interview scheduling or interview-stage message.
- `assessment`: assessment, form, references, background check, or explicit action item.
- `offer`: offer-stage message.
- `rejection`: rejection-stage message.
- `follow_up`: human recruiter/hiring-manager conversation without a clearer stage.
- `unknown`: not job-related or insufficient information.

## Tie-Breaking

- Prefer the most advanced concrete stage in the message.
- If an email asks the user to schedule an interview, label it `interview`, not `assessment`.
- If an email says "not moving forward" anywhere, label it `rejection`.
- If an automated no-reply email confirms receipt, label it `job_update` and stage `applied`.
- If the sender is a person and the content is conversational but not stage-specific, label it `conversation` and stage `follow_up`.

## Data Rules

- Use sanitized examples only.
- Use `.example` domains.
- Do not include real candidate names, personal email addresses, OAuth payloads, API keys, or raw Gmail identifiers.
- Golden dataset changes require a dataset version bump.
