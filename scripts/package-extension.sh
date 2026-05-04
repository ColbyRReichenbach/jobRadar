#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTENSION_DIR="${ROOT_DIR}/extension"
STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/apptrail-extension.XXXXXX")"

cleanup() {
  rm -rf "${STAGING_DIR}"
}
trap cleanup EXIT

VERSION="$(
  python3 - <<'PY' "${EXTENSION_DIR}/manifest.json"
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    manifest = json.load(fh)

print(manifest["version"])
PY
)"

OUTPUT_NAME="apptrail-extension-v${VERSION}.zip"
OUTPUT_PATH="${ROOT_DIR}/${OUTPUT_NAME}"

rm -f "${OUTPUT_PATH}"

cp -R "${EXTENSION_DIR}/." "${STAGING_DIR}/"
rm -f "${STAGING_DIR}/images/icon-source.svg" "${STAGING_DIR}/package.json"
rm -rf "${STAGING_DIR}/tests" "${STAGING_DIR}/store"

python3 - <<'PY' "${STAGING_DIR}/manifest.json"
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
local_hosts = {"http://localhost/*", "http://127.0.0.1/*"}
manifest["host_permissions"] = [
    item for item in manifest.get("host_permissions", []) if item not in local_hosts
]
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY

(
  cd "${STAGING_DIR}"
  zip -r "${OUTPUT_PATH}" . \
    -x "*.DS_Store" \
    -x "__MACOSX/*"
)

echo "Packaged: ${OUTPUT_NAME}"
du -h "${OUTPUT_PATH}" | awk '{print "Size: " $1}'
echo "Submit at: https://chrome.google.com/webstore/devconsole"
