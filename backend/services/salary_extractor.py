"""Sprint 16: Salary extraction from job descriptions.

Extracts salary ranges using regex patterns, normalizes to annual values.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Common salary patterns
SALARY_PATTERNS = [
    # "$120,000 - $150,000" or "$120k - $150k"
    r"\$\s*([\d,]+)\s*[kK]?\s*[-–—to]+\s*\$?\s*([\d,]+)\s*[kK]?(?:\s*(?:per\s+)?(?:year|yr|annually|annual|pa))?",
    # "$120,000/year" or "$120k/yr"
    r"\$\s*([\d,]+)\s*[kK]?\s*/\s*(?:year|yr|annum|annual)",
    # "$50 - $75/hr" or "$50-$75 per hour"
    r"\$\s*([\d,.]+)\s*[-–—to]+\s*\$?\s*([\d,.]+)\s*(?:per\s+hour|/\s*hr|/\s*hour|hourly)",
    # "$50/hr"
    r"\$\s*([\d,.]+)\s*/\s*(?:hr|hour)",
    # "120,000 - 150,000 USD"
    r"([\d,]+)\s*[-–—to]+\s*([\d,]+)\s*(?:USD|CAD|GBP|EUR)",
    # "Salary: $120,000"
    r"(?:salary|compensation|pay)[\s:]*\$\s*([\d,]+)\s*[kK]?",
]

HOURLY_PATTERNS = [
    r"\$\s*[\d,.]+\s*[-–—to]+\s*\$?\s*[\d,.]+\s*(?:per\s+hour|/\s*hr|/\s*hour|hourly)",
    r"\$\s*[\d,.]+\s*/\s*(?:hr|hour)",
]

CURRENCY_PATTERNS = {
    "USD": [r"\$", r"USD", r"US\s*dollars?"],
    "GBP": [r"£", r"GBP"],
    "EUR": [r"€", r"EUR"],
    "CAD": [r"CAD", r"C\$"],
}


def _clean_number(s: str) -> int:
    """Clean a salary string to integer."""
    s = s.replace(",", "").replace(" ", "").strip()
    try:
        return int(float(s))
    except ValueError:
        return 0


def _detect_currency(text: str) -> str:
    """Detect currency from text."""
    for currency, patterns in CURRENCY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return currency
    return "USD"


def _is_hourly(text: str) -> bool:
    """Check if the salary mentioned is hourly."""
    for pattern in HOURLY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def extract_salary(description: str) -> dict | None:
    """Extract salary range from job description text.

    Returns dict with salary_min, salary_max, salary_currency, salary_period.
    Returns None if no salary found.
    """
    if not description:
        return None

    for pattern in SALARY_PATTERNS:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            groups = match.groups()

            if len(groups) >= 2:
                min_val = _clean_number(groups[0])
                max_val = _clean_number(groups[1])
            elif len(groups) == 1:
                val = _clean_number(groups[0])
                min_val = val
                max_val = val
            else:
                continue

            if min_val == 0 and max_val == 0:
                continue

            # Ensure min <= max
            if min_val > max_val:
                min_val, max_val = max_val, min_val

            # Handle "k" suffix in original text
            matched_text = match.group(0)
            if re.search(r"[kK]", matched_text):
                if min_val < 1000:
                    min_val *= 1000
                if max_val < 1000:
                    max_val *= 1000

            currency = _detect_currency(description)
            is_hourly = _is_hourly(matched_text)
            period = "hourly" if is_hourly else "yearly"

            # Filter out unreasonable values
            if period == "yearly" and (min_val < 10000 or max_val > 5000000):
                continue
            if period == "hourly" and (min_val < 5 or max_val > 1000):
                continue

            return {
                "salary_min": min_val,
                "salary_max": max_val,
                "salary_currency": currency,
                "salary_period": period,
            }

    return None


def aggregate_salaries(
    salaries: list[dict],
) -> dict:
    """Aggregate salary data to compute percentiles.

    Input: list of dicts with salary_min and salary_max.
    Output: dict with p25, p50, p75, avg, count.
    """
    if not salaries:
        return {"p25": 0, "p50": 0, "p75": 0, "avg": 0, "count": 0}

    # Use midpoint of ranges for aggregation
    midpoints = sorted([
        (s["salary_min"] + s["salary_max"]) / 2
        for s in salaries
        if s.get("salary_min") and s.get("salary_max")
    ])

    if not midpoints:
        return {"p25": 0, "p50": 0, "p75": 0, "avg": 0, "count": 0}

    n = len(midpoints)
    return {
        "p25": int(midpoints[max(0, n // 4 - 1)]),
        "p50": int(midpoints[n // 2]),
        "p75": int(midpoints[min(n - 1, 3 * n // 4)]),
        "avg": int(sum(midpoints) / n),
        "count": n,
    }
