#!/usr/bin/env python3
"""Validate the Chrome Web Store submission surface for the extension."""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import zipfile
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[2]
EXTENSION_DIR = ROOT_DIR / "extension"
STORE_DIR = EXTENSION_DIR / "store"

FORBIDDEN_HIGH_RISK_HOSTS = ("linkedin.com", "indeed.com", "glassdoor.com")
FORBIDDEN_PERMISSIONS = {"cookies", "history", "management", "webRequest", "webRequestBlocking"}
EXPECTED_PERMISSIONS = {"activeTab", "sidePanel", "storage", "scripting", "tabs"}
LOCAL_DEV_HOST_PERMISSIONS = {"http://localhost/*", "http://127.0.0.1/*"}
EXPECTED_SCREENSHOT_DIMS = (1280, 800)
EXPECTED_PROMO_DIMS = {
    "promo-small-440x280": (440, 280),
    "promo-large-920x680": (920, 680),
    "promo-marquee-1400x560": (1400, 560),
}


class ValidationError(Exception):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def flatten(values: Iterable[Iterable[str]]) -> list[str]:
    return [item for group in values for item in group]


def assert_contains(text: str, needle: str, path: Path) -> None:
    if needle.lower() not in text.lower():
        fail(f"{path.relative_to(ROOT_DIR)} must mention: {needle}")


def assert_no_forbidden_hosts(values: Iterable[str], label: str) -> None:
    for value in values:
        lowered = value.lower()
        for host in FORBIDDEN_HIGH_RISK_HOSTS:
            if host in lowered:
                fail(f"{label} must not include high-risk host {host}: {value}")


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as fh:
        header = fh.read(24)
    if not header.startswith(b"\x89PNG\r\n\x1a\n"):
        fail(f"{path.relative_to(ROOT_DIR)} is not a PNG")
    return struct.unpack(">II", header[16:24])


def svg_dimensions(path: Path) -> tuple[int, int]:
    text = read_text(path)
    match = re.search(r"<svg[^>]*\bwidth=\"(\d+)\"[^>]*\bheight=\"(\d+)\"", text)
    if not match:
        fail(f"{path.relative_to(ROOT_DIR)} is missing explicit SVG width/height")
    return int(match.group(1)), int(match.group(2))


def validate_manifest() -> None:
    manifest_path = EXTENSION_DIR / "manifest.json"
    manifest = read_json(manifest_path)

    if manifest.get("manifest_version") != 3:
        fail("manifest.json must use Manifest V3")
    if len(manifest.get("description", "")) > 132:
        fail("manifest description must be 132 characters or fewer")

    permissions = set(manifest.get("permissions", []))
    unexpected = permissions - EXPECTED_PERMISSIONS
    if unexpected:
        fail(f"manifest has unexpected permissions: {sorted(unexpected)}")
    if FORBIDDEN_PERMISSIONS & permissions:
        fail(f"manifest has forbidden permissions: {sorted(FORBIDDEN_PERMISSIONS & permissions)}")

    host_permissions = manifest.get("host_permissions", [])
    optional_host_permissions = manifest.get("optional_host_permissions", [])
    content_script_matches = flatten(
        entry.get("matches", []) for entry in manifest.get("content_scripts", [])
    )
    assert_no_forbidden_hosts(host_permissions, "host_permissions")
    assert_no_forbidden_hosts(optional_host_permissions, "optional_host_permissions")
    extraction_scripts = [
        entry for entry in manifest.get("content_scripts", []) if "content.js" in entry.get("js", [])
    ]
    assert_no_forbidden_hosts(
        flatten(entry.get("matches", []) for entry in extraction_scripts),
        "extraction content script matches",
    )

    for permission in host_permissions + optional_host_permissions + content_script_matches:
        if permission in {"<all_urls>", "http://*/*", "https://*/*"}:
            fail(f"manifest must not request unrestricted host access: {permission}")

    csp = manifest.get("content_security_policy", {}).get("extension_pages")
    if csp != "script-src 'self'; object-src 'self'":
        fail("extension_pages CSP must restrict script execution to self")

    for size, icon_path in manifest.get("icons", {}).items():
        path = EXTENSION_DIR / icon_path
        if not path.exists():
            fail(f"manifest icon {size} is missing: {icon_path}")

    if png_dimensions(EXTENSION_DIR / "images/icon-128.png") != (128, 128):
        fail("extension/images/icon-128.png must be 128x128")


def validate_runtime_privacy_defaults() -> None:
    background = read_text(EXTENSION_DIR / "background.js")
    sidepanel = read_text(EXTENSION_DIR / "sidepanel.js")
    tracker = read_text(EXTENSION_DIR / "tracker.js")

    for source_name, source in {
        "background.js": background,
        "sidepanel.js": sidepanel,
    }.items():
        for setting in (
            "linkedinAutoExtract: false",
            "thirdPartyBoardAutoExtract: false",
            "careerTrackingEnabled: false",
            "submissionDetectionEnabled: false",
        ):
            if setting not in source:
                fail(f"{source_name} must default {setting}")

    for host in FORBIDDEN_HIGH_RISK_HOSTS:
        if host not in tracker:
            fail(f"tracker.js must explicitly skip {host}")

    for script_path in EXTENSION_DIR.glob("*.js"):
        source = read_text(script_path)
        if re.search(r"\beval\s*\(", source) or re.search(r"\bnew\s+Function\s*\(", source):
            fail(f"{script_path.relative_to(ROOT_DIR)} must not use dynamic code execution")
        if re.search(r"import\s*\([^)]*https?://", source):
            fail(f"{script_path.relative_to(ROOT_DIR)} must not import remote code")


