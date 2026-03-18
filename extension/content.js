// Universal job extraction content script.
// Runs on all matched job platform pages. Uses a layered extraction approach:
//   1. JSON-LD structured data (most reliable, standards-based)
//   2. Public ATS APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Rippling)
//   3. Embedded page JSON (__NEXT_DATA__, __remixContext, _initialData, etc.)
//   4. Platform-specific CSS selectors (least stable, multiple fallbacks)
//   5. MutationObserver for SPA re-renders

// ── Extractor version ──────────────────────────────────────────────
// Bump this on EVERY extraction logic change so reports are tagged.
// Format: ext-YYYY.MM.DD[a-z] (letter suffix for multiple changes per day)
const EXTRACTOR_VERSION = "ext-2026.03.18a";

// Guard against duplicate injection (background.js may re-inject on SPA navigation).
// On re-injection, trigger a fresh extract and store to session, then bail out.
if (window.__apptrailContentLoaded) {
  if (typeof window.__apptrailExtract === "function") {
    const _data = window.__apptrailExtract();
    if (_data) {
      chrome.storage.session.set({ extractedJob: _data }).catch(() => {});
    }
  }
  // Wrap remaining file in a conditional that won't execute
  window.__apptrailSkip = true;
} else {
  window.__apptrailSkip = false;
}
window.__apptrailContentLoaded = true;
if (!window.__apptrailSkip) {

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function isTrustedExtensionSender(sender) {
  return sender?.id === chrome.runtime.id;
}

function getFirst(selectors) {
  for (const selector of selectors) {
    try {
      const el = document.querySelector(selector);
      if (el) {
        const text = el.textContent.trim();
        if (text) return text;
      }
    } catch {
      // Invalid selector — skip
    }
  }
  return null;
}

function getHtml(selectors) {
  for (const selector of selectors) {
    try {
      const el = document.querySelector(selector);
      if (el && el.innerHTML.trim()) {
        return el.textContent.trim();
      }
    } catch {
      // skip
    }
  }
  return null;
}

function truncate(str, max = 5000) {
  if (!str) return null;
  return str.length > max ? str.substring(0, max) : str;
}

function cleanText(str) {
  if (!str) return null;
  return str.replace(/\s+/g, " ").trim();
}

// Scan description text for salary patterns (ported from backend salary_extractor.py)
function extractSalaryFromText(text) {
  if (!text) return null;

  const patterns = [
    // "$120,000 - $150,000" or "$120k - $150k"
    { re: /\$\s*([\d,]+)\s*[kK]?\s*[-–—to]+\s*\$?\s*([\d,]+)\s*[kK]?(?:\s*(?:per\s+)?(?:year|yr|annually|annual|pa))?/i, type: "range" },
    // "$50 - $75/hr" or "$50-$75 per hour"
    { re: /\$\s*([\d,.]+)\s*[-–—to]+\s*\$?\s*([\d,.]+)\s*(?:per\s+hour|\/\s*hr|\/\s*hour|hourly)/i, type: "hourly" },
    // "$120,000/year"
    { re: /\$\s*([\d,]+)\s*[kK]?\s*\/\s*(?:year|yr|annum|annual)/i, type: "single" },
    // "$50/hr"
    { re: /\$\s*([\d,.]+)\s*\/\s*(?:hr|hour)/i, type: "hourly_single" },
    // "170,600 - 213,250 USD" or "170,600.00 - 213,250.00 USD" (no $ prefix, currency after — most common Workday format)
    { re: /([\d,.]+)\s*[-–—to]+\s*([\d,.]+)\s*(?:USD|CAD|GBP|EUR|AUD|NZD|CHF|SEK|NOK|DKK|JPY|INR|SGD)/i, type: "range_currency" },
    // "USD 120,000 - 150,000" or "EUR 50,000-70,000" (currency before)
    { re: /(?:USD|CAD|GBP|EUR|AUD|NZD|CHF|SEK|NOK|DKK|JPY|INR|SGD)\s*([\d,.]+)\s*[-–—to]+\s*([\d,.]+)/i, type: "range_currency" },
    // "$120,000" standalone with optional "per year" / "annually"
    { re: /\$\s*([\d,]+)\s*[kK]?\s*(?:per\s+(?:year|annum)|annually|\/\s*(?:year|yr))/i, type: "single" },
    // "Salary: $120,000" or "Compensation: $120k"
    { re: /(?:salary|compensation|pay|base pay|base salary|total comp)[\s:]*\$\s*([\d,]+)\s*[kK]?/i, type: "single" },
    // "Salary range: 120,000 - 150,000" (no symbol, keyword prefix)
    { re: /(?:salary|compensation|pay|base pay|base salary|total comp)[\s:range]*\s*([\d,]+)\s*[-–—to]+\s*([\d,]+)/i, type: "range" },
    // Standalone "$120,000 - $150,000" without any suffix (less greedy, last resort)
    { re: /\$\s*([\d,]+)\s*[-–—]\s*\$\s*([\d,]+)/i, type: "range" },
  ];

  for (const { re, type } of patterns) {
    const m = text.match(re);
    if (!m) continue;

    const clean = (s) => {
      // Strip commas, spaces, and trailing decimal portions (.00)
      const stripped = s.replace(/[,\s]/g, "").replace(/\.\d+$/, "");
      return parseInt(stripped, 10) || 0;
    };
    let min, max;

    if (type === "range" || type === "hourly" || type === "range_currency") {
      min = clean(m[1]);
      max = clean(m[2]);
    } else {
      min = max = clean(m[1]);
    }

    if (min === 0 && max === 0) continue;
    if (min > max) [min, max] = [max, min];

    // Handle "k" suffix
    const matchedText = m[0];
    if (/[kK]/.test(matchedText)) {
      if (min < 1000) min *= 1000;
      if (max < 1000) max *= 1000;
    }

    const isHourly = type === "hourly" || type === "hourly_single";

    // Filter unreasonable
    if (!isHourly && (min < 10000 || max > 5000000)) continue;
    if (isHourly && (min < 5 || max > 1000)) continue;

    // Format as readable string
    const fmt = (n) => n.toLocaleString("en-US");
    if (isHourly) {
      return min === max ? `$${fmt(min)}/hr` : `$${fmt(min)} - $${fmt(max)}/hr`;
    }
    return min === max ? `$${fmt(min)}` : `$${fmt(min)} - $${fmt(max)}`;
  }

  return null;
}

function detectPlatformFromUrl(url) {
  const u = url || window.location.href;
  if (u.includes("linkedin.com/jobs")) return "linkedin";
  if (u.includes("boards.greenhouse.io") || u.includes("job-boards.greenhouse.io")) return "greenhouse";
  if (u.includes("jobs.lever.co")) return "lever";
  if (/wd\d+\.myworkday(?:jobs)?\.com/.test(u)) return "workday";
  if (u.includes("jobs.ashbyhq.com")) return "ashby";
  if (u.includes("indeed.com")) return "indeed";
  if (u.includes("glassdoor.com")) return "glassdoor";
  if (u.includes("ziprecruiter.com")) return "ziprecruiter";
  if (u.includes("wellfound.com")) return "wellfound";
  if (u.includes("smartrecruiters.com")) return "smartrecruiters";
  if (u.includes(".icims.com")) return "icims";
  if (u.includes("jobvite.com")) return "jobvite";
  if (u.includes("bamboohr.com")) return "bamboohr";
  if (u.includes("ats.rippling.com")) return "rippling";
  return "generic";
}

// ──────────────────────────────────────────────
// Layer 1: JSON-LD extraction (all platforms)
// ──────────────────────────────────────────────

function extractJsonLd() {
  const scripts = document.querySelectorAll('script[type="application/ld+json"]');
  for (const script of scripts) {
    try {
      let data = JSON.parse(script.textContent);
      // Handle arrays of JSON-LD objects
      if (Array.isArray(data)) {
        data = data.find((d) => d["@type"] === "JobPosting");
      }
      if (data && data["@type"] === "JobPosting") {
        const location = data.jobLocation
          ? Array.isArray(data.jobLocation)
            ? data.jobLocation
                .map((loc) => loc.address?.addressLocality || loc.name)
                .filter(Boolean)
                .join(", ")
            : data.jobLocation.address?.addressLocality || data.jobLocation.name
          : null;

        let salary = null;
        if (data.baseSalary) {
          const bs = data.baseSalary;
          const val = bs.value;
          if (val?.minValue && val?.maxValue) {
            salary = `${bs.currency || "$"}${val.minValue.toLocaleString()} - ${bs.currency || "$"}${val.maxValue.toLocaleString()} ${val.unitText || ""}`.trim();
          } else if (val?.value) {
            salary = `${bs.currency || "$"}${val.value.toLocaleString()} ${val.unitText || ""}`.trim();
          }
        }

        return {
          title: data.title || data.name || null,
          company: data.hiringOrganization?.name || null,
          description: truncate(cleanText(data.description)),
          location: location,
          salary: salary,
          department: data.occupationalCategory || null,
        };
      }
    } catch {
      continue;
    }
  }
  return null;
}

// ──────────────────────────────────────────────
// Layer 2: Meta tag extraction (all platforms)
// ──────────────────────────────────────────────

function extractMetaTags() {
  const get = (name) => {
    const el =
      document.querySelector(`meta[property="${name}"]`) ||
      document.querySelector(`meta[name="${name}"]`);
    return el?.content?.trim() || null;
  };

  const title = get("og:title");
  const description = get("og:description");

  if (!title) return null;

  return {
    title,
    company: null, // usually not in meta tags
    description: truncate(cleanText(description)),
    location: null,
    salary: null,
    department: null,
  };
}

// ──────────────────────────────────────────────
// Layer 3: Platform-specific extractors
// ──────────────────────────────────────────────

// --- LinkedIn ---
// View 1: /jobs/view/ID — dedicated full-page job view
// View 2: /jobs/search/?currentJobId=ID — search results with right detail pane
// View 3: /jobs/collections/recommended/?currentJobId=ID — recommended feed + detail pane
// The detail pane in views 2&3 uses the same component but inside a different container.
// LinkedIn frequently changes class names, so we use multiple fallback strategies.
function extractLinkedIn() {
  // Strategy: try the detail pane container first (views 2&3), then full page (view 1)
  // The detail pane is inside .jobs-search__job-details or .scaffold-layout__detail
  const detailPane =
    document.querySelector(".jobs-search__job-details") ||
    document.querySelector(".scaffold-layout__detail") ||
    document.querySelector("[class*='job-details']") ||
    document;

  function getFirstIn(container, selectors) {
    for (const sel of selectors) {
      try {
        const el = container.querySelector(sel);
        if (el) {
          const text = el.textContent.trim();
          if (text) return text;
        }
      } catch { /* skip */ }
    }
    return null;
  }

  const title = getFirstIn(detailPane, [
    "h1.job-details-jobs-unified-top-card__job-title",
    "h1.t-24.t-bold.inline",
    "h1.topcard__title",
    ".job-details-jobs-unified-top-card__job-title",
    ".jobs-unified-top-card__job-title",
    // Split-pane class names
    "h2.t-24.t-bold",
    "h2.jobs-unified-top-card__job-title",
    "h1[class*='job-title']",
    "h1[class*='topcard']",
    // Very broad fallbacks
    ".t-24.t-bold",
    "h1",
    "h2",
  ]);

  const company = getFirstIn(detailPane, [
    "div.job-details-jobs-unified-top-card__company-name a",
    "div.job-details-jobs-unified-top-card__company-name",
    ".jobs-unified-top-card__company-name a",
    ".jobs-unified-top-card__company-name",
    ".topcard__org-name-link",
    "a.topcard__org-name-link",
    "span.jobs-unified-top-card__company-name",
    // Split-pane: company link in the detail header
    "[class*='company-name'] a",
    "[class*='company-name']",
    // Some versions use primary-description
    "[class*='primary-description'] a",
  ]);

  const location = getFirstIn(detailPane, [
    "span.job-details-jobs-unified-top-card__bullet",
    ".jobs-unified-top-card__bullet",
    ".topcard__flavor--bullet",
    "span.jobs-unified-top-card__subtitle-primary-grouping span:nth-child(1)",
    "[class*='top-card'] [class*='bullet']",
    // Split-pane: location in subtitle
    "[class*='subtitle-primary-grouping'] [class*='bullet']",
    "[class*='workplace-type']",
  ]);

  const description = getFirstIn(detailPane, [
    "div.job-details-module__content",
    "div.jobs-description__content",
    "div.jobs-description-content__text",
    ".jobs-box__html-content",
    "section.description .show-more-less-html__markup",
    ".show-more-less-html__markup",
    // Split-pane: description in article or section
    "article [class*='description']",
    "[class*='description'] [class*='content']",
    "[class*='description-content']",
  ]);

  // Salary from job criteria list or insight cards
  let salary = null;
  const salarySelectors = [
    ".job-details-jobs-unified-top-card__job-insight",
    ".description__job-criteria-list li",
    "[class*='salary']",
    "[class*='compensation']",
  ];
  for (const sel of salarySelectors) {
    try {
      const items = detailPane.querySelectorAll(sel);
      for (const item of items) {
        const text = item.textContent;
        if (text && /\$[\d,]+/.test(text)) {
          salary = cleanText(text);
          break;
        }
      }
      if (salary) break;
    } catch { /* skip */ }
  }

  if (!title && !company) return null;
  return {
    title: title || null,
    company: company || null,
    description: truncate(description),
    location: location || null,
    salary,
    department: null,
  };
}

// --- Greenhouse ---
// View 1: boards.greenhouse.io/company/jobs/ID — classic board
// View 2: job-boards.greenhouse.io/company/jobs/ID — new Remix-based board
// View 3: Embedded on company career pages via iframe (src=boards.greenhouse.io)
// View 4: Embedded via Greenhouse API-powered custom pages (gh_jid param)
function extractGreenhouse() {
  // Try __remixContext first (new board)
  const scripts = document.querySelectorAll("script");
  for (const script of scripts) {
    const text = script.textContent;
    if (text.includes("__remixContext")) {
      try {
        const match = text.match(/window\.__remixContext\s*=\s*({.+?});?\s*(?:window\.|<\/script>)/s);
        if (match) {
          const ctx = JSON.parse(match[1]);
          const loaderData = ctx?.state?.loaderData;
          if (loaderData) {
            for (const key of Object.keys(loaderData)) {
              const ld = loaderData[key];
              if (ld?.job || ld?.jobPosting) {
                const job = ld.job || ld.jobPosting;
                return {
                  title: job.title || job.name || null,
                  company: job.company?.name || ld.company?.name || null,
                  description: truncate(cleanText(job.content || job.description)),
                  location: job.location?.name || null,
                  salary: null,
                  department: job.departments?.[0]?.name || null,
                };
              }
            }
          }
        }
      } catch {
        // parsing failed, continue
      }
    }
  }

  // Try __NEXT_DATA__ (some Greenhouse-powered pages use Next.js)
  const nextData = document.querySelector("script#__NEXT_DATA__");
  if (nextData) {
    try {
      const data = JSON.parse(nextData.textContent);
      const pp = data?.props?.pageProps;
      if (pp?.job || pp?.jobPosting) {
        const job = pp.job || pp.jobPosting;
        return {
          title: job.title || job.name || null,
          company: job.company?.name || pp.company?.name || null,
          description: truncate(cleanText(job.content || job.description)),
          location: job.location?.name || null,
          salary: null,
          department: job.departments?.[0]?.name || null,
        };
      }
    } catch { /* continue */ }
  }

  // Fallback: DOM selectors
  // Classic board (boards.greenhouse.io) uses different classes than new board
  const title = getFirst([
    // New board
    "h1.job__title",
    "h1[class*='job-title']",
    // Classic board
    ".app-title",
    "#header .company-name + h1",
    // Embedded on company pages
    ".greenhouse-job-board h1",
    "[id*='greenhouse'] h1",
    "h1",
  ]);
  const company = getFirst([
    ".company-name",
    "[class*='company']",
    // Classic board: company in header
    "#header .company-name",
  ]);
  const location = getFirst([
    ".location",
    "[class*='location']",
    // Classic board
    ".location-name",
  ]);
  const description = getFirst([
    "#content",
    ".job__description",
    ".job-description",
    "[class*='description']",
    // Classic board: content is in #content div
    "#app_body #content",
  ]);
  const department = getFirst([
    ".department",
    "[class*='department']",
  ]);

  // Try to get company from URL: boards.greenhouse.io/COMPANY/jobs/ID
  let urlCompany = null;
  const ghMatch = window.location.href.match(/(?:job-)?boards\.greenhouse\.io\/([^/]+)/);
  if (ghMatch) {
    urlCompany = ghMatch[1].replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  if (!title) return null;
  return {
    title,
    company: company || urlCompany || null,
    description: truncate(description),
    location: location || null,
    salary: null,
    department: department || null,
  };
}

// --- Lever (public API available, but also try DOM) ---
function extractLever() {
  const title = getFirst([
    ".posting-headline h2",
    "h2[class*='posting']",
    "h2",
  ]);

  const location = getFirst([
    ".posting-categories .location",
    ".location",
    "[class*='location']",
  ]);

  const department = getFirst([
    ".posting-categories .department",
    ".department",
  ]);

  const commitment = getFirst([
    ".posting-categories .commitment",
  ]);

  // Company from page title or logo alt
  const company =
    getFirst(["[class*='main-header-logo'] img"]) // alt text
    || document.querySelector("[class*='main-header-logo'] img")?.alt
    || null;

  // Description from content sections
  const descParts = [];
  document.querySelectorAll(".section-wrapper .section .content").forEach((el) => {
    const t = el.textContent.trim();
    if (t) descParts.push(t);
  });
  const description = descParts.join("\n\n");

  if (!title) return null;
  return {
    title,
    company: company || extractCompanyFromLeverUrl(),
    description: truncate(description) || null,
    location: location || null,
    salary: null,
    department: department || null,
  };
}

function extractCompanyFromLeverUrl() {
  const match = window.location.href.match(/jobs\.lever\.co\/([^/]+)/);
  if (match) {
    return match[1].replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return null;
}

// --- Workday (SPA — multiple view types) ---
// View 1: Direct job page (/job/Title_JR-ID) — full page with header + description
// View 2: Split-pane (/jobs) — job list on left, detail panel on right
// View 3: Search results — similar to split-pane
// All use data-automation-id attributes but with different containers.
function extractWorkday() {
  // --- Title ---
  // Direct page uses h2/h3 with jobPostingHeader
  // Split-pane uses the selected job's title in the detail panel
  const title = getFirst([
    "[data-automation-id='jobPostingHeader']",
    // Split-pane: detail panel header
    "[data-automation-id='job-detail-header']",
    "[data-automation-id='jobTitle']",
    // Some Workday instances use different casing
    "[data-automation-id='JobTitle']",
    "[data-automation-id='job-title']",
    // Broader: any h2/h3 inside a job detail section
    "[data-automation-id='jobPosting'] h2",
    "[data-automation-id='jobPosting'] h3",
    // Very broad fallback — first prominent heading
    "main h2",
    "h2",
  ]);

  // --- Location ---
  const location = getFirst([
    "[data-automation-id='locations'] dd",
    "[data-automation-id='locations']",
    "[data-automation-id='location']",
    "[data-automation-id='jobLocation']",
    // Split-pane detail
    "[data-automation-id='job-detail-location']",
    // Some instances put location in a list
    "[data-automation-id='jobPostingLocation']",
    // Text nodes near a "Location" label
    "dl [data-automation-id='locations'] + dd",
  ]);

  // --- Description ---
  // This is the biggest issue — split-pane renders description differently
  const description = getFirst([
    "[data-automation-id='jobPostingDescription']",
    // Split-pane detail panel
    "[data-automation-id='job-detail-description']",
    "[data-automation-id='jobDescription']",
    "[data-automation-id='JobDescription']",
    // Some Workday instances wrap in a generic content div
    "[data-automation-id='jobPosting'] [data-automation-id='richTextArea']",
    // Broader: look for large text blocks inside job posting containers
    "[data-automation-id='jobPosting'] .css-1wns4ln",
    "[data-automation-id='jobPosting'] .css-cygeeu",
    // Very broad — any richText area on the page
    "[data-automation-id='richTextArea']",
  ]);

  // --- Department ---
  const department = getFirst([
    "[data-automation-id='department']",
    "[data-automation-id='jobPostingDepartment']",
    "[data-automation-id='job-detail-department']",
  ]);

  // --- Salary (Workday sometimes shows pay range) ---
  const salary = getFirst([
    "[data-automation-id='salary']",
    "[data-automation-id='payRange']",
    "[data-automation-id='compensationRange']",
  ]);

  // --- Company name — prioritize subdomain (brand) over legal entity ---
  const company = extractCompanyFromWorkday();

  if (!title && !description) return null;
  return {
    title: title || null,
    company: company || null,
    description: truncate(description),
    location: location || null,
    salary: salary || null,
    department: department || null,
  };
}

// Legal entity suffixes that indicate a formal name, not a brand
const LEGAL_SUFFIXES = /\b(?:inc\.?|llc\.?|ltd\.?|corp\.?|co\.?|holdings|group|enterprises|l\.?p\.?|plc|gmbh|s\.?a\.?|n\.?v\.?)\s*$/i;

function extractCompanyFromWorkday() {
  // Strategy 1 (primary): URL subdomain — this is the brand name
  // e.g. "draftkings.wd5.myworkdayjobs.com" → "Draftkings"
  const url = window.location.href;
  const subdomainMatch = url.match(/https?:\/\/([^.]+)\./);
  const subdomainBrand = subdomainMatch
    ? subdomainMatch[1].replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : null;

  // Strategy 2: og:site_name or author meta — sometimes the clean brand
  const siteName =
    document.querySelector('meta[property="og:site_name"]')?.content?.trim() ||
    document.querySelector('meta[name="author"]')?.content?.trim();

  // Strategy 3: Logo alt text
  const logoAlt = document.querySelector('header img[alt]')?.alt?.trim();
  const logoCandidate = (logoAlt && logoAlt.length > 1 && logoAlt.length < 60 && logoAlt.toLowerCase() !== "logo")
    ? logoAlt : null;

  // Strategy 4: Page title — often "Job Title - Legal Entity Name"
  let titleCandidate = null;
  const pageTitle = document.title;
  if (pageTitle && pageTitle.includes(" - ")) {
    const parts = pageTitle.split(" - ");
    const last = parts[parts.length - 1].trim();
    if (last.length > 1 && last.length < 60 && !last.toLowerCase().includes("career")) {
      titleCandidate = last;
    }
  }

  // Pick best candidate: prefer shorter brand names, avoid legal entity suffixes
  const candidates = [subdomainBrand, siteName, logoCandidate, titleCandidate].filter(Boolean);

  // If we have a subdomain brand + another candidate that's a legal entity name,
  // prefer the subdomain (brand). E.g. "Draftkings" over "DK Crown Holdings Inc."
  if (subdomainBrand) {
    const otherCandidates = candidates.filter((c) => c !== subdomainBrand);
    // Only use a non-subdomain candidate if it's shorter and NOT a legal entity
    const betterBrand = otherCandidates.find(
      (c) => c.length < subdomainBrand.length && !LEGAL_SUFFIXES.test(c)
    );
    return betterBrand || subdomainBrand;
  }

  // Fallback: first candidate that isn't a legal entity, or just first candidate
  return candidates.find((c) => !LEGAL_SUFFIXES.test(c)) || candidates[0] || null;
}

// --- Ashby ---
function extractAshby() {
  // Try window.__appData embedded JSON
  const scripts = document.querySelectorAll("script");
  for (const script of scripts) {
    const text = script.textContent;
    if (text.includes("__appData") || text.includes("jobBoard")) {
      try {
        const match = text.match(/window\.__appData\s*=\s*({.+?});?\s*<\/script>/s)
          || text.match(/"jobPostings"\s*:\s*\[(.+?)\]/s);
        if (match) {
          const data = JSON.parse(match[0].includes("__appData") ? match[1] : `[${match[1]}]`);
          // This is the full board data; find the current job by URL
          const currentPath = window.location.pathname;
          const jobs = data.jobBoard?.jobPostings || data;
          if (Array.isArray(jobs)) {
            const job = jobs.find((j) => currentPath.includes(j.id) || currentPath.includes(j.slug));
            if (job) {
              return {
                title: job.title || null,
                company: job.organizationName || data.jobBoard?.organizationName || null,
                description: truncate(cleanText(job.descriptionPlain || job.descriptionHtml)),
                location: job.location || null,
                salary: job.compensation ? formatCompensation(job.compensation) : null,
                department: job.department || job.team || null,
              };
            }
          }
        }
      } catch {
        // continue
      }
    }
  }

  // Fallback: DOM
  const title = getFirst(["h1", "[class*='job-title']", "[class*='posting-title']"]);
  const company = getFirst(["[class*='company']", "[class*='org-name']"]);
  const location = getFirst(["[class*='location']"]);
  const description = getFirst(["[class*='description']", "[class*='content']"]);

  if (!title) return null;
  return {
    title,
    company: company || extractCompanyFromAshbyUrl(),
    description: truncate(description),
    location: location || null,
    salary: null,
    department: null,
  };
}

function extractCompanyFromAshbyUrl() {
  const match = window.location.href.match(/jobs\.ashbyhq\.com\/([^/]+)/);
  if (match) {
    return match[1].replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return null;
}

function formatCompensation(comp) {
  if (!comp) return null;
  if (comp.min && comp.max) {
    return `${comp.currency || "$"}${comp.min.toLocaleString()} - ${comp.currency || "$"}${comp.max.toLocaleString()}`;
  }
  return null;
}

// --- Indeed ---
// View 1: /viewjob?jk=ID — dedicated job page
// View 2: /jobs?q=...&vjk=ID — search results with right detail pane
// View 3: /rc/clk?jk=ID — redirect click-through (redirects to view 1)
// The split-pane view (2) renders job detail inside #mosaic-provider-jobcards or .jobsearch-ViewJobLayout
function extractIndeed() {
  // Try the right-side detail pane first (search view), then full page
  const detailPane =
    document.querySelector(".jobsearch-ViewJobLayout--inline") ||
    document.querySelector(".jobsearch-RightPane") ||
    document.querySelector("[class*='ViewJobLayout']") ||
    document;

  function getFirstIn(container, selectors) {
    for (const sel of selectors) {
      try {
        const el = container.querySelector(sel);
        if (el) {
          const text = el.textContent.trim();
          if (text) return text;
        }
      } catch { /* skip */ }
    }
    return null;
  }

  // Try embedded _initialData or mosaic data
  const scripts = document.querySelectorAll("script");
  for (const script of scripts) {
    const text = script.textContent;
    if (text.includes("_initialData") || text.includes("window.mosaic")) {
      try {
        const match = text.match(/window\._initialData\s*=\s*({.+?});\s*$/ms)
          || text.match(/window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*({.+?});/s);
        if (match) {
          const data = JSON.parse(match[1]);
          const jobData = data?.jobInfoWrapperModel?.jobInfoModel || data?.metaDataModel || data;
          if (jobData) {
            return {
              title: jobData.jobInfoHeaderModel?.jobTitle || jobData.title || null,
              company: jobData.jobInfoHeaderModel?.companyName || jobData.company || null,
              description: null,
              location: jobData.jobInfoHeaderModel?.formattedLocation || jobData.location || null,
              salary: jobData.salaryInfoModel?.salaryText || null,
              department: null,
            };
          }
        }
      } catch {
        // continue
      }
    }
  }

  // Fallback: DOM selectors — search in detail pane first
  const title = getFirstIn(detailPane, [
    "h1.jobsearch-JobInfoHeader-title",
    "h2.jobsearch-JobInfoHeader-title",
    "[data-testid='jobsearch-JobInfoHeader-title']",
    "h1[class*='JobTitle']",
    ".jobTitle",
    // Split-pane: job title in the right panel
    ".jcs-JobTitle",
    "[data-testid='job-title']",
    "h1",
    "h2",
  ]);

  const company = getFirstIn(detailPane, [
    "[data-testid='inlineHeader-companyName']",
    "[data-testid='company-name']",
    "[data-company-name]",
    ".jobsearch-InlineCompanyRating-companyHeader a",
    ".jobsearch-InlineCompanyRating a",
    "[class*='CompanyName']",
    // Split-pane
    ".companyName",
    "[class*='companyName'] a",
  ]);

  const location = getFirstIn(detailPane, [
    "[data-testid='inlineHeader-companyLocation']",
    "[data-testid='job-location']",
    ".jobsearch-JobInfoHeader-subtitle > div:last-child",
    ".companyLocation",
    "[class*='CompanyLocation']",
    // Split-pane
    "[data-testid='text-location']",
  ]);

  const description = getFirstIn(detailPane, [
    "#jobDescriptionText",
    ".jobsearch-jobDescriptionText",
    "[class*='jobDescription']",
    // Split-pane: description in the inline layout
    ".jobsearch-JobComponent-description",
  ]);

  const salary = getFirstIn(detailPane, [
    "#salaryInfoAndJobType",
    ".salary-snippet-container",
    ".metadata .attribute_snippet",
    "[class*='salary']",
    "[data-testid='attribute_snippet_testid']",
  ]);

  if (!title && !company) return null;
  return {
    title: title || null,
    company: company || null,
    description: truncate(description),
    location: location || null,
    salary: salary || null,
    department: null,
  };
}

// --- Glassdoor ---
function extractGlassdoor() {
  // Try __NEXT_DATA__ or Apollo cache
  const nextDataScript = document.querySelector("script#__NEXT_DATA__");
  if (nextDataScript) {
    try {
      const data = JSON.parse(nextDataScript.textContent);
      const pageProps = data?.props?.pageProps;
      const job = pageProps?.job || pageProps?.jobListing;
      if (job) {
        return {
          title: job.jobTitleText || job.header?.jobTitleText || null,
          company: job.employer?.shortName || job.header?.employerNameFromSearch || null,
          description: truncate(cleanText(job.description?.text || job.job?.description)),
          location: job.header?.locationName || job.map?.cityName || null,
          salary: job.salarySource?.payRangeLow
            ? `$${job.salarySource.payRangeLow.toLocaleString()} - $${job.salarySource.payRangeHigh.toLocaleString()}`
            : null,
          department: null,
        };
      }
    } catch {
      // continue
    }
  }

  // Fallback: data-test attribute selectors (more stable than class names)
  const title = getFirst([
    "[data-test='jobTitle']",
    "[data-test='job-title']",
    "h1[class*='JobTitle']",
    "h1",
  ]);

  const company = getFirst([
    "[data-test='employer-short-name']",
    "[data-test='employerName']",
    "[class*='EmployerName']",
  ]);

  const location = getFirst([
    "[data-test='employer-location']",
    "[data-test='location']",
    "[class*='location']",
  ]);

  const description = getFirst([
    "[class*='JobDesc']",
    ".desc",
    ".jobDescriptionContent",
  ]);

  if (!title && !company) return null;
  return {
    title: title || null,
    company: company || null,
    description: truncate(description),
    location: location || null,
    salary: null,
    department: null,
  };
}

// --- ZipRecruiter (JSON-LD primary, handled by Layer 1) ---
function extractZipRecruiter() {
  // JSON-LD should already be tried. DOM fallback:
  const title = getFirst([
    "h1.job_title",
    "h1[class*='title']",
    "h1",
  ]);

  const company = getFirst([
    "a.hiring_company",
    "[class*='hiring_company']",
    "[class*='company']",
  ]);

  const location = getFirst([
    "[class*='location']",
    ".hiring_location",
  ]);

  const description = getFirst([
    ".jobDescriptionSection",
    "[class*='description']",
  ]);

  if (!title && !company) return null;
  return {
    title: title || null,
    company: company || null,
    description: truncate(description),
    location: location || null,
    salary: null,
    department: null,
  };
}

// --- Wellfound ---
function extractWellfound() {
  // Try __NEXT_DATA__
  const nextDataScript = document.querySelector("script#__NEXT_DATA__");
  if (nextDataScript) {
    try {
      const data = JSON.parse(nextDataScript.textContent);
      const pageProps = data?.props?.pageProps;
      // Look for job listing in Apollo state
      const apolloState = pageProps?.apolloState?.data || pageProps;
      if (apolloState) {
        // Find job listing objects
        for (const key of Object.keys(apolloState)) {
          const obj = apolloState[key];
          if (obj?.title && (obj?.__typename === "JobListingSearchResult" || obj?.slug || obj?.remoteOk !== undefined)) {
            return {
              title: obj.title || null,
              company: obj.startup?.name || obj.companyName || null,
              description: truncate(cleanText(obj.description || obj.descriptionText)),
              location: obj.locationNames?.join(", ") || obj.location || null,
              salary: obj.compensation ? `${obj.compensation}` : null,
              department: null,
            };
          }
        }
      }
    } catch {
      // continue
    }
  }

  // Fallback: DOM
  const title = getFirst(["h1", "[class*='listing-title']"]);
  const company = getFirst(["h2 a", "[class*='company-name']"]);
  const location = getFirst(["[class*='location']"]);

  if (!title) return null;
  return {
    title,
    company: company || null,
    description: null,
    location: location || null,
    salary: null,
    department: null,
  };
}

// --- SmartRecruiters ---
function extractSmartRecruiters() {
  const title = getFirst([
    "h1",
    "h4.job-title",
    "[class*='job-title']",
  ]);

  const company = getFirst([
    "[class*='company-name']",
    "[class*='companyName']",
  ]);

  const location = getFirst([
    "[class*='location']",
    ".job-location",
  ]);

  const description = getFirst([
    "[class*='job-description']",
    "[class*='description']",
  ]);

  if (!title) return null;

  // Try to get company from URL: jobs.smartrecruiters.com/CompanyName/...
  const urlCompany = window.location.pathname.split("/")[1];
  return {
    title,
    company: company || (urlCompany ? urlCompany.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : null),
    description: truncate(description),
    location: location || null,
    salary: null,
    department: null,
  };
}

// --- iCIMS ---
function extractIcims() {
  const title = getFirst([
    "h1.iCIMS_Header",
    ".iCIMS_Header h1",
    "h1",
    "[class*='title']",
  ]);

  const company = getFirst([
    ".iCIMS_CompanyName",
    "[class*='company']",
  ]);

  const location = getFirst([
    ".iCIMS_JobLocation",
    "[class*='location']",
    "[class*='Location']",
  ]);

  const description = getFirst([
    ".iCIMS_MainWrapper",
    ".iCIMS_InfoMsg_Job",
    "[class*='description']",
  ]);

  if (!title) return null;
  return {
    title,
    company: company || null,
    description: truncate(description),
    location: location || null,
    salary: null,
    department: null,
  };
}

// --- Jobvite ---
function extractJobvite() {
  const title = getFirst([
    ".jv-header h2",
    ".jv-job-detail-name",
    "h2.jv-header",
    "h2",
  ]);

  const location = getFirst([
    ".jv-job-detail-meta .jv-job-detail-location",
    ".jv-job-list-location",
    "[class*='location']",
  ]);

  const department = getFirst([
    ".jv-job-detail-meta .jv-job-detail-department",
    ".jv-job-list-department",
    "[class*='department']",
  ]);

  const description = getFirst([
    ".jv-job-detail-description",
    "[class*='description']",
  ]);

  if (!title) return null;
  return {
    title,
    company: null, // Jobvite pages don't usually show company name in DOM
    description: truncate(description),
    location: location || null,
    salary: null,
    department: department || null,
  };
}

// --- BambooHR ---
function extractBambooHR() {
  const title = getFirst([
    "h1",
    ".ResizableHeader__title",
    "[class*='job-title']",
    "[class*='JobTitle']",
  ]);

  const location = getFirst([
    "[class*='location']",
    ".ResizableHeader__location",
  ]);

  const department = getFirst([
    "[class*='department']",
    ".ResizableHeader__department",
  ]);

  const description = getFirst([
    "[class*='job-description']",
    "[class*='JobDescription']",
    "[class*='content']",
  ]);

  // Company from URL: companyname.bamboohr.com
  const match = window.location.href.match(/https?:\/\/([^.]+)\.bamboohr\.com/);
  const company = match
    ? match[1].replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : null;

  if (!title) return null;
  return {
    title,
    company,
    description: truncate(description),
    location: location || null,
    salary: null,
    department: department || null,
  };
}

// --- Rippling ---
function extractRippling() {
  const title = getFirst([
    "h1",
    "[class*='job-title']",
    "[class*='JobTitle']",
  ]);

  const location = getFirst([
    "[class*='location']",
    "[class*='Location']",
  ]);

  const department = getFirst([
    "[class*='department']",
    "[class*='Department']",
  ]);

  const description = getFirst([
    "[class*='description']",
    "[class*='Description']",
    "[class*='content']",
  ]);

  // Company from URL: ats.rippling.com/company-slug/jobs/...
  const match = window.location.href.match(/ats\.rippling\.com\/([^/]+)/);
  const company = match
    ? match[1].replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : null;

  if (!title) return null;
  return {
    title,
    company,
    description: truncate(description),
    location: location || null,
    salary: null,
    department: department || null,
  };
}

// --- Generic fallback ---
function extractGeneric() {
  // Best-effort extraction for unknown sites
  const title = getFirst(["h1", "[class*='title']", "[class*='Title']"]);
  const company = getFirst(["[class*='company']", "[class*='Company']", "[class*='employer']"]);
  const location = getFirst(["[class*='location']", "[class*='Location']"]);
  const description = getFirst(["[class*='description']", "[class*='Description']", "[class*='content']"]);

  if (!title) return null;
  return {
    title,
    company: company || null,
    description: truncate(description),
    location: location || null,
    salary: null,
    department: null,
  };
}

// ──────────────────────────────────────────────
// Extractor dispatcher
// ──────────────────────────────────────────────

const PLATFORM_EXTRACTORS = {
  linkedin: extractLinkedIn,
  greenhouse: extractGreenhouse,
  lever: extractLever,
  workday: extractWorkday,
  ashby: extractAshby,
  indeed: extractIndeed,
  glassdoor: extractGlassdoor,
  ziprecruiter: extractZipRecruiter,
  wellfound: extractWellfound,
  smartrecruiters: extractSmartRecruiters,
  icims: extractIcims,
  jobvite: extractJobvite,
  bamboohr: extractBambooHR,
  rippling: extractRippling,
  generic: extractGeneric,
};

function extractJobData() {
  const platform = detectPlatformFromUrl();

  // Collect results from all layers — then merge.
  // This ensures e.g. JSON-LD title + DOM description both contribute.
  const layers = [];
  let primaryMethod = null;

  // Layer 1: JSON-LD (most reliable for structured fields)
  const jsonLd = extractJsonLd();
  if (jsonLd && (jsonLd.title || jsonLd.company)) {
    layers.push(jsonLd);
    primaryMethod = "json-ld";
  }

  // Layer 2: Platform-specific extractor (best for description, salary from DOM)
  const extractor = PLATFORM_EXTRACTORS[platform];
  if (extractor) {
    const extracted = extractor();
    if (extracted && (extracted.title || extracted.company || extracted.description)) {
      layers.push(extracted);
      if (!primaryMethod) primaryMethod = "platform";
    }
  }

  // Layer 3: Meta tags
  const meta = extractMetaTags();
  if (meta && meta.title) {
    layers.push(meta);
    if (!primaryMethod) primaryMethod = "meta";
  }

  // Layer 4: Generic fallback
  if (platform !== "generic") {
    const generic = extractGeneric();
    if (generic && (generic.title || generic.company)) {
      layers.push(generic);
      if (!primaryMethod) primaryMethod = "generic";
    }
  }

  if (layers.length === 0) return null;

  // Merge: first non-null value for each field wins (priority = layer order)
  const fields = ["title", "company", "description", "location", "salary", "department"];
  const merged = {};
  for (const field of fields) {
    for (const layer of layers) {
      if (layer[field]) {
        merged[field] = layer[field];
        break;
      }
    }
    if (!merged[field]) merged[field] = null;
  }

  if (!merged.title && !merged.company) return null;

  merged.source = platform;
  merged._method = primaryMethod;
  merged._extractor_version = EXTRACTOR_VERSION;

  // Post-processing: extract salary from description if no dedicated salary found
  if (!merged.salary && merged.description) {
    merged.salary = extractSalaryFromText(merged.description);
  }

  return merged;
}

// ──────────────────────────────────────────────
// MutationObserver for SPA re-renders
// ──────────────────────────────────────────────

let lastExtracted = null;
let observerTimer = null;

function setupObserver() {
  const observer = new MutationObserver(() => {
    // Debounce: wait for DOM to settle
    clearTimeout(observerTimer);
    observerTimer = setTimeout(() => {
      const data = extractJobData();
      if (data && JSON.stringify(data) !== JSON.stringify(lastExtracted)) {
        lastExtracted = data;
        // Store extraction so sidepanel can read it
        chrome.storage.session.set({ extractedJob: data }).catch(() => {});
      }
    }, 500);
  });

  observer.observe(document.body || document.documentElement, {
    childList: true,
    subtree: true,
  });
}

// ──────────────────────────────────────────────
// Message handler (sidepanel requests extraction)
// ──────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!isTrustedExtensionSender(sender)) {
    sendResponse(null);
    return false;
  }

  if (message.type === "EXTRACT_JOB" || message.type === "EXTRACT_LINKEDIN_JOB") {
    // Try immediate extraction
    const data = extractJobData();
    if (data && (data.title || data.company)) {
      sendResponse(data);
      return false;
    }

    // For SPAs, the DOM might not be ready yet. Retry with delay.
    let attempts = 0;
    const maxAttempts = 5;
    const interval = setInterval(() => {
      attempts++;
      const retryData = extractJobData();
      if ((retryData && (retryData.title || retryData.company)) || attempts >= maxAttempts) {
        clearInterval(interval);
        sendResponse(retryData || null);
      }
    }, 800);

    return true; // async response
  }

  return false;
});

// ──────────────────────────────────────────────
// Auto-extract on load + observe for SPA changes
// ──────────────────────────────────────────────

const initialData = extractJobData();
if (initialData) {
  lastExtracted = initialData;
  chrome.storage.session.set({ extractedJob: initialData }).catch(() => {});
}

// Set up observer for SPA navigation and dynamic content loading
if (document.body) {
  setupObserver();
} else {
  document.addEventListener("DOMContentLoaded", setupObserver);
}

// Expose extract function for re-injection guard
window.__apptrailExtract = extractJobData;

} // end: !window.__apptrailSkip
