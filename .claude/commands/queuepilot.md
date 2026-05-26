Run the QueuePilot tool to analyze Magento PR queue failures and generate an HTML dashboard report.

## Steps

1. Send `@qmbot dq $ARGUMENTS` to the `#pr-queue-dashboard` Slack channel using the slack_send_message tool with channel_id `C0B400Y1ZU2` and bot user `<@W015DAXESG0>`.

2. Wait a few seconds, then read the channel using slack_read_channel on channel `C0B400Y1ZU2` with oldest set to the sent message timestamp to get qmbot's response.

3. Parse the PR numbers from qmbot's response (format: `magento2ce 2.4-develop #<number>`).

4. Run the QueuePilot analysis script with the PR numbers and capture its output:
   ```
   python3 REPO_PATH/queuepilot.py $ARGUMENTS --prs <pr1> <pr2> ...
   ```
   The script prints the saved report path in the form `Open with: open <path>`. Parse that path from stdout.

5. Open the report using the path parsed from the script output:
   ```
   open <parsed-path>
   ```

6. Parse the report HTML and report back with a summary of failures found per PR. Do not narrate intermediate steps — just present the final summary.

If no branch argument is provided, default to `2.4-develop`.
