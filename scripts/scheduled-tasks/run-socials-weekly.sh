#!/usr/bin/env bash
# Socials-enrichment runner — invoked by cron on Linux.
#
# Spins up a non-interactive Claude Code session with the prompt body from
# scripts/scheduled-tasks/socials-weekly-enrichment.md (frontmatter stripped),
# runs it autonomously, logs stdout+stderr to a timestamped file, and emails
# a one-paragraph summary to admin via the project's Proton SMTP creds.
#
# Why a wrapper instead of inlining the prompt in crontab: the prompt is
# ~250 lines and version-controlled. The wrapper keeps cron tidy and gives
# us a single edit point.
#
# Cron entry (install via `crontab -e` for the bunker-admin user):
#   7 9 * * *  /home/bunker-admin/sovpro/scripts/scheduled-tasks/run-socials-weekly.sh
#
# Daily 09:07 local. Off-minute on purpose (not :00) so it doesn't clump
# with the rest of the fleet's hourly tasks at the top of the hour.
#
# (The filename retains the "weekly" suffix from the original design — the
# script itself is cadence-neutral; the cron schedule is what dictates how
# often it fires.)

set -euo pipefail

PROJECT_DIR="/home/bunker-admin/sovpro"
PROMPT_FILE="$PROJECT_DIR/scripts/scheduled-tasks/socials-weekly-enrichment.md"
LOG_DIR="$PROJECT_DIR/docs/runbooks/socials-agent-logs"
LOG_FILE="$LOG_DIR/$(date -u +%Y-%m-%dT%H%M%SZ).log"

# cron's PATH is minimal — make sure docker and claude are findable.
# The user's interactive PATH includes /usr/local/bin and ~/.local/bin
# where these usually live; explicitly include both.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$HOME/.local/bin:$HOME/bin:${PATH:-}"

mkdir -p "$LOG_DIR"

# Quiet exit + clear log line if anything we depend on is missing.
if ! command -v claude >/dev/null 2>&1; then
  echo "$(date -u +%FT%TZ) FATAL: claude CLI not on PATH" >> "$LOG_FILE"
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "$(date -u +%FT%TZ) FATAL: docker CLI not on PATH" >> "$LOG_FILE"
  exit 1
fi
if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "$(date -u +%FT%TZ) FATAL: prompt file missing: $PROMPT_FILE" >> "$LOG_FILE"
  exit 1
fi

# Strip the wiring/setup section above the second `---` divider, plus the
# header before it. What remains is the agent-facing prompt body.
# `awk '/^---$/{i++; next} i>=1'` would include the body verbatim from
# after the FIRST divider in the in-repo file; we want the second since
# the repo file has both an intro and a frontmatter-style divider.
BODY=$(awk '/^---$/{i++; next} i>=1' "$PROMPT_FILE")

cd "$PROJECT_DIR"

# Capture claude's exit status without aborting the email step below.
# Using a tmpfile is the cleanest way to thread the exit code OUT of
# the `{ ... } >> log 2>&1` redirection block, which otherwise swallows
# the inner exit code.
RC_FILE=$(mktemp)

{
  echo "=== socials enrichment scheduled run: $(date -u +%FT%TZ) ==="
  echo "host=$(hostname) user=$(whoami) pwd=$(pwd)"
  echo "prompt: $PROMPT_FILE ($(wc -c < "$PROMPT_FILE") bytes, body $(echo -n "$BODY" | wc -c) bytes)"
  echo "---"
  # acceptEdits is the right shape for autonomous file edits + DB queries
  # via docker exec. WebSearch and WebFetch are required by the prompt and
  # don't need extra flags — they're in the default tool set.
  set +e
  echo "$BODY" | claude -p \
    --model sonnet \
    --permission-mode acceptEdits \
    --add-dir "$PROJECT_DIR"
  CLAUDE_EXIT=$?
  set -e
  echo "$CLAUDE_EXIT" > "$RC_FILE"
  echo "=== exit_code=$CLAUDE_EXIT run_complete: $(date -u +%FT%TZ) ==="
} >> "$LOG_FILE" 2>&1

CLAUDE_EXIT=$(cat "$RC_FILE")
rm -f "$RC_FILE"

# Email a one-paragraph summary to admin@thebunkerops.ca via the
# project's existing Proton SMTP creds (.env). The helper script
# silently skips when SMTP isn't configured, so this is safe on
# fresh installs without credentials.
"$PROJECT_DIR/scripts/scheduled-tasks/send-run-summary.py" "$LOG_FILE" "$CLAUDE_EXIT" >> "$LOG_FILE" 2>&1 || true

# Prune logs older than 12 weeks (we run daily, so this keeps ~3 months of history).
find "$LOG_DIR" -name '*.log' -mtime +84 -delete 2>/dev/null || true

exit "$CLAUDE_EXIT"
