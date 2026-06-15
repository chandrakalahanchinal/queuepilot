# QueuePilot

Automatic triage of Magento functional test failures (CE / EE / B2B) for PRs in the `2.4-develop` queue. Send one Slack message — the full failure report appears as a reply in the same thread, automatically.

---

## How it works

```
You               →  @qmbot dq 2.4-develop         (#pr-queue-dashboard)
qmbot             →  replies with PR list           (channel message)
Watcher (watch.py)→  detects reply, waits 5 min    (macOS LaunchAgent, always running)
QueuePilot        →  analyzes all PRs in parallel   (GitHub + Allure + Jira)
Slack Connect bot →  posts report in qmbot's thread (one reply, nothing at top level)
```

The 5-minute wait gives Jenkins and Allure time to finish writing test data before QueuePilot reads it.

---

## Full integration flow

### 1. Slack → trigger detection

- Watcher polls `#pr-queue-dashboard` every **30 seconds** via `conversations.history`
- When any user sends `dq 2.4-develop`, a 10-minute window opens waiting for qmbot to reply
- When qmbot (`W015DAXESG0`) replies with GitHub PR URLs, the watcher:
  - Records qmbot's message `ts` as `qmbot_reply_ts` in `.watcher_state.json`
  - Schedules the report to fire **5 minutes later**
- At fire time, calls `queuepilot.py --reply-to-ts <qmbot_reply_ts>`
- After posting, clears state and resets

### 2. GitHub → PR and check-run data

For each PR, QueuePilot uses the GitHub CLI (`gh`) to fetch:
- PR metadata (title, author, URL) via `gh pr view`
- All check runs via `gh api repos/{repo}/commits/{sha}/check-runs`
- Identifies CE, EE, B2B check runs by name prefix; reads `conclusion` and `output.summary`

No separate GitHub token needed — uses whatever `gh auth` is configured.

### 3. Allure → test failure names (all runs)

When a check run has `conclusion: failure`, QueuePilot:
1. Extracts the Allure report URL from the check-run summary (falls back to scraping the Jenkins page)
2. Fetches `data/categories.json` (fallback: `suites.json` → `behaviors.json`)
3. Walks the tree collecting all leaf nodes with status `failed` or `broken`
4. For each UID calls `data/test-cases/{uid}.json` to get the fully-qualified Java test method name
5. Up to **10 test-case fetches in parallel** per PR; up to **5 PRs in parallel**

Retries up to `--allure-attempts` times (10-second pauses). Falls back to Prometheus stats if retries are exhausted.

**Previous runs via PR comments:** PRs are often re-triggered multiple times. Each run posts a bot comment containing Allure links. QueuePilot also scrapes all PR comments for Allure report URLs and fetches failures from every previous run, then unions them with the current run — deduplicated by test method name. This ensures no failure is missed across re-runs.

### 4. Jira → ticket links

If `JIRA_TOKEN` is set, QueuePilot searches `jira.corp.adobe.com` for each unique failing test:
- JQL: `project = ACQE AND summary ~ "{test_method_name}" ORDER BY created DESC`
- Only non-Done, non-Cancelled tickets are surfaced; picks most recently created active ticket
- Up to **5 Jira lookups in parallel**
- Results attached to each failure, shown in both the Slack summary and the HTML report

### 5. Slack → report delivery

The report is posted via `chat.postMessage` with `thread_ts` set to qmbot's message `ts`:
- **One bot reply in qmbot's thread** — nothing posted at top level of the channel
- The Slack Connect bot identity (the `SLACK_TOKEN` owner) is used
- No file attachments — summary message only

### 6. HTML report → local file

A self-contained HTML dashboard is saved to `reports/` in the project directory. It contains:
- Queue summary with CE / EE / B2B status badges per PR
- All failing tests sorted by total occurrence count, with Jira ticket links
- Per-PR breakdown with full test names, Allure links, and Jenkins links

---

## How the Slack result looks

The report is posted as a **single thread reply** inside qmbot's message. It has three parts:

### Part 1 — Header

```
🐛 QueuePilot — `2.4-develop`
*3 PR(s)* in queue  ·  *5 unique failing test(s)*
```

### Part 2 — Unique failures (sorted by total occurrence count)

Each line shows the test method name, how many times it failed in total across **all PRs and all editions** (CE + EE + B2B), and the linked Jira ticket if one exists.

```
• `AdminUserSetStatusForEachSourceItemTest`  *4x*  → ACQE-9629 _Tech Analysis_
• `StorefrontCheckTermsAndConditionIsPresentTest`  *3x*  → ACQE-10249 _Options Queue_
• `StockStatusChangedForConfigurableProductTest`  *2x*
• `CreateConfigurableProductWithTierPriceTest`  *1x*
```

`4x` means that test failed 4 times in total — for example CE+EE for PR1 and CE for PR2. It is **not** a PR count.

### Part 3 — Per-PR breakdown

One block per PR showing the GitHub link, author, CE/EE/B2B badge, and a deduplicated list of failing test names (union across all editions):

```
*#10762* Fix cart total rounding issue
by *harshityadav90*  ·  CE: *2 FAIL*  EE: ✅ PASS  B2B: *3 FAIL*
  • `AdminUserSetStatusForEachSourceItemTest`
  • `StorefrontCheckTermsAndConditionIsPresentTest`
  • `StockStatusChangedForConfigurableProductTest`

*#10758* Support Tier-4 flowers bugfixes
by *thiaramus*  ·  CE: *1 FAIL*  EE: *4 FAIL*  B2B: ✅ PASS
  • `CreateConfigurableProductWithTierPriceTest`
```

Badge meanings:

| Badge | Meaning |
|-------|---------|
| `N FAIL` | N tests failed in this edition |
| `✅ PASS` | All checks passed |
| `⏳ RUNNING` | Check still in progress |
| `N/A` | Check has not run for this edition |

---

## Cost

QueuePilot makes no paid API calls. All integrations are free:

| Integration | API | Cost |
|-------------|-----|------|
| Slack read | `conversations.history` | Free (bot token) |
| Slack write | `chat.postMessage` | Free (bot token) |
| GitHub | `gh` CLI + REST API | Free (authenticated user) |
| Allure | Static JSON from internal report URL | Free |
| Jira | REST API v2 search | Free (internal PAT) |

No LLM, no third-party service, no usage fees.

---

## Setup (once per machine)

### Prerequisites

| Tool | Install |
|------|---------|
| Python 3.10+ | [python.org](https://www.python.org/downloads/) — verify: `python3 --version` |
| GitHub CLI | `brew install gh` — verify: `gh --version` |

### Install

```bash
git clone https://github.com/chandrakalahanchinal/queuepilot.git
cd queuepilot
bash setup.sh
```

`setup.sh` will:
- Install Python dependencies
- Authenticate GitHub CLI (if not already done)
- Ask for your `SLACK_TOKEN` and optionally `JIRA_TOKEN`
- Install and start the background watcher as a macOS LaunchAgent
- Configure it to **start at every login** — you never need to run it again

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

# Start / restart the watcher (or update tokens)
bash setup.sh
```

---

## Manual trigger (optional)

Reads qmbot's latest message from Slack automatically:

```bash
export SLACK_TOKEN=xoxb-your-token-here
python3 queuepilot.py 2.4-develop
```

Skip Slack entirely — pass PR numbers directly:

```bash
python3 queuepilot.py 2.4-develop --prs 10737 10740 10741
```

Reply into a specific qmbot thread (watcher sets this automatically):

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
