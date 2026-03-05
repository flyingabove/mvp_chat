#!/usr/bin/env bash
set -e

RUN_TESTS="${RUN_TESTS:-1}"

if [ "$RUN_TESTS" = "0" ]; then
  echo "⚠️  RUN_TESTS=0 → skipping tests"
  exit 0
fi

echo "🧪 Running backend tests..."
pytest tests/backend
echo "✅ Tests passed"
