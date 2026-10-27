# Stage 2 — Counting composition and demographic patterns

[Project README](../../../README.md) · [README em português](../../../README.pt-BR.md)

**Primary repository record:** [Markdown report (Portuguese)](REPORT.pt-BR.md). Companion formats: [PDF](REPORT.pt-BR.pdf) · [self-contained HTML](report.html). [Back to the two study stages](../README.md).

The report compares both rounds by region, state, capital status, and municipality size, and examines the rise in Lula's accumulated share in São Paulo. It includes eight figures, descriptive decomposition, source provenance, and evidence CSVs. Municipality size is the **registered electorate**, not resident population. These sources do not identify individual demographic characteristics or causal mechanisms.

Main findings: the Northeast was represented earlier **relative to national section-count progress** in the second round, even though its absolute clock times were later. Capital-city sections reached the midpoint earlier in aggregate, with state-level exceptions and a weak overall municipality-size gradient. São Paulo's change reflects both the mix of municipalities being counted and ordering within them. Early flat parts of the second-round clock curve cover very few sections.

## Reproduce

From the repository root, after completing the original replay:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt
PYTHONPATH=src python3 -m election_replay.geography_run --output output/geography-step2 --randomizations 4999 --seed 20261027
```

The command checks the original input hashes, builds a separate analysis database, computes evidence, runs independent validation against the original replay database, and renders the figures and both report formats. The default replay database is `output/replay/replay.sqlite`; use `--replay-db` to select another completed replay. Output folders must be new or empty.

Randomization is opt-in: without `--randomizations`, the command retains the descriptive workflow. The published stage-2 run uses 4,999 permutations and seed `20261027`; its reference models, primary Holm family, pointwise envelopes, effect magnitudes, and limitations are documented in the Markdown report and the randomization manifest. Non-rejection is not proof of random order.

The independent checks can also be rerun separately:

```bash
python3 scripts/validate_geography.py --analysis-dir output/geography-step2
python3 scripts/validate_randomization.py --analysis-dir output/geography-step2
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Optional PDF export requires Playwright and Chromium (already available in the development environment):

```bash
python3 scripts/export_report_pdf.py output/geography-step2/report.html output/geography-step2/REPORT.pt-BR.pdf \
  --base-url https://github.com/TCGV/brazil-election-replay-2026/blob/master/reports/2026/geography/
```

This directory versions all evidence CSVs/JSONs, PNG/SVG figures, and the consolidated report. The approximately 301 MB analysis database and private `.randomization-cache/` simulation checkpoints stay in the Git-ignored `output/` folder. The independent randomization audit needs these retained draw caches to recompute the recorded Monte Carlo statistics; they can be regenerated with the same source files, code, seed, and permutation count. `analysis-manifest.json` records the original input hashes, analysis-source hashes, runtime dependencies, and execution status. The report is tied to the supplied snapshots and reconstructs recorded section timing retrospectively; it does not certify the public update history or external authenticity of the election results.
