// URL pattern matching for job platforms (PRD §10.9)
// Ordered: specific platforms first, generic catch-all last.
// Each pattern extracts platform-specific IDs when possible.
const PLATFORM_PATTERNS = [
  // --- LinkedIn (all /jobs/ paths) ---
  {
    platform: "linkedin",
    regex: /linkedin\.com\/jobs\/view\/(?:[\w-]+-)?(\d+)/,
    extract: (m) => ({ job_id: m[1] }),
  },
  {
    platform: "linkedin",
    regex: /linkedin\.com\/jobs\/.*[?&]currentJobId=(\d+)/,
    extract: (m) => ({ job_id: m[1] }),
  },
  {
    platform: "linkedin",
    regex: /linkedin\.com\/jobs\//,
    extract: () => ({}),
  },

  // --- Greenhouse ---
  {
    platform: "greenhouse",
    regex: /(?:job-)?boards\.greenhouse\.io\/([^/]+)\/jobs\/(\d+)/,
    extract: (m) => ({ token: m[1], job_id: m[2] }),
  },
  {
    platform: "greenhouse",
    regex: /(?:job-)?boards\.greenhouse\.io\/([^/?]+)\?(?:[^#]*&)?error=true(?:[&#]|$)/,
    extract: (m) => ({ token: m[1], unavailable: true }),
  },
  {
    platform: "greenhouse_hosted",
    regex: /[?&]gh_jid=(\d+)/,
    extract: (m) => ({ job_id: m[1] }),
  },

  // --- Lever ---
  {
    platform: "lever",
    regex: /jobs\.lever\.co\/([^/]+)\/([a-f0-9-]{36})/,
    extract: (m) => ({ company: m[1], uuid: m[2] }),
  },
  {
    platform: "lever",
    regex: /jobs\.lever\.co\/([^/]+)/,
    extract: (m) => ({ company: m[1] }),
  },

  // --- Workday (myworkdayjobs.com AND myworkday.com) ---
  {
    platform: "workday",
    regex: /(?:[\w-]+\.)?wd\d+\.myworkday(?:jobs)?\.com\//,
    extract: () => ({}),
  },

  // --- Ashby ---
  {
    platform: "ashby",
    regex: /jobs\.ashbyhq\.com\/([^/]+)\/([a-f0-9-]{36})/,
    extract: (m) => ({ company: m[1], uuid: m[2] }),
  },
  {
    platform: "ashby",
    regex: /jobs\.ashbyhq\.com\/([^/]+)/,
    extract: (m) => ({ company: m[1] }),
  },

  // --- Indeed (all country domains + mobile) ---
  {
    platform: "indeed",
    regex: /indeed\.com\/viewjob\?.*?jk=([a-z0-9]+)/i,
    extract: (m) => ({ job_key: m[1] }),
  },
  {
    platform: "indeed",
    regex: /indeed\.com\/rc\/clk\?.*?jk=([a-z0-9]+)/i,
    extract: (m) => ({ job_key: m[1] }),
  },
  {
    // Split-pane search view: /jobs?q=...&vjk=ID
    platform: "indeed",
    regex: /indeed\.com\/jobs\?.*?vjk=([a-z0-9]+)/i,
    extract: (m) => ({ job_key: m[1] }),
  },
  {
    platform: "indeed",
    regex: /indeed\.com\/(viewjob|jobs|cmp\/)/i,
    extract: () => ({}),
  },

  // --- Glassdoor ---
  {
    platform: "glassdoor",
    regex: /glassdoor\.com\/job-listing\/.*?[?&]jl=(\d+)/,
    extract: (m) => ({ job_id: m[1] }),
  },
  {
    platform: "glassdoor",
    regex: /glassdoor\.com\/(Job|Jobs|job-listing|partner\/jobListing)/,
    extract: () => ({}),
  },

  // --- ZipRecruiter ---
  {
    platform: "ziprecruiter",
    regex: /ziprecruiter\.com\/c\/[^/]+\/Job\/.*?[?&]jid=([a-z0-9]+)/i,
    extract: (m) => ({ job_id: m[1] }),
  },
  {
    platform: "ziprecruiter",
    regex: /ziprecruiter\.com\/(c\/|jobs|jobs-search)/,
    extract: () => ({}),
  },

  // --- Wellfound (formerly AngelList) ---
  {
    platform: "wellfound",
    regex: /wellfound\.com\/company\/([^/]+)\/jobs\/(\d+)/,
    extract: (m) => ({ company: m[1], job_id: m[2] }),
  },
  {
    platform: "wellfound",
    regex: /wellfound\.com\/(company\/[^/]+\/jobs|role\/|jobs)/,
    extract: () => ({}),
  },

  // --- SmartRecruiters ---
  {
    platform: "smartrecruiters",
    regex: /smartrecruiters\.com\/([^/]+)\/(\d+-[\w-]+)/,
    extract: (m) => ({ company: m[1], posting_id: m[2] }),
  },
  {
    platform: "smartrecruiters",
    regex: /smartrecruiters\.com\/([^/]+)/,
    extract: (m) => ({ company: m[1] }),
  },

  // --- iCIMS ---
  {
    platform: "icims",
    regex: /[\w-]+\.icims\.com\/jobs\/(\d+)/,
    extract: (m) => ({ job_id: m[1] }),
  },
  {
    platform: "icims",
    regex: /[\w-]+\.icims\.com\/jobs/,
    extract: () => ({}),
  },

  // --- Jobvite ---
  {
    platform: "jobvite",
    regex: /(jobs|app|talent)\.jobvite\.com\//,
    extract: () => ({}),
  },

  // --- BambooHR ---
  {
    platform: "bamboohr",
    regex: /[\w-]+\.bamboohr\.com\/(?:careers|hiring\/jobs)(?:\/(\d+))?/,
    extract: (m) => (m[1] ? { job_id: m[1] } : {}),
  },

  // --- Rippling ---
  {
    platform: "rippling",
    regex: /ats\.rippling\.com\/([^/]+)\/jobs(?:\/([a-f0-9-]{36}))?/,
    extract: (m) => (m[2] ? { board: m[1], uuid: m[2] } : { board: m[1] }),
  },

  // --- Generic catch-all (career/jobs pages on any domain) ---
  {
    platform: "generic",
    regex: /\/careers?\/|\/jobs?\/|careers?\.|jobs?\./,
    extract: () => ({}),
  },
];

export function detectPlatform(url) {
  for (const pattern of PLATFORM_PATTERNS) {
    const match = url.match(pattern.regex);
    if (match) {
      return {
        platform: pattern.platform,
        params: pattern.extract(match),
        url: url,
      };
    }
  }
  return null;
}

export { PLATFORM_PATTERNS };
