# Data schema (v1)

`data/lawsuits.json` has this top-level shape:

```json
{
  "schema_version": 1,
  "last_updated": "2026-08-03",
  "notes": "...",
  "aggregate_trackers": [ ... ],
  "lawsuits": [ ... ]
}
```

## Why this schema is flatter than flock-misuse-tracker's

[flock-misuse-tracker](https://github.com/DeFlockBHM/flock-misuse-tracker)
splits records into `incidents[]` and `cases[]` because officer-misuse sweeps
are routinely reported as "N officers arrested" well before every name is
public — a count-before-names problem that needs two linked record types to
handle without double-counting.

Civil litigation doesn't have that problem: a lawsuit is filed as a single
named case (`Doe v. Flock Safety, Inc.`) with a docket number from day one,
and there are far fewer of them. So `lawsuits[]` is one flat array — no
incident-wrapper layer, no `parent_incident_id` indirection.

## `lawsuits[]`

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable slug, e.g. `doe-v-flock-safety-2026-ca` |
| `case_name` | string | Full case caption, e.g. `Doe v. Flock Safety, Inc.` |
| `court` | string | e.g. `N.D. Cal.`, `Superior Court of Fulton County, GA` |
| `state` | string | Two-letter state code (jurisdiction, not necessarily where filed) |
| `filed_date` | ISO date or year/month string | As precise as the source allows |
| `defendant_type` | string | `deploying_agency` \| `flock_inc` \| `both` \| `other` — per the project brief, defendant identity is a field, not a repo split |
| `defendants` | array of strings | Named defendant(s) |
| `plaintiffs` | array of strings | Named plaintiff(s), or `["Unnamed (role/class)"]` if not yet public |
| `claim_type` | string | `fourth_amendment` \| `data_broker_privacy` \| `class_action` \| `public_records` \| `contract_procurement` \| `other` \| `mixed` |
| `allegation_summary` | string | 1–3 sentence factual summary |
| `status` | string | `filed` \| `ongoing` \| `dismissed` \| `settled` \| `ruling_for_plaintiff` \| `ruling_for_defendant` \| `appealed` \| `voluntarily_dismissed` |
| `status_detail` | string | Specific dates, ruling details, settlement terms if known; also where the script notes any uncertainty |
| `last_updated` | ISO date | Most recent known development |
| `sources` | array of strings | Source URLs — news coverage, not court-filing lookups (see Deliberate omissions) |
| `content_hash` | string | `sha256:` hash of `allegation_summary + status_detail + status`, recomputed on every update |
| `first_seen_at` / `last_seen_at` | ISO datetime | Append-only provenance — `first_seen_at` is never overwritten |
| `verified` | bool | Defaults to `false`; flipped to `true` on manual review |

## `aggregate_trackers[]`

Same convention as flock-misuse-tracker: external running counts (e.g. EFF's
or IJ's lawsuit trackers, if they publish one) that should be **checked
against, not summed with**, `lawsuits[]`.

## Deliberate omissions

This tracker is sourced from **news coverage only**, not PACER/court-filing
lookups or legal-database searches (CourtListener, Bloomberg Law, etc.). A
case's presence here means it was reported on, not that this is a complete
docket history. `status_detail` should note when a development is known only
secondhand through news reporting and hasn't been confirmed against a filing.

## Review workflow

Same as flock-misuse-tracker: nothing the automated script writes is
`verified: true`. A human periodically reviews `data/weekly-log/` entries and
anything with `verified: false` and corrects/confirms in `data/lawsuits.json`
directly.
