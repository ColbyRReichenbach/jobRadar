# Extension Beta Scope

This beta is for the AppTrail Chrome extension capture workflow, not the full Source Intelligence system.

## In Scope

- Install the Chrome extension from a packaged build or trusted tester Web Store listing.
- Connect the extension to AppTrail with a user-scoped API key.
- Keep the API key stored locally across browser sessions until the user clears it or revokes it from dashboard Settings.
- Detect supported ATS and career pages.
- Open the side panel and let the user review/edit extracted job details before saving.
- Save reviewed job data to the user's AppTrail pipeline.
- Queue saves locally while offline and retry sync later.
- Keep career-page visit tracking disabled by default.
- Keep application submission detection disabled by default.
- Allow users to enable or disable LinkedIn/manual broad-board extraction controls separately from first-party ATS extraction.
- Avoid automatic extraction or host permissions for LinkedIn, Indeed, and Glassdoor.

## Out Of Scope

- Full shared source-intelligence learning from Gmail or historical application links.
- New source registry tables such as `company_job_sources`, `user_application_links`, `job_postings`, and `application_source_links`.
- Shared source verification, Workday source reuse, provider health dashboards, and admin approval queues.
- Direct-source job search replacement for the existing search provider stack.
- Automatic application submission or auto-apply behavior.
- Direct scraping of LinkedIn or Indeed.

## Release Gate

The extension can be considered controlled-beta ready when:

- `bash scripts/release/run_beta_readiness_checks.sh` passes.
- `bash scripts/release/package_chrome_webstore.sh` produces the runtime ZIP and store submission bundle.
- A real Chrome install smoke test passes against the target backend.
- The public privacy policy URL is live and matches `extension/store/privacy-policy.md`.
- The Chrome Web Store privacy fields match `extension/store/privacy-fields.md`.
