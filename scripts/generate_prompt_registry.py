#!/usr/bin/env python3
"""Generate backend/PROMPT_REGISTRY.md from the shared AI task config."""

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.services.ai_orchestrator import write_prompt_registry


def main() -> None:
    output_path = REPO_ROOT / "backend" / "PROMPT_REGISTRY.md"
    write_prompt_registry(str(output_path))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
