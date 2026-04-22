ORCHESTRATOR_VERSION = "research_graph_v1"

DEPTH_TASK_LIMITS = {
    "quick": 4,
    "standard": 8,
    "deep": 12,
}

DEFAULT_MAX_RESULTS_PER_TASK = 5
SEARCH_TIMEOUT_SECONDS = 12
FETCH_TIMEOUT_SECONDS = 15
DEFAULT_FETCH_USER_AGENT = "AppTrailRadarResearch/1.0 (+https://apptrail.com)"

TRUSTED_DOMAIN_BONUS = {
    ".company": 0.55,
    ".careers": 0.55,
    "github.com": 0.45,
    "greenhouse.io": 0.45,
    "lever.co": 0.45,
    "workdayjobs.com": 0.45,
    "wellfound.com": 0.4,
}
