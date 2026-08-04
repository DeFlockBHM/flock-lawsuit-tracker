#!/usr/bin/env python3
"""
Weekly Flock Safety civil-lawsuit tracker updater (schema v1).

Loads the existing dataset (data/lawsuits.json), asks Claude (with the
web_search tool) to find developments from the last ~7-10 days via news
coverage, and merges results:

  - New lawsuits become an entry in `lawsuits[]`.
  - Status changes to existing lawsuits (filed -> dismissed, settled, ruling,
    appealed) update the existing entry by id.
  - All new/updated entries are written with verified: false -- auto-writing
    is a claim, not a fact, and should get human review later.
  - A content_hash is stored per entry (hash of the mutable summary fields)
    so future runs can cheaply detect when an entry's known facts have
    changed, without needing to re-fetch or archive the source article.

This tracker is sourced from news coverage only, not PACER/court-filing
lookups or legal databases -- see SCHEMA.md "Deliberate omissions".

Requires the ANTHROPIC_API_KEY environment variable (GitHub Actions secret).
"""
import hashlib
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAWSUITS_PATH = os.path.join(REPO_ROOT, "data", "lawsuits.json")
LOG_DIR = os.path.join(REPO_ROOT, "data", "weekly-log")

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOKENS = 8000

SYSTEM_PROMPT = """You are a research assistant maintaining a factual, well-sourced \
tracker of civil lawsuits related to Flock Safety ALPR (automated license plate \
reader) technology, in the United States. Defendants may be the law enforcement \
agency that deployed the cameras (e.g. Fourth Amendment claims) or Flock Safety, Inc. \
itself (e.g. data-broker/privacy claims), or both.

You are sourced from NEWS COVERAGE ONLY -- not PACER, court-filing lookups, or legal \
databases (CourtListener, Bloomberg Law, etc.). Only report what news articles \
describe; do not look up or infer docket details not mentioned in a news source.

Fields for each lawsuit entry:
  id, case_name, court, state, filed_date, defendant_type \
("deploying_agency" | "flock_inc" | "both" | "other"), defendants (array), \
plaintiffs (array, or ["Unnamed (role/class)"] if not yet public), claim_type \
("fourth_amendment" | "data_broker_privacy" | "class_action" | "public_records" | \
"contract_procurement" | "other" | "mixed"), allegation_summary, status \
("filed" | "ongoing" | "dismissed" | "settled" | "ruling_for_plaintiff" | \
"ruling_for_defendant" | "appealed" | "voluntarily_dismissed"), status_detail, \
last_updated, sources.

You will be given the CURRENT lawsuits (trimmed). Your job is to search the web for \
developments in roughly the last 7-10 days ONLY, and identify:

  1. Brand-new lawsuits not already in the dataset.
  2. Status changes to existing lawsuits (e.g. filed -> dismissed, a ruling, a \
     settlement, an appeal). Reference the existing id.

If nothing new is found in the time window, say so explicitly -- do not pad the \
response with things already in the dataset, and do not invent or guess at case \
details, parties, or outcomes not reported by a source.

Respond in two parts, in this exact order:

PART 1 -- a concise human-readable markdown summary of what's new (or "No new \
developments found this week"), with inline source citations as plain URLs.

PART 2 -- a fenced ```json code block containing ONE object with one array, using \
this exact schema (omit fields you don't know, but always include id and status):

{
  "new_or_updated_lawsuits": [
    {
      "id": "case-name-slug-year-st",
      "case_name": "Doe v. Flock Safety, Inc.",
      "court": "N.D. Cal.",
      "state": "XX",
      "filed_date": "YYYY-MM-DD",
      "defendant_type": "flock_inc",
      "defendants": ["Flock Safety, Inc."],
      "plaintiffs": ["Jane Doe"],
      "claim_type": "data_broker_privacy",
      "allegation_summary": "One to three sentence factual summary",
      "status": "filed",
      "status_detail": "Specific dates, ruling details, or settlement terms if known",
      "last_updated": "YYYY-MM-DD",
      "sources": ["https://..."]
    }
  ]
}

If there's nothing new, output {"new_or_updated_lawsuits": []}.

Follow standard copyright practice: paraphrase everything, never quote more than a \
short phrase from any source, and cite sources as plain URLs (not embedded quotes).
"""


