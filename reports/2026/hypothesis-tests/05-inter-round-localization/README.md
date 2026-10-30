# H5 — Localized changes between rounds

[Main report](REPORT.md) · [Method guide](METHOD.md) · [Hypothesis index](../README.md)

Start with the report for findings and interpretation. This page provides evidence locations and reproduction commands. The current English documents are an editorial revision of the published run; they introduce no new calculations.

## Evidence

| File | Contents |
|---|---|
| [pairing.csv](evidence/analysis/pairing.csv), [eligibility.csv](evidence/analysis/eligibility.csv), [unmatched.csv](evidence/analysis/unmatched.csv) | Physical keys, exclusions and unmatched records |
| [paired-sections.csv.gz](evidence/analysis/paired-sections.csv.gz) | Every matched key, original source lines, counts and cohort decisions |
| [distribution.csv](evidence/analysis/distribution.csv) | Section-level changes and contrasts, with explicit denominators |
| [section-screening.csv.gz](evidence/analysis/section-screening.csv.gz), [case-summary.csv](evidence/analysis/case-summary.csv) | Both peer comparisons and their coverage |
| [concentration-groups.csv.gz](evidence/analysis/concentration-groups.csv.gz), [coverage.csv](evidence/analysis/coverage.csv) | Conditional strata and exchange support |
| [place-results.csv.gz](evidence/analysis/place-results.csv.gz) | Every place's residual means, counts and score components |
| [tests.csv](evidence/analysis/tests.csv), [sensitivity.csv](evidence/analysis/sensitivity.csv) | Four formal decisions and ten descriptive sensitivity rows |
| [selected-source-context.csv](evidence/selected-source-context.csv), [context-manifest.json](evidence/context-manifest.json) | Eighteen source rows for the nine sections selected by the published screening/MAX rules |
| [analysis manifest](evidence/analysis/manifest.json), [independent audit](evidence/independent-validation.json), [test output](evidence/test-results.txt) | Original execution, validation scope and implementation checks |
| [figures/](figures/) | Published PNG/SVG companions; original labels remain in Portuguese |

Compressed CSVs retain all rows, without sampling. Python's standard-library `gzip.open(path, "rt", encoding="utf-8", newline="")` can pass directly to `csv.DictReader`.

The [original protocol](METHOD.pt-BR.md) and [original report](REPORT.pt-BR.md), in Portuguese, are preserved as historical execution records. The [pre-editorial inventory](evidence/artifact-manifest.pre-editorial.json) records the earlier publication; the [current publication inventory](evidence/artifact-manifest.json) covers this revised documentation as well.

## Reproduce the numerical run

Run from the repository root with Python 3.12+ and the packages pinned in [requirements-analysis.txt](../../../../requirements-analysis.txt). Retrieve the two nationwide CSVs through Git LFS as described in the [project README](../../../../README.md). No replay or geography database is required. Original source and accounting-provenance manifests must match the supplied snapshot.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt

H5_DIR=reports/2026/hypothesis-tests/05-inter-round-localization

python3 "$H5_DIR/code/run_analysis.py" \
  --output "$H5_DIR/.work/reproduction/analysis" \
  --cache "$H5_DIR/.work/data" \
  --simulation-cache "$H5_DIR/.work/reproduction/simulations" \
  --simulations 4999 --seed 20261029 --workers 4

python3 "$H5_DIR/code/validate_independently.py" \
  --analysis-dir "$H5_DIR/.work/reproduction/analysis" \
  --simulation-cache "$H5_DIR/.work/reproduction/simulations" \
  --output "$H5_DIR/.work/reproduction/independent-validation.json"

python3 "$H5_DIR/code/generate_figures.py" \
  --analysis-dir "$H5_DIR/.work/reproduction/analysis" \
  --output "$H5_DIR/.work/reproduction/figures"

python3 "$H5_DIR/code/extract_context.py" \
  --analysis-dir "$H5_DIR/.work/reproduction/analysis" \
  --output "$H5_DIR/.work/reproduction/selected-source-context.csv" \
  --manifest "$H5_DIR/.work/reproduction/context-manifest.json"

python3 -m unittest discover -s "$H5_DIR/code" -p 'test_*.py' -v

python3 "$H5_DIR/code/inventory_artifacts.py" --verify
```

Use new output paths; published evidence must remain unchanged. `.work/` is ignored by Git. Source-array and simulation caches are reused only with matching fingerprints. Keep simulation vectors for the independent audit: published means and quantiles do not replace them. Reproduction regenerates numerical evidence and original companion figures, not the reviewed English narrative. The inventory command separately verifies the current published folder.

## Implementation map

| Module | Role |
|---|---|
| [load_data.py](code/load_data.py) | Original-source parsing and category reconciliation |
| [pair_statistics.py](code/pair_statistics.py) | Pairing, cohort, section contrasts and concentration scores |
| [run_analysis.py](code/run_analysis.py) | Evidence tables, allocations and sensitivities |
| [validate_independently.py](code/validate_independently.py) | Separate parser and numerical audit |
| [generate_figures.py](code/generate_figures.py) | Figures from completed numerical evidence |
| [extract_context.py](code/extract_context.py) | Original detail rows selected by the published rules |

All pairing, screening and reference definitions are explained in the [method guide](METHOD.md). National rows summarize their UF rows; contexts, references and sensitivity scenarios overlap the same section pairs and must not be added as extra observations.
