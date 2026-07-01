# AEP / CJA Config Health & Drift Audit

A productized, fixed-scope deliverable for Adobe Experience Platform (AEP) and
Customer Journey Analytics (CJA) practitioners and teams. You hand it a snapshot
of your AEP/CJA configuration; it scores the configuration's health, detects
**drift** between two points in time, and produces a clean, buyer-facing report.

> **Clean-room build.** This repository is built entirely from generic, public
> Adobe-product domain knowledge. The concepts it works with — datasets, XDM
> schemas, data views, segments/audiences, dimensions/metrics, identity
> stitching — are standard Adobe product features, not anyone's proprietary IP.
> All shipped fixtures use **synthetic, fabricated identifiers** for a fictional
> company ("Northwind Retail"). There are **zero employer or customer
> identifiers anywhere** in this project.

---

## What it is

CJA and AEP configurations drift. Datasets quietly stop ingesting. A schema
field gets removed and three dimensions silently start returning null. A data
view's session timeout or timezone changes and every historical trend breaks
without a label. Identity-stitching coverage slips from 90% to 70% and unique
counts inflate. None of this throws an error — it just corrupts the numbers
people make decisions on.

This audit catches that. It takes two configuration **snapshots** (a baseline
and a current one), runs a battery of health checks plus a full drift diff, and
emits a report a technical buyer can act on the same day.

## Who it's for

- **Adobe Analytics / CJA practitioners** who own data views, dimensions,
  metrics, and segments and need to know when something upstream changed.
- **AEP data engineers / architects** managing datasets, XDM schemas, and the
  identity graph.
- **Analytics leads / consultants** who need a credible, repeatable
  configuration audit they can put in front of a client or a stakeholder.

## What the buyer gets

A single, fixed-scope deliverable:

1. **Overall health score** (0–100, letter grade) and a **score per dimension**:
   Completeness, Freshness, Naming & Hygiene, Orphaned Components, and Identity
   Stitching.
2. **A drift report** — everything that changed between the two snapshots,
   classified by severity (Critical / Warning / Info) across datasets, schemas,
   data views, and segments.
3. **A prioritized recommendation list** — what to fix first and why.
4. Two report formats: a **Markdown** report (for tickets / wikis / PRs) and a
   **self-contained HTML** report (inline CSS, opens in any browser, no
   dependencies) that reads like a consulting deliverable.

## What it checks

**Health checks** (run against the current snapshot):

| Dimension | What it verifies |
| --- | --- |
| Completeness | Every dataset binds to a known schema; every data view references live, enabled datasets. |
| Freshness | Enabled production datasets are still receiving data (staleness detection, lookup datasets get a longer tolerance). |
| Naming & Hygiene | No `TEST_`/`TMP_`/scratch datasets enabled in a production org; consistent casing. |
| Orphaned Components | Every dimension/metric maps to a field that exists in an attached schema; every segment points to a live data view. |
| Identity Stitching | Stitched data views meet a coverage target; flags critical drops. |

**Drift detection** (baseline vs current):

- **Datasets** — added, removed, disabled, or rebound to a different schema.
- **Schemas** — fields added, removed, or type-changed.
- **Data views** — changes to session timeout, timezone, lookback window,
  person identifier, stitching toggle, and dataset membership.
- **Segments** — created, removed, redefined, or sharp size swings (>40%).

## How it runs

```bash
python3 audit.py
```

That reads the two bundled fixtures and writes the reports to `output/`.

To run it against your own exported config:

```bash
python3 audit.py \
  --before fixtures/snapshot_2026-05-01.json \
  --after  fixtures/snapshot_2026-06-15.json \
  --out    output
```

The snapshot format is plain JSON (see `fixtures/` for the schema by example):
top-level `datasets`, `schemas`, `data_views`, `segments`, `dimensions`,
`metrics`, and `stitching`. In a real engagement these snapshots are produced by
a thin read-only collector against the AEP/CJA APIs; this demo ships
pre-captured synthetic snapshots so it runs fully offline.

## Requirements

**None beyond Python 3.8+.** Standard library only — no `pip install`, no
network calls, no paid infrastructure. See `requirements.txt`.

## Repository layout

```
aep-audit-demo/
├── README.md                       # this file
├── requirements.txt                # confirms zero external dependencies
├── audit.py                        # the audit orchestrator (stdlib only)
├── fixtures/
│   ├── snapshot_2026-05-01.json    # synthetic baseline config
│   └── snapshot_2026-06-15.json    # synthetic current config (with drift)
└── output/
    ├── sample-audit-report.md      # generated buyer-facing report (Markdown)
    └── sample-audit-report.html    # generated buyer-facing report (HTML)
```

## The sample report

`output/sample-audit-report.{md,html}` is the actual artifact a buyer sees,
generated by running `audit.py` against the two bundled snapshots. The synthetic
fixtures contain deliberately planted drift — a stale dataset, a removed schema
field, a disabled dataset still wired into a data view, a redefined segment, a
stitching-coverage collapse, a new dataset bound to an unpublished schema — so
the report demonstrates every category of finding.
