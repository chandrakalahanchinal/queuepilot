Run the QueuePilot tool to analyze Magento PR queue failures and generate an HTML dashboard report, then post the results to Slack.

## Steps

1. Send `@qmbot dq $ARGUMENTS` to the `#pr-queue-dashboard` Slack channel using the slack_send_message tool with channel_id `C0B400Y1ZU2` and bot user `<@W015DAXESG0>`.

2. Wait a few seconds, then read the channel using slack_read_channel on channel `C0B400Y1ZU2` with oldest set to the sent message timestamp to get qmbot's response.

3. Run the QueuePilot analysis script in read-only mode (it reads qmbot's response directly from the channel) with `--no-slack` so the watcher handles the single Slack post:
   ```
   python3 /Users/chandb/queuepilot/queuepilot.py $ARGUMENTS --read-only --no-slack --jira-token $JIRA_TOKEN
   ```
   The script prints the saved report path in the form `Open with: open <path>`. Parse that path from stdout.

4. Open the report using the path parsed from the script output:
   ```
   open <parsed-path>
   ```

5. Parse the report HTML and extract:
   - Total PR count and unique failing test count
   - Per-PR: CE / EE / B2B status and all failing test names
   - Jira ticket links (key + status) for each failing test

6. Report back in chat with the summary in this format. Do not narrate intermediate steps. Do NOT post to Slack — the watcher already posted.

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
