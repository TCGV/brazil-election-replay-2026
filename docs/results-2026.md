# Stage 1 — Published execution and validation

[Reconstruction report](../reports/2026/REPORT.md) · [Method](../reports/2026/METHOD.md)

The published run of October 27, 2026 processed 5,731,614 vote rows and 998,496 detail rows from the two nationwide CSVs recovered through Git LFS. It covers both rounds, the 27 domestic federative units, and overseas voting.

| Published check | Result | Evidence |
|---|---|---|
| Source integrity | File sizes and SHA-256 hashes match the versioned LFS pointers | [Independent validation](../reports/2026/independent-validation.json) |
| Independent totals | All 19 candidate/class totals match a separate aggregation | [Independent validation](../reports/2026/independent-validation.json) |
| Matching and reconciliation | All 998,411 vote-bearing section-round keys match unique details; no category discrepancy | [Output validation](../reports/2026/output-validation.json) |
| Timeline conservation | No votes excluded from either timestamp reference; increments and final accumulations agree | [Output validation](../reports/2026/output-validation.json) |
| Interactive report | Browser interactions passed without JavaScript errors | [Browser validation](../reports/2026/browser-validation.json) |

The original implementation suite passed 19 synthetic integration tests. These checks establish internal consistency and software behavior, without independently authenticating election results.

The [main report](../reports/2026/REPORT.md) presents timelines, final totals, and interpretation. The [original generated report](../reports/2026/report.md) and [input manifest](../reports/2026/input-manifest.json) remain historical execution records. Reproduction commands are in the [project README](../README.md#run-locally).

This English revision changes reading material only. No ingestion, statistical analysis, or previously published validation was rerun.
