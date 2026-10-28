# 2026 study — stages and evidence

[English project README](../../README.md) · [Leia em português](../../README.pt-BR.md)

## Study stages

| Stage | Question | Primary record |
|---|---|---|
| **1. Minute-by-minute reconstruction** | How can the supplied final section votes be associated retrospectively with recorded arrival times? | [Reconstruction report](report.md), [minute CSVs](replay-first-totalization-minute.csv), and [interactive chart](replay-report.html) |
| **2. Counting composition and demographic patterns** | Which regions, states, capitals, and municipality-size groups entered first, and how did that composition relate to accumulated vote shares? | [Consolidated Markdown report (Portuguese)](geography/REPORT.pt-BR.md), with [evidence tables](geography/) |
| **3. Hypothesis tests** | Are the proposed accounting and statistical anomalies present in the supplied records? | [Hypothesis index](hypothesis-tests/README.md); [H1 accounting report](hypothesis-tests/01-accounting-integrity/REPORT.pt-BR.md); [H2 turnout/concentration report](hypothesis-tests/02-turnout-concentration/REPORT.pt-BR.md); [H3 repetition report](hypothesis-tests/03-result-repetition/REPORT.pt-BR.md); [H4 temporal report](hypothesis-tests/04-temporal-residuals/REPORT.pt-BR.md) |

Stage 2 includes formal section-order randomization benchmarks. Geography and registered electorate are observable proxies; individual demographic characteristics are not inferred. HTML and PDF are companion formats, while Markdown is the main repository record.

Stage 3 evaluates hypotheses one at a time. H1 documents electorate-identity exceptions; H2 adds local turnout/concentration screening; H3 inventories repeated complete vectors and evaluates a restricted local block-pairing reference; H4 tests gradual and abrupt residual associations with minute-level counting order under two local references. Each hypothesis contains its own code and evidence. The index records progress and qualitative assessments; findings do not independently authenticate the original source snapshots.

## Stage 1 artifacts

This directory contains selected outputs from the validated two-round replay of the repository's nationwide input CSVs. It includes the minute timelines, final nationwide totals, data-quality summaries, provenance manifest, validation evidence, and charts. The full generated run remains in the Git-ignored `output/replay/` directory.

**Download [replay-report.html](replay-report.html) and open it in a browser** to explore the interactive report. The page is self-contained. GitHub's file viewer displays its source rather than running it; no GitHub Pages deployment is required to view the downloaded report. Download the accompanying CSVs as well if you want to use the report's download links locally.

Candidate 13 (Lula) is red; candidate 22 (Flávio Bolsonaro) is blue in HTML and SVG charts. These presentation changes do not alter any vote totals or timeline CSVs.

- [First-totalization timeline](replay-first-totalization-minute.csv)
- [BU-receipt timeline](replay-bu-received-minute.csv)
- [Final totals](final-results.csv)
- [Run report (Portuguese)](report.md)
- [Input provenance and full-run artifact inventory](input-manifest.json)
- [Charts](charts/)
- [Browser preview](report-preview.png)

The manifest describes the **full original processing run**, including its original commit/dirty-state observations and artifacts. Large intermediates, section-level exports, and the complete section-coverage and latency files listed there are not part of this compact snapshot. They can be reproduced using the commands in the project README. Chart colors and the browser validation/preview were refreshed after that processing run.

For **stage 2**, start with the [Markdown report](geography/REPORT.pt-BR.md). The [PDF](geography/REPORT.pt-BR.pdf), [HTML](geography/report.html), figures, and CSVs are complementary reading and audit formats.

The timelines are retrospective approximations based on the supplied snapshots, not a certified history of TSE public updates. Independent validation checks file integrity and arithmetic, not external authenticity of the election results.
