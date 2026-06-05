#!/usr/bin/env python3
"""
QueuePilot Watcher — polls #pr-queue-dashboard every 60 s.
Triggers queuepilot.py only when someone sends "@qmbot dq 2.4-develop"
in the channel and qmbot responds with a PR list.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

SLACK_TOKEN    = os.getenv("SLACK_TOKEN", "")
CHANNEL        = "C0B400Y1ZU2"
BOT_USER       = "W015DAXESG0"
JIRA_TOKEN     = os.getenv("JIRA_TOKEN", "")
POLL_INTERVAL  = 60    # seconds
TRIGGER_WINDOW = 600   # seconds: qmbot must respond within 10 min of the dq command
SCRIPT_DIR     = Path(__file__).parent
STATE_FILE     = SCRIPT_DIR / ".watcher_state.json"
SCRIPT         = SCRIPT_DIR / "queuepilot.py"

# Matches "dq 2.4-develop" in a message (with optional @qmbot mention before it)
TRIGGER_RE = re.compile(r"dq\s+2\.4-develop", re.IGNORECASE)


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_processed_ts": f"{time.time():.6f}", "pending_trigger_ts": None}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


def slack_history() -> list:
    r = requests.get(
        "https://slack.com/api/conversations.history",
        headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
        params={"channel": CHANNEL, "limit": 30},
        timeout=15,
    )
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data.get('error')}")
    return data.get("messages", [])


def parse_prs(text: str) -> list[dict]:
    seen: set = set()
    results = []
    for m in re.finditer(r"github\.com/(magento-commerce/[\w.-]+)/pull/(\d+)", text):
        key = (m.group(1), int(m.group(2)))
        if key not in seen:
            seen.add(key)
            results.append({"repo": m.group(1), "pr_number": int(m.group(2))})
    return results


def run_queuepilot(prs: list[dict]) -> None:
    log(f"Running QueuePilot (--read-only) for {len(prs)} PR(s) across all repos")
    env = {**os.environ, "SLACK_TOKEN": SLACK_TOKEN, "JIRA_TOKEN": JIRA_TOKEN}
    cmd = [
        sys.executable, str(SCRIPT),
        "2.4-develop",
        "--read-only",
        "--jira-token", JIRA_TOKEN,
        "--allure-attempts", "15",   # ~7 min — watcher runs in background, no rush
    ]
    result = subprocess.run(cmd, text=True, env=env, cwd=SCRIPT_DIR)
    if result.returncode != 0:
        log(f"QueuePilot exited with code {result.returncode}")


def main() -> None:
    if not SLACK_TOKEN:
        log("ERROR: SLACK_TOKEN not set. Export it before starting the watcher.")
        sys.exit(1)

    log(f"QueuePilot Watcher started — polling every {POLL_INTERVAL}s")
    log("Trigger: '@qmbot dq 2.4-develop' message in channel")
    state = load_state()
    log(f"Resuming from last processed TS: {state['last_processed_ts']}")

    while True:
        try:
            messages = slack_history()
            now = time.time()

            for msg in reversed(messages):   # oldest → newest
                ts   = msg.get("ts", "0")
                user = msg.get("user", "")
                text = msg.get("text", "")

                if ts <= state["last_processed_ts"]:
                    continue

                # User sent "@qmbot dq 2.4-develop" — arm the trigger
                if user != BOT_USER and TRIGGER_RE.search(text):
                    log(f"Trigger detected: 'dq 2.4-develop' from user {user}")
                    state["pending_trigger_ts"] = ts
                    state["last_processed_ts"] = ts
                    save_state(state)
                    continue

                # qmbot responded — only act if we have a recent pending trigger
                if user == BOT_USER:
                    pending = state.get("pending_trigger_ts")
                    if pending and (now - float(pending)) <= TRIGGER_WINDOW:
                        prs = parse_prs(text)
                        if prs:
                            log(f"qmbot responded with PRs after 'dq 2.4-develop': {[(p['repo'], p['pr_number']) for p in prs]}")
                            run_queuepilot(prs)
                            state["pending_trigger_ts"] = None  # reset until next dq command
                        else:
                            log("qmbot responded but no PRs found (empty queue?)")
                    else:
                        log(f"Ignoring qmbot message — no recent 'dq 2.4-develop' trigger")

                    state["last_processed_ts"] = ts
                    save_state(state)
                    continue

                # Any other message — just advance the cursor
                state["last_processed_ts"] = ts
                save_state(state)

            # Expire stale pending trigger
            pending = state.get("pending_trigger_ts")
            if pending and (now - float(pending)) > TRIGGER_WINDOW:
                log("Pending trigger expired (qmbot did not respond in time)")
                state["pending_trigger_ts"] = None
                save_state(state)

        except Exception as e:
            log(f"Error during poll: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
