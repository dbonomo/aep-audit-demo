#!/usr/bin/env python3
"""
AEP/CJA Config Health & Drift Audit
====================================

A clean-room, standard-library-only auditor for Adobe Experience Platform (AEP)
and Customer Journey Analytics (CJA) configurations.

It reads two point-in-time configuration snapshots (JSON), runs a battery of
config-health checks and drift-detection checks, scores each health dimension,
and emits a buyer-facing Markdown report and a self-contained HTML report.

Usage:
    python3 audit.py
    python3 audit.py --before fixtures/snapshot_2026-05-01.json \\
                     --after  fixtures/snapshot_2026-06-15.json \\
                     --out    output

No third-party dependencies. Python 3.8+ standard library only.

All concepts here (datasets, XDM schemas, data views, segments, dimensions,
metrics, identity stitching) are generic Adobe-product concepts. The fixtures
shipped alongside this script use entirely synthetic, fabricated identifiers
for a fictional company ("Northwind Retail"). No real organization is
represented.
"""

import argparse
import datetime as dt
import html
import json
import os
import sys
from collections import defaultdict

# --------------------------------------------------------------------------- #
# Configuration / thresholds
# --------------------------------------------------------------------------- #

# A dataset is considered "stale" if it has received no batch within this many
# hours, despite being enabled and tagged production.
STALE_HOURS = 48

# Stitching coverage thresholds (percent of records resolved to a person ID).
STITCH_WARN = 85.0
STITCH_CRIT = 75.0

# A drop in stitching coverage greater than this many points between snapshots
# is flagged regardless of absolute level.
STITCH_DROP_WARN = 5.0
STITCH_DROP_CRIT = 15.0

# Naming convention: production datasets are expected to be lower_snake_case and
# not prefixed with TEST_/TMP_/SANDBOX_.
BAD_NAME_PREFIXES = ("TEST_", "TMP_", "SANDBOX_", "DEV_", "DELETE_")

SEVERITY_ORDER = {"Critical": 0, "Warning": 1, "Info": 2}


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

class Finding:
    """A single audit observation."""

    def __init__(self, severity, category, title, detail, recommendation=""):
        assert severity in SEVERITY_ORDER, severity
        self.severity = severity
        self.category = category
        self.title = title
        self.detail = detail
        self.recommendation = recommendation

    def sort_key(self):
        return (SEVERITY_ORDER[self.severity], self.category, self.title)


class Snapshot:
    """Typed accessor over a raw snapshot dict."""

    def __init__(self, raw):
        self.raw = raw
        self.meta = raw.get("_meta", {})
        self.datasets = raw.get("datasets", [])
        self.schemas = raw.get("schemas", [])
        self.data_views = raw.get("data_views", [])
        self.segments = raw.get("segments", [])
        self.dimensions = raw.get("dimensions", [])
        self.metrics = raw.get("metrics", [])
        self.stitching = raw.get("stitching", {})

    @property
    def captured_at(self):
        return parse_ts(self.meta.get("snapshot_at"))

    # Index helpers --------------------------------------------------------- #
    def datasets_by_id(self):
        return {d["id"]: d for d in self.datasets}

    def schemas_by_id(self):
        return {s["id"]: s for s in self.schemas}

    def data_views_by_id(self):
        return {v["id"]: v for v in self.data_views}

    def segments_by_id(self):
        return {s["id"]: s for s in self.segments}

    def schema_field_paths(self, schema_id):
        s = self.schemas_by_id().get(schema_id)
        if not s:
            return set()
        return {f["path"] for f in s.get("fields", [])}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def parse_ts(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def load_snapshot(path):
    with open(path, "r", encoding="utf-8") as fh:
        return Snapshot(json.load(fh))


def pct_to_grade(score):
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))


# --------------------------------------------------------------------------- #
# Health checks (run against the "after" snapshot)
# --------------------------------------------------------------------------- #

class HealthResult:
    def __init__(self):
        self.findings = []
        # dimension name -> (score 0-100, one-line rationale)
        self.scores = {}

    def add(self, *findings):
        self.findings.extend(findings)


