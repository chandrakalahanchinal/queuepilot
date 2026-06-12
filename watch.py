#!/usr/bin/env python3
"""
QueuePilot Watcher — polls #pr-queue-dashboard every 60 s.

Flow:
  1. You (or a teammate) send "@qmbot dq 2.4-develop" in the channel.
  2. qmbot replies with the PR list.
  3. Watcher detects the reply and waits 5 minutes.
  4. Report is generated and posted to the channel.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

SLACK_TOKEN     = os.getenv("SLACK_TOKEN", "")
JIRA_TOKEN      = os.getenv("JIRA_TOKEN", "")
CHANNEL         = "C0B400Y1ZU2"   # #pr-queue-dashboard
BOT_USER        = "W015DAXESG0"   # qmbot
POLL_INTERVAL   = 30              # seconds between polls
TRIGGER_WINDOW  = 600             # seconds qmbot has to respond after "dq" is sent
WAIT_BEFORE_FIRE = 300            # seconds to wait after qmbot replies (5 min)
SCRIPT_DIR      = Path(__file__).parent
STATE_FILE      = SCRIPT_DIR / ".watcher_state.json"
SCRIPT          = SCRIPT_DIR / "queuepilot.py"

TRIGGER_RE = re.compile(r"\bdq\s+2\.4-develop\b", re.IGNORECASE)


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def load_state() -> dict:
    """
    Always start fresh from 'now' so old history is never replayed.
    Keep fire_after_ts if it was set before a restart (e.g. watcher crashed
    mid-wait), but discard it if it's more than 15 minutes overdue.
    """
    now = time.time()
    now_ts = f"{now:.6f}"
    fire_after_ts = None

    if STATE_FILE.exists():
        try:
            saved = json.loads(STATE_FILE.read_text())
            candidate = saved.get("fire_after_ts")
            if candidate:
                overdue = now - float(candidate)
                if overdue < 900:   # less than 15 min overdue — still worth firing
                    fire_after_ts = candidate
        except Exception:
            pass

    return {
        "last_processed_ts": now_ts,   # ignore all Slack history before this moment
        "pending_trigger_ts": None,    # cleared on every restart
        "fire_after_ts": fire_after_ts,
        "qmbot_reply_ts": None,        # ts of qmbot's PR-list message (for thread reply)
    }


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


def run_queuepilot(qmbot_reply_ts: Optional[str] = None) -> None:
    log("Triggering QueuePilot...")
    env = {**os.environ, "SLACK_TOKEN": SLACK_TOKEN, "JIRA_TOKEN": JIRA_TOKEN}
    cmd = [
        sys.executable, str(SCRIPT),
        "2.4-develop",
        "--allure-attempts", "4",
    ]
    if JIRA_TOKEN:
        cmd += ["--jira-token", JIRA_TOKEN]
    if qmbot_reply_ts:
        cmd += ["--reply-to-ts", qmbot_reply_ts]
    result = subprocess.run(cmd, text=True, env=env, cwd=SCRIPT_DIR)
    if result.returncode != 0:
        log(f"QueuePilot exited with code {result.returncode}")
    else:
        log("QueuePilot finished — report posted to qmbot thread.")


def main() -> None:
    if not SLACK_TOKEN:
        log("ERROR: SLACK_TOKEN env var not set. Export it and restart.")
        sys.exit(1)

    log(f"QueuePilot Watcher started — polling every {POLL_INTERVAL}s")
    log("Waiting for '@qmbot dq 2.4-develop' in the channel...")
    state = load_state()
    save_state(state)

    if state.get("fire_after_ts"):
        remaining = float(state["fire_after_ts"]) - time.time()
        if remaining > 0:
            log(f"Resuming — {remaining:.0f}s until scheduled report fires")
        else:
            log("Scheduled report is overdue — will fire on next poll")

    while True:
        try:
            now = time.time()

            # Fire the report if the 5-minute wait has elapsed
            fire_ts = state.get("fire_after_ts")
            if fire_ts and now >= float(fire_ts):
                log("5-minute wait complete — running QueuePilot")
                run_queuepilot(qmbot_reply_ts=state.get("qmbot_reply_ts"))
                state["fire_after_ts"]  = None
                state["qmbot_reply_ts"] = None
                save_state(state)

            messages = slack_history()
            now = time.time()  # refresh after the HTTP call

            for msg in reversed(messages):  # oldest → newest
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
                    # Break so qmbot's reply (if already in this batch) is NOT processed
                    # in the same cycle — avoids instant firing.
                    break

                # qmbot posted — check if it follows a pending trigger
                if user == BOT_USER:
                    pending = state.get("pending_trigger_ts")
                    if pending and (now - float(pending)) <= TRIGGER_WINDOW:
                        if has_prs(text):
                            fire_at = now + WAIT_BEFORE_FIRE
                            log(
                                f"qmbot replied with PRs — "
                                f"report scheduled in {WAIT_BEFORE_FIRE // 60} min"
                            )
                            state["fire_after_ts"]      = f"{fire_at:.6f}"
                            state["pending_trigger_ts"] = None
                            state["qmbot_reply_ts"]     = ts
                        else:
                            log("qmbot replied but no PRs found — nothing to report")
                            state["pending_trigger_ts"] = None
                    else:
                        log("qmbot message ignored — no recent 'dq 2.4-develop' trigger")

                    state["last_processed_ts"] = ts
                    save_state(state)
                    continue

                state["last_processed_ts"] = ts
                save_state(state)

            # Expire stale trigger if qmbot never responded in time
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
