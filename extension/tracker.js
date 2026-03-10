// Sprint 17: Career page visit tracker
// Runs as content script on career/job pages to passively track browsing

(function() {
  const CAREER_PATTERNS = [
    /\/careers?\//i,
    /\/jobs?\//i,
    /careers?\./i,
    /jobs?\./i,
    /\/job-openings/i,
    /\/opportunities/i,
    /\/work-with-us/i,
    /\/join-us/i,
  ];

  // ATS confirmation page patterns (Sprint 17 Task 1)
  const CONFIRMATION_PATTERNS = [
    // Greenhouse
    { platform: 'greenhouse', pattern: /thank\s*you\s*for\s*(your\s*)?appl/i },
    { platform: 'greenhouse', pattern: /application\s*(has\s*been\s*)?submitted/i },
    // Lever
    { platform: 'lever', pattern: /thanks?\s*for\s*applying/i },
    { platform: 'lever', pattern: /your\s*application\s*has\s*been\s*received/i },
    // Workday
    { platform: 'workday', pattern: /successfully\s*submitted/i },
    { platform: 'workday', pattern: /thank\s*you\s*for\s*your\s*interest/i },
    // Generic
    { platform: 'generic', pattern: /application\s*(?:received|submitted|complete)/i },
  ];

  function extractDomain(url) {
    try {
      const hostname = new URL(url).hostname;
      const parts = hostname.replace('www.', '').split('.');
      return parts.length > 2 ? parts.slice(-2).join('.') : hostname;
    } catch {
      return '';
    }
  }

  function isCareerPage(url) {
    return CAREER_PATTERNS.some(p => p.test(url));
  }

  function checkForConfirmation() {
    const bodyText = document.body?.innerText || '';
    for (const { platform, pattern } of CONFIRMATION_PATTERNS) {
      if (pattern.test(bodyText)) {
        return { platform, confirmed: true };
      }
    }
    return null;
  }

  function extractSalaryFromPage() {
    const bodyText = document.body?.innerText || '';
    // Simple salary extraction from visible page text
    const salaryMatch = bodyText.match(
      /\$\s*([\d,]+)\s*[kK]?\s*[-–—to]+\s*\$?\s*([\d,]+)\s*[kK]?(?:\s*(?:per\s+)?(?:year|yr|annually))?/
    );
    if (salaryMatch) {
      return `$${salaryMatch[1]} - $${salaryMatch[2]}`;
    }
    return null;
  }

  function extractDepartmentFromPage() {
    const selectors = [
      '[data-department]',
      '.department',
      '.job-department',
      '[class*="department"]',
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) return el.textContent.trim();
    }
    return null;
  }

  async function trackVisit() {
    const url = window.location.href;
    const domain = extractDomain(url);
    if (!domain) return;

    // Only track career-related pages
    if (!isCareerPage(url)) return;

    // Get existing visits from storage
    const key = `visits_${domain}`;
    const data = await chrome.storage.local.get(key);
    const existing = data[key] || { domain, urls: [], count: 0, firstVisit: Date.now() };

    existing.count += 1;
    existing.lastVisit = Date.now();
    if (!existing.urls.includes(url)) {
      existing.urls.push(url);
    }

    await chrome.storage.local.set({ [key]: existing });

    // Notify background about visit
    chrome.runtime.sendMessage({
      type: 'CAREER_PAGE_VISIT',
      domain,
      url,
      visitCount: existing.count,
    });
  }

  async function checkConfirmation() {
    const confirmation = checkForConfirmation();
    if (confirmation) {
      const salary = extractSalaryFromPage();
      const department = extractDepartmentFromPage();

      chrome.runtime.sendMessage({
        type: 'APPLICATION_SUBMITTED',
        platform: confirmation.platform,
        url: window.location.href,
        domain: extractDomain(window.location.href),
        enrichment: { salary, department },
      });
    }
  }

  // Run on page load
  trackVisit();

  // Check for confirmation after a delay (ATS pages may load dynamically)
  setTimeout(checkConfirmation, 2000);
})();
