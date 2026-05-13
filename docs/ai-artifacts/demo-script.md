# Demo Script

Date: 2026-05-02
Audience: Product and AI platform review
Target length: 8 to 10 minutes

## 1. Problem

After graduation, job discovery was fragmented across LinkedIn, Greenhouse, Indeed, company sites, email, and personal notes. The hard part was not only tracking applications. The hard part was understanding which companies were moving, what roles were changing, and which skills were becoming important.

## 2. Product

AppTrail centralizes applications, job-related email, contacts, interviews, search, and Opportunity Radar. It turns scattered job-search signals into a governed workspace.

## 3. AI Layer

The AI layer supports:

- classifying job-related emails
- indexing user-owned job/search records
- answering pipeline questions through Copilot
- researching company and role movement through Radar
- measuring AI usage, cost, latency, and quality

## 4. Governance Walkthrough

Open Admin AI Ops and show:

1. telemetry overview for calls, cost, tokens, p95 latency, fallback rate, and failures
2. task-level cost and reliability table
3. run table with model, prompt version, status, latency, tokens, and cost
4. redacted run detail
5. reason-gated full trace access
6. trace access audit log
7. artifacts linked back to model calls
8. model cards and promotion reports

## 5. Decision Story

Use the cost memo:

"If a larger model is 2% better but twice the cost, I would not blindly choose either. I would look at task criticality, false-negative cost, prompt length, latency, and projected traffic. Sometimes the best move is not a smaller model; it is a shorter prompt with the same model."

## 6. Risk Story

Use the risk-control artifact:

"The model never gets to retrieve arbitrary data from the client. The backend scopes records by user, logs model calls, redacts sensitive metadata, and requires admin trace access reasons. I am treating AI as a production system with controls, not a demo prompt."

## 7. Close

The project demonstrates full-stack engineering, data contracts, ML evaluation thinking, cost modeling, risk controls, and production AI governance. The strongest point is not just that the app uses AI. It is that the app records, reviews, and improves AI behavior over time.
