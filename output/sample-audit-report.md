# AEP / CJA Config Health & Drift Audit

**Organization:** Northwind Retail (`demo`)  
**Baseline snapshot:** 2026-05-01T08:00:00Z  
**Current snapshot:** 2026-06-15T08:00:00Z  
**Report generated:** 2026-06-27 13:51 UTC  
**Audit engine:** aep-audit-demo (clean-room, synthetic data)

> All identifiers in this report are synthetic. No real organization, dataset, or schema is represented.

---

## Executive Summary

Overall configuration health: **85/100 (grade B)**.

We evaluated **12 datasets**, **8 schemas**, **3 data views**, and **5 segments**, then compared the current configuration against the 2026-05-01 baseline.

The audit produced **20 findings**: **7 Critical**, **7 Warning**, **6 Info**.

**Top issues requiring immediate attention:**

- Dataset 'northwind_app_push' references an unknown schema
- Reporting timezone changed on data view 'Northwind Marketing Engagement'
- Field removed from schema 'CRM Profile v2'
- Stitching coverage critically low on 'Northwind Web + Mobile (Behavioral)'
- Dimension 'Country' maps to a missing field

## Health Score by Dimension

| Dimension | Score | Grade | Notes |
| --- | ---: | :---: | --- |
| Completeness | 82/100 | B | Datasets, schemas, and data-view references resolve cleanly. |
| Freshness | 88/100 | B | 10/11 production datasets fresh. |
| Identity Stitching | 82/100 | B | 2 stitched data view(s) assessed. |
| Naming & Hygiene | 92/100 | A | 1 naming/hygiene offender(s) found. |
| Orphaned Components | 82/100 | B | 2 orphaned dimension/metric(s). |
| **Overall** | **85/100** | **B** | Mean of dimension scores |

## Configuration Drift (Baseline -> Current)

| Severity | Area | Finding |
| :--- | :--- | :--- |
| 🔴 Critical | Data Views | Reporting timezone changed on data view 'Northwind Marketing Engagement' |
| 🔴 Critical | Schemas | Field removed from schema 'CRM Profile v2' |
| 🟠 Warning | Data Views | Lookback window changed on data view 'Northwind Web + Mobile (Behavioral)' |
| 🟠 Warning | Data Views | Session timeout changed on data view 'Northwind Web + Mobile (Behavioral)' |
| 🟠 Warning | Datasets | Dataset disabled: 'northwind_ad_impressions' |
| 🟠 Warning | Segments | Segment 'Email Engaged Non-Buyers' shrank sharply |
| 🟠 Warning | Segments | Segment 'High-Value Loyalty Members' was redefined |
| 🔵 Info | Data Views | Dataset added to data view 'Northwind Omnichannel Revenue' |
| 🔵 Info | Datasets | New dataset added: 'northwind_app_push' |
| 🔵 Info | Datasets | New dataset added: 'northwind_returns' |
| 🔵 Info | Schemas | Field added to schema 'CRM Profile v2' |
| 🔵 Info | Schemas | Field added to schema 'Web Events v1' |
| 🔵 Info | Segments | New segment created: 'Recent Returners' |

## All Findings (Detail)

### Critical (7)

#### [Completeness] Dataset 'northwind_app_push' references an unknown schema

Dataset 6e4f2c0a8b3d5f7c9e1b2d4a is bound to schema 'https://ns.adobe.com/demo/schemas/push_engagement_v1', which is not present in the schema registry snapshot. Reporting on this dataset will fail or silently drop fields.

**Recommendation:** Confirm the schema exists and is published; rebind the dataset or restore the missing schema.

#### [Drift: Data Views] Reporting timezone changed on data view 'Northwind Marketing Engagement'

Reporting timezone changed from 'America/New_York' to 'America/Chicago'. This silently shifts historical comparisons (sessions, day boundaries, or person counts).

**Recommendation:** Confirm the change was intentional and annotate dashboards so trend breaks are explained.

#### [Drift: Schemas] Field removed from schema 'CRM Profile v2'

