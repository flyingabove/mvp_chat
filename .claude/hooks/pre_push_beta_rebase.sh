#!/usr/bin/env bash
# PreToolUse hook (Bash matcher, filtered to `git push*` via settings.json's
# "if"). Before any push that targets the beta branch, run
# `git pull --rebase origin beta` so the push always carries the latest
# beta history (CLAUDE.md workflow #7: multiple agents push to beta
# concurrently). If the rebase hits conflicts (or fails for any other
# reason - dirty tree, network, etc.), block the push instead of letting
# it proceed against a stale base. This hook never resolves conflicts
# itself - CLAUDE.md explicitly forbids blindly picking --ours/--theirs -
# it only stops the push so a human or the agent resolves them by hand,
# then retries.
#
# Target detection parses the actual `git push` segment(s) of the command
# (2026-09-24 fix): the old `*push*beta*` glob matched "beta" ANYWHERE in the
# command, so `git push origin prod && git checkout beta` rebased the prod
# branch onto beta mid-release. Now beta is the target only when a refspec's
# destination is beta, or when no refspec is given and the current branch is
# beta. A beta-targeted push from a checked-out `prod` branch is denied
# instead of rebasing prod history.
#
# Uses `python` (stdlib only) instead of jq - jq is not installed on this
# project's Windows dev machines.
set -u

input="$(cat)"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
decision="$(printf '%s' "$input" | BRANCH="$branch" python "$(dirname "$0")/push_target.py")"

deny() {
  REASON="$1" python -c "
import json, os
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': os.environ['REASON'],
    }
}))
"
  exit 0
}

case "$decision" in
  skip)
    echo '{}'
    exit 0
    ;;
  deny-prod)
    deny "Refusing to push to beta from the checked-out prod branch: the pre-push sync would rebase prod history onto beta. Switch to the beta branch (git checkout beta) and push from there."
    ;;
esac

pull_output="$(git pull --rebase origin beta 2>&1)"
rc=$?

if [ $rc -ne 0 ]; then
  deny "git pull --rebase origin beta failed before push - resolve by hand (git status; fix conflicted files; git rebase --continue - never blindly take --ours/--theirs, see AI_LEARNINGS_PUSHING_CODE.md), then retry the push. Output:
$(printf '%s' "$pull_output" | tail -c 1200)"
fi

echo '{}'
exit 0
