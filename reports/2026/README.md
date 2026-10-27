# Validated 2026 replay: compact results

[English project README](../../README.md) · [Leia em português](../../README.pt-BR.md)

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

The timelines are retrospective approximations based on the supplied snapshots, not a certified history of TSE public updates. Independent validation checks file integrity and arithmetic, not external authenticity of the election results.
