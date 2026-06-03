#!/usr/bin/env python3
"""
QueuePilot Watcher — polls #pr-queue-dashboard every 60 s and fires
queuepilot.py the moment qmbot posts a new PR queue message.
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

SLACK_TOKEN   = os.getenv("SLACK_TOKEN", "")
CHANNEL       = "C0B400Y1ZU2"
BOT_USER      = "W015DAXESG0"
JIRA_TOKEN    = os.getenv("JIRA_TOKEN", "")
POLL_INTERVAL = 60   # seconds
SCRIPT_DIR    = Path(__file__).parent
STATE_FILE    = SCRIPT_DIR / ".watcher_state.json"
SCRIPT        = SCRIPT_DIR / "queuepilot.py"


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    # First run — start from now so old messages are ignored
    return {"last_processed_ts": f"{time.time():.6f}"}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


def slack_history() -> list:
    r = requests.get(
        "https://slack.com/api/conversations.history",
        headers={"Authorization": f"Bearer {SLACK_TOKEN}"},
        params={"channel": CHANNEL, "limit": 20},
        timeout=15,
    )
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data.get('error')}")
    return data.get("messages", [])


def parse_prs(text: str) -> list[int]:
    return [int(m) for m in re.findall(r"magento2ce[^\|]+?#(\d+)", text)]


def run_queuepilot(prs: list[int]) -> None:
    cmd = [
        sys.executable, str(SCRIPT),
        "2.4-develop",
        "--prs", *[str(n) for n in prs],
        "--jira-token", JIRA_TOKEN,
    ]
    env = {**os.environ, "SLACK_TOKEN": SLACK_TOKEN, "JIRA_TOKEN": JIRA_TOKEN}
    log(f"Running QueuePilot for PRs: {prs}")
    result = subprocess.run(cmd, text=True, env=env, cwd=SCRIPT_DIR)
    if result.returncode != 0:
        log(f"QueuePilot exited with code {result.returncode}")


def main() -> None:
    if not SLACK_TOKEN:
        log("ERROR: SLACK_TOKEN not set. Export it before starting the watcher.")
        sys.exit(1)

    log(f"QueuePilot Watcher started — polling every {POLL_INTERVAL}s")
    state = load_state()
    log(f"Resuming from last processed TS: {state['last_processed_ts']}")

    while True:
        try:
            messages = slack_history()

            for msg in reversed(messages):   # process oldest → newest
                ts   = msg.get("ts", "0")
                user = msg.get("user", "")
                text = msg.get("text", "")

                # Skip already-processed messages
                if ts <= state["last_processed_ts"]:
                    continue

                # Only care about qmbot messages with PR numbers
                if user != BOT_USER:
                    continue

                prs = parse_prs(text)
                if not prs:
                    # Empty queue or non-PR message — mark as seen, skip
                    state["last_processed_ts"] = ts
                    save_state(state)
                    log(f"qmbot message has no PRs (empty queue?), skipping.")
                    continue

                log(f"New qmbot message detected! PRs: {prs}")
                run_queuepilot(prs)   # posts to Slack automatically via SLACK_TOKEN
                state["last_processed_ts"] = ts
                save_state(state)

        except Exception as e:
            log(f"Error during poll: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
