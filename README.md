# QueuePilot

Evidence-based triage of Magento functional test failures (CE / EE / B2B / SVC) for PRs in the `2.4-develop` queue. Runs as a real-time Slack watcher — as soon as `@qmbot` posts a PR list, QueuePilot posts the failure dashboard back to the channel automatically.

---

## Team Setup

Follow these steps once on each machine where you want to use QueuePilot.

### 1. Prerequisites

| Tool | Install | Verify |
|------|---------|--------|
| Python 3.10+ | [python.org](https://www.python.org/downloads/) | `python3 --version` |
| GitHub CLI | `brew install gh` | `gh --version` |
| Claude Code | [claude.ai/code](https://claude.ai/code) | `claude --version` |

### 2. Clone the repo

```bash
git clone https://github.com/chandrakalahanchinal/queuepilot.git
cd queuepilot
pip install -r requirements.txt
```

### 3. Authenticate GitHub CLI

```bash
gh auth login
# Select: GitHub.com → HTTPS → Login with a web browser
```

### 4. Set up the slash command

```bash
mkdir -p ~/.claude/commands
cp .claude/commands/queuepilot.md ~/.claude/commands/queuepilot.md
```

Open `~/.claude/commands/queuepilot.md` and replace `REPO_PATH` with your absolute clone path (`pwd` inside the repo).

### 5. Connect Slack in Claude Code

1. Open Claude Code → **Settings** → **Integrations** → connect **Slack**
2. If `#pr-queue-dashboard` is private, invite the bots once from inside the channel:
   ```
   /invite @slack_connector
   /invite @qmbot
   ```

### 6. Pre-approve shell commands (recommended)

```bash
mkdir -p .claude
cat > .claude/settings.local.json << 'EOF'
{
  "permissions": {
    "allow": [
      "mcp__claude_ai_Slack__slack_send_message",
      "mcp__claude_ai_Slack__slack_read_channel",
      "Bash"
    ]
  },
  "env": {
    "JIRA_TOKEN": "<your-jira-token>"
  }
}
EOF
```

### 7. Start the real-time watcher (recommended)

The watcher polls `#pr-queue-dashboard` every 60 seconds. When `@qmbot` posts a PR list, it immediately runs QueuePilot and posts the dashboard back to Slack — no manual trigger needed.

```bash
# Copy and load the LaunchAgent (runs at login, restarts automatically)
cp launchagent/com.queuepilot.watcher.plist ~/Library/LaunchAgents/
```

Edit `~/Library/LaunchAgents/com.queuepilot.watcher.plist` and fill in your `SLACK_TOKEN` and `JIRA_TOKEN`, then:

```bash
launchctl load ~/Library/LaunchAgents/com.queuepilot.watcher.plist
```

Check it's running:
```bash
tail -f watcher.log
```

Stop it:
```bash
launchctl unload ~/Library/LaunchAgents/com.queuepilot.watcher.plist
```

### 8. Run it manually (Claude Code slash command)

```bash
cd /path/to/queuepilot
claude
```

Then type:

```
/queuepilot 2.4-develop
```

Claude will post to Slack, fetch all PR failures, generate an HTML dashboard, open it in your browser, and post the full summary to `#pr-queue-dashboard` so the whole team sees it instantly.

---

## What it does

1. **Watches** `#pr-queue-dashboard` for `@qmbot` responses (real-time watcher) **or** posts `@qmbot dq <branch>` and reads the reply (slash command)
2. Fetches GitHub check-run results for every PR in parallel (up to 5 at once)
3. Extracts failing test names from Allure reports (CE / EE / B2B) with up to 8 retries
4. Looks up ACQE Jira tickets for each failing test by name
5. Checks Semantic Version Checker status
6. Generates a self-contained **HTML dashboard** and opens it in your browser
7. Saves the report to `reports/` **and** `~/Downloads/`
8. Posts a formatted summary to `#pr-queue-dashboard` with per-PR failures and Jira ticket links

---

## How the watcher works

```
watch.py (runs in background via LaunchAgent)
    │
    ├── Every 60 seconds: poll #pr-queue-dashboard
    │
    ├── New qmbot message with PRs? → run queuepilot.py --prs <n> ...
    │                                       │
    │                                       ├── Fetch GitHub check-runs
    │                                       ├── Download Allure test data
    │                                       ├── Look up Jira tickets
    │                                       ├── Generate HTML report
    │                                       └── Post summary to Slack ✅
    │
    └── No new message or already processed? → skip
```

---

## Usage without Claude Code

### Pass PR numbers directly (no Slack needed)

```bash
python3 queuepilot.py 2.4-develop --prs 10737 10740 10741
```

### With Jira ticket lookup

```bash
python3 queuepilot.py 2.4-develop --prs 10737 --jira-token <token>
```

### Full auto flow via Slack (requires SLACK_TOKEN)

```bash
export SLACK_TOKEN=xoxb-your-token-here
python3 queuepilot.py 2.4-develop
```

### Read-only mode (Slack message already sent)

```bash
export SLACK_TOKEN=xoxb-your-token-here
python3 queuepilot.py 2.4-develop --read-only
```

---

## All options

```
python3 queuepilot.py <branch> [options]

positional:
  branch              Queue branch name, e.g. 2.4-develop

options:
  --channel ID        Slack channel ID        (default: C0B400Y1ZU2)
  --bot ID            Slack bot user ID       (default: W015DAXESG0)
  --cmd CMD           Bot command             (default: dq)
  --repo OWNER/REPO   GitHub repo             (default: magento-commerce/magento2ce)
  --output FILE       Output HTML path        (default: reports/queuepilot-{branch}-{date}-{n}.html)
  --read-only         Read latest qmbot response, don't post
  --prs N [N ...]     Skip Slack, use these PR numbers directly
  --jira-token TOKEN  Jira personal access token for ticket lookup
```

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SLACK_TOKEN` | Slack bot token (`xoxb-...`) — enables Slack mode and auto-posting | required for Slack mode |
| `JIRA_TOKEN` | Jira personal access token — enables ticket lookup | optional |
| `SLACK_CHANNEL` | Override default channel ID | `C0B400Y1ZU2` |
| `SLACK_BOT_ID` | Override default bot user ID | `W015DAXESG0` |
| `GITHUB_REPO` | Override GitHub repo slug | `magento-commerce/magento2ce` |

---

## Dashboard sections

Each HTML report contains:

1. **Stats bar** — PR count and unique failing test count (deduplicated across editions)
2. **Queue summary table** — all PRs at a glance with CE / EE / B2B / SVC badges
3. **All Failing Tests table** — every unique failing test aggregated across all PRs and editions, sorted by fail frequency, with Jira ticket links
4. **Per-PR failure cards** — 3-column layout (CE | EE | B2B) with full test names, Jira badges, Allure links, and Jenkins links

Reports are saved to:
- `reports/queuepilot-2.4-develop-YYYY-MM-DD-N.html`
- `~/Downloads/queuepilot-2.4-develop-YYYY-MM-DD-N.html`

## Slack summary format

After every run, a message is posted to `#pr-queue-dashboard`:

```
🐛 QueuePilot — `2.4-develop`
*2 PR(s)* in queue · *7 unique failing test(s)*

*#10758* [Support Tier-4 flowers] — thiaramus
CE: 1 FAIL | EE: 4 FAIL | B2B: 6 FAIL
  • `AdminUserSetStatusForEachSourceItemTest` → ACQE-9629 (Tech Analysis)
  • `StorefrontCheckTermsAndConditionIsPresentInPaymentPageTest` → ACQE-10249 (Options Queue)
  ...
```
