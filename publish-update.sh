#!/usr/bin/env bash
# Publish FitterCalcs so phones can update online.
# Needs: gh auth login  (once)  and a public repo macski777/fittercalcs
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

NAME="$(grep -E "versionName" app/build.gradle | head -1 | sed -E "s/.*'([^']+)'.*/\1/")"
CODE="$(grep -E "versionCode" app/build.gradle | head -1 | sed -E "s/[^0-9]//g")"
APK="$ROOT/FitterCalcs.apk"
NOTES="${1:-FitterCalcs $NAME}"

if [ ! -f "$APK" ]; then
  echo "Missing $APK — build the APK first."
  exit 1
fi

cat > "$ROOT/update.json" <<EOF
{
  "versionCode": $CODE,
  "versionName": "$NAME",
  "apkUrl": "https://github.com/macski777/fittercalcs/releases/latest/download/FitterCalcs.apk",
  "notes": $(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$NOTES")
}
EOF

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub is not logged in. Run:  gh auth login"
  echo "Then run this script again. Until then phones cannot see the online update."
  exit 1
fi

if ! gh repo view macski777/fittercalcs >/dev/null 2>&1; then
  gh repo create macski777/fittercalcs --public --source="$ROOT" --remote=origin --push || true
fi

git add update.json
git diff --cached --quiet || git commit -m "update.json $NAME"
git push origin HEAD:main 2>/dev/null || git push -u origin HEAD:main

gh release create "v$NAME" "$APK#FitterCalcs.apk" --title "FitterCalcs $NAME" --notes "$NOTES" --clobber 2>/dev/null \
  || gh release upload "v$NAME" "$APK#FitterCalcs.apk" --clobber

echo "Published $NAME (versionCode $CODE)"
echo "Phones on 2.18+ will see the update next time they open FitterCalcs."