def validate_store_copy() -> None:
    listing = STORE_DIR / "listing.md"
    privacy = STORE_DIR / "privacy-policy.md"
    guide = STORE_DIR / "SUBMISSION_GUIDE.md"
    privacy_fields = STORE_DIR / "privacy-fields.md"
    beta_scope = STORE_DIR / "beta-scope.md"

    for path in (listing, privacy, guide, privacy_fields, beta_scope):
        if not path.exists():
            fail(f"Missing store document: {path.relative_to(ROOT_DIR)}")

    assert_contains(read_text(listing), "revoke", listing)
    assert_contains(read_text(listing), "stored locally", listing)
    assert_contains(read_text(listing), "does not sell", listing)
    assert_contains(read_text(listing), "supported job-related pages", listing)

    privacy_text = read_text(privacy)
    assert_contains(privacy_text, "Limited Use", privacy)
    assert_contains(privacy_text, "Chrome Web Store User Data Policy", privacy)
    assert_contains(privacy_text, "does not monitor general browsing", privacy)

    fields_text = read_text(privacy_fields)
    for permission in EXPECTED_PERMISSIONS:
        assert_contains(fields_text, permission, privacy_fields)
    assert_contains(fields_text, "No remote code", privacy_fields)
    assert_contains(fields_text, "Capture job listings", privacy_fields)


def validate_store_asset_sources() -> None:
    screenshots = sorted(STORE_DIR.glob("screenshot-*.svg"))
    if len(screenshots) < 1:
        fail("At least one screenshot SVG is required")
    if len(screenshots) > 5:
        fail("Chrome Web Store supports at most five screenshots")
    for path in screenshots:
        dims = svg_dimensions(path)
        if dims != EXPECTED_SCREENSHOT_DIMS:
            fail(f"{path.relative_to(ROOT_DIR)} must be 1280x800, got {dims}")

    for name, dims in EXPECTED_PROMO_DIMS.items():
        path = STORE_DIR / f"{name}.svg"
        if not path.exists():
            fail(f"Missing promo asset source: {path.relative_to(ROOT_DIR)}")
        if svg_dimensions(path) != dims:
            fail(f"{path.relative_to(ROOT_DIR)} must be {dims}")


def validate_generated_package(package_dir: Path | None) -> None:
    if not package_dir:
        return
    if not package_dir.exists():
        fail(f"Generated package dir does not exist: {package_dir}")

    zip_files = sorted(package_dir.glob("apptrail-extension-v*.zip"))
    if len(zip_files) != 1:
        fail(f"Expected exactly one runtime extension zip in {package_dir}")

    with zipfile.ZipFile(zip_files[0]) as archive:
        names = set(archive.namelist())
        if "manifest.json" not in names:
            fail("runtime extension zip must include manifest.json at the root")
        runtime_manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        runtime_hosts = set(runtime_manifest.get("host_permissions", []))
        leaked_dev_hosts = sorted(runtime_hosts & LOCAL_DEV_HOST_PERMISSIONS)
        if leaked_dev_hosts:
            fail(f"runtime extension zip must not include local development hosts: {leaked_dev_hosts}")
        forbidden_prefixes = ("store/", "tests/", "package.json")
        for name in names:
            if name.startswith(forbidden_prefixes) or name == "package.json":
                fail(f"runtime extension zip contains non-runtime file: {name}")

    assets_dir = package_dir / "assets"
    if not assets_dir.exists():
        fail("Generated package must include an assets directory")

    screenshot_pngs = sorted(assets_dir.glob("screenshot-*.png"))
    if not screenshot_pngs:
        fail("Generated package must include screenshot PNGs")
    for path in screenshot_pngs:
        if png_dimensions(path) != EXPECTED_SCREENSHOT_DIMS:
            fail(f"{path.relative_to(ROOT_DIR)} must be 1280x800")

    promo_small = assets_dir / "promo-small-440x280.png"
    if not promo_small.exists():
        fail("Generated package must include promo-small-440x280.png")
    if png_dimensions(promo_small) != (440, 280):
        fail("promo-small-440x280.png must be 440x280")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-package-dir", type=Path)
    args = parser.parse_args()

    try:
        validate_manifest()
        validate_runtime_privacy_defaults()
        validate_store_copy()
        validate_store_asset_sources()
        validate_generated_package(args.store_package_dir)
    except ValidationError as exc:
        print(f"Chrome Web Store readiness check failed: {exc}", file=sys.stderr)
        return 1

    print("Chrome Web Store readiness checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
