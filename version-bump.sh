#!/bin/bash
set -e

VERSION_FILE="frontend/version.json"

# Create version.json if missing
if [ ! -f "$VERSION_FILE" ]; then
    echo '{"version":1}' > "$VERSION_FILE"
fi

# Extract number
CURRENT=$(jq -r '.version' "$VERSION_FILE" 2>/dev/null || echo "0")

# Ensure it's numeric
if ! [[ "$CURRENT" =~ ^[0-9]+$ ]]; then
    CURRENT=0
fi

NEXT=$((CURRENT + 1))

# Write updated version.json
echo "{\"version\": $NEXT}" > "$VERSION_FILE"

echo "Version bumped: $CURRENT → $NEXT"
