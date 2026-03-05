#!/usr/bin/env bash
set -e

VERSION_FILE="frontend/version.json"

# Create version.json if missing
if [ ! -f "$VERSION_FILE" ]; then
    echo '{"version":1}' > "$VERSION_FILE"
fi

# Extract version number without jq (portable across macOS/Linux/Windows Git Bash)
CURRENT=$(
    grep -Eo '"version"[[:space:]]*:[[:space:]]*[0-9]+' "$VERSION_FILE" \
    | grep -Eo '[0-9]+' \
    | head -n 1 \
    || true
)

if [ -z "$CURRENT" ]; then
    CURRENT=0
fi

# Ensure it's numeric
if ! [[ "$CURRENT" =~ ^[0-9]+$ ]]; then
    CURRENT=0
fi

NEXT=$((CURRENT + 1))

# Write updated version.json
printf '{"version": %s}\n' "$NEXT" > "$VERSION_FILE"

echo "Version bumped: $CURRENT → $NEXT"
