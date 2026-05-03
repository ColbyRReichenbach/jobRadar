"""Company identity layer — extract company info from email sender domain.

Maps sender domains to company names and optional logo URLs.
Logo URLs come from a third-party provider and should only be exposed when
third-party enrichment consent is granted.
"""

import re

# Known ATS/platform domains that should NOT be treated as company domains
PLATFORM_DOMAINS = {
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkday.com",
    "icims.com", "jobvite.com", "smartrecruiters.com", "taleo.net",
    "gmail.com", "outlook.com", "yahoo.com", "hotmail.com",
    "googlemail.com", "icloud.com", "protonmail.com",
    "linkedin.com", "indeed.com", "glassdoor.com",
    "github.com", "notion.so", "slack.com",
}

# Known domain → company name overrides
DOMAIN_TO_COMPANY = {
    "google.com": "Google",
    "meta.com": "Meta",
    "facebook.com": "Meta",
    "apple.com": "Apple",
    "amazon.com": "Amazon",
    "microsoft.com": "Microsoft",
    "netflix.com": "Netflix",
    "stripe.com": "Stripe",
    "coinbase.com": "Coinbase",
    "uber.com": "Uber",
    "lyft.com": "Lyft",
    "airbnb.com": "Airbnb",
    "spotify.com": "Spotify",
    "twitter.com": "X",
    "x.com": "X",
    "salesforce.com": "Salesforce",
    "adobe.com": "Adobe",
    "oracle.com": "Oracle",
    "ibm.com": "IBM",
    "intel.com": "Intel",
    "nvidia.com": "NVIDIA",
    "draftkings.com": "DraftKings",
    "fanduel.com": "FanDuel",
    "snap.com": "Snap",
    "pinterest.com": "Pinterest",
    "reddit.com": "Reddit",
    "twitch.tv": "Twitch",
    "databricks.com": "Databricks",
    "snowflake.com": "Snowflake",
    "palantir.com": "Palantir",
    "robinhood.com": "Robinhood",
    "plaid.com": "Plaid",
    "figma.com": "Figma",
    "vercel.com": "Vercel",
    "datadog.com": "Datadog",
    "cloudflare.com": "Cloudflare",
    "hashicorp.com": "HashiCorp",
    "elastic.co": "Elastic",
    "mongodb.com": "MongoDB",
    "confluent.io": "Confluent",
    "cockroachlabs.com": "Cockroach Labs",
}

COMPANY_TO_DOMAIN: dict[str, str] = {}
for _domain, _company in DOMAIN_TO_COMPANY.items():
    COMPANY_TO_DOMAIN.setdefault(_company.lower(), _domain)


def extract_domain(email_address: str) -> str:
    """Extract domain from email address."""
    match = re.search(r"@([\w.-]+)", email_address or "")
    return match.group(1).lower() if match else ""


def is_company_domain(domain: str) -> bool:
    """Check if domain represents a real company (not a platform/ATS)."""
    return bool(domain) and domain not in PLATFORM_DOMAINS


def domain_to_company_name(domain: str) -> str | None:
    """Convert domain to company name.

    Uses known mappings first, then capitalizes the domain base.
    Returns None for platform/generic domains.
    """
    if not domain or domain in PLATFORM_DOMAINS:
        return None

    # Check known overrides
    if domain in DOMAIN_TO_COMPANY:
        return DOMAIN_TO_COMPANY[domain]

    # Extract base name from domain (e.g., "draftkings" from "draftkings.com")
    base = domain.split(".")[0]

    # Try to make a reasonable company name
    # Handle common patterns: "my-company" -> "My Company"
    name = base.replace("-", " ").replace("_", " ")
    return name.title()


def get_logo_url(domain: str) -> str | None:
    """Get company logo URL from domain.

    Uses logo.clearbit.com which provides logos for most companies.
    Falls back to None if domain is a platform.
    """
    if not domain or domain in PLATFORM_DOMAINS:
        return None

    return f"https://logo.clearbit.com/{domain}"


def company_name_to_logo_url(company_name: str | None) -> str | None:
    """Return a logo URL for a known company name when we have a canonical domain."""
    normalized = (company_name or "").strip().lower()
    if not normalized:
        return None
    domain = COMPANY_TO_DOMAIN.get(normalized)
    if not domain:
        return None
    return get_logo_url(domain)


def get_company_info(sender_email: str, include_logo: bool = True) -> dict:
    """Extract company identity from sender email.

    Returns:
        {
            "domain": "stripe.com",
            "company_name": "Stripe",
            "logo_url": "https://logo.clearbit.com/stripe.com",
            "is_company": True
        }
    """
    domain = extract_domain(sender_email)

    if not is_company_domain(domain):
        return {
            "domain": domain,
            "company_name": None,
            "logo_url": None,
            "is_company": False,
        }

    return {
        "domain": domain,
        "company_name": domain_to_company_name(domain),
        "logo_url": get_logo_url(domain) if include_logo else None,
        "is_company": True,
    }
