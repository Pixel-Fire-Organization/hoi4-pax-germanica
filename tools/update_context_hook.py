#!/usr/bin/env python3
"""Claude Code *Stop* hook: remind the agent to refresh the auto-maintained status block.

When a run has changed the repository, this nudges the agent to update the
"Project Status (auto-maintained)" section of `.github/copilot-instructions.md` before it
finishes, so the standing context never drifts from the actual state of the project.

Design goals:
  * Fail-safe   — any error (no git, bad input, ...) allows the stop. A hook must never wedge a run.
  * No loops    — honours `stop_hook_active`, so it reminds at most once per stop cycle.
  * No false nags — silent on read-only runs (clean tree), and it ignores edits to the
                    instruction files themselves (otherwise updating them would re-trigger it).

Communication follows the Claude Code hook contract: to ask the agent to keep going, print
`{"decision": "block", "reason": "..."}` to stdout and exit 0. To allow the stop, print nothing.
"""

import json
import os
import subprocess
import sys

# Paths (relative to the repo root) whose changes should NOT trigger a reminder.
IGNORED = {".github/copilot-instructions.md", "CLAUDE.md"}

REASON = (
    "This run changed the repository. Before finishing, refresh the "
    "'Project Status (auto-maintained)' section of .github/copilot-instructions.md "
    "(update 'Last updated', the document inventory, the current-story summary, recent "
    "changes, and next-up) so it matches the new state, then stop. Keep it terse and do "
    "not contradict docs/. If nothing material changed, you may stop without editing."
)


def allow_stop() -> None:
    """Allow the agent to stop: emit nothing, exit cleanly."""
    sys.exit(0)


def main() -> None:
    # 1. Parse the hook payload from stdin; on any trouble, allow the stop.
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow_stop()

    # 2. Already continuing because of this hook? Don't remind again — avoids any loop.
    if payload.get("stop_hook_active"):
        allow_stop()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 3. What changed this working tree? If git is unavailable, allow the stop.
    try:
        result = subprocess.run(
            ["git", "-C", repo_root, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        allow_stop()

    if result.returncode != 0:
        allow_stop()

    # 4. Reduce porcelain output to the set of changed paths, dropping the ignored ones.
    changed = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:]                      # strip the two-char status + the space
        if " -> " in path:                   # renames: "old -> new" — keep the destination
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"').replace("\\", "/")
        if path and path not in IGNORED:
            changed.append(path)

    # 5. Nothing material changed → silent. Otherwise, nudge the agent to update the file.
    if not changed:
        allow_stop()

    print(json.dumps({"decision": "block", "reason": REASON}))
    sys.exit(0)


if __name__ == "__main__":
    main()
