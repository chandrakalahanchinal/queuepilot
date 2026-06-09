# QueuePilot

Automatic triage of Magento functional test failures (CE / EE / B2B / SVC) for PRs in the `2.4-develop` queue.

## How it works

1. Send `@qmbot dq 2.4-develop` in `#pr-queue-dashboard`
2. qmbot replies with the PR list
3. QueuePilot automatically generates the failure report and posts it to the channel

No other steps. The watcher runs in the background and handles everything.

---

## Setup (do this once per machine)

### Prerequisites

| Tool | Install |
|------|---------|
| Python 3.10+ | [python.org](https://www.python.org/downloads/) — verify: `python3 --version` |
| GitHub CLI | `brew install gh` — verify: `gh --version` |

### 1. Clone the repo

```bash
git clone https://github.com/chandrakalahanchinal/queuepilot.git
cd queuepilot
```

### 2. Run setup

```bash
bash setup.sh
```

The script will:
- Install Python dependencies
- Authenticate GitHub CLI (if not already done)
- Ask for your `SLACK_TOKEN` and optionally `JIRA_TOKEN`
- Install and start the background watcher automatically
- Configure it to **start at every login** — you never need to run it again

That's it. After setup, just send the Slack message and the report appears.

---

## Tokens

| Token | Where to get it | Required? |
|-------|----------------|-----------|
| `SLACK_TOKEN` | Slack app settings → OAuth tokens → Bot token (`xoxb-...`) | Yes |
| `JIRA_TOKEN` | Jira → Profile → Personal Access Tokens | No (enables Jira ticket links in report) |

---

## Useful commands

```bash
# Check watcher logs
tail -f watcher.log

# Stop the watcher
launchctl unload ~/Library/LaunchAgents/com.queuepilot.watcher.plist

# Start the watcher again (or re-run setup to update tokens)
bash setup.sh
```

---

## Manual trigger (optional)

If you want to run the report manually without the watcher:

```bash
export SLACK_TOKEN=xoxb-your-token-here
python3 queuepilot.py 2.4-develop
```

Or skip Slack and pass PR numbers directly:

```bash
python3 queuepilot.py 2.4-develop --prs 10737 10740 10741
```

---

## Report contents

Each run posts a formatted Slack message to `#pr-queue-dashboard` and saves an HTML dashboard to `reports/` and `~/Downloads/`.

The HTML report includes:
1. **Stats** — PR count and unique failing test count
2. **Queue summary** — all PRs with CE / EE / B2B / SVC status badges
3. **All Failing Tests** — deduplicated list sorted by failure frequency, with Jira ticket links
4. **Per-PR details** — CE | EE | B2B columns with full test names, Jira badges, Allure and Jenkins links

---

## All CLI options

```
python3 queuepilot.py <branch> [options]

  --channel ID        Slack channel ID        (default: C0B400Y1ZU2)
  --bot ID            Slack bot user ID       (default: W015DAXESG0)
  --repo OWNER/REPO   GitHub repo             (default: magento-commerce/magento2ce)
  --output FILE       HTML output path        (default: auto-timestamped)
  --no-slack          Skip posting to Slack
  --prs N [N ...]     Use these PR numbers instead of reading from Slack
  --jira-token TOKEN  Jira PAT for ticket lookup
  --allure-attempts N Allure retry count      (default: 2)
```
