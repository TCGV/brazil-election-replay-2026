# English editorial review

Baseline: `f267004bf2aebdd086a3177098a21c42604f6563`. The review standardizes current reading documents in US English and puts findings before technical detail. It uses existing reports and evidence without rerunning ingestion, simulations, statistical tests, or analyses.

## Deliveries

| Delivery | Scope | Review outcome | Commit |
|---|---|---|---|
| 1 | Stage 1 reconstruction | English report and method; duplicate execution narrative consolidated. No material inconsistency identified. | [4e5c9aa](https://github.com/TCGV/brazil-election-replay-2026/commit/4e5c9aa407d7ec096fec52f38dba7f50fe56476e) |
| 2 | Stage 2 counting composition | English narrative centers regional weights, state differences, capital/size patterns, and São Paulo; no material inconsistency identified. | [4012fe4](https://github.com/TCGV/brazil-election-replay-2026/commit/4012fe4da9750d8e21e7a44887998069b628117e) |
| 3 | Hypothesis index | One result/limit row per analysis; repeated summaries removed and labels aligned with the questions actually tested. | [1115738](https://github.com/TCGV/brazil-election-replay-2026/commit/11157388fbeae6df412e0d28a3d5e8228f521611) |
| 4 | H1 | English report, method, and evidence guide; scope and numerical wording reviewed without recalculation. | [70afe60](https://github.com/TCGV/brazil-election-replay-2026/commit/70afe6005f6b9f520f4d6f1a3399da8053034ea9) |
| 5 | H2 | English report, method, and evidence guide; scope and numerical wording reviewed without recalculation. | [115829e](https://github.com/TCGV/brazil-election-replay-2026/commit/115829ebbac7097000d67c5d6c46ee674c8867ef) |
| 6 | H3 | English report, method, and evidence guide; scope and numerical wording reviewed without recalculation. | [1c82733](https://github.com/TCGV/brazil-election-replay-2026/commit/1c8273335036c5e9b4d6be9bc309ee79cf692fb0) |
| 7 | H4 | English report, method, and evidence guide; scope and numerical wording reviewed without recalculation. | [6f41fb4](https://github.com/TCGV/brazil-election-replay-2026/commit/6f41fb456e67323edfb17c270e2d9f986b2a0bd8) |
| 8 | H5 | English report, method, and evidence guide; scope and numerical wording reviewed without recalculation. | [0cb96ce](https://github.com/TCGV/brazil-election-replay-2026/commit/0cb96ce1ca468d2b920dba6553b8dda40860aafa) |
| 9 | H6 | English report, method, and evidence guide; scope and numerical wording reviewed without recalculation. | [bfa850c](https://github.com/TCGV/brazil-election-replay-2026/commit/bfa850cac3d9c51d71a32dc746195b3b2a6687e3) |
| 10 | H7 | English report, method, and evidence guide; scope and numerical wording reviewed without recalculation. | [4f2cee6](https://github.com/TCGV/brazil-election-replay-2026/commit/4f2cee6ee136736ef3b634773e4349ec06d20c3a) |
| 11 | Repository-wide navigation and consistency | English navigation, terminology, compatibility links, and decisions consolidated | This commit |

Each delivery has its own commit followed by a push. Unsupported conclusions are narrowed in the text; no additional tests are generated to rescue them.

## Preservation policy

English `REPORT.md` and `METHOD.md` files are the current reading documents. Original generated reports, hash-bound Portuguese protocols, numerical tables, charts, execution manifests, and validation records remain historical evidence at their original paths. They describe the original execution, rather than a second current-language edition. Generators retain their original formats and must write to new output directories.

Where an inventory includes an edited README, the inventory's original bytes are retained as `evidence/artifact-manifest.pre-editorial.json`, tied to the baseline commit. The current publication inventory is refreshed to include English documents. A presentation revision does not rewrite the execution or its validation.

## Stage 1

Coverage, candidate counts, time windows, and validation statements were reviewed against existing execution documents and compact evidence. The English text distinguishes nominal from all-class votes, section-round keys from physical sections, BU receipt from publication, and reconstruction from public-update history. A generic duplicate-handling rule is no longer presented as an observed exception when the duplicate count is zero. No material numerical or methodological correction was identified.

## Stage 2

The revision separates clock time from section progress, section completion from nominal-vote weights, and municipality-weighted correlations from section-weighted curves. State examples retain the variation hidden by regional averages. Accounting components are described without causal explanatory percentages; non-detection is not labeled randomness. Original figures and HTML/PDF remain historical companions with their original labels. Complete state tables remain accessible in the preserved report and existing CSVs. No numerical processing was needed.

## Hypothesis index

The index separates findings from limitations and preserves the requested ordinal rubric. Hypothesis labels now describe the measured question instead of implying that rejection establishes an implausible or artificial outcome. Per-analysis links now lead directly to the current English reports. No scores were changed.

## H1

Core vote/turnout/duplicate checks are separated from the additional electorate identity. The exception concerns 41 physical overseas sections, repeated in both rounds, and registered voters rather than candidate votes. Overlapping violation rows are not described as separate sections. No material numerical inconsistency requiring recalculation was identified. The pre-editorial inventory was archived, and the current publication inventory was verified.

## H2

Formal aggregate tests, descriptive magnitude screening, and closer local comparisons remain distinct. Candidate coverage means every nominal candidacy in each round, not the same roster in both rounds. Persistent flags are not individual significant-test results. No material numerical inconsistency requiring recalculation was identified. The pre-editorial inventory was archived, and the current publication inventory was verified.

## H3

The national inventory is distinguished from the restricted local statistic and its informative support. Cantelli outputs are conservative bounds rather than exact p-values. The broad assessment remains inconclusive; nondetection is not treated as evidence of naturalness. No material numerical inconsistency requiring recalculation was identified. The pre-editorial inventory was archived, and the current publication inventory was verified.

## H4

The report distinguishes residual magnitude, formal detection, and temporal support. A broad interpretation of São Paulo as following finer composition is replaced with the measured reference-specific reductions; no causal explanatory percentage is claimed. No material numerical inconsistency requiring recalculation was identified. The pre-editorial inventory was archived, and the current publication inventory was verified.

## H5

Strict local screening and between-place allocation tests answer different questions. The two overseas flags are reported against their prespecified magnitude thresholds and partial coverage. The São Paulo maximum is not conflated with those flags or assigned a causal interpretation. No material numerical inconsistency requiring recalculation was identified. The pre-editorial inventory was archived, and the current publication inventory was verified.

## H6

The national count balance is arithmetic, not an individual voter-flow reconstruction. Small conditional correlations, supported populations, and the difference between count gains and equally weighted section changes are explicit. Slopes do not estimate new-voter preferences. No material numerical inconsistency requiring recalculation was identified. The pre-editorial inventory was archived, and the current publication inventory was verified.

## H7

The descriptive municipal census and the fixed-target formal population remain separate. No illustrative percentage becomes a benchmark. Planned test tails, observed values outside the retained reference intervals, and the inability to establish global naturalness are preserved. No material numerical inconsistency requiring recalculation was identified. The pre-editorial inventory was archived, and the current publication inventory was verified.

## Final integration

Root and study indexes now lead to the English reports without duplicating their narratives. Earlier Portuguese entry points are English compatibility links; original execution reports and hash-bound protocols stay immutable. Source generators, figures, HTML, and PDF retain their historical formats, which are clearly labeled. Output-field semantics moved from the root README into the reconstruction method guide.

A separate textual read checked all nine main English reports against the original reports and compact published evidence. It found no material numerical contradiction requiring recalculation. Wording changes narrow claims to accounting, association, or the stated conditional reference; no unsupported causal or naturalness conclusion was retained. Minor terminology corrections clarify pooled within-group rank correlation and the 27 domestic federative units.

The final documentation check verifies local file and heading links, Markdown whitespace, seven current publication inventories, and preservation of baseline computation files and numerical evidence. The machine-readable [verification record](editorial-validation.json) records the scope. No ingestion, statistical test, simulation, figure generation, or numerical audit was rerun for this review; checking file hashes does not recalculate results.
