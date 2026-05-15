from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI
from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.services.ai_pricing import estimate_cost_cents


DEFAULT_JD_CASES = Path("docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed/curated_jd_cases_reviewed.json")
DEFAULT_EVIDENCE_CARDS = Path("docs/ai-artifacts/generated/resume-tailoring-curated-evidence/curated_evidence_cards.csv")
DEFAULT_OUTPUT_DIR = Path("docs/ai-artifacts/generated/resume-tailoring-prompt-experiment")
DEFAULT_MODEL = os.getenv("RESUME_PROMPT_EXPERIMENT_MODEL", "gpt-4o")
DEFAULT_MAX_OUTPUT_TOKENS = 2600
EXPERIMENT_VERSION = "resume_prompt_tailoring_experiment_v1"


def _load_env_file(path: Path, *, preserve_existing: bool = True) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if preserve_existing and os.getenv(key):
            continue
        os.environ[key] = value


def load_local_env() -> None:
    # Keep a real .env key if .env.local has a blank override.
    _load_env_file(REPO_ROOT / ".env", preserve_existing=True)
    _load_env_file(REPO_ROOT / ".env.local", preserve_existing=True)


def extract_resume_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    return path.read_text(encoding="utf-8")


def redact_resume_text(text: str) -> str:
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", text)
    text = re.sub(r"\(?\b\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE]", text)
    text = re.sub(r"https?://\S+", "[URL]", text)
    text = re.sub(r"\b(?:linkedin\.com|github\.com|[\w.-]+\.vercel\.app|[\w.-]+\.github\.io)/\S*", "[URL]", text)
    return text


def _load_cases(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(case["id"]): case for case in payload}


def _job_text(case: dict[str, Any]) -> str:
    lines = [
        f"Company: {case.get('company', '')}",
        f"Role: {case.get('role_title', case.get('title', ''))}",
        f"Source URL: {case.get('source_url', '')}",
        "",
        "Requirements:",
    ]
    for requirement in case.get("expected_requirements", []):
        lines.append(f"- {requirement.get('query', '')}")
    return "\n".join(lines).strip()


def _lazy_prompt(*, resume_text: str, job_text: str) -> tuple[str, str]:
    system = "You are a helpful resume writing assistant."
    user = f"""Tailor my resume to this job description. Make it ATS optimized and emphasize the most relevant experience. Rewrite bullets where needed so I look like a strong fit.

Here is my resume:
{resume_text}

Here is the job description:
{job_text}
"""
    return system, user


def _engineered_prompt(*, resume_text: str, job_text: str) -> tuple[str, str]:
    system = (
        "You are an expert technical resume editor for data science, machine learning, "
        "analytics engineering, and applied AI roles. Your highest priority is factual accuracy."
    )
    user = f"""Tailor my resume to the job description while preserving factual accuracy.

Rules:
- Do not invent tools, models, metrics, employers, degrees, dates, certifications, or outcomes.
- Do not claim I used a technology unless it appears in my resume.
- Do not turn a prototype, local artifact, or evaluation into production experience unless the resume says it was production.
- Do not exaggerate business impact.
- Preserve contact, education, dates, employers, and overall resume structure.
- Keep bullets concise, specific, and achievement-oriented.
- If the job asks for something my resume does not support, do not add it.
- Prefer honest transferable framing over exact-match hallucination.

Output:
1. Tailored resume
2. Changed bullets, with original evidence from the resume for each change
3. Unsupported or weakly supported job requirements that should not be claimed
4. Risk notes: any places where the rewrite could overstate experience

Here is my resume:
{resume_text}

Here is the job description:
{job_text}
"""
    return system, user


def build_prompt(*, mode: str, resume_text: str, job_text: str) -> tuple[str, str]:
    if mode == "lazy":
        return _lazy_prompt(resume_text=resume_text, job_text=job_text)
    if mode == "engineered":
        return _engineered_prompt(resume_text=resume_text, job_text=job_text)
    raise ValueError(f"Unsupported mode: {mode}")


