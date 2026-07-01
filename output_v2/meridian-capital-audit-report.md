# AEP / CJA Config Health & Drift Audit

**Organization:** Meridian Capital (Fictional) (`meridian-cap`)  
**Baseline snapshot:** 2026-04-15T07:00:00Z  
**Current snapshot:** 2026-06-20T07:00:00Z  
**Report generated:** 2026-06-29 13:19 UTC  
**Audit engine:** aep-audit-demo (clean-room, synthetic data)

> All identifiers in this report are synthetic. No real organization, dataset, or schema is represented.

---

## Executive Summary

Overall configuration health: **87/100 (grade B)**.

We evaluated **10 datasets**, **9 schemas**, **3 data views**, and **5 segments**, then compared the current configuration against the 2026-04-15 baseline.

The audit produced **14 findings**: **5 Critical**, **6 Warning**, **3 Info**.

**Top issues requiring immediate attention:**

- Reporting timezone changed on data view 'Meridian Client Engagement'
- Dataset 'meridian_client_portal_events' was rebound to a different schema
- Field removed from schema 'Advisor CRM Profile v1'
- Stitching coverage critically low on 'Meridian Client Engagement'
- Dimension 'Advisor AUM Band' maps to a missing field

## Health Score by Dimension

| Dimension | Score | Grade | Notes |
| --- | ---: | :---: | --- |
| Completeness | 88/100 | B | Datasets, schemas, and data-view references resolve cleanly. |
| Freshness | 93/100 | A | 8/9 production datasets fresh. |
| Identity Stitching | 73/100 | C | 2 stitched data view(s) assessed. |
| Naming & Hygiene | 92/100 | A | 1 naming/hygiene offender(s) found. |
| Orphaned Components | 91/100 | A | 1 orphaned dimension/metric(s). |
| **Overall** | **87/100** | **B** | Mean of dimension scores |

## Configuration Drift (Baseline -> Current)

| Severity | Area | Finding |
| :--- | :--- | :--- |
| 🔴 Critical | Data Views | Reporting timezone changed on data view 'Meridian Client Engagement' |
| 🔴 Critical | Datasets | Dataset 'meridian_client_portal_events' was rebound to a different schema |
| 🔴 Critical | Schemas | Field removed from schema 'Advisor CRM Profile v1' |
| 🟠 Warning | Datasets | Dataset disabled: 'meridian_email_campaigns' |
| 🔵 Info | Data Views | Dataset added to data view 'Meridian Advisor Journey' |
| 🔵 Info | Datasets | New dataset added: 'meridian_mobile_advisor_app' |
| 🔵 Info | Segments | New segment created: 'Mobile-Only Advisors' |

## All Findings (Detail)

### Critical (5)

#### [Drift: Data Views] Reporting timezone changed on data view 'Meridian Client Engagement'

Reporting timezone changed from 'America/New_York' to 'America/Chicago'. This silently shifts historical comparisons (sessions, day boundaries, or person counts).

**Recommendation:** Confirm the change was intentional and annotate dashboards so trend breaks are explained.

#### [Drift: Datasets] Dataset 'meridian_client_portal_events' was rebound to a different schema

Schema changed from 'https://ns.adobe.com/meridian/schemas/client_web_events_v1' to 'https://ns.adobe.com/meridian/schemas/client_web_events_v2'. Field-level reporting may break.

**Recommendation:** Validate field mappings against the new schema.

#### [Drift: Schemas] Field removed from schema 'Advisor CRM Profile v1'

Field 'advisor.aum_band' present at baseline was removed. Any dimension, metric, or segment referencing it will break.

**Recommendation:** Trace every component built on this field before removing it; restore if still in use.

#### [Identity Stitching] Stitching coverage critically low on 'Meridian Client Engagement'

Person-ID resolution is at 61.4% (method=private-graph, primary=ClientID). Below 75% means a large share of events are counted as anonymous, inflating unique counts and fragmenting journeys.

**Recommendation:** Audit the identity graph and event-level identity population; verify the primary identity is set and populated on all attached datasets.

#### [Orphaned Components] Dimension 'Advisor AUM Band' maps to a missing field

In data view 'Meridian Advisor Journey', the dimension is sourced from 'advisor.aum_band', which no longer exists in any attached schema. The component will return null/empty.

**Recommendation:** Repoint the dimension to a valid field or restore the field in the schema.

### Warning (6)

#### [Completeness] Data view 'Meridian Client Engagement' includes a disabled dataset

Dataset 'meridian_email_campaigns' (ee5f6a7b8c9d0e1f2a3b4c5d) is disabled but still attached to data view dv_mc_b2c3d4e5f6a7. Its data will quietly stop flowing into reports.

