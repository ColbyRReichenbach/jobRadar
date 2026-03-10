"""Tech stack extraction from job descriptions via regex pattern matching."""

import re

# Curated tech dictionary: canonical_name -> [regex patterns]
TECH_CATALOG = {
    # Languages
    "Python": [r"\bpython\b"],
    "JavaScript": [r"\bjavascript\b"],
    "TypeScript": [r"\btypescript\b"],
    "Java": [r"\bjava\b(?!script)"],
    "C++": [r"\bc\+\+\b", r"\bcpp\b"],
    "C#": [r"\bc#\b", r"\bcsharp\b"],
    "Go": [r"\bgolang\b", r"\bgo\s+(?:developer|engineer|programming|language)\b"],
    "Rust": [r"\brust\b(?:\s+(?:developer|engineer|programming|language))", r"\brustlang\b"],
    "Ruby": [r"\bruby\b"],
    "PHP": [r"\bphp\b"],
    "Swift": [r"\bswift\b"],
    "Kotlin": [r"\bkotlin\b"],
    "Scala": [r"\bscala\b"],
    "Dart": [r"\bdart\b"],
    "Elixir": [r"\belixir\b"],
    # Frontend Frameworks
    "React": [r"\breact\b(?![\s-]*native)", r"\breactjs\b", r"\breact\.js\b"],
    "Vue.js": [r"\bvue\b", r"\bvuejs\b", r"\bvue\.js\b"],
    "Angular": [r"\bangular\b"],
    "Next.js": [r"\bnext\.js\b", r"\bnextjs\b"],
    "Svelte": [r"\bsvelte\b"],
    # Backend Frameworks
    "Node.js": [r"\bnode\.js\b", r"\bnodejs\b"],
    "Django": [r"\bdjango\b"],
    "Flask": [r"\bflask\b"],
    "FastAPI": [r"\bfastapi\b"],
    "Spring": [r"\bspring\s*boot\b", r"\bspring\s+framework\b"],
    "Express": [r"\bexpressjs\b", r"\bexpress\.js\b"],
    "Rails": [r"\brails\b", r"\bruby on rails\b"],
    "Laravel": [r"\blaravel\b"],
    ".NET": [r"\.net\b", r"\bdotnet\b", r"\basp\.net\b"],
    "NestJS": [r"\bnestjs\b"],
    # Databases
    "PostgreSQL": [r"\bpostgresql\b", r"\bpostgres\b"],
    "MySQL": [r"\bmysql\b"],
    "MongoDB": [r"\bmongodb\b", r"\bmongo\b"],
    "Redis": [r"\bredis\b"],
    "Elasticsearch": [r"\belasticsearch\b"],
    "DynamoDB": [r"\bdynamodb\b"],
    "Cassandra": [r"\bcassandra\b"],
    "SQLite": [r"\bsqlite\b"],
    "Neo4j": [r"\bneo4j\b"],
    "CockroachDB": [r"\bcockroachdb\b"],
    "ClickHouse": [r"\bclickhouse\b"],
    "Supabase": [r"\bsupabase\b"],
    "Firebase": [r"\bfirebase\b"],
    # Cloud
    "AWS": [r"\baws\b", r"\bamazon web services\b"],
    "GCP": [r"\bgcp\b", r"\bgoogle cloud\b"],
    "Azure": [r"\bazure\b"],
    "Vercel": [r"\bvercel\b"],
    "Heroku": [r"\bheroku\b"],
    "Netlify": [r"\bnetlify\b"],
    "Cloudflare": [r"\bcloudflare\b"],
    # DevOps & Infrastructure
    "Docker": [r"\bdocker\b"],
    "Kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "Terraform": [r"\bterraform\b"],
    "Ansible": [r"\bansible\b"],
    "Jenkins": [r"\bjenkins\b"],
    "GitHub Actions": [r"\bgithub actions\b"],
    "CircleCI": [r"\bcircleci\b"],
    "ArgoCD": [r"\bargocd\b", r"\bargo\s*cd\b"],
    "Prometheus": [r"\bprometheus\b"],
    "Grafana": [r"\bgrafana\b"],
    "Datadog": [r"\bdatadog\b"],
    "Nginx": [r"\bnginx\b"],
    # Data & ML
    "Spark": [r"\bspark\b", r"\bpyspark\b", r"\bapache spark\b"],
    "Kafka": [r"\bkafka\b"],
    "Airflow": [r"\bairflow\b"],
    "dbt": [r"\bdbt\b"],
    "Snowflake": [r"\bsnowflake\b"],
    "BigQuery": [r"\bbigquery\b"],
    "Redshift": [r"\bredshift\b"],
    "Databricks": [r"\bdatabricks\b"],
    "TensorFlow": [r"\btensorflow\b"],
    "PyTorch": [r"\bpytorch\b"],
    "Pandas": [r"\bpandas\b"],
    "NumPy": [r"\bnumpy\b"],
    "scikit-learn": [r"\bscikit-learn\b", r"\bsklearn\b"],
    "Hugging Face": [r"\bhugging\s*face\b", r"\bhuggingface\b"],
    "LangChain": [r"\blangchain\b"],
    "Tableau": [r"\btableau\b"],
    "Looker": [r"\blooker\b"],
    "Power BI": [r"\bpower bi\b"],
    # Mobile
    "React Native": [r"\breact[\s-]*native\b"],
    "Flutter": [r"\bflutter\b"],
    "iOS": [r"\bios\b"],
    "Android": [r"\bandroid\b"],
    "SwiftUI": [r"\bswiftui\b"],
    # Tools & Services
    "Git": [r"\bgit\b(?!hub|lab)"],
    "GitHub": [r"\bgithub\b"],
    "GitLab": [r"\bgitlab\b"],
    "Jira": [r"\bjira\b"],
    "GraphQL": [r"\bgraphql\b"],
    "REST": [r"\brest\s+api\b", r"\brestful\b"],
    "gRPC": [r"\bgrpc\b"],
    "RabbitMQ": [r"\brabbitmq\b"],
    "Celery": [r"\bcelery\b"],
    "Webpack": [r"\bwebpack\b"],
    "Vite": [r"\bvite\b"],
    "Jest": [r"\bjest\b"],
    "Cypress": [r"\bcypress\b"],
    "Playwright": [r"\bplaywright\b"],
    "Tailwind": [r"\btailwind\b"],
    "Prisma": [r"\bprisma\b"],
    "SQLAlchemy": [r"\bsqlalchemy\b"],
    "Linux": [r"\blinux\b"],
    "CI/CD": [r"\bci/cd\b", r"\bci\s*cd\b"],
}

