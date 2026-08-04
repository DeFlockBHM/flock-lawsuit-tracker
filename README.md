# Flock Lawsuit Tracker

An automatically-updating dataset tracking **civil litigation** related to
Flock Safety ALPR (automated license plate reader) technology — whether the
defendant is the law enforcement agency that deployed the cameras (e.g.
Fourth Amendment claims) or Flock Safety, Inc. itself (e.g.
data-broker/privacy claims). Defendant identity is tracked as a field on
each entry rather than split across repos.

- `data/lawsuits.json` — the structured, running dataset. Launched empty;
  populated by the automated weekly run.
- `data/weekly-log/` — one dated markdown report per run, summarizing what
  changed.
- `scripts/update_tracker.py` — calls the Claude API (with the web search
  tool) to look for new filings and status changes, sourced from **news
  coverage only** (not PACER or legal-database lookups — see SCHEMA.md).

## How it stays current

A scheduled job re-checks Flock-related civil litigation weekly, searching
for developments in roughly the last 7-10 days, and appends or updates
entries in `data/lawsuits.json`. Everything it writes lands as
`verified: false` — see **Data quality / review model** below — and a
summary of each run is saved to `data/weekly-log/`.

## Data schema

`data/lawsuits.json` is a single flat array of lawsuit entries — unlike
[flock-misuse-tracker](https://github.com/DeFlockBHM/flock-misuse-tracker)'s
`incidents[]`/`cases[]` split, which exists to handle "N officers arrested"
sweeps reported before names are public. Civil suits don't have that
problem: each is a single named case from the moment it's filed, and there
are far fewer of them. See [`SCHEMA.md`](SCHEMA.md) for the full field
reference.

`data/lawsuits.json` also has an `aggregate_trackers` array for external
running counts (e.g. EFF's or IJ's own lawsuit trackers, if they publish
one) that should be checked against, not summed with, `lawsuits[]`.

## Data quality / review model

Everything the automated script writes is `verified: false` by default.
Check `data/weekly-log/` after each run and periodically review
`verified: false` entries in `data/lawsuits.json`.

## Known limitations

- This is a **best-effort, LLM-assisted tracker**, not an official or legal
  record. Always check the cited sources before relying on any entry.
- **News-sourced only.** This tracker does not query PACER, CourtListener,
  or other legal databases — coverage depends entirely on what's been
  publicly reported. A case with sparse or no news coverage won't appear
  here even if it exists on a docket somewhere.
- The search window per run is narrow (~7-10 days) by design, to keep runs
  cheap and reports incremental — it isn't meant to re-verify the entire
  dataset each time.
