#!/usr/bin/env bash
# The unit run: same selection as the Dockerfile test gate and the CI unit job.
# Anything that calls a real LLM is @pytest.mark.integration and is NOT run here
# (run it by hand: pytest tests/ -m integration).
set -e

RUN_TESTS="${RUN_TESTS:-1}"

if [ "$RUN_TESTS" = "0" ]; then
  echo "⚠️  RUN_TESTS=0 → skipping tests"
  exit 0
fi

echo "🧪 Running unit tests (no LLM calls)..."
OPENAI_API_KEY= TYPESAFE_API_KEY= LANGSMITH_API_KEY= LANGCHAIN_API_KEY= \
LANGCHAIN_TRACING_V2=false TESTS_BLOCK_LLM_NETWORK=1 \
pytest tests/ .claude/skills/promote-to-prod/tests -m "not integration" --disable-warnings --tb=short -ra --continue-on-collection-errors

if command -v node >/dev/null 2>&1; then
  echo "🧪 Running Node frontend tests..."
  node --test tests/frontend/*.test.cjs
else
  echo "⚠️  node not found: skipping tests/frontend/*.test.cjs (CI runs them)"
fi
echo "✅ Tests passed"