# Technology categories
TECH_CATEGORIES = {
    "Languages": {"Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust", "Ruby", "PHP", "Swift", "Kotlin", "Scala", "Dart", "Elixir"},
    "Frontend": {"React", "Vue.js", "Angular", "Next.js", "Svelte", "Tailwind"},
    "Backend": {"Node.js", "Django", "Flask", "FastAPI", "Spring", "Express", "Rails", "Laravel", ".NET", "NestJS"},
    "Databases": {"PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "DynamoDB", "Cassandra", "SQLite", "Neo4j", "CockroachDB", "ClickHouse", "Supabase", "Firebase"},
    "Cloud": {"AWS", "GCP", "Azure", "Vercel", "Heroku", "Netlify", "Cloudflare"},
    "DevOps": {"Docker", "Kubernetes", "Terraform", "Ansible", "Jenkins", "GitHub Actions", "CircleCI", "ArgoCD", "Prometheus", "Grafana", "Datadog", "Nginx", "CI/CD"},
    "Data & ML": {"Spark", "Kafka", "Airflow", "dbt", "Snowflake", "BigQuery", "Redshift", "Databricks", "TensorFlow", "PyTorch", "Pandas", "NumPy", "scikit-learn", "Hugging Face", "LangChain", "Tableau", "Looker", "Power BI"},
    "Mobile": {"React Native", "Flutter", "iOS", "Android", "SwiftUI"},
    "Tools": {"Git", "GitHub", "GitLab", "Jira", "GraphQL", "REST", "gRPC", "RabbitMQ", "Celery", "Webpack", "Vite", "Jest", "Cypress", "Playwright", "Prisma", "SQLAlchemy", "Linux"},
}


def _get_category(tech_name: str) -> str:
    for cat, techs in TECH_CATEGORIES.items():
        if tech_name in techs:
            return cat
    return "Other"


def extract_tech_stack(text: str) -> list[dict]:
    """Extract technologies from text.

    Returns list of {"name": str, "category": str}.
    """
    if not text:
        return []

    text_lower = text.lower()
    found = []
    seen: set[str] = set()

    for tech_name, patterns in TECH_CATALOG.items():
        if tech_name in seen:
            continue
        for pattern in patterns:
            if re.search(pattern, text_lower):
                found.append({"name": tech_name, "category": _get_category(tech_name)})
                seen.add(tech_name)
                break

    return sorted(found, key=lambda x: x["name"])
