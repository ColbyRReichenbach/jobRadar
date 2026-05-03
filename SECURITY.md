# Security Model

This document summarizes the main security decisions in AppTrail, the risks they are meant to address, and the areas that still deserve continued hardening work.

## Authentication And Session Design

### Dashboard sign-in

The dashboard uses Google OAuth for sign-in. The backend handles the OAuth flow and exchanges the callback for a short-lived application session.

The important design choices are:

- access tokens are kept in memory on the client
- refresh tokens are stored in an HttpOnly cookie
- the OAuth callback completes through a one-time auth code instead of handing a JWT back in the URL

This reduces the usual browser risks around token leakage through local storage, query strings, browser history, and referrer headers.

### Extension authentication

The Chrome extension authenticates with a per-user API key rather than reusing the dashboard session. Raw keys are shown once, stored locally in the extension, and hashed in the database.

That keeps the browser extension on a separate trust path from the dashboard while still allowing the backend to tie requests to a real user account.

## Token Handling

AppTrail uses three auth artifacts:

- access JWTs for API requests
- refresh tokens for silent re-authentication
- short-lived auth codes for the post-OAuth handoff

Revocation and one-time code storage are backed by Redis, with local in-memory fallbacks so development does not depend on a full cloud stack.

## Secrets And Stored Credentials

Secrets are expected from environment variables. They are not meant to live in the repo or in client code.

Sensitive credentials include:

- `JWT_SECRET`
- `OPENAI_API_KEY`
- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY`
- `HUNTER_API_KEY`
- `SERPAPI_KEY`
- Twilio credentials when SMS is enabled

Gmail access and refresh tokens are encrypted before they are written to the database.

## Consent And Data Boundaries

AppTrail has explicit consent controls for:

- AI processing
- third-party enrichment

That matters because the product does not only store user-entered data. It can also read connected Gmail content and call external enrichment services. Consent needs to be part of the implementation, not just the policy language.

The current system enforces those choices in the product flow rather than treating them as front-end decoration.

## Browser And Extension Boundary

The dashboard and extension have different security concerns.

### Dashboard

- React escapes rendered content by default
- sessions are not persisted in browser storage
- CORS is limited to approved local origins, preview deployments, and extension origins
- the app uses a restrictive content security policy for extension pages and a controlled client origin model for the dashboard

### Extension

- content scripts are scoped to job-related pages and supported ATS patterns
- the extension stores its own API key and local queue state in extension storage
- detection and extraction logic do not rely on `eval` or unsafe HTML insertion
- background and side-panel flows validate message types and known paths

## API And Request Protection

The backend uses:

- typed validation with Pydantic
- request-size limits
- rate limiting with Redis-backed storage and local fallback
- URL validation for job parsing
- structured logging with redaction of sensitive values

Those controls are there to protect both the product surface and the external integrations it depends on.

## Observability And Auditability

Security is easier to maintain when failures are visible. AppTrail now exposes:

- structured request logging
- Prometheus-compatible metrics
- AI task metrics and fallback counts
- generated prompt inventory for internal review
- extraction reports and audit views in the product

This is not only an operations concern. It also makes product behavior easier to trace when users question how a classification, extraction, or recommendation happened.

## Current Risk Areas Worth Continuing To Improve

These are the main areas I would keep pushing on:

- tighter CSP and header enforcement at the deployment edge
- scheduled dependency and container image review
- periodic review of extension host permissions as supported ATS patterns evolve
- clearer operational playbooks for incident response and secret rotation
- stronger admin-only visibility around internal metrics and audit endpoints if the product grows beyond a small trusted team

## Bottom Line

The security model in AppTrail is not built around a single control. It is layered:

- separate auth paths for dashboard and extension
- short-lived browser sessions
- encrypted connected-service tokens
- consent-aware processing
- request validation and rate limiting
- observable background behavior

That is the right shape for a product that touches inbox data, browser activity on job pages, and third-party enrichment.
