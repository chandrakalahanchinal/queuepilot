# QueuePilot

Evidence-based triage of Magento functional test failures (CE / EE / B2B / SVC) for PRs in the `2.4-develop` queue.

Inspired by [flakebuster-agent](https://github.com/OneAdobe/flakebuster-agent).

---

## Team Setup

Follow these steps once on each machine where you want to use QueuePilot.

### 1. Prerequisites

Install these tools before proceeding:

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

QueuePilot uses `gh` to fetch PR check-run results from GitHub.

```bash
gh auth login
# Select: GitHub.com → HTTPS → Login with a web browser
```

Verify it works:

```bash
gh api user --jq .login
# Should print your GitHub username
```

### 4. Set up the slash command

Copy the slash command file to your Claude user commands folder:

```bash
# macOS / Linux
mkdir -p ~/.claude/commands
cp .claude/commands/queuepilot.md ~/.claude/commands/queuepilot.md
```

Open the copied file and replace `REPO_PATH` with the absolute path to where you cloned the repo. Find your path with:

```bash
pwd   # run this inside the queuepilot directory
```

Then edit `~/.claude/commands/queuepilot.md` — find the line that reads:

```
python3 REPO_PATH/queuepilot.py $ARGUMENTS --prs <pr1> <pr2> ...
```

Replace `REPO_PATH` with your actual path, for example:

```
python3 /Users/yourname/queuepilot/queuepilot.py $ARGUMENTS --prs <pr1> <pr2> ...
```

### 5. Connect Slack in Claude Code

QueuePilot posts to Slack and reads the PR list through Claude Code's Slack integration — no `SLACK_TOKEN` env var needed.

1. Open Claude Code → **Settings** → **Integrations** → connect **Slack**
2. If the `#pr-queue-dashboard` channel is private, invite the bots once from inside that channel:
   ```
   /invite @slack_connector
   /invite @qmbot
   ```

### 6. Allow Bash commands without prompts (recommended)

Create a local settings file inside the repo to pre-approve the shell commands QueuePilot needs:

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
  }
}
EOF
```

This file is gitignored and only affects your local session.

### 7. Run it

Open Claude Code from inside the `queuepilot` directory:

```bash
cd /path/to/queuepilot
claude
```

Then type:

```
/queuepilot 2.4-develop
```

Claude will post to Slack, fetch all PR failures, generate an HTML dashboard, open it in your browser, and print a per-PR summary in chat.

Reports are saved to `reports/` as `queuepilot-2.4-develop-YYYY-MM-DD-N.html`.

---

## What it does

1. Posts `@qmbot dq <branch>` to `#pr-queue-dashboard` and reads the PR list
2. Fetches GitHub check-run results for every PR in parallel
3. Extracts failing test names from Allure reports (CE / EE / B2B)
4. Checks Semantic Version Checker status
5. Generates a self-contained **HTML dashboard** and opens it in your browser
6. Prints a per-PR failure summary directly in Claude Code chat

---

## Usage without Claude Code

### Pass PR numbers directly (no Slack needed)

```bash
python3 queuepilot.py 2.4-develop --prs 10737 10740 10741
```

### Full auto flow via Slack (requires SLACK_TOKEN)

```bash
export SLACK_TOKEN=xoxb-your-token-here
python3 queuepilot.py 2.4-develop
```

### Read-only mode (you already sent the Slack message)

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
  --channel ID        Slack channel ID        (default: C0B400Y1ZU2 = #pr-queue-dashboard)
  --bot ID            Slack bot user ID       (default: W015DAXESG0 = qmbot)
  --cmd CMD           Bot command             (default: dq)
  --repo OWNER/REPO   GitHub repo             (default: magento-commerce/magento2ce)
  --output FILE       Output HTML path        (default: reports/queuepilot-{branch}-{date}-{n}.html)
  --read-only         Read latest qmbot response, don't post
  --prs N [N ...]     Skip Slack, use these PR numbers directly
```

## Environment variables

| Variable        | Description                              | Default                             |
|-----------------|------------------------------------------|-------------------------------------|
| `SLACK_TOKEN`   | Slack bot token (`xoxb-...`)             | required for Slack mode             |
| `SLACK_CHANNEL` | Override default channel ID              | `C0B400Y1ZU2` (#pr-queue-dashboard) |
| `SLACK_BOT_ID`  | Override default bot user ID             | `W015DAXESG0` (qmbot)               |
| `GITHUB_REPO`   | Override GitHub repo slug                | `magento-commerce/magento2ce`       |

---

## Output

Reports are saved to `reports/` inside the repo with sequential daily filenames:

```
reports/
  queuepilot-2.4-develop-2026-05-26-1.html
  queuepilot-2.4-develop-2026-05-26-2.html
  ...
```

Each report is a self-contained dark-themed HTML dashboard with:

- **Summary table** — all PRs at a glance with CE / EE / B2B / SVC badges
- **Per-PR cards** — 3-column layout (CE | EE | B2B) with full failing test names
- **Direct links** — Allure reports and Jenkins jobs for each check suite