def load_dataset():
    with open(LAWSUITS_PATH, "r") as f:
        return json.load(f)


def save_dataset(data):
    with open(LAWSUITS_PATH, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def content_hash(entry):
    material = "|".join([
        entry.get("allegation_summary", ""),
        entry.get("status_detail", ""),
        entry.get("status", ""),
    ])
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def call_claude(dataset):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    trimmed_lawsuits = [
        {
            "id": l["id"],
            "case_name": l.get("case_name"),
            "state": l.get("state"),
            "defendant_type": l.get("defendant_type"),
            "status": l.get("status"),
        }
        for l in dataset["lawsuits"]
    ]

    user_message = (
        "Current lawsuits:\n" + json.dumps(trimmed_lawsuits, indent=2)
        + f"\n\nToday's date is {date.today().isoformat()}. Search for developments "
        "in Flock Safety-related civil litigation from roughly the last 7-10 days "
        "and report per the instructions."
    )

    body = json.dumps(
        {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_message}],
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=300) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    text_blocks = [b["text"] for b in payload.get("content", []) if b.get("type") == "text"]
    return "\n".join(text_blocks)


def split_response(full_text):
    match = re.search(r"```json\s*(\{.*?\})\s*```", full_text, re.DOTALL)
    if not match:
        return full_text.strip(), {"new_or_updated_lawsuits": []}

    summary = full_text[: match.start()].strip()
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        parsed = {"new_or_updated_lawsuits": []}
    parsed.setdefault("new_or_updated_lawsuits", [])
    return summary, parsed


def merge(dataset, parsed):
    now = datetime.now(timezone.utc).isoformat()
    lawsuits_by_id = {l["id"]: l for l in dataset["lawsuits"]}

    added, updated = [], []

    for entry in parsed["new_or_updated_lawsuits"]:
        lid = entry.get("id")
        if not lid:
            continue

        if lid in lawsuits_by_id:
            lawsuits_by_id[lid].update({k: v for k, v in entry.items() if v is not None})
            lawsuits_by_id[lid]["content_hash"] = content_hash(lawsuits_by_id[lid])
            lawsuits_by_id[lid]["last_seen_at"] = now
            lawsuits_by_id[lid]["verified"] = False
            updated.append(lid)
        else:
            entry["content_hash"] = content_hash(entry)
            entry["first_seen_at"] = now
            entry["last_seen_at"] = now
            entry["verified"] = False
            dataset["lawsuits"].append(entry)
            lawsuits_by_id[lid] = entry
            added.append(lid)

    return added, updated


def main():
    dataset = load_dataset()
    full_text = call_claude(dataset)
    summary, parsed = split_response(full_text)

    added, updated = merge(dataset, parsed)
    today = date.today().isoformat()
    dataset["last_updated"] = today
    save_dataset(dataset)

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"{today}.md")
    with open(log_path, "w") as f:
        f.write(f"# Flock Lawsuit Tracker — Weekly Update ({today})\n\n")
        f.write(summary + "\n\n")
        if added:
            f.write(f"**New lawsuits:** {', '.join(added)}\n\n")
        if updated:
            f.write(f"**Updated lawsuits:** {', '.join(updated)}\n\n")
        if not (added or updated):
            f.write("_No structured changes this run._\n")
        f.write(
            f"\n---\n_Generated {datetime.now(timezone.utc).isoformat()} "
            f"by scripts/update_tracker.py using model `{MODEL}`._\n"
        )

    print(f"Wrote {log_path}")
    print(f"New lawsuits: {added}")
    print(f"Updated lawsuits: {updated}")


if __name__ == "__main__":
    main()
