#!/usr/bin/env bash
# Builds the React dashboard and embeds it into the python package.
# Usage: scripts/build_ui.sh   (npm install is run on first use)
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET=better_utils/static

mkdir -p "$(dirname "$TARGET")"

if [ -f frontend/package.json ] && [ -d frontend/src ]; then
    if [ ! -d frontend/node_modules ]; then
        echo "==> npm install (frontend deps)"
        (cd frontend && npm install --no-fund --no-audit)
    fi
    echo "==> npm run build (dashboard)"
    (cd frontend && npm run build)
    rm -rf "$TARGET"
    mkdir -p "$TARGET"
    cp -r frontend/dist/. "$TARGET/"
else
    echo "==> frontend sources missing; installing a placeholder dashboard"
    rm -rf "$TARGET"
    mkdir -p "$TARGET"
    cat > "$TARGET/index.html" <<'HTML'
<!doctype html><meta charset="utf-8">
<title>Better Utils — no dashboard bundled</title>
<body style="font-family: system-ui, sans-serif; padding: 3rem; color: #334155">
  <h1>Better Utils — no dashboard bundled</h1>
  <p>This wheel was built without the frontend sources.</p>
  <p>Rebuild with the UI:</p>
  <pre>frontend$ npm install &amp;&amp; npm run build &amp;&amp; ../scripts/build_ui.sh</pre>
</body>
HTML
fi

echo "==> dashboard files in $TARGET:"
ls "$TARGET" | sed 's/^/    /'
