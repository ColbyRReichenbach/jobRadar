# Chrome Web Store Privacy Fields

Use this file when filling out the Chrome Web Store developer dashboard privacy and permission fields.

## Single Purpose

```text
Capture job listings from supported career pages and save them to the user's AppTrail pipeline.
```

## Data Collection Disclosure

Select only the categories that match the final production behavior:

- Website content: visible job listing text from supported job and career pages, used to prefill the side panel.
- Web history or browsing activity: limited career-page visit and submission-confirmation signals only when the user enables those controls.
- Authentication information: a user-scoped AppTrail API key stored locally in Chrome extension storage until the user clears it or revokes it from dashboard Settings.
- User activity: local queue state for saves and opt-in tracking events while offline.

Do not select unrelated categories such as financial/payment information, health information, or location unless the product behavior changes.

## Limited Use Certification

```text
The extension uses user data only to provide or improve its single purpose: capturing supported job listings and syncing user-approved job-search activity to the user's AppTrail account. AppTrail does not sell extension data, does not use extension data for advertising, and does not transfer extension data except as required to provide the AppTrail service, comply with law, investigate abuse or security issues, or complete a merger/acquisition/sale of assets.
```

## Remote Code

```text
No remote code. The extension executes only code packaged with the extension and enforces an extension page CSP of script-src 'self'; object-src 'self'.
```

## Permission Justifications

### `activeTab`

Needed to temporarily read the current job page when the user invokes AppTrail from the toolbar or side panel.

### `sidePanel`

Needed to show the AppTrail capture and review panel next to the current browser tab.

### `storage`

Needed to store the local API key, extension settings, queued offline sync events, and lightweight opt-in tracking state until the user clears it.

### `scripting`

Needed to inject extraction logic into the active supported job page when user-initiated side-panel capture is required.

### `tabs`

Needed to read the active tab URL and title so the extension can determine whether the page is a supported job or career page.

## Host Permission Justification

```text
The extension requests access to the AppTrail API host for authenticated sync and to supported ATS/career-page hosts so it can extract visible job listing details. Localhost hosts are included only for development builds. Broad third-party job boards such as LinkedIn, Indeed, and Glassdoor are not requested as host permissions and are limited to manual/user-initiated detection paths.
```

## Privacy Policy URL

```text
https://apptrail.com/privacy
```

## Homepage URL

```text
https://apptrail.com
```

## Test Instructions

```text
1. Install the extension package.
2. Open the extension setup page.
3. Enter an AppTrail API key generated from dashboard Settings.
4. Open a supported job page such as Greenhouse, Lever, Ashby, Workday, SmartRecruiters, or Workable.
5. Confirm the side panel opens and extracted job details can be reviewed before saving.
6. Confirm career-page visit tracking and submission detection stay disabled until explicitly enabled in the side panel settings.
7. Confirm the locally stored key can be cleared from the extension and revoked from dashboard Settings.
```
