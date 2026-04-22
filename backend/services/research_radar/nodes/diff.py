from __future__ import annotations


def _keys_from_evidence(items: list[dict]) -> list[str]:
    return [item.get("_key") for item in items if item.get("_key")]


async def build_report_diff(state):
    previous_report = state.get("user_context", {}).get("previous_report") or {}
    previous_keys = set((previous_report.get("structured_json") or {}).get("evidence_keys", []))
    current_keys = set(_keys_from_evidence(state.get("evidence_items", [])))
    new_findings = sorted(current_keys - previous_keys)
    unchanged_findings = sorted(current_keys & previous_keys)
    dropped_findings = sorted(previous_keys - current_keys)
    changed_findings: list[str] = []

    if not previous_keys:
        diff_summary = "This is the first saved report for this tracker."
    else:
        diff_summary = (
            f"{len(new_findings)} new findings, {len(changed_findings)} changed findings, "
            f"and {len(dropped_findings)} dropped findings since the last report."
        )

    return {
        "diff_summary": {
            "new_findings": new_findings,
            "changed_findings": changed_findings,
            "dropped_findings": dropped_findings,
            "unchanged_findings": unchanged_findings,
            "diff_summary": diff_summary,
            "all_keys": sorted(current_keys),
        }
    }
