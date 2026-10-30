# H2 — Evidence and reproduction

[Main report](REPORT.md) · [Method guide](METHOD.md) · [Hypothesis index](../README.md)

Start with the main report for the findings. This guide locates the evidence and preserves the commands for reproducing the published analysis.

## Evidence

| File | Purpose |
|---|---|
| [coverage.csv](evidence/analysis/coverage.csv) | Eligibility, peer support, and state coverage |
| [association-tests.csv](evidence/analysis/association-tests.csv) | All 15 formal tests, expectations, simulated ranges, and p-values |
| [cases.csv](evidence/analysis/cases.csv) | Every primary joint-tail case, including counts, magnitudes, and local context |
| [strata.csv](evidence/analysis/strata.csv) | Comparison groups and effective tail sizes for every candidate |
| [uf-summary.csv](evidence/analysis/uf-summary.csv) | State summaries without additional state-level tests |
| [sensitivity.csv](evidence/analysis/sensitivity.csv) | Seven descriptive configurations and retention of primary cases |
| [run manifest](evidence/analysis/manifest.json) | Sources, execution parameters, and fingerprints |
| [independent validation](evidence/independent-validation.json) | Separate source parser, exact-ratio comparisons, and regenerated simulation counts |
| [publication validation](evidence/publication-validation.json) | Summary and figure checks against validated evidence |
| [implementation tests](evidence/test-results.txt) | Original test output using artificial fixtures |
| [publication inventory](evidence/artifact-manifest.json) | Current published file hashes |
| [code/](code/) and [figures/](figures/) | Analysis implementation and four PNG/SVG figures |

A case is one candidate/section/round occurrence. Different candidates or rounds do not necessarily identify different physical sections. Group sizes repeat for each candidate in `strata.csv`; national coverage rows repeat the aggregate of state rows. These are not additional observations.

## Reproduce

Run from the repository root with Python 3.12+ and the pinned [analysis dependencies](../../../../requirements-analysis.txt). Retrieve the original CSVs with Git LFS using the [project instructions](../../../../README.md). Matching stage 1 and H1 manifests are required; a replay SQLite database is not.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt

H2_DIR=reports/2026/hypothesis-tests/02-turnout-concentration

python3 "$H2_DIR/code/run_analysis.py" \
  --output "$H2_DIR/.work/reproduction/analysis" \
  --cache "$H2_DIR/.work/data" \
  --reference-cache "$H2_DIR/.work/reference" \
  --simulations 19999 --seed 20261028 --workers 4

python3 "$H2_DIR/code/validate_independently.py" \
  --analysis-dir "$H2_DIR/.work/reproduction/analysis" \
  --reference-cache "$H2_DIR/.work/reference" \
  --output "$H2_DIR/.work/reproduction/independent-validation.json"

python3 "$H2_DIR/code/generate_figures.py" \
  --analysis-dir "$H2_DIR/.work/reproduction/analysis" \
  --output "$H2_DIR/.work/reproduction/figures"

python3 "$H2_DIR/code/validate_publication.py" \
  --analysis-dir "$H2_DIR/.work/reproduction/analysis" \
  --figures "$H2_DIR/.work/reproduction/figures" \
  --output "$H2_DIR/.work/reproduction/publication-validation.json"

python3 -m unittest discover -s "$H2_DIR/code" -p 'test_*.py' -v
python3 "$H2_DIR/code/inventory_artifacts.py" --verify
```

Use new output paths. `.work/` is ignored by Git; source and simulation caches may be reused only when their fingerprints match. Retain the simulation vectors for the independent audit. New source files or method choices require a new reviewed analysis, not reuse of this report's conclusions.

## Historical execution records

The [original Portuguese report](REPORT.pt-BR.md) and [original protocol](METHOD.pt-BR.md) remain unchanged for provenance. The pre-editorial publication inventory is preserved separately from the current inventory. The current reading documents are `REPORT.md`, `METHOD.md`, and this README. Existing figures and numerical outputs retain the original execution's content.
