Run the QueuePilot tool to analyze Magento PR queue failures and generate an HTML dashboard report, then post the results to Slack.

## Steps

1. Send `@qmbot dq $ARGUMENTS` to the `#pr-queue-dashboard` Slack channel using the slack_send_message tool with channel_id `C0B400Y1ZU2` and bot user `<@W015DAXESG0>`.

2. Wait a few seconds, then read the channel using slack_read_channel on channel `C0B400Y1ZU2` with oldest set to the sent message timestamp to get qmbot's response.

3. Parse the PR numbers from qmbot's response (format: `magento2ce 2.4-develop #<number>`).

4. Run the QueuePilot analysis script with the PR numbers and capture its output:
   ```
   python3 REPO_PATH/queuepilot.py $ARGUMENTS --prs <pr1> <pr2> ... --jira-token NDAyMDU1NDE1MTxxOniCItVCD8QEttEaH940E18nDA4V
   ```
   The script prints the saved report path in the form `Open with: open <path>`. Parse that path from stdout.

5. Open the report using the path parsed from the script output:
   ```
   open <parsed-path>
   ```

6. Parse the report HTML and extract:
   - Total PR count and unique failing test count
   - Per-PR: CE / EE / B2B status and all failing test names
   - Jira ticket links (key + status) for each failing test

7. Post the full summary immediately to Slack channel `C0B400Y1ZU2` (#pr-queue-dashboard) using slack_send_message with this format:

   ```
   🐛 QueuePilot — `<branch>`
   *<N> PR(s)* in queue · *<N> unique failing test(s)*

   *#<number>* <PR title> — <author>
   CE: <status> | EE: <status> | B2B: <status> | SVC: <status>
     • `<TestMethodName>` → <ACQE-XXXX> (<status>)
     • `<TestMethodName2>`

   *#<number>* <PR title> — <author>
   ...
   ```

   Use *bold* for PR numbers and counts. If a test has a Jira ticket, include the ticket key and status. If all editions pass, post: `✅ QueuePilot — <branch>: No failures found.`

8. Report back in chat with the same summary. Do not narrate intermediate steps.

If no branch argument is provided, default to `2.4-develop`.
