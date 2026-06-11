#!/bin/bash
# QueuePilot setup — installs dependencies and starts the background watcher.
# Run once after cloning: bash setup.sh

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_LABEL="com.queuepilot.watcher"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
PYTHON="$(which python3)"

echo ""
echo "=== QueuePilot Setup ==="
echo ""

# ── 1. Python dependencies ────────────────────────────────────────────────────
echo "Installing Python dependencies..."
pip3 install -r "$REPO_DIR/requirements.txt" --quiet
echo "  ✓ Done"

# ── 2. GitHub CLI ─────────────────────────────────────────────────────────────
if ! command -v gh &>/dev/null; then
    echo ""
    echo "ERROR: GitHub CLI (gh) is required. Install it first:"
    echo "  brew install gh"
    exit 1
fi

if ! gh auth status &>/dev/null; then
    echo ""
    echo "Authenticating GitHub CLI (follow the prompts)..."
    gh auth login
fi
echo "  ✓ GitHub CLI authenticated"

# ── 3. Slack token ────────────────────────────────────────────────────────────
echo ""
read -rp "Enter your SLACK_TOKEN (xoxb-...): " SLACK_TOKEN
if [ -z "$SLACK_TOKEN" ]; then
    echo "ERROR: SLACK_TOKEN is required."
    exit 1
fi

# ── 4. Jira token (optional) ──────────────────────────────────────────────────
read -rp "Enter your JIRA_TOKEN (optional — press Enter to skip): " JIRA_TOKEN

# ── 5. Install LaunchAgent ────────────────────────────────────────────────────
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$REPO_DIR/watch.py</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>SLACK_TOKEN</key>
        <string>$SLACK_TOKEN</string>
        <key>JIRA_TOKEN</key>
        <string>$JIRA_TOKEN</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>WorkingDirectory</key>
    <string>$REPO_DIR</string>

    <key>StandardOutPath</key>
    <string>$REPO_DIR/watcher.log</string>
    <key>StandardErrorPath</key>
    <string>$REPO_DIR/watcher.log</string>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
PLIST

# Unload if already running, then load fresh
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo ""
echo "✅ QueuePilot watcher is running and will start automatically at every login."
echo ""
echo "   Usage : Send '@qmbot dq 2.4-develop' in #pr-queue-dashboard"
echo "           The report appears in the channel automatically."
echo ""
echo "   Logs  : tail -f $REPO_DIR/watcher.log"
echo "   Stop  : launchctl unload $PLIST_PATH"
echo "   Re-run: bash $REPO_DIR/setup.sh"
echo ""
