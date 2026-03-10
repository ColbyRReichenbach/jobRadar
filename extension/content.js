// LinkedIn content script — runs on linkedin.com/jobs/view/* only
// Reads DOM data when requested by sidepanel. No backend calls.

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "EXTRACT_LINKEDIN_JOB") {
    const jobData = extractLinkedInJob();
    sendResponse(jobData);
  }
  return true; // keep channel open for async response
});

function extractLinkedInJob() {
  // Try DOM selectors first (PRD §10.7)
  const selectors = {
    title: "h1.job-details-jobs-unified-top-card__job-title",
    company: "div.job-details-jobs-unified-top-card__company-name",
    description: "div.job-details-module__content",
    location: "span.job-details-jobs-unified-top-card__bullet",
  };

  let title = getText(selectors.title);
  let company = getText(selectors.company);
  let description = getText(selectors.description);
  let location = getText(selectors.location);

  // Fallback to JSON-LD if DOM selectors fail
  if (!title) {
    const jsonLd = extractJsonLd();
    if (jsonLd) {
      title = jsonLd.title || title;
      company = jsonLd.company || company;
      description = jsonLd.description || description;
      location = jsonLd.location || location;
    }
  }

  return {
    title: title || null,
    company: company || null,
    description: description || null,
    location: location || null,
    source: "linkedin",
  };
}

function getText(selector) {
  const el = document.querySelector(selector);
  return el ? el.textContent.trim() : null;
}

function extractJsonLd() {
  const scripts = document.querySelectorAll(
    'script[type="application/ld+json"]'
  );
  for (const script of scripts) {
    try {
      const data = JSON.parse(script.textContent);
      if (data["@type"] === "JobPosting") {
        return {
          title: data.title || data.name,
          company: data.hiringOrganization?.name,
          description: data.description,
          location: data.jobLocation?.address?.addressLocality,
        };
      }
    } catch {
      continue;
    }
  }
  return null;
}
