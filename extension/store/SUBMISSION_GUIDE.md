# Chrome Web Store Submission Guide

This guide covers the remaining manual steps to publish the AppTrail extension.

## Before You Start

Make sure you have:

- a Chrome Web Store developer account
- a public privacy policy URL
- the packaged extension zip
- store screenshots and promo tiles converted to PNG

## Packaging

Build the full Chrome Web Store submission bundle with:

```bash
bash scripts/release/package_chrome_webstore.sh
```

The script runs the extension release checks, builds the runtime extension ZIP, exports PNG store assets, validates the generated package, and writes the submission bundle to `dist/chrome-webstore/`.

For runtime-only packaging, use:

```bash
bash scripts/package-extension.sh
```

Confirm that the runtime ZIP contains extension files only. The `store/` working assets should not be included in the runtime ZIP.

## Required Store Assets

The submission package script converts the SVG store assets in `extension/store/` to PNG before submission.

Recommended output set:

- icon: `extension/images/icon-128.png`
- screenshots: 1280x800 PNG exports of the five store screenshots
- promo tile: `promo-small-440x280.png`
- optional larger promo tiles if you want richer store presentation

If real product screenshots are available, use them instead of mock visuals. They are more credible and convert better.

## Store Form Values

Use [listing.md](listing.md) for:

- name
- short description
- detailed description
- category
- language
- tags

Use [privacy-fields.md](privacy-fields.md) for:

- single purpose statement
- data collection disclosures
- limited-use certification copy
- remote-code declaration
- permission justifications
- test instructions

## Privacy Form

Use:

- privacy policy URL: `https://apptrail.com/privacy`
- homepage/support URL: `https://apptrail.com`

Recommended single-purpose statement:

```text
Capture job listings from supported career pages and save them to the user's AppTrail pipeline.
```

## Permission Explanations

### `activeTab`

Needed to read structured job details from the page the user is currently viewing.

### `sidePanel`

Needed to display the AppTrail side panel next to the current tab.

### `storage`

Needed to store the user's API key until they clear it, local queue data, opt-in tracking settings, and lightweight extension state.

### `scripting`

Needed to inject extraction logic on supported sites that rely on client-side navigation.

### `tabs`

Needed to read the active tab URL and determine whether the page matches a supported job or career pattern.

## Host Permission Explanation

The extension needs:

- the AppTrail backend host for sync
- development-only localhost hosts in the source manifest; the release packaging script strips them from the Chrome Web Store runtime zip
- supported ATS and career-page host access so it can read job pages; broad third-party job boards are manual or user-initiated by default

## Submission Checklist

- run `bash scripts/release/run_beta_readiness_checks.sh`
- package the release zip
- export the store images to PNG
- upload the extension
- paste the listing copy
- add the privacy policy URL
- explain the permissions
- fill the privacy fields from `privacy-fields.md`
- confirm the release scope in `beta-scope.md`
- submit for review

## After Approval

1. Add the published Web Store URL to the dashboard environment as `VITE_CHROME_EXTENSION_URL`.
2. Update any product links that should point to the live store listing.
3. Keep `listing.md` and `privacy-policy.md` in sync with the published listing.