**Recommendation:** Re-enable the dataset or detach it from the data view and communicate the metric impact to stakeholders.

#### [Completeness] Data view 'Meridian Marketing & Events' includes a disabled dataset

Dataset 'meridian_email_campaigns' (ee5f6a7b8c9d0e1f2a3b4c5d) is disabled but still attached to data view dv_mc_c3d4e5f6a7b8. Its data will quietly stop flowing into reports.

**Recommendation:** Re-enable the dataset or detach it from the data view and communicate the metric impact to stakeholders.

#### [Drift: Datasets] Dataset disabled: 'meridian_email_campaigns'

Dataset ee5f6a7b8c9d0e1f2a3b4c5d was enabled at baseline and is now disabled. Data flow has stopped.

**Recommendation:** Verify this was intentional; downstream reports will show a step-change drop.

#### [Identity Stitching] Stitching coverage below target on 'Meridian Advisor Journey'

Coverage is 84.9% (target >= 85%).

**Recommendation:** Investigate datasets contributing un-keyed events.

#### [Naming & Hygiene] Test/scratch dataset 'SANDBOX_lead_scoring_test' is enabled in production org

Dataset cc9d0e1f2a3b4c5d6e7f8a9b uses a scratch prefix yet is enabled. Scratch datasets in a production org inflate cost, pollute the schema picker, and risk accidental inclusion in data views.

**Recommendation:** Disable or delete scratch datasets, or move them to a development sandbox.

#### [Staleness] Dataset 'meridian_aum_snapshot' has stopped receiving data

Last batch was 13.1d ago (last_batch_at=2026-06-07T05:00:00Z). The dataset is enabled and tagged production but ingested 0 records in the last 24h.

**Recommendation:** Check the ingestion source / data feed for this dataset; a broken pipeline silently degrades every report and audience built on it.

### Info (3)

#### [Drift: Data Views] Dataset added to data view 'Meridian Advisor Journey'

Dataset dd0e1f2a3b4c5d6e7f8a9b0c was attached to the data view.

**Recommendation:** Verify metrics did not double-count after the addition.

#### [Drift: Datasets] New dataset added: 'meridian_mobile_advisor_app'

Dataset dd0e1f2a3b4c5d6e7f8a9b0c (schema https://ns.adobe.com/meridian/schemas/advisor_mobile_events_v1) appeared since the baseline snapshot.

**Recommendation:** Confirm the new dataset is intentional and governed (schema, naming, data view membership).

#### [Drift: Segments] New segment created: 'Mobile-Only Advisors'

Segment seg_mc_e5f6a7b8 appeared since baseline.

**Recommendation:** Confirm ownership and activation targets for the new audience.

## Prioritized Recommendations

1. **[Critical]** Reporting timezone changed on data view 'Meridian Client Engagement' - Confirm the change was intentional and annotate dashboards so trend breaks are explained.
2. **[Critical]** Dataset 'meridian_client_portal_events' was rebound to a different schema - Validate field mappings against the new schema.
3. **[Critical]** Field removed from schema 'Advisor CRM Profile v1' - Trace every component built on this field before removing it; restore if still in use.
4. **[Critical]** Stitching coverage critically low on 'Meridian Client Engagement' - Audit the identity graph and event-level identity population; verify the primary identity is set and populated on all attached datasets.
5. **[Critical]** Dimension 'Advisor AUM Band' maps to a missing field - Repoint the dimension to a valid field or restore the field in the schema.
6. **[Warning]** Data view 'Meridian Client Engagement' includes a disabled dataset - Re-enable the dataset or detach it from the data view and communicate the metric impact to stakeholders.
7. **[Warning]** Data view 'Meridian Marketing & Events' includes a disabled dataset - Re-enable the dataset or detach it from the data view and communicate the metric impact to stakeholders.
8. **[Warning]** Dataset disabled: 'meridian_email_campaigns' - Verify this was intentional; downstream reports will show a step-change drop.
9. **[Warning]** Stitching coverage below target on 'Meridian Advisor Journey' - Investigate datasets contributing un-keyed events.
10. **[Warning]** Test/scratch dataset 'SANDBOX_lead_scoring_test' is enabled in production org - Disable or delete scratch datasets, or move them to a development sandbox.
11. **[Warning]** Dataset 'meridian_aum_snapshot' has stopped receiving data - Check the ingestion source / data feed for this dataset; a broken pipeline silently degrades every report and audience built on it.

---

*Generated by the AEP/CJA Config Health & Drift Audit. Standard-library Python, runs fully offline. This is a clean-room demo using synthetic data.*