def _usage_dict(usage: Any) -> dict[str, int | None]:
    if usage is None:
        return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def _safe_slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return re.sub(r"-+", "-", value).strip("-") or "run"


def run_experiment(
    *,
    resume_path: Path,
    jd_case_id: str,
    mode: str,
    model: str,
    output_dir: Path,
    jd_cases_path: Path,
    redact: bool,
    max_output_tokens: int,
) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required for live prompt experiments.")

    raw_resume_text = extract_resume_text(resume_path)
    resume_text = redact_resume_text(raw_resume_text) if redact else raw_resume_text
    cases = _load_cases(jd_cases_path)
    if jd_case_id not in cases:
        raise SystemExit(f"Unknown jd_case_id {jd_case_id!r}. Available: {', '.join(sorted(cases)[:10])}...")
    case = cases[jd_case_id]
    job_text = _job_text(case)
    system_prompt, user_prompt = build_prompt(mode=mode, resume_text=resume_text, job_text=job_text)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    case_slug = _safe_slug(jd_case_id)
    run_dir = output_dir / run_id / case_slug / mode
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "resume_input_redacted.md").write_text(resume_text + "\n", encoding="utf-8")
    (run_dir / "job_description.md").write_text(job_text + "\n", encoding="utf-8")
    (run_dir / "prompt.md").write_text(
        f"# System\n\n{system_prompt}\n\n# User\n\n{user_prompt}\n",
        encoding="utf-8",
    )

    client = OpenAI(api_key=api_key)
    request_kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    token_key = "max_completion_tokens" if model.startswith("gpt-5") else "max_tokens"
    request_kwargs[token_key] = max_output_tokens

    started = time.perf_counter()
    response = client.chat.completions.create(**request_kwargs)
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    output_text = response.choices[0].message.content or ""
    usage = _usage_dict(response.usage)
    cost_cents, cost_breakdown = estimate_cost_cents(
        model=model,
        provider="openai",
        prompt_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
    )
    estimated_cost_usd = round(cost_cents / 100, 4)

    (run_dir / "output.md").write_text(output_text + "\n", encoding="utf-8")
    metrics = {
        "experiment_version": EXPERIMENT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "model": model,
        "jd_case_id": jd_case_id,
        "company": case.get("company"),
        "role_title": case.get("role_title"),
        "control_type": case.get("control_type"),
        "source_url": case.get("source_url"),
        "resume_path": str(resume_path),
        "jd_cases_path": str(jd_cases_path),
        "redacted_resume_input": redact,
        "latency_ms": latency_ms,
        "usage": usage,
        "estimated_cost_usd": estimated_cost_usd,
        "estimated_cost_cents_ceiled": cost_cents,
        "cost_breakdown": cost_breakdown,
        "pricing_note": "Uses backend/services/ai_pricing.py local pricing config; verify against current provider pricing before publication.",
        "output_chars": len(output_text),
        "run_dir": str(run_dir),
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live lazy/engineered resume tailoring prompt experiments.")
    parser.add_argument("--resume", type=Path, required=True)
    parser.add_argument("--jd-case-id", required=True)
    parser.add_argument("--mode", choices=["lazy", "engineered"], required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--jd-cases", type=Path, default=DEFAULT_JD_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument("--no-redact", action="store_true", help="Send raw resume text. Default redacts email, phone, and URLs.")
    args = parser.parse_args()

    load_local_env()
    metrics = run_experiment(
        resume_path=args.resume,
        jd_case_id=args.jd_case_id,
        mode=args.mode,
        model=args.model,
        output_dir=args.output_dir,
        jd_cases_path=args.jd_cases,
        redact=not args.no_redact,
        max_output_tokens=args.max_output_tokens,
    )
    print(json.dumps(metrics, sort_keys=True))


if __name__ == "__main__":
    main()
