# 🐛 QueuePilot

Evidence-based triage of Magento functional test failures (CE / EE / B2B / SVC) for PRs in the `2.4-develop` queue.

Inspired by [flakebuster-agent](https://github.com/OneAdobe/flakebuster-agent).

---

## Team Setup (start here)

### 1. Prerequisites

| Tool | Install | Check |
|------|---------|-------|
| Python 3.10+ | [python.org](https://www.python.org/downloads/) | `python3 --version` |
| GitHub CLI | `brew install gh` | `gh --version` |
| Claude Code | [claude.ai/code](https://claude.ai/code) | `claude --version` |

### 2. Clone and install

```bash
git clone https://github.com/chandrakalahanchinal/queuepilot.git
cd queuepilot
pip install -r requirements.txt
```

### 3. Authenticate GitHub CLI

```bash
gh auth login
# choose: GitHub.com → HTTPS → authenticate via browser
```

Verify: `gh api user --jq .login` should print your username.

### 4. Set up the Claude Code slash command

Copy the slash command file into your Claude commands folder:

```bash
# macOS / Linux
cp .claude/commands/queuepilot.md ~/.claude/commands/queuepilot.md
```

Then open the copied file and replace `REPO_PATH` with your actual clone path:

```bash
# find your clone path
pwd   # run this inside the queuepilot directory
```

Edit `~/.claude/commands/queuepilot.md` — replace the placeholder path with your own:

```
python3 /your/path/to/queuepilot/queuepilot.py ...
```

### 5. Connect Slack in Claude Code

Make sure you have the **Slack MCP** connected in Claude Code (Settings → Integrations → Slack). No `SLACK_TOKEN` env var needed — Claude uses its own Slack integration.

If the `#pr-queue-dashboard` channel is private, invite the bots once:
```
/invite @slack_connector
/invite @qmbot
```

### 6. Run it

Open Claude Code in the `queuepilot` directory and type:

```
/queuepilot 2.4-develop
```

Reports are saved to `queuepilot/reports/` inside the repo as `queuepilot-2.4-develop-YYYY-MM-DD-N.html`.

---

## What it does

1. Posts `@qmbot dq <branch>` to `#pr-queue-dashboard` and reads the PR list
2. Fetches GitHub check-run results for every PR in parallel
3. Extracts failing test names from Allure reports (CE / EE / B2B)
4. Checks Semantic Version Checker status
5. Generates a self-contained **HTML dashboard** and opens it in your browser
6. Prints a per-PR failure summary directly in the Claude Code chat

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
  --channel ID        Slack channel ID        (default: #pr-queue-dashboard)
  --bot ID            Slack bot user ID       (default: qmbot)
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

Reports are saved to `reports/` inside the repo directory with sequential daily filenames:

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