Field 'loyalty.tier' present at baseline was removed. Any dimension, metric, or segment referencing it will break.

**Recommendation:** Trace every component built on this field before removing it; restore if still in use.

#### [Identity Stitching] Stitching coverage critically low on 'Northwind Web + Mobile (Behavioral)'

Person-ID resolution is at 71.2% (method=private-graph, primary=ECID). Below 75% means a large share of events are counted as anonymous, inflating unique counts and fragmenting journeys.

**Recommendation:** Audit the identity graph and event-level identity population; verify the primary identity is set and populated on all attached datasets.

#### [Orphaned Components] Dimension 'Country' maps to a missing field

In data view 'Northwind Marketing Engagement', the dimension is sourced from 'placeContext.geo.countryCode', which no longer exists in any attached schema. The component will return null/empty.

**Recommendation:** Repoint the dimension to a valid field or restore the field in the schema.

#### [Orphaned Components] Dimension 'Loyalty Tier' maps to a missing field

In data view 'Northwind Omnichannel Revenue', the dimension is sourced from 'loyalty.tier', which no longer exists in any attached schema. The component will return null/empty.

**Recommendation:** Repoint the dimension to a valid field or restore the field in the schema.

#### [Staleness] Dataset 'northwind_email_engagement' has stopped receiving data

Last batch was 23.6d ago (last_batch_at=2026-05-22T18:30:00Z). The dataset is enabled and tagged production but ingested 0 records in the last 24h.

**Recommendation:** Check the ingestion source / data feed for this dataset; a broken pipeline silently degrades every report and audience built on it.

### Warning (7)

#### [Completeness] Data view 'Northwind Marketing Engagement' includes a disabled dataset

Dataset 'northwind_ad_impressions' (2a0b8d6f9c4e1b3a5f7d8e9b) is disabled but still attached to data view dv_9b5d1f7a3c8e2b6d. Its data will quietly stop flowing into reports.

**Recommendation:** Re-enable the dataset or detach it from the data view and communicate the metric impact to stakeholders.

#### [Drift: Data Views] Lookback window changed on data view 'Northwind Web + Mobile (Behavioral)'

Lookback window changed from '13' to '7'. This silently shifts historical comparisons (sessions, day boundaries, or person counts).

**Recommendation:** Confirm the change was intentional and annotate dashboards so trend breaks are explained.

#### [Drift: Data Views] Session timeout changed on data view 'Northwind Web + Mobile (Behavioral)'

Session timeout changed from '30' to '45'. This silently shifts historical comparisons (sessions, day boundaries, or person counts).

**Recommendation:** Confirm the change was intentional and annotate dashboards so trend breaks are explained.

#### [Drift: Datasets] Dataset disabled: 'northwind_ad_impressions'

Dataset 2a0b8d6f9c4e1b3a5f7d8e9b was enabled at baseline and is now disabled. Data flow has stopped.

**Recommendation:** Verify this was intentional; downstream reports will show a step-change drop.

#### [Drift: Segments] Segment 'Email Engaged Non-Buyers' shrank sharply

Estimated size moved from 27,510 to 12,030 (-56%).

**Recommendation:** Large swings often indicate an upstream data or definition problem; investigate before activating.

#### [Drift: Segments] Segment 'High-Value Loyalty Members' was redefined

Definition changed.
  Before: loyalty.tier IN ('gold','platinum') AND commerce.order.priceTotal > 500 (trailing 90d)
  After:  loyalty.tier IN ('gold','platinum') AND commerce.order.priceTotal > 750 (trailing 90d)

**Recommendation:** Redefinitions break historical audience comparisons; communicate the change to activation owners.

#### [Naming & Hygiene] Test/scratch dataset 'TEST_clickstream_sandbox' is enabled in production org

Dataset 4c2d0f8b1e6a3d5c7b9f0a1d uses a scratch prefix yet is enabled. Scratch datasets in a production org inflate cost, pollute the schema picker, and risk accidental inclusion in data views.

**Recommendation:** Disable or delete scratch datasets, or move them to a development sandbox.

