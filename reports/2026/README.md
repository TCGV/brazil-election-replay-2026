# 2026 study — Reports and evidence

[Project README](../../README.md) · [Editorial review](../../docs/editorial-review.md)

Read the three stages in order, or open an individual report. Current reports are in US English and describe the supplied source snapshots.

| Stage | Main report | Method and evidence |
|---|---|---|
| 1 — Minute-by-minute reconstruction | [What the replay recovers](REPORT.md) | [Method](METHOD.md) · [Validation](../../docs/results-2026.md) |
| 2 — Counting composition | [Regions, states, capitals, size, and vote-share changes](geography/REPORT.md) | [Method](geography/METHOD.md) · [Evidence and reproduction](geography/README.md) |
| 3 — Hypothesis tests | [Seven questions, findings, limits, and assessments](hypothesis-tests/README.md) | Each hypothesis has its own report, method, code, and evidence folder |

## Explore the reconstruction

- [Interactive replay](replay-report.html): download and open locally; GitHub does not run the HTML. Original interface labels remain in Portuguese.
- [First-totalization minute CSV](replay-first-totalization-minute.csv) and [BU-receipt minute CSV](replay-bu-received-minute.csv): complete series for both rounds.
- [Final candidate/class totals](final-results.csv): the supplied counts that anchor the replay.
- [Exportable charts](charts/): candidate 13 in red and candidate 22 in blue.
- [Input manifest](input-manifest.json): original source fingerprints and full execution inventory.

The manifest describes the full historical run. Large intermediates and some listed exports are not committed in this compact snapshot; reproduction commands remain in the project README. It does not inventory the later English editorial edition.

## Current reports and historical records

English `REPORT.md` files are the current narrative. `METHOD.md` guides carry definitions and technical scope; folder READMEs map evidence and reproduction commands. The [original generated reconstruction report](report.md), original Portuguese reports/protocols, and companion formats remain preserved execution records. Their original labels and hashes do not imply a second current-language edition.

The replay is retrospective, geographic composition does not identify individual demographics, and statistical tests concern specified references. None of the stages independently authenticates the source snapshots or reconstructs individual voter transitions.