def check_completeness(snap, result):
    """Datasets must map to a known schema; data views must reference live
    datasets; dimensions/metrics must map to real schema fields."""
    score = 100.0
    schemas = snap.schemas_by_id()
    datasets = snap.datasets_by_id()

    # Datasets -> schema existence (schema mismatch).
    for d in snap.datasets:
        if d["schema_id"] not in schemas:
            score -= 12
            result.add(Finding(
                "Critical", "Completeness",
                f"Dataset '{d['name']}' references an unknown schema",
                f"Dataset {d['id']} is bound to schema '{d['schema_id']}', "
                f"which is not present in the schema registry snapshot. "
                f"Reporting on this dataset will fail or silently drop fields.",
                "Confirm the schema exists and is published; rebind the dataset "
                "or restore the missing schema.",
            ))

    # Data views -> dataset existence + enabled.
    for v in snap.data_views:
        for ds_id in v.get("datasets", []):
            ds = datasets.get(ds_id)
            if ds is None:
                score -= 10
                result.add(Finding(
                    "Critical", "Completeness",
                    f"Data view '{v['name']}' references a missing dataset",
                    f"Data view {v['id']} includes dataset {ds_id}, which no "
                    f"longer exists in the snapshot.",
                    "Remove the orphaned dataset reference or restore the dataset.",
                ))
            elif not ds.get("enabled", True):
                score -= 6
                result.add(Finding(
                    "Warning", "Completeness",
                    f"Data view '{v['name']}' includes a disabled dataset",
                    f"Dataset '{ds['name']}' ({ds_id}) is disabled but still "
                    f"attached to data view {v['id']}. Its data will quietly stop "
                    f"flowing into reports.",
                    "Re-enable the dataset or detach it from the data view and "
                    "communicate the metric impact to stakeholders.",
                ))

    result.scores["Completeness"] = (
        clamp(score),
        "Datasets, schemas, and data-view references resolve cleanly.",
    )


def check_staleness(snap, result):
    """Enabled production datasets should be receiving data."""
    score = 100.0
    now = snap.captured_at or dt.datetime.now(dt.timezone.utc)
    stale = 0
    prod_datasets = [d for d in snap.datasets if "production" in d.get("tags", [])]

    for d in prod_datasets:
        if not d.get("enabled", True):
            continue
        last = parse_ts(d.get("last_batch_at"))
        if last is None:
            continue
        age_h = (now - last).total_seconds() / 3600.0
        is_lookup = "lookup" in d.get("tags", []) or "reference" in d.get("tags", [])
        threshold = STALE_HOURS * 4 if is_lookup else STALE_HOURS
        if age_h > threshold:
            stale += 1
            sev = "Critical" if age_h > threshold * 3 else "Warning"
            score -= 12 if sev == "Critical" else 7
            result.add(Finding(
                sev, "Staleness",
                f"Dataset '{d['name']}' has stopped receiving data",
                f"Last batch was {fmt_age(age_h)} ago "
                f"(last_batch_at={d.get('last_batch_at')}). The dataset is "
                f"enabled and tagged production but ingested "
                f"{d.get('record_count_24h', 0):,} records in the last 24h.",
                "Check the ingestion source / data feed for this dataset; a "
                "broken pipeline silently degrades every report and audience "
                "built on it.",
            ))

    result.scores["Freshness"] = (
        clamp(score),
        f"{len(prod_datasets) - stale}/{len(prod_datasets)} production datasets fresh.",
    )


def check_naming(snap, result):
    """Production datasets should follow naming convention and not be test/scratch."""
    score = 100.0
    offenders = 0
    for d in snap.datasets:
        name = d["name"]
        bad_prefix = name.upper().startswith(BAD_NAME_PREFIXES)
        is_prod = "production" in d.get("tags", [])
        if bad_prefix and (is_prod or d.get("enabled", True)):
            offenders += 1
            score -= 8
            result.add(Finding(
                "Warning", "Naming & Hygiene",
                f"Test/scratch dataset '{name}' is enabled in production org",
                f"Dataset {d['id']} uses a scratch prefix yet is enabled. "
                f"Scratch datasets in a production org inflate cost, pollute the "
                f"schema picker, and risk accidental inclusion in data views.",
                "Disable or delete scratch datasets, or move them to a "
                "development sandbox.",
            ))
        elif name != name.lower() and not bad_prefix:
            score -= 3
            result.add(Finding(
                "Info", "Naming & Hygiene",
                f"Dataset '{name}' is not lower_snake_case",
                "Inconsistent casing makes datasets harder to find and script "
                "against.",
                "Adopt a single naming convention (lower_snake_case) across "
                "datasets.",
            ))
    result.scores["Naming & Hygiene"] = (
        clamp(score),
        f"{offenders} naming/hygiene offender(s) found.",
    )


