Run QueuePilot to analyze test failures for PRs in the Magento queue.

**Before running:** Make sure you've already sent `@qmbot dq $ARGUMENTS` in `#pr-queue-dashboard` and qmbot has replied with the PR list.

## Steps

1. Run the QueuePilot analysis script — it reads qmbot's latest response from the channel, analyzes all PRs, and posts the results to Slack:
   ```
   python3 REPO_PATH/queuepilot.py $ARGUMENTS --jira-token $JIRA_TOKEN
   ```
   The script prints the saved report path in the form `Open with: open <path>`. Parse that path from stdout.

2. Open the report using the path parsed from the script output:
   ```
   open <parsed-path>
   ```

3. Parse the report HTML and extract:
   - Total PR count and unique failing test count
   - Per-PR: CE / EE / B2B status and all failing test names
   - Jira ticket links (key + status) for each failing test

4. Report back in chat with the summary in this format. Do not narrate intermediate steps.

   ```
   🐛 QueuePilot — `<branch>`
   *<N> PR(s)* in queue · *<N> unique failing test(s)*

   *#<number>* <PR title> — <author>
   CE: <status> | EE: <status> | B2B: <status>
     • `<TestMethodName>` → <ACQE-XXXX> (<status>)
     • `<TestMethodName2>`

   *#<number>* <PR title> — <author>
   ...
   ```

   Use *bold* for PR numbers and counts. If a test has a Jira ticket, include the ticket key and status. If all editions pass, post: `✅ QueuePilot — <branch>: No failures found.`

If no branch argument is provided, default to `2.4-develop`.
