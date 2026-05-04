#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXTENSION_DIR="${ROOT_DIR}/extension"
STORE_DIR="${EXTENSION_DIR}/store"

if ! command -v sips >/dev/null 2>&1; then
  echo "sips is required to export Chrome Web Store PNG assets on macOS." >&2
  echo "Install ImageMagick/Inkscape and add a converter fallback before using this script on Linux." >&2
  exit 1
fi

VERSION="$(
  python3 - <<'PY' "${EXTENSION_DIR}/manifest.json"
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    manifest = json.load(fh)

print(manifest["version"])
PY
)"

RELEASE_ROOT="${ROOT_DIR}/dist/chrome-webstore"
RELEASE_DIR="${RELEASE_ROOT}/apptrail-extension-v${VERSION}"
ASSETS_DIR="${RELEASE_DIR}/assets"
SUBMISSION_ZIP="${RELEASE_ROOT}/apptrail-chrome-webstore-submission-v${VERSION}.zip"
RUNTIME_ZIP="${ROOT_DIR}/apptrail-extension-v${VERSION}.zip"

rm -rf "${RELEASE_DIR}" "${SUBMISSION_ZIP}" "${RUNTIME_ZIP}"
mkdir -p "${ASSETS_DIR}"

echo "Running release checks..."
bash "${ROOT_DIR}/scripts/ci/run_extension_checks.sh"

echo "Packaging runtime extension..."
bash "${ROOT_DIR}/scripts/package-extension.sh" >/tmp/apptrail-extension-package.log
mv "${RUNTIME_ZIP}" "${RELEASE_DIR}/"

echo "Copying store submission copy..."
cp "${STORE_DIR}/listing.md" \
   "${STORE_DIR}/privacy-policy.md" \
   "${STORE_DIR}/privacy-fields.md" \
   "${STORE_DIR}/SUBMISSION_GUIDE.md" \
   "${STORE_DIR}/beta-scope.md" \
   "${RELEASE_DIR}/"

cp "${EXTENSION_DIR}/images/icon-128.png" "${ASSETS_DIR}/icon-128.png"

echo "Exporting store SVG assets to PNG..."
for svg in "${STORE_DIR}"/screenshot-*.svg "${STORE_DIR}"/promo-*.svg; do
  name="$(basename "${svg}" .svg)"
  sips -s format png "${svg}" --out "${ASSETS_DIR}/${name}.png" >/dev/null
done

python3 "${ROOT_DIR}/scripts/release/validate_chrome_store_readiness.py" \
  --store-package-dir "${RELEASE_DIR}"

(
  cd "${RELEASE_ROOT}"
  zip -qr "$(basename "${SUBMISSION_ZIP}")" "$(basename "${RELEASE_DIR}")"
)

echo "Chrome Web Store submission bundle:"
echo "  ${SUBMISSION_ZIP}"
echo "Runtime extension ZIP:"
echo "  ${RELEASE_DIR}/apptrail-extension-v${VERSION}.zip"
echo "Store copy and PNG assets:"
echo "  ${RELEASE_DIR}"
