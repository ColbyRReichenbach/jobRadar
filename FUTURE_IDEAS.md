# Future Ideas — Parking Lot

Ideas that are interesting but not in the current build plan. Revisit as the product matures.

---

## Application Auto-Fill
- If we have the user's parsed resume/profile, we could pre-fill common ATS fields (name, email, phone, LinkedIn, education, work history)
- Greenhouse, Lever, Workday all have similar form structures
- Extension could detect the form and offer to fill known fields
- **Why deferred**: We want humans to apply — not bots. Auto-fill is a slippery slope to auto-submit. Need to think carefully about where the line is so we don't contribute to the recruiter spam problem.

## Auto-Apply / One-Click Apply
- Explicitly NOT building this. Goes against our two-sided value philosophy.
- Recruiters already hate getting hundreds of low-effort bot applications.
- Our competitive advantage is that AppTrail users are organized, intentional applicants — not spray-and-pray.

## Voice-to-Text Interview Notes
- After each interview, offer voice recording → transcription → structured notes
- "What questions did they ask?" "What went well?" "What would you change?"
- Feeds into interview prep for next rounds and similar companies

## AI Mock Interviewer
- Practice interviews with AI based on company question patterns
- Uses knowledge graph data: "Stripe tends to ask system design, here's a practice question"
- Feedback on answers: clarity, structure, technical accuracy

## LinkedIn Profile Optimization
- Compare LinkedIn profile against job descriptions user is targeting
- "Your headline says X but most Data Analyst roles search for Y"
- Suggest profile changes that align with target umbrella roles

## Referral Network Discovery
- Cross-user (opt-in): "A user in your network works at Company X — would you like an intro?"
- Very long-term, requires scale and trust
- Could partner with LinkedIn data if API access becomes available

## Browser-Based Job Board Aggregator
- Instead of relying on SerpAPI, build our own job board scraper
- Aggregate from LinkedIn, Indeed, Glassdoor, company career pages
- Deduplicate by company + role + location
- Would reduce API costs and give us more control

## Negotiation Intelligence
- Track offer amounts across users (anonymized, opt-in)
- "The average accepted offer for this role at this company is $X"
- AI-assisted negotiation email drafts
- Counter-offer strategy based on market data

## Application Withdrawal Automation
- When user accepts an offer, prompt: "Want to withdraw from your other active applications?"
- Draft professional withdrawal emails for each active pipeline item
- One-click send (or review + send)

---

*Created: 2026-03-09*