def check_orphans(snap, result):
    """Dimensions/metrics must map to a field that exists in at least one of the
    data view's underlying schemas; segments must reference a live data view."""
    score = 100.0
    dvs = snap.data_views_by_id()
    datasets = snap.datasets_by_id()

    def fields_for_data_view(dv):
        paths = set()
        for ds_id in dv.get("datasets", []):
            ds = datasets.get(ds_id)
            if ds:
                paths |= snap.schema_field_paths(ds["schema_id"])
        return paths

    orphan_count = 0
    for kind, items in (("dimension", snap.dimensions), ("metric", snap.metrics)):
        for item in items:
            dv = dvs.get(item["data_view_id"])
            if dv is None:
                continue
            available = fields_for_data_view(dv)
            if item["source_field"] not in available:
                orphan_count += 1
                score -= 9
                result.add(Finding(
                    "Critical", "Orphaned Components",
                    f"{kind.capitalize()} '{item['name']}' maps to a missing field",
                    f"In data view '{dv['name']}', the {kind} is sourced from "
                    f"'{item['source_field']}', which no longer exists in any "
                    f"attached schema. The component will return null/empty.",
                    f"Repoint the {kind} to a valid field or restore the field in "
                    f"the schema.",
                ))

    # Segments -> live data view.
    for seg in snap.segments:
        if seg.get("data_view_id") not in dvs:
            score -= 8
            result.add(Finding(
                "Warning", "Orphaned Components",
                f"Segment '{seg['name']}' references a missing data view",
                f"Segment {seg['id']} is bound to data view "
                f"{seg.get('data_view_id')}, which is not present.",
                "Rebind the segment to an existing data view.",
            ))

    result.scores["Orphaned Components"] = (
        clamp(score),
        f"{orphan_count} orphaned dimension/metric(s).",
    )


def check_stitching(snap, result):
    """Identity stitching coverage should be high for stitched data views."""
    score = 100.0
    measured = 0
    for dv_id, info in snap.stitching.items():
        dv = snap.data_views_by_id().get(dv_id)
        dv_name = dv["name"] if dv else dv_id
        stitched = dv.get("stitching_enabled", False) if dv else False
        coverage = info.get("coverage_pct", 0.0)
        if not stitched:
            continue
        measured += 1
        if coverage < STITCH_CRIT:
            score -= 18
            result.add(Finding(
                "Critical", "Identity Stitching",
                f"Stitching coverage critically low on '{dv_name}'",
                f"Person-ID resolution is at {coverage:.1f}% "
                f"(method={info.get('method')}, primary={info.get('primary_identity')}). "
                f"Below {STITCH_CRIT:.0f}% means a large share of events are "
                f"counted as anonymous, inflating unique counts and fragmenting "
                f"journeys.",
                "Audit the identity graph and event-level identity population; "
                "verify the primary identity is set and populated on all "
                "attached datasets.",
            ))
        elif coverage < STITCH_WARN:
            score -= 9
            result.add(Finding(
                "Warning", "Identity Stitching",
                f"Stitching coverage below target on '{dv_name}'",
                f"Coverage is {coverage:.1f}% (target >= {STITCH_WARN:.0f}%).",
                "Investigate datasets contributing un-keyed events.",
            ))
    if measured == 0:
        result.scores["Identity Stitching"] = (100.0, "No stitched data views to assess.")
    else:
        result.scores["Identity Stitching"] = (
            clamp(score),
            f"{measured} stitched data view(s) assessed.",
        )


# --------------------------------------------------------------------------- #
# Drift detection (before vs after)
# --------------------------------------------------------------------------- #

def fmt_age(hours):
    if hours < 48:
        return f"{hours:.0f}h"
    return f"{hours / 24:.1f}d"


def diff_datasets(before, after, result):
    b = before.datasets_by_id()
    a = after.datasets_by_id()

    for ds_id in a.keys() - b.keys():
        ds = a[ds_id]
        result.add(Finding(
            "Info", "Drift: Datasets",
            f"New dataset added: '{ds['name']}'",
            f"Dataset {ds_id} (schema {ds['schema_id']}) appeared since the "
            f"baseline snapshot.",
            "Confirm the new dataset is intentional and governed (schema, "
            "naming, data view membership).",
        ))

    for ds_id in b.keys() - a.keys():
        ds = b[ds_id]
        result.add(Finding(
            "Warning", "Drift: Datasets",
            f"Dataset removed: '{ds['name']}'",
            f"Dataset {ds_id} present at baseline is gone in the latest "
            f"snapshot. Any data view or audience referencing it is now broken.",
            "Confirm the deletion was intentional and downstream references "
            "were cleaned up.",
        ))

    for ds_id in a.keys() & b.keys():
        bd, ad = b[ds_id], a[ds_id]
        if bd.get("enabled") and not ad.get("enabled"):
            result.add(Finding(
                "Warning", "Drift: Datasets",
                f"Dataset disabled: '{ad['name']}'",
                f"Dataset {ds_id} was enabled at baseline and is now disabled. "
                f"Data flow has stopped.",
                "Verify this was intentional; downstream reports will show a "
                "step-change drop.",
            ))
        if bd.get("schema_id") != ad.get("schema_id"):
            result.add(Finding(
                "Critical", "Drift: Datasets",
                f"Dataset '{ad['name']}' was rebound to a different schema",
                f"Schema changed from '{bd.get('schema_id')}' to "
                f"'{ad.get('schema_id')}'. Field-level reporting may break.",
                "Validate field mappings against the new schema.",
            ))


