"""Manage GitHub issues for models missing pricing.

Uses the `gh` CLI (available in GitHub Actions) so we don't need a Python gh lib.

Subcommands:
  resolve-existing   Re-check open missing-pricing issues; close any now-resolved.
  open-missing       Open issues for models in outputs/missing_pricing.json that
                     don't already have an open issue.
  open-failure       Open a single pipeline-failure issue (dedup'd).

Issue bodies embed <!-- model:<normalized> --> so the model identity survives
titles being edited.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fetch_pricing import fetch_aa_pricing
from join import normalize_name

LABEL_MISSING = "missing-pricing"
LABEL_FAILURE = "pipeline-failure"
MODEL_TAG = re.compile(r"<!--\s*model:([^\s>]+)\s*-->")

OUTPUTS = Path(__file__).parent.parent / "outputs"
MISSING_JSON = OUTPUTS / "missing_pricing.json"


def _gh(*args: str, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        check=check,
        text=True,
        capture_output=True,
        input=input_text,
    )


def _ensure_label(name: str, color: str, description: str) -> None:
    try:
        _gh("label", "create", name, "--color", color, "--description", description, check=True)
    except subprocess.CalledProcessError as exc:
        if "already exists" not in (exc.stderr or ""):
            raise


def _list_open_issues(label: str) -> list[dict]:
    res = _gh(
        "issue", "list",
        "--label", label,
        "--state", "open",
        "--json", "number,title,body",
        "--limit", "500",
    )
    return json.loads(res.stdout or "[]")


def _extract_model_tag(body: str) -> str | None:
    m = MODEL_TAG.search(body or "")
    return m.group(1) if m else None


def resolve_existing() -> None:
    issues = _list_open_issues(LABEL_MISSING)
    if not issues:
        print("No open missing-pricing issues.")
        return

    # Reuse the AA response cached by build_data.py to avoid a second API call.
    price_df = fetch_aa_pricing(use_cache=True)
    price_df["normalized"] = price_df["name"].apply(normalize_name)
    priced = set(price_df.loc[price_df["price_blended"].notna(), "normalized"])

    for issue in issues:
        tag = _extract_model_tag(issue.get("body", ""))
        if not tag:
            print(f"#{issue['number']}: no model tag found, skipping")
            continue
        if tag in priced:
            row = price_df.loc[price_df["normalized"] == tag].iloc[0]
            comment = (
                f"Pricing is now available for `{tag}`:\n\n"
                f"- input: ${row['price_input']}/M\n"
                f"- output: ${row['price_output']}/M\n"
                f"- 3:1 blend: ${row['price_blended']}/M\n\n"
                f"Closing automatically."
            )
            _gh("issue", "close", str(issue["number"]), "--comment", comment)
            print(f"#{issue['number']}: closed (pricing found for {tag})")
        else:
            print(f"#{issue['number']}: still missing pricing for {tag}")


def open_missing() -> None:
    if not MISSING_JSON.exists():
        print(f"{MISSING_JSON} not found; nothing to do")
        return

    payload = json.loads(MISSING_JSON.read_text())
    missing = payload.get("missing", [])
    if not missing:
        print("No models missing pricing.")
        return

    _ensure_label(
        LABEL_MISSING,
        "d73a4a",
        "An ECI model has no pricing data on Artificial Analysis",
    )

    existing = {_extract_model_tag(i.get("body", "")) for i in _list_open_issues(LABEL_MISSING)}
    existing.discard(None)

    today = datetime.now(timezone.utc).date().isoformat()
    for entry in missing:
        tag = entry["normalized"]
        if tag in existing:
            print(f"{tag}: issue already open, skipping")
            continue
        title = f"Missing pricing for {entry['model']}"
        eci_str = f"{entry['eci']:.2f}" if entry.get("eci") is not None else "n/a"
        body = (
            f"<!-- model:{tag} -->\n\n"
            f"Epoch lists an ECI score for **{entry['model']}** but no matching entry was "
            f"found in the Artificial Analysis pricing API.\n\n"
            f"- ECI: {eci_str}\n"
            f"- Normalized join key: `{tag}`\n"
            f"- First noticed: {today}\n\n"
            f"If this is a naming mismatch, add an entry to "
            f"`data/name_overrides.json` mapping the Epoch name to the AA name. "
            f"Otherwise, this will auto-close once AA publishes pricing."
        )
        _gh("issue", "create", "--title", title, "--body", body, "--label", LABEL_MISSING)
        print(f"{tag}: opened issue '{title}'")


def open_failure(run_url: str | None = None) -> None:
    _ensure_label(
        LABEL_FAILURE,
        "b60205",
        "Daily pipeline run crashed",
    )
    existing = _list_open_issues(LABEL_FAILURE)
    if existing:
        print(f"Pipeline-failure issue already open (#{existing[0]['number']}); skipping")
        return

    today = datetime.now(timezone.utc).date().isoformat()
    body_parts = [
        f"The daily pricing pipeline failed on {today}.",
        "",
        f"Run: {run_url}" if run_url else "",
        "",
        "Check the workflow logs for the traceback. Close this issue once the pipeline is green again.",
    ]
    _gh(
        "issue", "create",
        "--title", f"Pricing pipeline failed on {today}",
        "--body", "\n".join(p for p in body_parts if p is not None),
        "--label", LABEL_FAILURE,
    )
    print("Opened pipeline-failure issue")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("resolve-existing", help="Close missing-pricing issues that are now resolved")
    sub.add_parser("open-missing", help="Open issues for new missing-pricing entries")
    p_fail = sub.add_parser("open-failure", help="Open a pipeline-failure issue if none exists")
    p_fail.add_argument("--run-url", default=None)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    if args.command == "resolve-existing":
        resolve_existing()
    elif args.command == "open-missing":
        open_missing()
    elif args.command == "open-failure":
        open_failure(args.run_url)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
