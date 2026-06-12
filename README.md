# QueuePilot

Automatic triage of Magento functional test failures (CE / EE / B2B) for PRs in the `2.4-develop` queue. Zero manual steps — send one Slack message, get a full failure report in the same thread.

---

## How it works

```
You          →  @qmbot dq 2.4-develop          (Slack: #pr-queue-dashboard)
qmbot        →  replies with PR list            (Slack thread)
Watcher      →  detects reply, waits 5 min      (background process on your Mac)
QueuePilot   →  analyzes all PRs                (GitHub + Allure + Jira)
Slack Connect bot → posts report in qmbot thread (one reply, no extra messages)
```

The 5-minute wait lets Jenkins/Allure finish writing test data before QueuePilot reads it.

---

## Full integration flow

### 1. Slack → trigger detection

- Watcher polls `#pr-queue-dashboard` every 30 seconds via `conversations.history`
- When it sees `dq 2.4-develop` (from any user), it opens a 10-minute window waiting for qmbot to reply
- When qmbot (`W015DAXESG0`) replies and the message contains GitHub PR URLs, the watcher records qmbot's message `ts` and schedules the report to fire 5 minutes later
- After the report is posted, the `ts` is cleared and the watcher resets

### 2. GitHub → PR and check-run data

For each PR, QueuePilot calls the GitHub CLI (`gh`) to fetch:
- PR metadata (title, author, URL) via `gh pr view`
- All check runs via `gh api repos/{repo}/commits/{sha}/check-runs`
- It looks for check runs named `ce-`, `ee-`, `b2b-` and reads their `conclusion` and `output.summary`

No GitHub API token is required separately — it uses whatever `gh auth` is set up.

### 3. Allure → test failure names

When a check run has `conclusion: failure`, QueuePilot extracts the Allure report URL from the check run's summary text, then:

1. Fetches `data/categories.json` (or falls back to `data/suites.json` → `data/behaviors.json`)
2. Walks the tree to find all leaf nodes with status `failed` or `broken`
3. For each failed test UID, calls `data/test-cases/{uid}.json` to get the fully-qualified Java method name (e.g. `Magento\Catalog\Test\Mftf\Test\...`)
4. Up to 10 test-case fetches run in parallel per PR; up to 5 PRs are analyzed in parallel

If Allure data isn't ready yet, it retries up to `--allure-attempts` times with 10-second pauses.

### 4. Jira → ticket links

If `JIRA_TOKEN` is set, QueuePilot searches `jira.corp.adobe.com` for each unique failing test:
- JQL: `project = ACQE AND summary ~ "{test_method_name}" ORDER BY created DESC`
- Only non-Done, non-Cancelled tickets are surfaced
- Up to 5 Jira lookups run in parallel
- Results are attached to each failure and shown in both the Slack summary and the HTML report

### 5. Slack → report delivery

The report is posted as a **thread reply to qmbot's message** using `chat.postMessage` with `thread_ts` set to qmbot's `ts`. This means:
- One bot message in the thread, nothing at the top-level channel
- The Slack Connect bot identity is used (whichever identity the `SLACK_TOKEN` belongs to)
- The summary includes: PR count, unique failing test count, per-test occurrence count across all PRs/editions, Jira links, and per-PR CE/EE/B2B pass/fail badges

### 6. HTML report → local file

An HTML dashboard is saved to `reports/` on your Mac. It contains:
- Queue summary with CE / EE / B2B status badges per PR
- All failing tests table sorted by frequency, with Jira ticket links
- Per-PR breakdown with full test names, Allure links, and Jenkins links

---

## Cost

QueuePilot makes no paid API calls. All integrations are free:

| Integration | API | Cost |
|-------------|-----|------|
| Slack read | `conversations.history` | Free (bot token) |
| Slack write | `chat.postMessage` | Free (bot token) |
| GitHub | `gh` CLI + REST API | Free (authenticated user) |
| Allure | Static JSON files from report URL | Free (internal) |
| Jira | REST API v2 search | Free (internal PAT) |

No LLM, no third-party service, no usage fees.

---

## Setup (once per machine)

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
- Install and start the background watcher as a macOS LaunchAgent
- Configure it to **start at every login** — you never need to run it again

After setup, just send the Slack message and the report appears in the thread.

---

## Tokens

| Token | Where to get it | Required? |
|-------|----------------|-----------|
| `SLACK_TOKEN` | Slack app settings → OAuth tokens → Bot token (`xoxb-...`) | Yes |
| `JIRA_TOKEN` | Jira → Profile → Personal Access Tokens | No — enables Jira ticket links |

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

Run without the watcher — reads qmbot's latest message from Slack automatically:

```bash
export SLACK_TOKEN=xoxb-your-token-here
python3 queuepilot.py 2.4-develop
```

Skip Slack entirely and pass PR numbers directly:

```bash
python3 queuepilot.py 2.4-develop --prs 10737 10740 10741
```

Post the report as a reply to a specific Slack message:

```bash
python3 queuepilot.py 2.4-develop --reply-to-ts 1718000000.123456
```

---

## All CLI options

```
python3 queuepilot.py <branch> [options]

  --output FILE         HTML output path          (default: auto-timestamped in reports/)
  --no-slack            Skip posting to Slack
  --prs N [N ...]       Use these PR numbers instead of reading from Slack
  --jira-token TOKEN    Jira PAT for ticket lookup (or set JIRA_TOKEN env var)
  --allure-attempts N   Allure retry count         (default: 2, ~10s each)
  --reply-to-ts TS      Slack message ts to reply into (set automatically by watcher)
```
