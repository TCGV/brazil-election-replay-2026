# H4 — Evidence and reproduction

[Report](REPORT.md) · [Method guide](METHOD.md) · [Hypothesis index](../README.md)

Start with the report for findings and interpretation. This page maps the published evidence and documents how to reproduce the original execution. The English narrative is an editorial review; no calculations were rerun for this edition.

## Evidence map

| File | What it records |
|---|---|
| [tests.csv](evidence/analysis/tests.csv) | All 90 primary scores, signs, reference summaries, p-values, and Holm decisions |
| [eligibility.csv](evidence/analysis/eligibility.csv) | Cohort inclusions and exclusive exclusions by round and state |
| [coverage.csv](evidence/analysis/coverage.csv) | Groups and informative sections for each candidate/reference |
| [group-spans.csv](evidence/analysis/group-spans.csv), [span-summary.csv](evidence/analysis/span-summary.csv) | Temporal reach of the comparisons |
| [group-totals.csv.gz](evidence/analysis/group-totals.csv.gz) | Complete group inventory, including singletons |
| [curves.csv.gz](evidence/analysis/curves.csv.gz), [milestones.csv](evidence/analysis/milestones.csv) | Minute curves and fixed section-progress milestones |
| [uf-summary.csv](evidence/analysis/uf-summary.csv) | Descriptive state-level scores and denominators |
| [sensitivity.csv](evidence/analysis/sensitivity.csv) | Predefined descriptive alternatives for every candidate |
| [summary.json](evidence/analysis/summary.json), [execution manifest](evidence/analysis/manifest.json) | Results, original sources, parameters, and fingerprints |
| [figures/](figures/) | Original composition, residual, score, and support figures; original labels are preserved |
| [code/](code/) | Original implementation and artificial controls |

National (`BR`) rows summarize state rows and must not be summed as additional sections. References and timestamp sources reuse the same cohort. Counts of candidate/round comparisons do not represent distinct voters. Compressed CSVs retain every row; compression is not sampling.

## Validation already completed

The published execution passed **55 implementation tests** and an independent original-source audit with **6,676,231 checks and zero mismatches**; the maximum absolute numerical difference was **3.33e-16**. These are overlapping integrity comparisons, not independent statistical observations.

The independent implementation reconstructs all numerical tables, including descriptive alternatives, and checks scores, quantiles, exceedances, and Holm against retained simulation arrays. It independently repeats realizations 0 and 1 of each round/reference: **eight complete assignments**, rather than all **19,996 assignments**.

- [Independent validation record](evidence/independent-validation.json)
- [Implementation test output](evidence/test-results.txt)
- [Current publication inventory](evidence/artifact-manifest.json)

## Reproduce the original analysis

Use Python 3.12+ and NumPy/Matplotlib from [requirements-analysis.txt](../../../../requirements-analysis.txt). Retrieve the two nationwide CSVs through Git LFS using the [project instructions](../../../../README.md). The stage 1 and accounting-audit records for the same source snapshot are prerequisites; neither a replay SQLite database nor a processed geographic database is required.

From the repository root, choose new output paths to preserve published evidence:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt

H4_DIR=reports/2026/hypothesis-tests/04-temporal-residuals

python3 "$H4_DIR/code/run_analysis.py" \
  --output "$H4_DIR/.work/reproduction/analysis" \
  --cache "$H4_DIR/.work/data" \
  --simulation-cache "$H4_DIR/.work/reproduction/simulations" \
  --simulations 4999 --seed 20261028 --workers 4

python3 "$H4_DIR/code/validate_independently.py" \
  --analysis-dir "$H4_DIR/.work/reproduction/analysis" \
  --simulation-cache "$H4_DIR/.work/reproduction/simulations" \
  --output "$H4_DIR/.work/reproduction/independent-validation.json"

python3 "$H4_DIR/code/generate_figures.py" \
  --analysis-dir "$H4_DIR/.work/reproduction/analysis" \
  --output "$H4_DIR/.work/reproduction/figures"

python3 -m unittest discover -s "$H4_DIR/code" -p 'test_*.py' -v

python3 "$H4_DIR/code/inventory_artifacts.py" --verify
```

`.work/` is ignored by Git. Source and simulation caches are reused only when fingerprints match. Retain the simulation arrays for the independent audit; published quantiles do not replace them. A fresh reproduction writes new numerical artifacts and figures, without regenerating the reviewed English report.

Read a compressed table with the standard library:

```python
import csv
import gzip

with gzip.open("path/to/curves.csv.gz", "rt", encoding="utf-8", newline="") as stream:
    row = next(csv.DictReader(stream))
```

## Frozen execution records

The [original Portuguese protocol](METHOD.pt-BR.md) and [original Portuguese report](REPORT.pt-BR.md) are retained unchanged as historical records. The protocol's hash is pinned by the original code and manifests. Current reading and navigation use [REPORT.md](REPORT.md) and [METHOD.md](METHOD.md); the original documents do not override editorial clarifications in this edition. Existing figures are also preserved rather than presented as regenerated results. The publication inventory covers the current files; the pre-editorial inventory is retained separately when the edition is published.
