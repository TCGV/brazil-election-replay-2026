# H3 — Evidence and reproduction

[Main report](REPORT.md) · [Method guide](METHOD.md) · [Hypothesis index](../README.md)

Start with the report for findings and the method guide for technical interpretation. This directory contains the original-source analysis, exact-match inventory, restricted conditional reference, validation, and figures for both rounds.

## Evidence map

| File | Purpose |
|---|---|
| [inventory.csv](evidence/analysis/inventory.csv) | Section, group, pair, and multiplicity counts by round, population, and signature |
| [clusters.csv.gz](evidence/analysis/clusters.csv.gz) and [cluster-members.csv.gz](evidence/analysis/cluster-members.csv.gz) | Repeated signatures, source keys, and original line references |
| [turnout-distribution.csv](evidence/analysis/turnout-distribution.csv) | Inventory by exact turnout |
| [coverage.csv](evidence/analysis/coverage.csv) and [strata.csv.gz](evidence/analysis/strata.csv.gz) | Local reference groups and informative support |
| [conditional-tests.csv](evidence/analysis/conditional-tests.csv) | Observed pairs, exact moments, conservative bounds, and Holm adjustment |
| [sensitivity.csv](evidence/analysis/sensitivity.csv) | Predefined descriptive alternatives |
| [independent-validation.json](evidence/independent-validation.json) | Independent primary-calculation audit |
| [test-results.txt](evidence/test-results.txt) | Published implementation-test output |
| [figures/](figures/) | Three companion PNG/SVG figures |
| [code/](code/) | Source loaders, primary and independent calculations, figure generator, and tests |

Large CSVs use gzip without sampling. Read them with `gzip.open(path, "rt", encoding="utf-8", newline="")` and `csv.DictReader`. The `all_details` population overlaps the others; full and extended signatures are views of the same sections. Matching pairs can overlap within a group. Do not add these categories as independent sections or incidents.

## Reproduce

Run from the repository root with Python 3.12+ and the pinned packages in [requirements-analysis.txt](../../../../requirements-analysis.txt). Retrieve the two original CSVs through Git LFS using the [project instructions](../../../../README.md). Source-matching stage 1 and accounting-audit manifests are prerequisites; a replay SQLite database is not required.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt

H3_DIR=reports/2026/hypothesis-tests/03-result-repetition

python3 "$H3_DIR/code/run_analysis.py" \
  --output "$H3_DIR/.work/reproduction/analysis" \
  --cache "$H3_DIR/.work/data"

python3 "$H3_DIR/code/validate_independently.py" \
  --analysis-dir "$H3_DIR/.work/reproduction/analysis" \
  --output "$H3_DIR/.work/reproduction/independent-validation.json"

python3 "$H3_DIR/code/generate_figures.py" \
  --analysis-dir "$H3_DIR/.work/reproduction/analysis" \
  --output "$H3_DIR/.work/reproduction/figures"

python3 -m unittest discover -s "$H3_DIR/code" -p 'test_*.py' -v

python3 "$H3_DIR/code/inventory_artifacts.py" --verify
```

Use new output paths to preserve the publication. `.work/` is ignored by Git; parsing and inventories may take several minutes and several GB of memory. Caches are reusable only when their fingerprints match. The published calculation uses exact rational moments and conservative bounds, not Monte Carlo simulation.

## Publication records

The current English [report](REPORT.md) and [method guide](METHOD.md) are editorial reading versions. They introduce no new analysis. The hash-recorded [execution protocol](METHOD.pt-BR.md), [original report](REPORT.pt-BR.md), numerical evidence, code, and figures are preserved historical records; original figure labels remain in Portuguese. Reproduction regenerates numerical evidence and figures, rather than the reviewed English narrative.

The [artifact inventory](evidence/artifact-manifest.json) records current publication-file integrity; [the pre-editorial inventory](evidence/artifact-manifest.pre-editorial.json) preserves the earlier publication snapshot. The [analysis manifest](evidence/analysis/manifest.json) and independent audit record the numerical execution's provenance; hashes do not independently authenticate election results.
