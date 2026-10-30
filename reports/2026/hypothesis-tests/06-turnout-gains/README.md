# H6 — Turnout changes and finalists' gains

[Main report](REPORT.md) · [Method](METHOD.md) · [Hypothesis index](../README.md)

The report presents the national count balance, conditional association, assessment, and limits. The method guide defines the measures and references. This English editorial edition uses the published results without recalculation; the [original protocol](METHOD.pt-BR.md) and [original report](REPORT.pt-BR.md) remain frozen execution records.

## Evidence guide

| File | Contents |
|---|---|
| [totals.csv](evidence/analysis/totals.csv) | Original totals and exact count balances for Brazil, states, and regions |
| [descriptive.csv](evidence/analysis/descriptive.csv) | Cohort summaries, correlations, slopes, and arithmetic decomposition |
| [paired-sections.csv.gz](evidence/analysis/paired-sections.csv.gz) | All physical pairs, original counts, source rows, and eligibility decisions |
| [section-measures.csv.gz](evidence/analysis/section-measures.csv.gz) | Every cohort section's rates, changes, arithmetic components, and support |
| [association-groups.csv.gz](evidence/analysis/association-groups.csv.gz) | Both references' strata and covariance components |
| [coverage.csv](evidence/analysis/coverage.csv) | Informative and excluded support by reference and state |
| [tests.csv](evidence/analysis/tests.csv) | Four primary tests with signed magnitudes and Holm adjustment |
| [permutation-scores.csv.gz](evidence/analysis/permutation-scores.csv.gz) | All 9,998 retained signed-score rows |
| [sensitivity.csv](evidence/analysis/sensitivity.csv) | Fourteen descriptive reference/scenario combinations |
| [x-bins.csv](evidence/analysis/x-bins.csv), [heatmap.csv](evidence/analysis/heatmap.csv) | Turnout-change bands and the complete binned section-count grid |
| [Execution manifest](evidence/analysis/manifest.json) | Frozen method, source and code hashes, parameters, and numerical inventory |
| [Independent validation](evidence/independent-validation.json), [test output](evidence/test-results.txt) | Original audit scope and implementation-test results |
| [Current inventory](evidence/artifact-manifest.json), [pre-editorial inventory](evidence/artifact-manifest.pre-editorial.json) | Current publication integrity and preserved original publication inventory |
| [code/](code/), [figures/](figures/) | Analysis and synthetic implementation tests; four PNG/SVG figures |

Compressed CSVs contain every row, not a sample. Generated tables use UTF-8 and commas; read `.csv.gz` directly with Python's `gzip.open(..., "rt")` and `csv.DictReader`. National, regional, and state summaries overlap, as do references and sensitivities; their counts are not independent populations.

## Reproduce

Use Python 3.12+ and the pinned NumPy/Matplotlib dependencies in [requirements-analysis.txt](../../../../requirements-analysis.txt). Retrieve the two nationwide CSVs through Git LFS as described in the [project README](../../../../README.md). A replay or geography database is not required; the existing source manifests and accounting audit must match the same snapshot.

Run from the repository root, using new output paths to preserve published evidence:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt
```

```bash
H6_DIR=reports/2026/hypothesis-tests/06-turnout-gains

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python3 "$H6_DIR/code/run_analysis.py" \
  --output "$H6_DIR/.work/reproduction/analysis" \
  --cache "$H6_DIR/.work/data" \
  --simulation-cache "$H6_DIR/.work/reproduction/simulations" \
  --simulations 4999 --seed 20261029 --workers 4

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python3 "$H6_DIR/code/validate_independently.py" \
  --analysis "$H6_DIR/.work/reproduction/analysis" \
  --cache "$H6_DIR/.work/independent-source" \
  --output "$H6_DIR/.work/reproduction/independent-validation.json"

python3 "$H6_DIR/code/generate_figures.py" \
  --analysis-dir "$H6_DIR/.work/reproduction/analysis" \
  --output "$H6_DIR/.work/reproduction/figures"

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python3 -m unittest discover -s "$H6_DIR/code" -p 'test_*.py' -v

python3 "$H6_DIR/code/inventory_artifacts.py" --verify
```

The inventory command verifies this published folder, including the English editorial documents. It is separate from reproducing numerical evidence in `.work/`. The pre-editorial inventory preserves the original publication record.

Single-threaded BLAS avoids competition with analysis workers. Source and simulation caches are fingerprinted; incompatible caches must not be silently reused. The original files are Latin-1, semicolon-delimited CSVs. Original-source parsing, cohort construction, statistics, orchestration, independent validation, and figure generation are separate modules under `code/`.

Reproduction regenerates numerical evidence and figures, not the reviewed English report. New source data require a new run and a review of the narrative. The frozen protocol is hash-bound and must not be translated or edited in place.