def diff_schemas(before, after, result):
    b = before.schemas_by_id()
    a = after.schemas_by_id()
    for sid in a.keys() & b.keys():
        bf = {f["path"]: f for f in b[sid].get("fields", [])}
        af = {f["path"]: f for f in a[sid].get("fields", [])}
        title = a[sid].get("title", sid)
        added = af.keys() - bf.keys()
        removed = bf.keys() - af.keys()
        for path in sorted(added):
            result.add(Finding(
                "Info", "Drift: Schemas",
                f"Field added to schema '{title}'",
                f"New field '{path}' ({af[path].get('type')}) added.",
                "Consider exposing the new field as a dimension/metric if it is "
                "analytically useful.",
            ))
        for path in sorted(removed):
            result.add(Finding(
                "Critical", "Drift: Schemas",
                f"Field removed from schema '{title}'",
                f"Field '{path}' present at baseline was removed. Any dimension, "
                f"metric, or segment referencing it will break.",
                "Trace every component built on this field before removing it; "
                "restore if still in use.",
            ))
        for path in af.keys() & bf.keys():
            if af[path].get("type") != bf[path].get("type"):
                result.add(Finding(
                    "Warning", "Drift: Schemas",
                    f"Field type changed in schema '{title}'",
                    f"Field '{path}' changed type from {bf[path].get('type')} "
                    f"to {af[path].get('type')}.",
                    "Type changes can silently corrupt aggregations; validate "
                    "downstream metrics.",
                ))


def diff_data_views(before, after, result):
    b = before.data_views_by_id()
    a = after.data_views_by_id()
    watched = [
        ("session_timeout_minutes", "Session timeout"),
        ("timezone", "Reporting timezone"),
        ("lookback_months", "Lookback window"),
        ("person_id", "Person identifier"),
        ("stitching_enabled", "Stitching toggle"),
    ]
    for dv_id in a.keys() & b.keys():
        bv, av = b[dv_id], a[dv_id]
        name = av.get("name", dv_id)
        for key, label in watched:
            if bv.get(key) != av.get(key):
                sev = "Critical" if key in ("person_id", "timezone") else "Warning"
                result.add(Finding(
                    sev, "Drift: Data Views",
                    f"{label} changed on data view '{name}'",
                    f"{label} changed from '{bv.get(key)}' to '{av.get(key)}'. "
                    f"This silently shifts historical comparisons "
                    f"(sessions, day boundaries, or person counts).",
                    "Confirm the change was intentional and annotate dashboards "
                    "so trend breaks are explained.",
                ))
        # dataset membership change
        bset, aset = set(bv.get("datasets", [])), set(av.get("datasets", []))
        for ds_id in aset - bset:
            result.add(Finding(
                "Info", "Drift: Data Views",
                f"Dataset added to data view '{name}'",
                f"Dataset {ds_id} was attached to the data view.",
                "Verify metrics did not double-count after the addition.",
            ))
        for ds_id in bset - aset:
            result.add(Finding(
                "Warning", "Drift: Data Views",
                f"Dataset removed from data view '{name}'",
                f"Dataset {ds_id} was detached from the data view.",
                "Expect a drop in volume for affected metrics.",
            ))


