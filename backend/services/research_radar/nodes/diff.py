from __future__ import annotations


def _keys_from_evidence(items: list[dict]) -> list[str]:
    return [item.get("_key") for item in items if item.get("_key")]


async def build_report_diff(state):
    previous_report = state.get("user_context", {}).get("previous_report") or {}
    previous_structured = previous_report.get("structured_json") or {}
    previous_index = previous_structured.get("evidence_index", {})
    previous_keys = set(previous_structured.get("evidence_keys", []))
    current_index = {
        item.get("_key"): {
            "claim": item.get("claim"),
            "title": item.get("title"),
            "company_name": item.get("company_name"),
            "role_title": item.get("role_title"),
            "url": item.get("url"),
        }
        for item in state.get("evidence_items", [])
        if item.get("_key")
    }
    current_keys = set(current_index)
    new_findings = sorted(current_keys - previous_keys)
    changed_findings = sorted(
        key
        for key in (current_keys & previous_keys)
        if previous_index.get(key, {}).get("claim") != current_index.get(key, {}).get("claim")
        or previous_index.get(key, {}).get("title") != current_index.get(key, {}).get("title")
    )
    unchanged_findings = sorted((current_keys & previous_keys) - set(changed_findings))
    dropped_findings = sorted(previous_keys - current_keys)

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
            "evidence_index": current_index,
        }
    }
