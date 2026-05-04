#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/../.."

python3 -m json.tool extension/manifest.json >/dev/null

(
  cd extension
  npm test
)

python3 scripts/release/validate_chrome_store_readiness.py

bash scripts/package-extension.sh >/tmp/apptrail-extension-package.log
python3 - <<'PY'
import json
import zipfile
from pathlib import Path

zip_files = sorted(Path(".").glob("apptrail-extension-v*.zip"))
if len(zip_files) != 1:
    raise SystemExit(f"Expected one packaged extension zip, found {len(zip_files)}")
with zipfile.ZipFile(zip_files[0]) as archive:
    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
hosts = set(manifest.get("host_permissions", []))
local_hosts = {"http://localhost/*", "http://127.0.0.1/*"}
if hosts & local_hosts:
    raise SystemExit(f"Packaged extension includes local development hosts: {sorted(hosts & local_hosts)}")
PY
rm -f apptrail-extension-v*.zip