def diff_segments(before, after, result):
    b = before.segments_by_id()
    a = after.segments_by_id()
    for sid in a.keys() - b.keys():
        result.add(Finding(
            "Info", "Drift: Segments",
            f"New segment created: '{a[sid]['name']}'",
            f"Segment {sid} appeared since baseline.",
            "Confirm ownership and activation targets for the new audience.",
        ))
    for sid in b.keys() - a.keys():
        result.add(Finding(
            "Warning", "Drift: Segments",
            f"Segment removed: '{b[sid]['name']}'",
            f"Segment {sid} present at baseline is gone.",
            "Verify no activation/destination still expects this audience.",
        ))
    for sid in a.keys() & b.keys():
        bs, as_ = b[sid], a[sid]
        if bs.get("definition") != as_.get("definition"):
            result.add(Finding(
                "Warning", "Drift: Segments",
                f"Segment '{as_['name']}' was redefined",
                f"Definition changed.\n"
                f"  Before: {bs.get('definition')}\n"
                f"  After:  {as_.get('definition')}",
                "Redefinitions break historical audience comparisons; "
                "communicate the change to activation owners.",
            ))
        size_b = bs.get("size_estimate", 0)
        size_a = as_.get("size_estimate", 0)
        if size_b and abs(size_a - size_b) / size_b >= 0.40:
            direction = "shrank" if size_a < size_b else "grew"
            result.add(Finding(
                "Warning", "Drift: Segments",
                f"Segment '{as_['name']}' {direction} sharply",
                f"Estimated size moved from {size_b:,} to {size_a:,} "
                f"({(size_a - size_b) / size_b * 100:+.0f}%).",
                "Large swings often indicate an upstream data or definition "
                "problem; investigate before activating.",
            ))


# --------------------------------------------------------------------------- #
# Scoring & reporting
# --------------------------------------------------------------------------- #

def severity_counts(findings):
    counts = defaultdict(int)
    for f in findings:
        counts[f.severity] += 1
    return counts


def overall_score(health_scores):
    if not health_scores:
        return 0.0
    return sum(s for s, _ in health_scores.values()) / len(health_scores)


