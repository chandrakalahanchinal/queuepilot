#!/usr/bin/env python3
"""
QueuePilot — Evidence-based triage of Magento functional test failures in PR queues.

Usage:
    python queuepilot.py 2.4-develop
    python queuepilot.py 2.4-develop --channel C2MG0TNPL --bot W015DAXESG0
    python queuepilot.py 2.4-develop --output report.html

Environment variables:
    SLACK_TOKEN   Slack API token (required)
    GITHUB_REPO   GitHub repo slug (default: magento-commerce/magento2ce)
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

import requests

# ──────────────────────────────────────────────────────────────────────────────
# Defaults
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_CHANNEL    = "C0B400Y1ZU2"  # #pr-queue-dashboard
DEFAULT_BOT_ID     = "W015DAXESG0"  # qmbot
DEFAULT_BOT_CMD    = "dq"
DEFAULT_REPO       = "magento-commerce/magento2ce"
DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
BOT_WAIT_TIMEOUT   = 90   # seconds to wait for bot reply
ALLURE_WORKER_MAX  = 10   # parallel workers per PR for test-case fetches
PR_WORKER_MAX      = 4    # parallel PR analyses


# ──────────────────────────────────────────────────────────────────────────────
# Slack
# ──────────────────────────────────────────────────────────────────────────────
def slack_join_channel(token: str, channel: str) -> None:
    resp = requests.post(
        "https://slack.com/api/conversations.join",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel},
        timeout=15,
    )
    resp.raise_for_status()


def slack_post(token: str, channel: str, text: str) -> dict:
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel, "text": text},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack postMessage error: {data.get('error')}")
    return data


def slack_history(token: str, channel: str, oldest: str, limit: int = 30) -> list:
    resp = requests.get(
        "https://slack.com/api/conversations.history",
        headers={"Authorization": f"Bearer {token}"},
        params={"channel": channel, "oldest": oldest, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack history error: {data.get('error')}")
    return data.get("messages", [])


def wait_for_bot_reply(token: str, channel: str, bot_id: str, after_ts: str,
                       timeout: int = BOT_WAIT_TIMEOUT) -> Optional[str]:
    print(f"  Waiting for bot reply (up to {timeout}s)...", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        msgs = slack_history(token, channel, oldest=after_ts)
        for msg in reversed(msgs):
            if msg.get("user") == bot_id and msg.get("ts") != after_ts:
                return msg.get("text", "")
        time.sleep(3)
    return None


def parse_pr_numbers(bot_text: str) -> list[int]:
    return [int(m) for m in re.findall(r"magento2ce[^\|]+?#(\d+)", bot_text)]


# ──────────────────────────────────────────────────────────────────────────────
# GitHub
# ──────────────────────────────────────────────────────────────────────────────
def gh_json(args: list[str]) -> dict | list:
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def get_pr_info(repo: str, pr_number: int) -> dict:
    return gh_json([
        "pr", "view", str(pr_number), "--repo", repo,
        "--json", "title,author,headRefOid,headRefName,url",
    ])


def get_check_runs(repo: str, sha: str) -> list:
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/commits/{sha}/check-runs",
             "--paginate", "--jq", ".check_runs[]"],
            capture_output=True, text=True, check=True,
        )
        runs = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line:
                runs.append(json.loads(line))
        return runs
    except subprocess.CalledProcessError:
        return []


def extract_allure_url(summary: str, edition: str) -> Optional[str]:
    pattern = rf"\[Functional tests\]\((https://[^\)]+allure-report-{edition}/index\.html)\)"
    m = re.search(pattern, summary or "")
    return m.group(1) if m else None


# ──────────────────────────────────────────────────────────────────────────────
# Allure
# ──────────────────────────────────────────────────────────────────────────────
def allure_base(index_url: str) -> str:
    return index_url.replace("/index.html", "")


def fetch_json(url: str) -> Optional[dict | list]:
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _collect_failed(node: dict | list, results: list) -> None:
    """Recursively walk the Allure categories tree and collect failed/broken leaf tests."""
    if isinstance(node, list):
        for item in node:
            _collect_failed(item, results)
        return
    if not isinstance(node, dict):
        return
    # Leaf node — has a uid and status
    if "uid" in node and node.get("status") in ("failed", "broken"):
        results.append({
            "uid": node["uid"],
            "name": node.get("name", ""),
            "status": node.get("status"),
        })
    # Walk children regardless
    for child in node.get("children", []):
        _collect_failed(child, results)


def _dedup_uids(results: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for r in results:
        if r["uid"] not in seen:
            seen.add(r["uid"])
            unique.append(r)
    return unique


def get_failed_uids(base_url: str) -> list[dict]:
    """Try categories.json first, fall back to suites.json."""
    for endpoint in ("data/categories.json", "data/suites.json"):
        data = fetch_json(f"{base_url}/{endpoint}")
        if not data:
            continue
        results = []
        _collect_failed(data, results)
        unique = _dedup_uids(results)
        if unique:
            return unique
    return []


def find_allure_url_from_jenkins(jenkins_url: str, edition: str) -> Optional[str]:
    """Scrape the Jenkins build page for a public Allure report URL."""
    try:
        r = requests.get(jenkins_url, timeout=15, allow_redirects=False)
        if r.status_code not in (200,):
            return None
        # Look for the public Allure storage URL pattern in the page HTML
        pattern = rf"https://[^\s\"'<>]+allure-report-{edition}/index\.html"
        m = re.search(pattern, r.text)
        return m.group(0) if m else None
    except Exception:
        return None


def get_test_method_name(base_url: str, uid: str) -> str:
    data = fetch_json(f"{base_url}/data/test-cases/{uid}.json")
    if not data:
        return uid
    full_name = data.get("fullName", "")
    if "::" in full_name:
        return full_name.split("::")[-1]
    return full_name or uid


def get_prometheus_stats(base_url: str) -> Optional[dict]:
    """Fetch summary counts from Allure prometheus export as fallback."""
    try:
        r = requests.get(f"{base_url}/export/prometheusData.txt", timeout=10)
        if r.status_code != 200 or "<html" in r.text[:50]:
            return None
        stats = {}
        for line in r.text.splitlines():
            parts = line.strip().split()
            if len(parts) == 2:
                stats[parts[0]] = int(float(parts[1]))
        return stats if stats else None
    except Exception:
        return None


def resolve_failures(base_url: str, failed_uids: list[dict]) -> list[dict]:
    results = []
    with ThreadPoolExecutor(max_workers=ALLURE_WORKER_MAX) as ex:
        futures = {
            ex.submit(get_test_method_name, base_url, t["uid"]): t
            for t in failed_uids
        }
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                method = fut.result()
            except Exception:
                method = t["name"]
            results.append({
                "method": method,
                "label": t["name"],
                "status": t["status"],
                "uid": t["uid"],
            })
    return sorted(results, key=lambda x: x["method"])


# ──────────────────────────────────────────────────────────────────────────────
# PR analysis
# ──────────────────────────────────────────────────────────────────────────────
def analyze_pr(repo: str, pr_number: int) -> dict:
    print(f"  [PR #{pr_number}] Fetching info...", flush=True)
    pr_info  = get_pr_info(repo, pr_number)
    sha      = pr_info["headRefOid"]
    check_runs = get_check_runs(repo, sha)
    check_map  = {cr["name"]: cr for cr in check_runs}

    result = {
        "pr_number": pr_number,
        "title":     pr_info["title"],
        "author":    pr_info["author"]["login"],
        "branch":    pr_info["headRefName"],
        "url":       pr_info.get("url", f"https://github.com/{repo}/pull/{pr_number}"),
        "editions":  {},
        "svc":       None,
    }

    for edition in ["ce", "ee", "b2b"]:
        check_name = f"Functional Tests {edition.upper()}"
        cr = check_map.get(check_name)
        if not cr:
            result["editions"][edition] = {"status": "not_run", "failures": [], "report_url": None}
            continue

        conclusion   = cr.get("conclusion")
        cr_status    = cr.get("status", "")
        summary      = cr.get("output", {}).get("summary", "")
        report_url   = extract_allure_url(summary, edition)
        jenkins_url  = cr.get("details_url", "")

        if cr_status in ("in_progress", "queued") and conclusion is None:
            result["editions"][edition] = {"status": "in_progress", "failures": [], "report_url": report_url, "jenkins_url": jenkins_url}
            continue

        if conclusion is None:
            conclusion = "unknown"

        if conclusion != "failure":
            result["editions"][edition] = {"status": conclusion, "failures": [], "report_url": report_url, "jenkins_url": jenkins_url}
            continue

        print(f"  [PR #{pr_number}] Fetching {edition.upper()} Allure failures...", flush=True)
        failures = []
        prom_stats = None

        # If no Allure URL in check summary, try scraping it from the Jenkins build page
        if not report_url and jenkins_url:
            print(f"  [PR #{pr_number}] No Allure URL found — checking Jenkins build page for {edition.upper()}...", flush=True)
            report_url = find_allure_url_from_jenkins(jenkins_url, edition)

        if report_url:
            base = allure_base(report_url)
            # Retry up to 5 times — report may still be uploading or server may be busy
            for attempt in range(5):
                uids = get_failed_uids(base)
                failures = resolve_failures(base, uids)
                if failures:
                    break
                prom_stats = get_prometheus_stats(base)
                if prom_stats:
                    break
                if attempt < 4:
                    time.sleep(5)

        result["editions"][edition] = {
            "status":      "failure",
            "failures":    failures,
            "report_url":  report_url,
            "jenkins_url": jenkins_url,
            "prom_stats":  prom_stats,
        }

    # Semantic Version Checker
    cr = check_map.get("Semantic Version Checker")
    if cr:
        result["svc"] = {
            "status":      cr.get("conclusion", "unknown"),
            "details_url": cr.get("details_url", ""),
            "summary":     cr.get("output", {}).get("summary", ""),
        }

    return result


# ──────────────────────────────────────────────────────────────────────────────
# HTML dashboard
# ──────────────────────────────────────────────────────────────────────────────
STATUS_BADGE = {
    "failure":     '<span class="badge fail">FAIL</span>',
    "success":     '<span class="badge pass">PASS</span>',
    "skipped":     '<span class="badge skip">SKIP</span>',
    "neutral":     '<span class="badge neutral">NEUTRAL</span>',
    "not_run":     '<span class="badge neutral">N/A</span>',
    "unknown":     '<span class="badge neutral">?</span>',
    "in_progress": '<span class="badge running">RUNNING</span>',
}


def badge(status: str) -> str:
    return STATUS_BADGE.get(status, STATUS_BADGE["unknown"])


def failure_count_badge(edition_data: dict) -> str:
    if edition_data["status"] != "failure":
        return badge(edition_data["status"])
    n = len(edition_data["failures"])
    return f'<span class="badge fail">{n} FAIL</span>'


def render_failures_table(failures: list[dict], report_url: Optional[str]) -> str:
    if not failures:
        return ""
    rows = ""
    for f in failures:
        method = html.escape(f["method"])
        status_cls = "broken" if f["status"] == "broken" else "failed"
        rows += f'<tr><td><code class="{status_cls}">{method}</code></td></tr>'
    report_link = f'<a href="{html.escape(report_url)}" target="_blank">Open Allure Report ↗</a>' if report_url else ""
    return f"""
    <table class="failures">
      <tbody>{rows}</tbody>
    </table>
    {report_link}"""


def render_svc_block(svc: Optional[dict]) -> str:
    if not svc:
        return ""
    status = svc.get("status", "unknown")
    if status == "success":
        return f'<div class="svc-block pass-bg">Semantic Version Checker: {badge("success")}</div>'
    url = html.escape(svc.get("details_url", ""))
    link = f'<a href="{url}" target="_blank">View Report ↗</a>' if url else ""
    return f'<div class="svc-block fail-bg">Semantic Version Checker: {badge("failure")} {link}</div>'


def render_pr_card(pr: dict) -> str:
    pr_url    = html.escape(pr["url"])
    title     = html.escape(pr["title"])
    author    = html.escape(pr["author"])
    branch    = html.escape(pr["branch"])

    edition_sections = ""
    for edition in ["ce", "ee", "b2b"]:
        ed = pr["editions"].get(edition, {"status": "not_run", "failures": [], "report_url": None})
        label = edition.upper()
        table = render_failures_table(ed["failures"], ed.get("report_url"))
        fail_badge = failure_count_badge(ed)
        if ed["status"] == "not_run":
            no_data = '<p class="muted">ℹ️ Checks not available.</p>'
        elif ed["status"] == "in_progress":
            jenkins_link = ""
            if ed.get("jenkins_url"):
                jenkins_link = f' <a href="{html.escape(ed["jenkins_url"])}" target="_blank">Jenkins ↗</a>'
            no_data = f'<p class="muted">⏳ Checks are currently running.{jenkins_link}</p>'
        elif ed["status"] == "failure" and not ed["failures"]:
            links = ""
            if ed.get("report_url"):
                links += f' <a href="{html.escape(ed["report_url"])}" target="_blank">Allure ↗</a>'
            if ed.get("jenkins_url"):
                links += f' <a href="{html.escape(ed["jenkins_url"])}" target="_blank">Jenkins ↗</a>'
            prom = ed.get("prom_stats")
            if prom:
                failed_c  = prom.get("launch_status_failed", 0)
                broken_c  = prom.get("launch_status_broken", 0)
                passed_c  = prom.get("launch_status_passed", 0)
                skipped_c = prom.get("launch_status_skipped", 0)
                no_data = (
                    f'<p class="muted warn">⚠ Individual test names unavailable — full report data not uploaded.<br>'
                    f'<strong>Counts:</strong> '
                    f'<span class="badge failed">{failed_c} failed</span> '
                    f'<span class="badge broken">{broken_c} broken</span> '
                    f'<span class="badge pass">{passed_c} passed</span> '
                    f'<span class="badge skip">{skipped_c} skipped</span>'
                    f'<br>{links}</p>'
                )
            elif ed.get("report_url"):
                no_data = f'<p class="muted warn">⚠ Test data fetch failed — report exists but could not be read. Check Allure directly.{links}</p>'
            else:
                no_data = f'<p class="muted warn">⚠ Build failed before tests ran — no report data.{links}</p>'
        else:
            no_data = '<p class="muted">✓ No failures.</p>'
        edition_sections += f"""
      <div class="edition-block">
        <h4>Functional Tests {label} {fail_badge}</h4>
        {table if table else no_data}
      </div>"""

    svc_block = render_svc_block(pr.get("svc"))

    return f"""
  <div class="pr-card">
    <div class="pr-header">
      <span class="pr-num"><a href="{pr_url}" target="_blank">#{pr['pr_number']}</a></span>
      <span class="pr-title">{title}</span>
      <span class="pr-meta">by <strong>{author}</strong> · <code>{branch}</code></span>
    </div>
    {svc_block}
    <div class="editions">
      {edition_sections}
    </div>
  </div>"""


def render_summary_table(prs: list[dict]) -> str:
    rows = ""
    for pr in prs:
        ce = failure_count_badge(pr["editions"].get("ce", {"status": "not_run", "failures": []}))
        ee = failure_count_badge(pr["editions"].get("ee", {"status": "not_run", "failures": []}))
        b2b = failure_count_badge(pr["editions"].get("b2b", {"status": "not_run", "failures": []}))
        svc_status = pr.get("svc", {})
        svc_b = badge(svc_status.get("status", "not_run")) if svc_status else badge("success")
        pr_url = html.escape(pr["url"])
        rows += f"""
      <tr>
        <td><a href="{pr_url}" target="_blank">#{pr['pr_number']}</a></td>
        <td>{html.escape(pr['author'])}</td>
        <td>{html.escape(pr['title'][:60])}{'…' if len(pr['title']) > 60 else ''}</td>
        <td>{ce}</td>
        <td>{ee}</td>
        <td>{b2b}</td>
        <td>{svc_b}</td>
      </tr>"""
    return f"""
  <table class="summary">
    <thead>
      <tr><th>PR</th><th>Author</th><th>Title</th><th>CE</th><th>EE</th><th>B2B</th><th>SVC</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>"""


def render_html(branch: str, prs: list[dict], generated_at: str) -> str:
    summary_table = render_summary_table(prs)
    pr_cards      = "\n".join(render_pr_card(pr) for pr in prs)
    total_prs     = len(prs)
    total_fails   = sum(
        len(pr["editions"].get(ed, {}).get("failures", []))
        for pr in prs for ed in ["ce", "ee", "b2b"]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QueuePilot Report — {html.escape(branch)}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0d1117; color: #c9d1d9; min-height: 100vh; }}
    a {{ color: #58a6ff; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 0.85em;
             background: #161b22; padding: 2px 6px; border-radius: 4px; }}

    /* Layout */
    .container {{ max-width: 98vw; margin: 0 auto; padding: 24px 32px; }}
    header {{ border-bottom: 1px solid #21262d; padding-bottom: 20px; margin-bottom: 28px; }}
    header h1 {{ font-size: 1.6rem; color: #f0f6fc; }}
    header .meta {{ margin-top: 6px; color: #8b949e; font-size: 0.85rem; }}
    .stats {{ display: flex; gap: 20px; margin: 20px 0 28px; flex-wrap: wrap; }}
    .stat-box {{ background: #161b22; border: 1px solid #21262d; border-radius: 8px;
                  padding: 14px 20px; min-width: 120px; text-align: center; }}
    .stat-box .num {{ font-size: 2rem; font-weight: 700; color: #f0f6fc; }}
    .stat-box .lbl {{ font-size: 0.75rem; color: #8b949e; text-transform: uppercase; margin-top: 2px; }}

    /* Badges */
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
               font-size: 0.75rem; font-weight: 600; white-space: nowrap; }}
    .badge.fail   {{ background: #da3633; color: #fff; }}
    .badge.pass   {{ background: #1a7f37; color: #fff; }}
    .badge.skip   {{ background: #6e7681; color: #fff; }}
    .badge.neutral{{ background: #3d444d; color: #c9d1d9; }}
    .badge.failed {{ background: #da3633; color: #fff; }}
    .badge.broken {{ background: #9e6a03; color: #fff; }}
    .badge.running{{ background: #1158c7; color: #fff; }}

    /* Summary table */
    .summary-section h2 {{ font-size: 1.1rem; color: #f0f6fc; margin-bottom: 12px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
    th {{ background: #161b22; color: #8b949e; text-align: left; padding: 8px 12px;
           border-bottom: 1px solid #21262d; font-weight: 600; text-transform: uppercase;
           font-size: 0.75rem; letter-spacing: 0.04em; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #21262d; vertical-align: middle; }}
    tr:hover td {{ background: #161b22; }}

    /* PR cards */
    .pr-section {{ margin-top: 36px; }}
    .pr-section h2 {{ font-size: 1.1rem; color: #f0f6fc; margin-bottom: 16px; }}
    .pr-card {{ background: #161b22; border: 1px solid #21262d; border-radius: 10px;
                 margin-bottom: 20px; overflow: hidden; }}
    .pr-header {{ padding: 16px 20px; border-bottom: 1px solid #21262d;
                   display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }}
    .pr-num {{ font-size: 1.1rem; font-weight: 700; color: #f0f6fc; }}
    .pr-title {{ flex: 1; font-weight: 600; color: #f0f6fc; }}
    .pr-meta {{ font-size: 0.8rem; color: #8b949e; white-space: nowrap; }}
    .editions {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: #21262d; }}
    .edition-block {{ background: #161b22; padding: 14px 24px; }}
    .edition-block h4 {{ font-size: 0.85rem; color: #8b949e; text-transform: uppercase;
                          letter-spacing: 0.05em; margin-bottom: 8px; display: flex;
                          align-items: center; gap: 8px; }}
    .failures {{ margin-top: 4px; width: 100%; table-layout: fixed; }}
    .failures td {{ padding: 4px 0; width: 100%; }}
    .failures a {{ display: inline-block; margin-top: 8px; font-size: 0.8rem; }}
    .muted {{ color: #8b949e; font-size: 0.8rem; }}
    .muted.warn {{ color: #e3b341; }}
    code.failed {{ color: #ff7b72; background: transparent; padding: 0; font-size: 0.9rem;
                   white-space: normal; word-break: break-word; display: block; width: 100%; }}
    code.broken {{ color: #e3b341; background: transparent; padding: 0; font-size: 0.9rem;
                   white-space: normal; word-break: break-word; display: block; width: 100%; }}

    /* SVC block */
    .svc-block {{ padding: 10px 20px; font-size: 0.85rem; border-bottom: 1px solid #21262d;
                   display: flex; align-items: center; gap: 10px; }}
    .fail-bg {{ background: #2d1517; }}
    .pass-bg {{ background: #12261e; }}

    footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid #21262d;
               text-align: center; color: #6e7681; font-size: 0.8rem; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>🐛 QueuePilot Report — <code>{html.escape(branch)}</code></h1>
      <div class="meta">Generated at {html.escape(generated_at)} · magento-commerce/magento2ce</div>
    </header>

    <div class="stats">
      <div class="stat-box"><div class="num">{total_prs}</div><div class="lbl">PRs in queue</div></div>
      <div class="stat-box"><div class="num">{total_fails}</div><div class="lbl">Total failures</div></div>
    </div>

    <div class="summary-section">
      <h2>Queue Summary</h2>
      {summary_table}
    </div>

    <div class="pr-section">
      <h2>Per-PR Failure Details</h2>
      {pr_cards}
    </div>

    <footer>Generated by QueuePilot · <a href="https://github.com/OneAdobe/queuepilot-agent" target="_blank">Inspired by queuepilot-agent</a></footer>
  </div>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="QueuePilot — Magento PR test failure analyzer")
    parser.add_argument("branch", help="Branch/queue name, e.g. 2.4-develop")
    parser.add_argument("--channel",  default=os.getenv("SLACK_CHANNEL", DEFAULT_CHANNEL),
                        help="Slack channel ID")
    parser.add_argument("--bot",      default=os.getenv("SLACK_BOT_ID", DEFAULT_BOT_ID),
                        help="Slack bot user ID")
    parser.add_argument("--cmd",      default=os.getenv("SLACK_BOT_CMD", DEFAULT_BOT_CMD),
                        help="Bot command to send (default: dq)")
    parser.add_argument("--repo",     default=os.getenv("GITHUB_REPO", DEFAULT_REPO),
                        help="GitHub repo slug")
    parser.add_argument("--output",   default=None, help="Output HTML file path (default: timestamped file in project dir)")
    parser.add_argument("--no-slack", action="store_true",
                        help="Skip Slack; pass PR numbers directly via --prs")
    parser.add_argument("--prs",      nargs="+", type=int,
                        help="Manually specify PR numbers (skips Slack)")
    parser.add_argument("--read-only", action="store_true",
                        help="Don't post to Slack; just read the latest qmbot response from the channel")
    args = parser.parse_args()

    print(f"\n🐛 QueuePilot — {args.branch}\n")

    # ── Step 1: Get PR list ────────────────────────────────────────────────────
    pr_numbers = []

    if args.prs:
        pr_numbers = args.prs
        print(f"Using provided PRs: {pr_numbers}")
    else:
        token = os.getenv("SLACK_TOKEN")
        if not token:
            print("ERROR: SLACK_TOKEN env var is required (or use --prs to skip Slack).")
            sys.exit(1)

        if args.read_only:
            # Read latest qmbot response without posting (message sent externally e.g. via MCP)
            print(f"1. Reading latest qmbot response from #{args.channel}...")
            msgs = slack_history(token, args.channel, oldest="0", limit=50)
            bot_text = None
            for msg in msgs:
                if msg.get("user") == args.bot:
                    bot_text = msg.get("text", "")
                    break
            if not bot_text:
                print("ERROR: No recent qmbot message found in channel.")
                sys.exit(1)
        else:
            print(f"1. Sending @qmbot {args.cmd} {args.branch} to #{args.channel}...")
            try:
                slack_join_channel(token, args.channel)
            except Exception:
                pass
            try:
                msg_data = slack_post(token, args.channel, f"<@{args.bot}> {args.cmd} {args.branch}")
            except RuntimeError as e:
                if "channel_not_found" in str(e) or "not_in_channel" in str(e):
                    print("\nERROR: Bot is not a member of this channel.")
                    print("Fix: Open the channel in Slack and run:")
                    print(f"  /invite @slack_connector")
                    print(f"  /invite @qmbot")
                    print("\nThen re-run queuepilot.")
                    sys.exit(1)
                raise
            sent_ts = msg_data["ts"]
            bot_text = wait_for_bot_reply(token, args.channel, args.bot, sent_ts)
        if not bot_text:
            print("ERROR: Timed out waiting for bot response.")
            sys.exit(1)

        pr_numbers = parse_pr_numbers(bot_text)
        if not pr_numbers:
            print(f"ERROR: Could not parse PR numbers from bot reply:\n{bot_text}")
            sys.exit(1)

        print(f"   Found {len(pr_numbers)} PR(s): {pr_numbers}")

    # ── Step 2: Analyze PRs ────────────────────────────────────────────────────
    print(f"\n2. Analyzing {len(pr_numbers)} PR(s)...")
    pr_results = []
    with ThreadPoolExecutor(max_workers=PR_WORKER_MAX) as ex:
        futures = {ex.submit(analyze_pr, args.repo, n): n for n in pr_numbers}
        for fut in as_completed(futures):
            pr_num = futures[fut]
            try:
                pr_results.append(fut.result())
            except Exception as e:
                print(f"  WARNING: Failed to analyze PR #{pr_num}: {e}")

    pr_results.sort(key=lambda x: pr_numbers.index(x["pr_number"]))

    # ── Step 3: Generate HTML ──────────────────────────────────────────────────
    now = datetime.now()
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    html_content = render_html(args.branch, pr_results, generated_at)

    if args.output:
        output_path = os.path.abspath(args.output)
    else:
        date_str = now.strftime("%Y-%m-%d")
        branch_slug = args.branch.replace("/", "-")
        # Find next available sequence number for today
        n = 1
        while True:
            filename = f"queuepilot-{branch_slug}-{date_str}-{n}.html"
            candidate = os.path.join(DEFAULT_OUTPUT_DIR, filename)
            if not os.path.exists(candidate):
                break
            n += 1
        output_path = os.path.join(DEFAULT_OUTPUT_DIR, filename)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\n✅ Done! Report saved to:\n   {output_path}\n")
    print(f"   Open with: open {output_path}\n")


if __name__ == "__main__":
    main()
