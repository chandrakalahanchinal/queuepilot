#!/usr/bin/env python3
"""
QueuePilot Watcher — polls #pr-queue-dashboard every 60 s.

Flow:
  1. You send "@qmbot dq 2.4-develop" in the channel.
  2. qmbot replies with the PR list.
  3. This watcher detects the reply and runs queuepilot.py automatically,
     which generates the report and posts it back to the channel.
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
JIRA_TOKEN     = os.getenv("JIRA_TOKEN", "")
CHANNEL        = "C0B400Y1ZU2"   # #pr-queue-dashboard
BOT_USER       = "W015DAXESG0"   # qmbot
POLL_INTERVAL  = 30              # seconds between polls
TRIGGER_WINDOW = 600             # seconds qmbot has to respond after "dq" is sent
SCRIPT_DIR     = Path(__file__).parent
STATE_FILE     = SCRIPT_DIR / ".watcher_state.json"
SCRIPT         = SCRIPT_DIR / "queuepilot.py"

TRIGGER_RE = re.compile(r"\bdq\s+2\.4-develop\b", re.IGNORECASE)


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


def has_prs(text: str) -> bool:
    return bool(re.search(r"github\.com/magento-commerce/[\w.-]+/pull/\d+", text))


def run_queuepilot() -> None:
    log("Triggering QueuePilot...")
    env = {**os.environ, "SLACK_TOKEN": SLACK_TOKEN, "JIRA_TOKEN": JIRA_TOKEN}
    cmd = [
        sys.executable, str(SCRIPT),
        "2.4-develop",
        "--allure-attempts", "4",
    ]
    if JIRA_TOKEN:
        cmd += ["--jira-token", JIRA_TOKEN]
    result = subprocess.run(cmd, text=True, env=env, cwd=SCRIPT_DIR)
    if result.returncode != 0:
        log(f"QueuePilot exited with code {result.returncode}")
    else:
        log("QueuePilot finished — report posted to channel.")


def main() -> None:
    if not SLACK_TOKEN:
        log("ERROR: SLACK_TOKEN env var not set. Export it and restart.")
        sys.exit(1)

    log(f"QueuePilot Watcher started — polling every {POLL_INTERVAL}s")
    log("Waiting for '@qmbot dq 2.4-develop' in the channel...")
    state = load_state()
    log(f"Resuming from ts={state['last_processed_ts']}")

    while True:
        try:
            messages = slack_history()
            now = time.time()

            for msg in reversed(messages):  # process oldest → newest
                ts   = msg.get("ts", "0")
                user = msg.get("user", "")
                text = msg.get("text", "")

                if ts <= state["last_processed_ts"]:
                    continue

                # Someone (not qmbot) sent a message containing "dq 2.4-develop"
                if user != BOT_USER and TRIGGER_RE.search(text):
                    log(f"Trigger detected from user {user} — waiting for qmbot reply...")
                    state["pending_trigger_ts"] = ts
                    state["last_processed_ts"]  = ts
                    save_state(state)
                    continue

                # qmbot posted — check if it's a reply to our pending trigger
                if user == BOT_USER:
                    pending = state.get("pending_trigger_ts")
                    if pending and (now - float(pending)) <= TRIGGER_WINDOW:
                        if has_prs(text):
                            log(f"qmbot replied with PRs — running QueuePilot")
                            run_queuepilot()
                            state["pending_trigger_ts"] = None
                        else:
                            log("qmbot replied but no PRs found (empty queue?)")
                    else:
                        log("qmbot message ignored — no recent 'dq 2.4-develop' trigger")

                    state["last_processed_ts"] = ts
                    save_state(state)
                    continue

                state["last_processed_ts"] = ts
                save_state(state)

            # Expire stale trigger if qmbot never responded
            pending = state.get("pending_trigger_ts")
            if pending and (now - float(pending)) > TRIGGER_WINDOW:
                log("Trigger expired — qmbot did not respond in time")
                state["pending_trigger_ts"] = None
                save_state(state)

        except Exception as e:
            log(f"Poll error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