### Info (6)

#### [Drift: Data Views] Dataset added to data view 'Northwind Omnichannel Revenue'

Dataset 5d3e1b9f7a2c4e6b8d0a1c3f was attached to the data view.

**Recommendation:** Verify metrics did not double-count after the addition.

#### [Drift: Datasets] New dataset added: 'northwind_app_push'

Dataset 6e4f2c0a8b3d5f7c9e1b2d4a (schema https://ns.adobe.com/demo/schemas/push_engagement_v1) appeared since the baseline snapshot.

**Recommendation:** Confirm the new dataset is intentional and governed (schema, naming, data view membership).

#### [Drift: Datasets] New dataset added: 'northwind_returns'

Dataset 5d3e1b9f7a2c4e6b8d0a1c3f (schema https://ns.adobe.com/demo/schemas/transaction_v1) appeared since the baseline snapshot.

**Recommendation:** Confirm the new dataset is intentional and governed (schema, naming, data view membership).

#### [Drift: Schemas] Field added to schema 'CRM Profile v2'

New field 'person.birthDayAndMonth' (string) added.

**Recommendation:** Consider exposing the new field as a dimension/metric if it is analytically useful.

#### [Drift: Schemas] Field added to schema 'Web Events v1'

New field 'web.webReferrer.URL' (string) added.

**Recommendation:** Consider exposing the new field as a dimension/metric if it is analytically useful.

#### [Drift: Segments] New segment created: 'Recent Returners'

Segment seg_e5b9a3c7f1d6 appeared since baseline.

**Recommendation:** Confirm ownership and activation targets for the new audience.

## Prioritized Recommendations

1. **[Critical]** Dataset 'northwind_app_push' references an unknown schema - Confirm the schema exists and is published; rebind the dataset or restore the missing schema.
2. **[Critical]** Reporting timezone changed on data view 'Northwind Marketing Engagement' - Confirm the change was intentional and annotate dashboards so trend breaks are explained.
3. **[Critical]** Field removed from schema 'CRM Profile v2' - Trace every component built on this field before removing it; restore if still in use.
4. **[Critical]** Stitching coverage critically low on 'Northwind Web + Mobile (Behavioral)' - Audit the identity graph and event-level identity population; verify the primary identity is set and populated on all attached datasets.
5. **[Critical]** Dimension 'Country' maps to a missing field - Repoint the dimension to a valid field or restore the field in the schema.
6. **[Critical]** Dimension 'Loyalty Tier' maps to a missing field - Repoint the dimension to a valid field or restore the field in the schema.
7. **[Critical]** Dataset 'northwind_email_engagement' has stopped receiving data - Check the ingestion source / data feed for this dataset; a broken pipeline silently degrades every report and audience built on it.
8. **[Warning]** Data view 'Northwind Marketing Engagement' includes a disabled dataset - Re-enable the dataset or detach it from the data view and communicate the metric impact to stakeholders.
9. **[Warning]** Lookback window changed on data view 'Northwind Web + Mobile (Behavioral)' - Confirm the change was intentional and annotate dashboards so trend breaks are explained.
10. **[Warning]** Session timeout changed on data view 'Northwind Web + Mobile (Behavioral)' - Confirm the change was intentional and annotate dashboards so trend breaks are explained.
11. **[Warning]** Dataset disabled: 'northwind_ad_impressions' - Verify this was intentional; downstream reports will show a step-change drop.
12. **[Warning]** Segment 'Email Engaged Non-Buyers' shrank sharply - Large swings often indicate an upstream data or definition problem; investigate before activating.
13. **[Warning]** Segment 'High-Value Loyalty Members' was redefined - Redefinitions break historical audience comparisons; communicate the change to activation owners.
14. **[Warning]** Test/scratch dataset 'TEST_clickstream_sandbox' is enabled in production org - Disable or delete scratch datasets, or move them to a development sandbox.

---

*Generated by the AEP/CJA Config Health & Drift Audit. Standard-library Python, runs fully offline. This is a clean-room demo using synthetic data.*
