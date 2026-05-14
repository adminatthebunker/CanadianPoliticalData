#!/usr/bin/env python3
"""Email a one-paragraph summary of a scheduled enrichment run.

Invoked by run-socials-weekly.sh after the headless Claude Code
session finishes. Reads the log file, extracts the agent's own summary
(everything after the final "socials enrichment complete" line that
the prompt's safety-rule section instructs the agent to emit), and
sends it to the admin via the project's existing Proton SMTP setup.

Why not just rely on cron's MAILTO: the user's crontab pins MAILTO=""
to suppress fleet mail. We want one targeted email per run, not the
entire stdout+stderr stream cron would otherwise mail.

Exits 0 on success, 0 on "SMTP not configured" (silent skip — runs
without email are fine), 1 on email send failure.
"""

from __future__ import annotations

import os
import smtplib
import sys
from email.mime.text import MIMEText
from email.utils import formatdate
from pathlib import Path


def load_env(env_path: Path) -> None:
    """Source .env into os.environ for SMTP_* lookups. Lines starting
    with '#' or blank are ignored; values are taken as-is (no quote
    stripping — Proton creds don't have weird chars)."""
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        # Don't clobber env vars the cron context may have already set.
        os.environ.setdefault(key.strip(), val.strip())


def build_subject(exit_code: int, log_path: Path) -> str:
    pass_fail = "✓" if exit_code == 0 else "✗"
    return f"[CPD socials enrichment] {pass_fail} run {log_path.stem} (exit={exit_code})"


def build_body(log_path: Path, exit_code: int) -> str:
    """Read the log, surface the agent-emitted summary if present,
    else fall back to the last 80 lines."""
    if not log_path.exists():
        return f"Log file missing: {log_path}\nExit code: {exit_code}\n"
    content = log_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()

    # Look for the agent's signal line. The prompt instructs the agent
    # to print this exact phrase on completion; grep for it as the
    # divider between the agent's verbose reasoning and the canonical
    # one-line summary it produces.
    marker_idx = None
    for i, ln in enumerate(lines):
        if "socials enrichment complete" in ln:
            marker_idx = i
            break

    if marker_idx is not None:
        # Take from the marker onward — that's the agent's report.
        summary = "\n".join(lines[marker_idx:])
    else:
        # No marker found (run failed before summary was emitted, or
        # claude -p errored out). Surface the tail for diagnosis.
        summary = "\n".join(lines[-80:])

    header = (
        f"Run: {log_path.name}\n"
        f"Exit code: {exit_code}\n"
        f"Log path: {log_path}\n"
        f"Full log line count: {len(lines)}\n"
        f"---\n"
    )
    return header + summary + "\n"


def smtp_configured() -> bool:
    return bool(
        os.environ.get("SMTP_HOST")
        and os.environ.get("SMTP_USERNAME")
        and os.environ.get("SMTP_PASSWORD")
        and os.environ.get("SMTP_FROM")
    )


def send(to_addr: str, subject: str, body: str) -> None:
    """Blocking SMTP send via STARTTLS. Same shape as alerts_worker's
    Proton sender so the operator can debug both with the same
    creds + dashboard."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.ehlo()
        s.starttls()
        s.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        s.sendmail(os.environ["SMTP_FROM"], [to_addr], msg.as_string())


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: send-run-summary.py <log_path> <exit_code>", file=sys.stderr)
        return 2

    log_path = Path(argv[1])
    try:
        exit_code = int(argv[2])
    except ValueError:
        exit_code = -1

    # Source SMTP creds from the project .env (cron's environment
    # doesn't inherit anything from the user's interactive shell).
    project_env = Path("/home/bunker-admin/sovpro/.env")
    load_env(project_env)

    if not smtp_configured():
        print("SMTP not configured — skipping email send", file=sys.stderr)
        return 0  # Silent skip — not a failure condition.

    to_addr = os.environ.get("CPD_OPS_EMAIL", "admin@thebunkerops.ca")
    subject = build_subject(exit_code, log_path)
    body = build_body(log_path, exit_code)

    try:
        send(to_addr, subject, body)
    except Exception as e:  # noqa: BLE001
        print(f"SMTP send failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print(f"emailed run summary to {to_addr} (subject: {subject})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
