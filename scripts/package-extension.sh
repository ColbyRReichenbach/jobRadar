#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTENSION_DIR="${ROOT_DIR}/extension"

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

(
  cd "${EXTENSION_DIR}"
  zip -r "${OUTPUT_PATH}" . \
    -x "*.DS_Store" \
    -x "__MACOSX/*" \
    -x "images/icon-source.svg" \
    -x "store/*"
)

echo "Packaged: ${OUTPUT_NAME}"
du -h "${OUTPUT_PATH}" | awk '{print "Size: " $1}'
echo "Submit at: https://chrome.google.com/webstore/devconsole"
