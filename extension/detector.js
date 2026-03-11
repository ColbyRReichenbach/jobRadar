// URL pattern matching for job platforms (PRD §10.9)
const PLATFORM_PATTERNS = [
  {
    platform: "greenhouse",
    regex: /boards\.greenhouse\.io\/([^/]+)\/jobs\/(\d+)/,
    extract: (m) => ({ token: m[1], job_id: m[2] }),
  },
  {
    platform: "greenhouse",
    regex: /job-boards\.greenhouse\.io\/([^/]+)\/jobs\/(\d+)/,
    extract: (m) => ({ token: m[1], job_id: m[2] }),
  },
  {
    platform: "greenhouse_hosted",
    regex: /[?&]gh_jid=(\d+)/,
    extract: (m) => ({ job_id: m[1] }),
  },
  {
    platform: "lever",
    regex: /jobs\.lever\.co\/([^/]+)\/([a-f0-9-]{36})/,
    extract: (m) => ({ company: m[1], uuid: m[2] }),
  },
  {
    platform: "workday",
    regex: /(?:wd\d+\.)?myworkdayjobs\.com\/([^/]+)\/job\//,
    extract: (m) => ({ site: m[1] }),
  },
  {
    platform: "ashby",
    regex: /jobs\.ashbyhq\.com\/([^/]+)\/([a-f0-9-]{36})/,
    extract: (m) => ({ company: m[1], uuid: m[2] }),
  },
  {
    platform: "linkedin",
    regex: /linkedin\.com\/jobs\/view\/(\d+)/,
    extract: (m) => ({ job_id: m[1] }),
  },
  {
    platform: "indeed",
    regex: /indeed\.com\/viewjob\?jk=([a-z0-9]+)/i,
    extract: (m) => ({ job_key: m[1] }),
  },
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
