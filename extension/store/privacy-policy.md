# AppTrail Chrome Extension Privacy Policy

Last updated: April 22, 2026

This policy applies to the AppTrail Chrome extension.

## What The Extension Stores

The extension may store:

- the user-scoped API key used to connect to AppTrail
- extracted job details from supported pages
- visit counts for supported career pages when career visit tracking is enabled
- submission detections on supported application-confirmation pages when confirmation detection is enabled
- queued sync events when the browser is offline

## What The Extension Reads

The extension reads page content only on supported job and career-related pages so it can:

- detect whether the current page is a job listing
- extract visible job information
- recognize common application submission pages when the user enables confirmation detection
- support visit tracking on relevant career pages when the user enables career visit tracking

The extension does not monitor general browsing outside those supported pages.

## How The Data Is Used

The extension uses stored and captured data to:

- prefill the side panel
- let the user save a role into AppTrail
- track repeated career-page visits when enabled
- sync saved activity to the user's AppTrail account
- hold data locally until sync succeeds

## How Data Is Shared

The extension sends data only to the AppTrail backend configured by the user. It does not sell data or send browsing information to ad networks.

## Limited Use

The extension uses user data only to provide or improve visible AppTrail features: capturing supported job listings, saving reviewed roles to the user's pipeline, syncing user-approved job-search activity, and supporting opt-in career-page visit or submission-confirmation signals. AppTrail's use of extension data complies with the Chrome Web Store User Data Policy, including the Limited Use requirements.

## Local Storage

Extension data is stored in Chrome extension storage on the user's device. That includes configuration, local queue state, and temporary activity records.

## Security

- the extension stores the API key locally and uses it only for authenticated calls to AppTrail
- the backend stores a hash of the key rather than the raw value
- runtime logic is limited to supported job and career-related pages
- queued activity is sanitized and retried until it is delivered or cleared by the user

## User Controls

Users can:

- disconnect the extension by removing or rotating the API key
- clear the locally stored extension key from the setup screen or side panel
- clear extension storage
- uninstall the extension
- delete synced records from the AppTrail product

## Contact

For privacy questions, contact `privacy@apptrail.com`.
