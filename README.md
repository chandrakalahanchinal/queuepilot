# QueuePilot

Evidence-based triage of Magento functional test failures (CE / EE / B2B / SVC) for PRs in the `2.4-develop` queue.

---

## How it works

1. Start the watcher once (keeps running in the background)
2. Send `@qmbot dq 2.4-develop` in `#pr-queue-dashboard`
3. qmbot replies with the PR list → watcher automatically runs the analysis and posts the report to the channel

That's it. No other commands needed.

---

## Team Setup

### 1. Prerequisites

| Tool | Install | Verify |
|------|---------|--------|
| Python 3.10+ | [python.org](https://www.python.org/downloads/) | `python3 --version` |
| GitHub CLI | `brew install gh` | `gh --version` |

### 2. Clone and install

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

### 4. Set your tokens

```bash
export SLACK_TOKEN=xoxb-your-token-here
export JIRA_TOKEN=your-jira-token   # optional, enables Jira ticket links
```

Add these to your shell profile (`~/.zshrc` or `~/.bash_profile`) to make them permanent.

### 5. Start the watcher

```bash
python3 watch.py
```

Keep this terminal open (or run it in the background). The watcher polls `#pr-queue-dashboard` every 30 seconds.

---

## Usage

Once the watcher is running, just send the command in Slack:

```
@qmbot dq 2.4-develop
```

After qmbot replies with the PR list, QueuePilot will automatically:
- Fetch GitHub check-run results for every PR
- Extract failing test names from Allure reports (CE / EE / B2B) in parallel
- Look up ACQE Jira tickets for each failing test
- Generate an HTML dashboard saved to `reports/` and `~/Downloads/`
- Post the formatted summary to `#pr-queue-dashboard`

---

## Manual run (optional)

If the watcher isn't running, you can trigger the report manually after qmbot has already replied:

```bash
export SLACK_TOKEN=xoxb-your-token-here
python3 queuepilot.py 2.4-develop
```

Or pass PR numbers directly (no Slack needed):

```bash
python3 queuepilot.py 2.4-develop --prs 10737 10740 10741
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
  --allure-attempts N Max retries for Allure data (default: 2, ~10s)
```

## Environment variables

| Variable | Description |
|----------|-------------|
| `SLACK_TOKEN` | Slack bot token (`xoxb-...`) — required |
| `JIRA_TOKEN` | Jira personal access token — optional, enables ticket lookup |
| `SLACK_CHANNEL` | Override default channel ID (`C0B400Y1ZU2`) |
| `SLACK_BOT_ID` | Override default bot user ID (`W015DAXESG0`) |
| `GITHUB_REPO` | Override GitHub repo slug (`magento-commerce/magento2ce`) |

---

## Dashboard sections

Each HTML report contains:

1. **Stats bar** — PR count and unique failing test count
2. **Queue summary table** — all PRs with CE / EE / B2B / SVC badges
3. **All Failing Tests table** — deduplicated, sorted by fail frequency, with Jira links
4. **Per-PR failure cards** — CE | EE | B2B columns with test names, Jira badges, Allure/Jenkins links

Reports are saved to:
- `reports/queuepilot-2.4-develop-YYYY-MM-DD-N.html`
- `~/Downloads/queuepilot-2.4-develop-YYYY-MM-DD-N.html`
