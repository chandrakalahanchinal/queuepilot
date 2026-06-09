# QueuePilot

Evidence-based triage of Magento functional test failures (CE / EE / B2B / SVC) for PRs in the `2.4-develop` queue.

---

## How it works

1. You send `@qmbot dq 2.4-develop` in `#pr-queue-dashboard`
2. Once qmbot replies with the PR list, run `/queuepilot 2.4-develop` in Claude Code
3. QueuePilot reads qmbot's response, analyzes all PRs, generates an HTML dashboard, and posts the summary back to `#pr-queue-dashboard`

---

## Team Setup

Follow these steps once on each machine.

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

---

## Usage

### Via Claude Code slash command (recommended)

```
/queuepilot 2.4-develop
```

Make sure you've already sent `@qmbot dq 2.4-develop` in the channel and qmbot has replied before running this.

### Direct CLI

```bash
export SLACK_TOKEN=xoxb-your-token-here

# Read qmbot's latest response and generate report
python3 queuepilot.py 2.4-develop

# Pass PR numbers directly (no Slack required)
python3 queuepilot.py 2.4-develop --prs 10737 10740 10741

# With Jira ticket lookup
python3 queuepilot.py 2.4-develop --jira-token <token>
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
  --repo OWNER/REPO   GitHub repo             (default: magento-commerce/magento2ce)
  --output FILE       Output HTML path        (default: reports/queuepilot-{branch}-{date}-{n}.html)
  --no-slack          Skip posting results to Slack
  --prs N [N ...]     Skip Slack, use these PR numbers directly
  --jira-token TOKEN  Jira personal access token for ticket lookup
  --allure-attempts N Max retries for Allure data (default: 4, ~2 min)
```

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SLACK_TOKEN` | Slack bot token (`xoxb-...`) — reads qmbot response and posts results | required unless `--prs` |
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
