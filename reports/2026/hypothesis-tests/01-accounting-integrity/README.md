# H1 — Accounting integrity

[Main report (Portuguese)](REPORT.pt-BR.md) · [Hypothesis index](../README.md) · [Índice em português](../README.pt-BR.md)

This folder contains the first hypothesis test of stage 3, covering both presidential rounds and all 27 federative units (26 states and the Federal District) plus overseas sections (`ZZ`). The report distinguishes the absence of vote/turnout overflows and duplicate keys from 82 raw electorate-identity exceptions in uninstalled overseas sections. These are 41 physical sections appearing in both rounds, without votes or turnout. The exceptions remain documented; the hypothesis is not declared fully refuted.

**Assessment: 1/10 — predominantly refuted, with an additional accounting qualification.** Scale: **0 — Fully refuted → 10 — Fully confirmed**. No approved core signal appeared; the broader accounting scope retains 41 electorate-identity exceptions per round without an independently confirmed explanation. This is a qualitative, post-analysis assessment across both rounds, not a probability or measure of manipulation. See the [scale rubric](../README.md#assessment-scale) and the [report rationale](REPORT.pt-BR.md#avaliação-na-escala).

## Contents

| Path | Purpose |
|---|---|
| [REPORT.pt-BR.md](REPORT.pt-BR.md) | Hypothesis, difficulty, method, results, exceptions, and limits |
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
| [evidence/artifact-manifest.json](evidence/artifact-manifest.json) | SHA-256 inventory of the published H1 report, code, and evidence |

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

The primary scanner reads both original files, fingerprints parsed records before aggregation, and builds a temporary SQLite database in this hypothesis's ignored `.work/` folder. That temporary database is removed after processing. Reserve several GB for temporary disk use. The independent implementation uses in-memory dictionaries and needs several GB of RAM. Both scans can take several minutes. Original CSVs and earlier study outputs are read-only inputs.

Numeric checks are exhaustive and use exact integers. `checks.csv` reports each denominator and unavailable comparison. `violations.csv` includes overlapping checks: the same electorate exception appears in the unconditional check and the uninstalled stratum; do not sum rows as distinct incidents. Empty exception files still contain their column headers.

The Markdown report is a reviewed narrative of this published snapshot. Reproduction regenerates numerical evidence; applying the study to new data also requires reviewing and updating the narrative.
