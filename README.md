# 🐛 QueuePilot

Evidence-based triage of Magento functional test failures (CE / EE / B2B / SVC) for PRs in the `2.4-develop` queue.

Inspired by [flakebuster-agent](https://github.com/OneAdobe/flakebuster-agent).

---

## Using with Claude Code (recommended)

QueuePilot ships as a **Claude Code slash command** — no token setup, no terminal needed.  
Claude handles the Slack call, runs the script, and summarises failures inline.

### One-time setup

Save the following as `.claude/commands/queuepilot.md` inside this repo (or your home `~/.claude/commands/`):

````markdown
Run the QueuePilot tool to analyze Magento PR queue failures and generate an HTML dashboard report.

## Steps

1. Send `@qmbot dq $ARGUMENTS` to the `#pr-queue-dashboard` Slack channel using the
   slack_send_message tool with channel_id `C0B400Y1ZU2` and bot user `<@W015DAXESG0>`.

2. Wait a few seconds, then read the channel using slack_read_channel on channel `C0B400Y1ZU2`
   with oldest set to the sent message timestamp to get qmbot's response.

3. Parse the PR numbers from qmbot's response (format: `magento2ce 2.4-develop #<number>`).

4. Run the QueuePilot analysis script with the PR numbers:
   ```
   python3 /path/to/queuepilot.py $ARGUMENTS --prs <pr1> <pr2> ...
   ```

5. Open the report:
   ```
   open /path/to/queuepilot-report.html
   ```

6. Report back with a summary of failures found per PR.

If no branch argument is provided, default to `2.4-develop`.
````

> **Requirement:** Claude Code must have the Slack MCP connected (`mcp__claude_ai_Slack__*` tools available).  
> No `SLACK_TOKEN` env var is needed — Claude uses its connected Slack integration.

### Running it

In any Claude Code session, type:

```
/queuepilot 2.4-develop
```

Or just `/queuepilot` to default to `2.4-develop`.

Claude will:
1. Post `@qmbot dq 2.4-develop` to `#pr-queue-dashboard` via Slack MCP
2. Read the bot's reply and parse PR numbers
3. Run `queuepilot.py --prs ...` automatically
4. Open the HTML report in your browser
5. Print a per-PR failure summary directly in the chat

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
git clone https://github.com/chandrakalahanchinal/queuepilot.git
cd queuepilot
pip install -r requirements.txt
```

---

## Usage

### Full auto flow (Slack → PRs → Report)

```bash
export SLACK_TOKEN=xoxb-your-token-here
python3 queuepilot.py 2.4-develop
```

The script will:
- Post `@qmbot dq 2.4-develop` to `#pr-queue-dashboard`
- Wait for the bot to reply with the PR list
- Analyze all PRs
- Save `queuepilot-report.html` → open it in your browser

### Read-only mode (message already sent manually)

If you sent `@qmbot dq 2.4-develop` yourself in Slack:

```bash
export SLACK_TOKEN=xoxb-your-token-here
python3 queuepilot.py 2.4-develop --read-only
```

### Skip Slack — pass PR numbers directly

```bash
python3 queuepilot.py 2.4-develop --prs 10717 10620 10727 10730
```

No token needed. Goes straight to analysis.

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
  --output FILE       Output HTML path        (default: queuepilot-report.html)
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

The tool generates `queuepilot-report.html` — a dark-themed dashboard with:

- **Summary table** — all PRs at a glance with CE / EE / B2B / SVC badges
- **Per-PR cards** — full list of failing test method names per suite
- **Fallback counts** — when Allure data is partial, shows failed/broken/passed counts
- **Direct links** — Allure reports and Jenkins jobs for each check

```
open queuepilot-report.html
```
