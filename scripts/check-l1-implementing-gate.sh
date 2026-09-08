#!/usr/bin/env bash
# Validate L1 implementing phase exit gates (unique per-task commits, no backfill).
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
STATE_FILE="$ROOT/.superpowers/pipeline-state.json"
PROGRESS_FILE="$ROOT/.superpowers/sdd/progress.md"
MODE="${1:-}"

if [[ ! -f "$STATE_FILE" ]]; then
  echo "check-l1-implementing-gate: no pipeline state (OK)"
  exit 0
fi

exec python3 - "$STATE_FILE" "$PROGRESS_FILE" "$MODE" <<'PY'
import json
import re
import subprocess
import sys
from pathlib import Path


def report(errors: list[str]) -> None:
    if not errors:
        print("check-l1-implementing-gate: PASS")
        return
    print("check-l1-implementing-gate: FAIL", file=sys.stderr)
    for item in errors:
        print(f"  - {item}", file=sys.stderr)


state_path = Path(sys.argv[1])
progress_path = Path(sys.argv[2])
mode = sys.argv[3] if len(sys.argv) > 3 else ""

if mode != "--exit-implementing":
    print("Usage: check-l1-implementing-gate.sh --exit-implementing", file=sys.stderr)
    sys.exit(2)

state = json.loads(state_path.read_text())
phase = state.get("phase", "")

if phase != "implementing":
    print(f"OK: phase is {phase!r}, not implementing")
    sys.exit(0)

implementing = state.get("implementing") or {}
plan_path = state.get("plan_path")
total = int(implementing.get("total_tasks") or 0)
completed = list(implementing.get("completed_tasks") or [])
next_task = int(implementing.get("next_task") or 1)
errors: list[str] = []

if total <= 0:
    errors.append("implementing.total_tasks is missing or zero")

if plan_path:
    plan_file = Path(plan_path)
    if not plan_file.is_file():
        plan_file = state_path.parent.parent / plan_path
    if plan_file.is_file():
        plan_tasks = len(
            re.findall(r"^### Task \d+:", plan_file.read_text(), re.MULTILINE)
        )
        if plan_tasks and plan_tasks != total:
            errors.append(
                f"plan has {plan_tasks} tasks but implementing.total_tasks={total}"
            )
    else:
        errors.append(f"plan file not found: {plan_path}")
else:
    errors.append("plan_path is not set in pipeline-state.json")

if not progress_path.is_file():
    errors.append(f"missing progress ledger: {progress_path}")
    report(errors)
    sys.exit(1)

progress_text = progress_path.read_text()
line_re = re.compile(
    r"^Task (\d+): complete \(commits ([0-9a-f]{7,40})\.\.([0-9a-f]{7,40}), review clean\)\s*$",
    re.MULTILINE,
)
matches = line_re.findall(progress_text)

if len(matches) != total:
    errors.append(
        f"progress has {len(matches)} valid complete lines, expected {total}"
    )

if re.search(r"\bHEAD\b", progress_text):
    errors.append("progress.md must not reference HEAD; use full commit shas")

heads = [head for _, _, head in matches]
if len(heads) != len(set(heads)):
    errors.append(
        "duplicate head commits across tasks — batch backfill or single-commit bypass detected"
    )

task_nums = sorted(int(n) for n, _, _ in matches)
if task_nums and task_nums != list(range(1, len(task_nums) + 1)):
    errors.append(f"task numbers not contiguous from 1: {task_nums}")

for task_num, base, head in matches:
    if base == head:
        errors.append(f"Task {task_num}: base and head commit are identical")
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", base, head],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        errors.append(f"Task {task_num}: base {base} is not ancestor of head {head}")

for earlier, later in zip(heads, heads[1:], strict=False):
    if earlier == later:
        errors.append(f"tasks share commit {earlier}")
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", earlier, later],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        errors.append(
            f"task head {later} is not descended from prior task head {earlier}"
        )

if len(completed) != total:
    errors.append(
        f"completed_tasks has {len(completed)} entries, expected {total}"
    )

if next_task != total + 1:
    errors.append(f"next_task is {next_task}, expected {total + 1}")

report(errors)
sys.exit(1 if errors else 0)
PY
