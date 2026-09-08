#!/usr/bin/env bash
# Block gh pr create while L1 implementing gates are not satisfied.
set -euo pipefail

input=$(cat)
command=$(echo "$input" | python3 -c "import json,sys; print(json.load(sys.stdin).get('command',''))")

if [[ ! "$command" =~ gh[[:space:]]+pr[[:space:]]+create ]]; then
  echo '{"permission":"allow"}'
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE="$ROOT/.superpowers/pipeline-state.json"

if [[ ! -f "$STATE" ]]; then
  echo '{"permission":"allow"}'
  exit 0
fi

phase=$(python3 -c "import json; print(json.load(open('$STATE')).get('phase',''))")

if [[ "$phase" == "implementing" ]]; then
  if ! "$ROOT/scripts/check-l1-implementing-gate.sh" --exit-implementing >/dev/null 2>&1; then
    echo '{
      "permission": "deny",
      "user_message": "L1 pipeline: cannot open PR during implementing until every plan task has a unique commit and review-clean progress line. Run: scripts/check-l1-implementing-gate.sh --exit-implementing",
      "agent_message": "Blocked gh pr create: implementing gate failed. Complete all tasks serially (one commit + reviewer per task), then run scripts/check-l1-implementing-gate.sh --exit-implementing before branch_review."
    }'
    exit 0
  fi
fi

echo '{"permission":"allow"}'
exit 0
