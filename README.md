# 🐛 Flakebuster

Evidence-based triage of Magento functional test failures (CE / EE / B2B / SVC) for PRs in the `2.4-develop` queue.

Inspired by [flakebuster-agent](https://github.com/OneAdobe/flakebuster-agent).

---

## What it does

1. Posts `@qmbot dq <branch>` to your Slack channel and reads the PR queue
2. Fetches GitHub check-run results for every PR in parallel
3. Extracts failing test names from Allure reports (CE / EE / B2B)
4. Checks Semantic Version Checker status
5. Generates a self-contained **HTML dashboard** you can open in any browser

---

## Requirements

- Python 3.10+
- [GitHub CLI (`gh`)](https://cli.github.com/) — authenticated (`gh auth login`)
- `pip install -r requirements.txt`
- A Slack **bot token** (`xoxb-...`) with scopes:
  - `chat:write`
  - `channels:history` / `groups:history`

---

## Setup

```bash
git clone https://github.com/chandrakalahanchinal/flakebuster.git
cd flakebuster
pip install -r requirements.txt
```

---

## Usage

### Full auto flow (Slack → PRs → Report)

```bash
export SLACK_TOKEN=xoxb-your-token-here
python3 flakebuster.py 2.4-develop
```

The script will:
- Post `@qmbot dq 2.4-develop` to `#pr-queue-dashboard`
- Wait for the bot to reply with the PR list
- Analyze all PRs
- Save `flakebuster-report.html` → open it in your browser

### Read-only mode (message already sent manually)

If you sent `@qmbot dq 2.4-develop` yourself in Slack:

```bash
export SLACK_TOKEN=xoxb-your-token-here
python3 flakebuster.py 2.4-develop --read-only
```

### Skip Slack — pass PR numbers directly

```bash
python3 flakebuster.py 2.4-develop --prs 10717 10620 10727 10730
```

No token needed. Goes straight to analysis.

---

## All options

```
python3 flakebuster.py <branch> [options]

positional:
  branch              Queue branch name, e.g. 2.4-develop

options:
  --channel ID        Slack channel ID        (default: #pr-queue-dashboard)
  --bot ID            Slack bot user ID       (default: qmbot)
  --cmd CMD           Bot command             (default: dq)
  --repo OWNER/REPO   GitHub repo             (default: magento-commerce/magento2ce)
  --output FILE       Output HTML path        (default: flakebuster-report.html)
  --read-only         Read latest qmbot response, don't post
  --prs N [N ...]     Skip Slack, use these PR numbers directly
```

## Environment variables

| Variable        | Description                              | Default                        |
|-----------------|------------------------------------------|--------------------------------|
| `SLACK_TOKEN`   | Slack bot token (`xoxb-...`)             | required for Slack mode        |
| `SLACK_CHANNEL` | Override default channel ID              | `C0B400Y1ZU2` (#pr-queue-dashboard) |
| `SLACK_BOT_ID`  | Override default bot user ID             | `W015DAXESG0` (qmbot)          |
| `GITHUB_REPO`   | Override GitHub repo slug                | `magento-commerce/magento2ce`  |

---

## Slack setup (first time)

For private channels, invite both bots before running:

```
/invite @slack_connector
/invite @qmbot
```

---

## Output

The tool generates `flakebuster-report.html` — a dark-themed dashboard with:

- **Summary table** — all PRs at a glance with CE / EE / B2B / SVC badges
- **Per-PR cards** — full list of failing test method names per suite
- **Fallback counts** — when Allure data is partial, shows failed/broken/passed counts
- **Direct links** — Allure reports and Jenkins jobs for each check

```
open flakebuster-report.html
```
