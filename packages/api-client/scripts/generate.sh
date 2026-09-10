#!/usr/bin/env bash
# Regenerate the typed API surface from the running API's OpenAPI document.
#
# Generated, not hand-written, and checked in nowhere: `src/generated/` is
# git-ignored. A hand-maintained client drifts from the API silently, and the
# drift is discovered by a runtime type error in whichever app touched the
# field that moved.
set -euo pipefail
cd "$(dirname "$0")/.."
API_URL="${ACMIS_API_URL:-http://localhost:8000}"
mkdir -p src/generated
echo "Reading OpenAPI from ${API_URL}/openapi.json"
npx --yes openapi-typescript "${API_URL}/openapi.json" -o src/generated/schema.ts
echo "Wrote src/generated/schema.ts"