def build_report_context(before, after, health, drift):
    all_findings = health.findings + drift.findings
    all_findings.sort(key=lambda f: f.sort_key())
    overall = overall_score(health.scores)
    return {
        "before": before,
        "after": after,
        "health": health,
        "drift": drift,
        "all_findings": all_findings,
        "overall": overall,
        "overall_grade": pct_to_grade(overall),
        "counts": severity_counts(all_findings),
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


# ---- Markdown ------------------------------------------------------------- #

def render_markdown(ctx):
    b, a = ctx["before"], ctx["after"]
    lines = []
    add = lines.append

    add("# AEP / CJA Config Health & Drift Audit")
    add("")
    add(f"**Organization:** {a.meta.get('company')} "
        f"(`{a.meta.get('org_slug')}`)  ")
    add(f"**Baseline snapshot:** {b.meta.get('snapshot_at')}  ")
    add(f"**Current snapshot:** {a.meta.get('snapshot_at')}  ")
    add(f"**Report generated:** {ctx['generated_at']}  ")
    add(f"**Audit engine:** aep-audit-demo (clean-room, synthetic data)")
    add("")
    add("> All identifiers in this report are synthetic. No real organization, "
        "dataset, or schema is represented.")
    add("")
    add("---")
    add("")

    # Executive summary
    add("## Executive Summary")
    add("")
    add(f"Overall configuration health: **{ctx['overall']:.0f}/100 "
        f"(grade {ctx['overall_grade']})**.")
    add("")
    c = ctx["counts"]
    add(f"We evaluated **{len(a.datasets)} datasets**, **{len(a.schemas)} schemas**, "
        f"**{len(a.data_views)} data views**, and **{len(a.segments)} segments**, "
        f"then compared the current configuration against the "
        f"{b.meta.get('snapshot_at', '')[:10]} baseline.")
    add("")
    add(f"The audit produced **{len(ctx['all_findings'])} findings**: "
        f"**{c.get('Critical', 0)} Critical**, "
        f"**{c.get('Warning', 0)} Warning**, "
        f"**{c.get('Info', 0)} Info**.")
    add("")
    crits = [f for f in ctx["all_findings"] if f.severity == "Critical"]
    if crits:
        add("**Top issues requiring immediate attention:**")
        add("")
        for f in crits[:5]:
            add(f"- {f.title}")
        add("")

    # Health scores
    add("## Health Score by Dimension")
    add("")
    add("| Dimension | Score | Grade | Notes |")
    add("| --- | ---: | :---: | --- |")
    for dim, (score, note) in sorted(ctx["health"].scores.items()):
        add(f"| {dim} | {score:.0f}/100 | {pct_to_grade(score)} | {note} |")
    add(f"| **Overall** | **{ctx['overall']:.0f}/100** | "
        f"**{ctx['overall_grade']}** | Mean of dimension scores |")
    add("")

    # Drift summary
    add("## Configuration Drift (Baseline -> Current)")
    add("")
    drift_findings = [f for f in ctx["all_findings"]
                      if f.category.startswith("Drift")]
    if not drift_findings:
        add("No configuration drift detected between the two snapshots.")
    else:
        add("| Severity | Area | Finding |")
        add("| :--- | :--- | :--- |")
        for f in sorted(drift_findings, key=lambda x: x.sort_key()):
            area = f.category.replace("Drift: ", "")
            add(f"| {sev_badge_md(f.severity)} | {area} | {md_cell(f.title)} |")
    add("")

    # Full findings
    add("## All Findings (Detail)")
    add("")
    for sev in ("Critical", "Warning", "Info"):
        group = [f for f in ctx["all_findings"] if f.severity == sev]
        if not group:
            continue
        add(f"### {sev} ({len(group)})")
        add("")
        for f in group:
            add(f"#### [{f.category}] {f.title}")
            add("")
            add(md_block(f.detail))
            add("")
            if f.recommendation:
                add(f"**Recommendation:** {f.recommendation}")
                add("")

    # Recommendations roll-up
    add("## Prioritized Recommendations")
    add("")
    n = 1
    for sev in ("Critical", "Warning"):
        for f in [x for x in ctx["all_findings"] if x.severity == sev and x.recommendation]:
            add(f"{n}. **[{sev}]** {f.title} - {f.recommendation}")
            n += 1
    if n == 1:
        add("No action required; configuration is healthy and stable.")
    add("")
    add("---")
    add("")
    add("*Generated by the AEP/CJA Config Health & Drift Audit. "
        "Standard-library Python, runs fully offline. "
        "This is a clean-room demo using synthetic data.*")
    add("")
    return "\n".join(lines)


def sev_badge_md(sev):
    return {"Critical": "🔴 Critical", "Warning": "🟠 Warning", "Info": "🔵 Info"}[sev]


def md_cell(text):
    return text.replace("|", "\\|").replace("\n", " ")


def md_block(text):
    # Indent multi-line details as a blockquote-friendly paragraph.
    return "\n".join(text.split("\n"))


# ---- HTML ----------------------------------------------------------------- #

CSS = """
:root{--crit:#c0392b;--warn:#d97706;--info:#2563eb;--ok:#16a34a;
--ink:#1f2933;--muted:#6b7280;--line:#e5e7eb;--bg:#f8fafc;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,
Arial,sans-serif;color:var(--ink);margin:0;background:var(--bg);line-height:1.5}
.wrap{max-width:960px;margin:0 auto;padding:40px 28px 80px;background:#fff;
box-shadow:0 1px 3px rgba(0,0,0,.06)}
h1{font-size:28px;margin:0 0 4px}
h2{font-size:20px;margin:40px 0 12px;padding-bottom:6px;border-bottom:2px solid var(--line)}
h3{font-size:16px;margin:24px 0 8px}
.sub{color:var(--muted);font-size:13px;margin:2px 0}
.note{background:#fffbeb;border:1px solid #fde68a;color:#92400e;padding:10px 14px;
border-radius:8px;font-size:13px;margin:16px 0}
.scorecard{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}
.bigscore{flex:0 0 auto;text-align:center;padding:18px 28px;border-radius:12px;
background:linear-gradient(135deg,#0f172a,#334155);color:#fff;min-width:150px}
.bigscore .num{font-size:42px;font-weight:700;line-height:1}
.bigscore .lbl{font-size:12px;opacity:.8;text-transform:uppercase;letter-spacing:.05em}
.pills{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.pill{display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:999px;
font-size:13px;font-weight:600}
.pill.crit{background:#fde8e4;color:var(--crit)}
.pill.warn{background:#fef3e2;color:var(--warn)}
.pill.info{background:#e6efff;color:var(--info)}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--bg);font-size:12px;text-transform:uppercase;letter-spacing:.04em;
color:var(--muted)}
td.num,th.num{text-align:right}
.grade{display:inline-block;width:26px;height:26px;line-height:26px;text-align:center;
border-radius:6px;font-weight:700;color:#fff;font-size:13px}
.g-A{background:#16a34a}.g-B{background:#65a30d}.g-C{background:#d97706}
.g-D{background:#ea580c}.g-F{background:#c0392b}
.bar{height:8px;border-radius:4px;background:var(--line);overflow:hidden;margin-top:4px}
.bar>span{display:block;height:100%}
.finding{border:1px solid var(--line);border-left-width:4px;border-radius:8px;
padding:12px 16px;margin:12px 0;background:#fff}
.finding.crit{border-left-color:var(--crit)}
.finding.warn{border-left-color:var(--warn)}
.finding.info{border-left-color:var(--info)}
.finding .cat{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.finding .ttl{font-weight:600;margin:2px 0 6px}
.finding .dtl{font-size:14px;white-space:pre-wrap;color:#374151}
.finding .rec{font-size:13px;margin-top:8px;background:var(--bg);padding:8px 10px;
border-radius:6px}
.sevtag{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;color:#fff}
.sevtag.crit{background:var(--crit)}.sevtag.warn{background:var(--warn)}
.sevtag.info{background:var(--info)}
ol{padding-left:20px}ol li{margin:6px 0}
footer{margin-top:48px;font-size:12px;color:var(--muted);border-top:1px solid var(--line);
padding-top:16px}
code{background:var(--bg);padding:1px 5px;border-radius:4px;font-size:12px}
"""


def bar_color(score):
    if score >= 80:
        return "#16a34a"
    if score >= 70:
        return "#d97706"
    return "#c0392b"


def esc(text):
    return html.escape(str(text)).replace("\n", "<br>")


def render_html(ctx):
    b, a = ctx["before"], ctx["after"]
    c = ctx["counts"]
    out = []
    w = out.append

    w("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    w("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w(f"<title>AEP/CJA Audit - {esc(a.meta.get('company'))}</title>")
    w(f"<style>{CSS}</style></head><body><div class='wrap'>")

    w("<h1>AEP / CJA Config Health &amp; Drift Audit</h1>")
    w(f"<p class='sub'>Organization: <strong>{esc(a.meta.get('company'))}</strong> "
      f"(<code>{esc(a.meta.get('org_slug'))}</code>)</p>")
    w(f"<p class='sub'>Baseline: {esc(b.meta.get('snapshot_at'))} &nbsp;&rarr;&nbsp; "
      f"Current: {esc(a.meta.get('snapshot_at'))}</p>")
    w(f"<p class='sub'>Generated {esc(ctx['generated_at'])} by aep-audit-demo</p>")
    w("<div class='note'>All identifiers in this report are synthetic. "
      "No real organization, dataset, or schema is represented. "
      "Runs fully offline on the Python standard library.</div>")

    # Scorecard
    w("<h2>Executive Summary</h2>")
    w("<div class='scorecard'>")
    w(f"<div class='bigscore'><div class='num'>{ctx['overall']:.0f}</div>"
      f"<div class='lbl'>Health / 100 &middot; Grade {ctx['overall_grade']}</div></div>")
    w("<div class='pills'>")
    w(f"<span class='pill crit'>&#9679; {c.get('Critical',0)} Critical</span>")
    w(f"<span class='pill warn'>&#9679; {c.get('Warning',0)} Warning</span>")
    w(f"<span class='pill info'>&#9679; {c.get('Info',0)} Info</span>")
    w("</div></div>")
    w(f"<p>We evaluated <strong>{len(a.datasets)} datasets</strong>, "
      f"<strong>{len(a.schemas)} schemas</strong>, "
      f"<strong>{len(a.data_views)} data views</strong>, and "
      f"<strong>{len(a.segments)} segments</strong>, then compared the current "
      f"configuration against the {esc(b.meta.get('snapshot_at','')[:10])} "
      f"baseline. The audit produced "
      f"<strong>{len(ctx['all_findings'])} findings</strong>.</p>")

    crits = [f for f in ctx["all_findings"] if f.severity == "Critical"]
    if crits:
        w("<p><strong>Top issues requiring immediate attention:</strong></p><ul>")
        for f in crits[:5]:
            w(f"<li>{esc(f.title)}</li>")
        w("</ul>")

    # Health by dimension
    w("<h2>Health Score by Dimension</h2>")
    w("<table><thead><tr><th>Dimension</th><th class='num'>Score</th>"
      "<th>Grade</th><th>Coverage</th><th>Notes</th></tr></thead><tbody>")
    for dim, (score, note) in sorted(ctx["health"].scores.items()):
        g = pct_to_grade(score)
        w(f"<tr><td>{esc(dim)}</td><td class='num'>{score:.0f}</td>"
          f"<td><span class='grade g-{g}'>{g}</span></td>"
          f"<td style='min-width:120px'><div class='bar'><span "
          f"style='width:{score:.0f}%;background:{bar_color(score)}'></span></div></td>"
          f"<td>{esc(note)}</td></tr>")
    og = ctx["overall_grade"]
    w(f"<tr><td><strong>Overall</strong></td><td class='num'><strong>"
      f"{ctx['overall']:.0f}</strong></td><td><span class='grade g-{og}'>{og}</span>"
      f"</td><td></td><td>Mean of dimension scores</td></tr>")
    w("</tbody></table>")

    # Drift table
    w("<h2>Configuration Drift (Baseline &rarr; Current)</h2>")
    drift_findings = [f for f in ctx["all_findings"] if f.category.startswith("Drift")]
    if not drift_findings:
        w("<p>No configuration drift detected between the two snapshots.</p>")
    else:
        w("<table><thead><tr><th>Severity</th><th>Area</th><th>Finding</th>"
          "</tr></thead><tbody>")
        for f in sorted(drift_findings, key=lambda x: x.sort_key()):
            sv = f.severity.lower()[:4]
            area = f.category.replace("Drift: ", "")
            w(f"<tr><td><span class='sevtag {sv}'>{esc(f.severity)}</span></td>"
              f"<td>{esc(area)}</td><td>{esc(f.title)}</td></tr>")
        w("</tbody></table>")

    # Detailed findings
    w("<h2>All Findings (Detail)</h2>")
    for sev in ("Critical", "Warning", "Info"):
        group = [f for f in ctx["all_findings"] if f.severity == sev]
        if not group:
            continue
        sv = sev.lower()[:4]
        w(f"<h3>{esc(sev)} ({len(group)})</h3>")
        for f in group:
            w(f"<div class='finding {sv}'>")
            w(f"<div class='cat'>{esc(f.category)}</div>")
            w(f"<div class='ttl'><span class='sevtag {sv}'>{esc(f.severity)}</span> "
              f"{esc(f.title)}</div>")
            w(f"<div class='dtl'>{esc(f.detail)}</div>")
            if f.recommendation:
                w(f"<div class='rec'><strong>Recommendation:</strong> "
                  f"{esc(f.recommendation)}</div>")
            w("</div>")

    # Recommendations
    w("<h2>Prioritized Recommendations</h2><ol>")
    any_rec = False
    for sev in ("Critical", "Warning"):
        for f in [x for x in ctx["all_findings"]
                  if x.severity == sev and x.recommendation]:
            any_rec = True
            w(f"<li><strong>[{esc(sev)}]</strong> {esc(f.title)} &mdash; "
              f"{esc(f.recommendation)}</li>")
    if not any_rec:
        w("<li>No action required; configuration is healthy and stable.</li>")
    w("</ol>")

    w("<footer>Generated by the AEP/CJA Config Health &amp; Drift Audit "
      "&mdash; standard-library Python, fully offline. "
      "Clean-room demo using synthetic data.</footer>")
    w("</div></body></html>")
    return "".join(out)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def run_health_checks(snap):
    result = HealthResult()
    check_completeness(snap, result)
    check_staleness(snap, result)
    check_naming(snap, result)
    check_orphans(snap, result)
    check_stitching(snap, result)
    return result


def run_drift_checks(before, after):
    result = HealthResult()
    diff_datasets(before, after, result)
    diff_schemas(before, after, result)
    diff_data_views(before, after, result)
    diff_segments(before, after, result)
    return result


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="AEP/CJA Config Health & Drift Audit")
    parser.add_argument("--before", default=os.path.join(here, "fixtures", "snapshot_2026-05-01.json"))
    parser.add_argument("--after", default=os.path.join(here, "fixtures", "snapshot_2026-06-15.json"))
    parser.add_argument("--out", default=os.path.join(here, "output"))
    parser.add_argument("--basename", default="sample-audit-report")
    args = parser.parse_args(argv)

    before = load_snapshot(args.before)
    after = load_snapshot(args.after)

    health = run_health_checks(after)
    drift = run_drift_checks(before, after)
    ctx = build_report_context(before, after, health, drift)

    os.makedirs(args.out, exist_ok=True)
    md_path = os.path.join(args.out, args.basename + ".md")
    html_path = os.path.join(args.out, args.basename + ".html")

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(ctx))
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_html(ctx))

    c = ctx["counts"]
    print("AEP/CJA Config Health & Drift Audit - complete")
    print(f"  Baseline : {args.before}")
    print(f"  Current  : {args.after}")
    print(f"  Overall health: {ctx['overall']:.0f}/100 (grade {ctx['overall_grade']})")
    print(f"  Findings: {len(ctx['all_findings'])} "
          f"({c.get('Critical',0)} Critical / {c.get('Warning',0)} Warning / "
          f"{c.get('Info',0)} Info)")
    print("  Dimension scores:")
    for dim, (score, _) in sorted(health.scores.items()):
        print(f"    - {dim}: {score:.0f}/100 ({pct_to_grade(score)})")
    print(f"  Wrote: {md_path}")
    print(f"  Wrote: {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
