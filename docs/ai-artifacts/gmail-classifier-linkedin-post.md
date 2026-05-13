# LinkedIn Draft

Sometimes the right AI decision is not "train a bigger model."

I spent the last few cycles rebuilding and evaluating the Gmail classifier inside AppTrail, my job-search workflow product.

The classifier has a deceptively simple job: decide whether an email is noise, a job alert, a recruiter conversation, an application update, or something that needs review.

But the real problem was not just label prediction. It was product routing.

If the system mistakes a job-board promo for an application update, it pollutes the user's workflow. If it filters out a recruiter reply, the user may miss an opportunity. So I treated this as a business-decision system first and an ML system second.

What I did:

- manually reviewed 300+ real Gmail priority rows across two labeling waves
- built route/subtype labels around product behavior, not generic email categories
- found that phrases like "apply" and "onsite" were causing high-confidence false positives
- rewrote the classifier to route first, then assign subtype
- tested TF-IDF + Logistic Regression as a shadow route model
- tested a route-conditioned subtype architecture
- tested synthetic LLM-generated training examples
- reviewed an external Kaggle job-email dataset as a research-only probe

The result:

- route-first heuristics dramatically reduced unwanted stored workflow rows
- LR looked great on random split: 94.2% route accuracy / 91.6% macro F1
- but LR dropped under source/account grouped testing: 55.9% route accuracy / 22.0% macro F1
- route-conditioned subtype models looked promising only when the route was already correct
- synthetic data was schema-valid but still semantically risky without human/critic review

The decision:

Keep heuristics in production.
Keep LR in shadow.
Use LLMs only for ambiguous, preflight-safe adjudication.
Collect more real labels before promoting a learned model.

The lesson:

ML is not always the first place to look. The first place to look is the business decision, the failure mode, the available data, and the cost of being wrong.

That is where applied AI engineering gets interesting: not picking the fanciest model, but building the evidence loop that tells you when a model is actually ready.
