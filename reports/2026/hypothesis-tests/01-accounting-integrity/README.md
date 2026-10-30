# H1 — Accounting integrity

[Main report](REPORT.md) · [Method](METHOD.md) · [Hypothesis index](../README.md)

Start with the report for findings and the method guide for definitions. This page lists the published evidence and reproduction commands. The English editorial edition uses the existing results without recalculating them. The [original Portuguese report](REPORT.pt-BR.md) and original execution evidence remain frozen historical records.

## Contents

| Path | Purpose |
|---|---|
| [REPORT.md](REPORT.md) | Question, findings, accounting exception, assessment, and limits |
| [METHOD.md](METHOD.md) | Source interpretation, exact checks, exception handling, and validation |
| [code/run_audit.py](code/run_audit.py) | Primary original-CSV scan, disk-backed joins, exact integer checks |
| [code/validate_independently.py](code/validate_independently.py) | Separate original-CSV parser using dictionaries; no primary/replay imports |
| [code/compare_validations.py](code/compare_validations.py) | Compare both implementations, input/code hashes, and stage 1 snapshot hashes |
| [code/inventory_artifacts.py](code/inventory_artifacts.py) | Write or verify the published-file inventory |
| [code/test_audit.py](code/test_audit.py), [code/test_independent.py](code/test_independent.py) | Synthetic corruption fixtures; these are not election results |
| [code/test_comparison.py](code/test_comparison.py) | Tampering and omission checks on temporary copies of the published evidence |
| [evidence/accounting/](evidence/accounting/) | Primary checks, violations, totals, coverage, context, and manifest |
| [evidence/independent-validation.json](evidence/independent-validation.json) | Independent counts, checks, flags, and exception examples |
| [evidence/validation-comparison.json](evidence/validation-comparison.json) | Exact agreement of the two scans |
| [evidence/test-results.txt](evidence/test-results.txt) | Automated test output |
| [evidence/artifact-manifest.json](evidence/artifact-manifest.json) | Current publication inventory, including the English editorial documents |
| [evidence/artifact-manifest.pre-editorial.json](evidence/artifact-manifest.pre-editorial.json) | Preserved inventory of the original H1 publication |

## Reproduce

Use Python 3.12+ and SQLite 3.39+ (included with Python in the study environment). No third-party packages are needed. Run from the repository root after retrieving the two nationwide source CSVs with Git LFS, as described in the [project README](../../../../README.md).

Choose **new output paths**; existing evidence is preserved. For example:

```bash
python3 reports/2026/hypothesis-tests/01-accounting-integrity/code/run_audit.py \
  --output reports/2026/hypothesis-tests/01-accounting-integrity/.work/reproduction/accounting

python3 reports/2026/hypothesis-tests/01-accounting-integrity/code/validate_independently.py \
  --output reports/2026/hypothesis-tests/01-accounting-integrity/.work/reproduction/independent-validation.json

python3 reports/2026/hypothesis-tests/01-accounting-integrity/code/compare_validations.py \
  --evidence reports/2026/hypothesis-tests/01-accounting-integrity/.work/reproduction \
  --output reports/2026/hypothesis-tests/01-accounting-integrity/.work/reproduction/validation-comparison.json

python3 -m unittest discover \
  -s reports/2026/hypothesis-tests/01-accounting-integrity/code -p 'test_*.py' -v

python3 reports/2026/hypothesis-tests/01-accounting-integrity/code/inventory_artifacts.py --verify
```

The primary scanner accepts `--votes`, `--details`, and `--year`; the independent validator accepts `--root` and is intentionally fixed to the study's 2026 nationwide files. The comparison verifies that the inputs still match the stage 1 manifest. If the source snapshot changes, it must be reviewed as a new study run rather than silently compared with this report.

The primary scanner fingerprints parsed records before aggregation and uses a temporary SQLite database in this hypothesis's ignored `.work/` folder; the database is removed afterward. Reserve several GB of temporary disk space. The independent scan requires several GB of RAM. Both read the original CSVs without modifying them.

Numeric checks are exhaustive and use exact integers. `checks.csv` retains denominators and unavailable comparisons; `violations.csv` includes overlapping checks, so rows are not distinct incidents. Header-only exception files record that no cases were found. See the method guide for interpretation.

The preserved pre-editorial inventory describes the original publication, including its original README. The current inventory covers the English editorial edition as well. Reproduction regenerates numerical evidence. New source data require a new run and review of the narrative.
