#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/../.."

python3 -m json.tool extension/manifest.json >/dev/null

(
  cd extension
  npm test
)

bash scripts/package-extension.sh >/tmp/apptrail-extension-package.log
rm -f apptrail-extension-v*.zip
