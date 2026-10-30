# Stage 1 — Method and scope

[Main report](REPORT.md) · [Run instructions](../../README.md#run-locally)

## Inputs and matching

The pipeline reads the original nationwide CSVs for section votes and counting details. It discovers the election codes and rounds present and retains overseas records (`ZZ`). Source fingerprints, extraction metadata, and parameters are in [input-manifest.json](input-manifest.json). Collection time was not independently established.

Votes match details by election, round, state, municipality, electoral zone, and section. Uniqueness, unmatched keys, category reconciliation, and conservation are checked. These checks concern internal consistency of the supplied sources, not external authenticity.

## Timelines

Each section's final vote payload is assigned retrospectively to its first partial-totalization timestamp or BU-receipt timestamp. These are separate views of the same votes, not independent election observations.

Times retain Hora TSE without an inferred UTC offset. A minute labeled 17:00 includes events from 17:00:00 up to, but excluding, 17:01:00. CSVs retain every minute between the first and last vote event. Interactive charts may reduce displayed points; the CSVs preserve the complete series.

Missing details, duplicate details, missing timestamps, and invalid timestamps are distinct exception categories. Such votes remain in final totals even when they cannot enter a timeline. In the published run, no votes were excluded from either timeline.

## Denominators

Candidate shares divide accumulated candidate votes by all accumulated nominal votes with a usable time. Blank (95), null (96), and separately counted (97) votes remain separate. Round 1 includes every nominal candidacy, not only the eventual finalists.

The operational nominal classification uses numbers other than 95/96/97. It does not certify each vote's legal validity. Sections with unusual status are reported; their votes are not silently discarded.

## Validation and reproduction

The [independent aggregation](independent-validation.json), [output validation](output-validation.json), and [browser validation](browser-validation.json) cover distinct checks. Source sums and timeline conservation concern arithmetic; browser checks concern chart behavior. Synthetic implementation tests are separate from election-data evidence.

The compact repository snapshot contains selected outputs. The manifest describes the full historical run, including large intermediates not committed here. Original report hashes identify that execution's documents, not the current English editorial report.

Reproduce the computation in a new output directory with the project README commands. The generator retains its original report format; its output must not overwrite the curated English report. No code or numerical computation changed in this editorial revision.
