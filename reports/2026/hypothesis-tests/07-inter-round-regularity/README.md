# H7 — Evidence and reproduction

[Main report](REPORT.md) · [Method guide](METHOD.md) · [Hypothesis index](../README.md)

The English report separates municipal gain frequencies from the tests of their territorial allocation. The method guide defines the populations, scores, planned tails, and limits. This editorial edition introduces no new analysis.

## Evidence map

| File | Purpose |
|---|---|
| [municipal-census.csv](evidence/analysis/municipal-census.csv) and [candidate-totals.csv.gz](evidence/analysis/candidate-totals.csv.gz) | Raw/cohort municipal counts, candidate totals, coverage, and separate overseas units |
| [gain-directions.csv](evidence/analysis/gain-directions.csv) | Exact improvement directions, ties, undefined cases, and denominators |
| [pairing.csv](evidence/analysis/pairing.csv), [eligibility.csv](evidence/analysis/eligibility.csv), and [unmatched.csv](evidence/analysis/unmatched.csv) | Source join, ordered exclusions, and missing counterparts |
| [cohort-sections.csv.gz](evidence/analysis/cohort-sections.csv.gz) | All eligible paired sections, original counts, changes, and support |
| [allocation-units.csv.gz](evidence/analysis/allocation-units.csv.gz) and [allocation-groups.csv.gz](evidence/analysis/allocation-groups.csv.gz) | Complete section/block representations and initial-composition strata |
| [municipality-results.csv](evidence/analysis/municipality-results.csv) and [adjacent-profiles.csv](evidence/analysis/adjacent-profiles.csv) | Municipal residuals, targets, and every fixed profile pair |
| [tests.csv](evidence/analysis/tests.csv) and [permutation-scores.csv.gz](evidence/analysis/permutation-scores.csv.gz) | Ten formal tests and all 9,998 retained five-score vectors |
| [coverage.csv](evidence/analysis/coverage.csv) and [sensitivity.csv](evidence/analysis/sensitivity.csv) | Allocation support and 14 descriptive model/scenario rows |
| [distribution.csv](evidence/analysis/distribution.csv) and [exact-repetitions.csv.gz](evidence/analysis/exact-repetitions.csv.gz) | Magnitude summaries and repeated exact rational changes |
| [independent-validation.json](evidence/independent-validation.json) and [test-results.txt](evidence/test-results.txt) | Published numerical audit and implementation-test results |
| [code/](code/) and [figures/](figures/) | Calculation/validation code, tests, and four PNG/SVG figures |

Brazilian municipalities and overseas source units are different populations. Raw and paired-cohort totals are different universes. Region, state, and national summaries overlap the same records. Vote-weighted municipal classifications describe where votes are located, not candidate vote shares or voter transitions. Large gzip CSVs preserve all rows; read them using `gzip.open(..., "rt")` and `csv.DictReader`.

## Reproduce

Use Python 3.12+ and the pinned packages in [requirements-analysis.txt](../../../../requirements-analysis.txt). Retrieve the original nationwide CSVs through Git LFS as described in the [project README](../../../../README.md). An existing replay or geography database is not required. Run from the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt

H7_DIR=reports/2026/hypothesis-tests/07-inter-round-regularity

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python3 "$H7_DIR/code/run_analysis.py" \
  --output "$H7_DIR/.work/reproduction/analysis" \
  --cache "$H7_DIR/.work/data" \
  --simulation-cache "$H7_DIR/.work/reproduction/simulations" \
  --simulations 4999 --seed 20261029 --workers 4

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python3 "$H7_DIR/code/validate_independently.py" \
  --analysis "$H7_DIR/.work/reproduction/analysis" \
  --cache "$H7_DIR/.work/independent-source" \
  --output "$H7_DIR/.work/reproduction/independent-validation.json"

python3 "$H7_DIR/code/generate_figures.py" \
  --analysis-dir "$H7_DIR/.work/reproduction/analysis" \
  --output "$H7_DIR/.work/reproduction/figures"

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python3 -m unittest discover -s "$H7_DIR/code" -p 'test_*.py' -v

python3 "$H7_DIR/code/inventory_artifacts.py" --verify
```

Choose new output paths. Private `.work/` caches are fingerprinted and must not be reused if incompatible or incomplete. Single-threaded BLAS avoids competition with analysis workers. Reproduction generates numerical evidence and figures, rather than the reviewed English report.

## Publication records

The [English method guide](METHOD.md) incorporates the interpretation revision that retired the illustrative percentage comparison. The [original protocol](METHOD.pt-BR.md), [original report](REPORT.pt-BR.md), [interpretation revision](METHOD-REVISION.pt-BR.md), and [revision verification](evidence/revision-validation.json) remain unchanged historical records. Their `reaches99_*` fields have no evaluative role. Original figure labels remain in Portuguese.

The [current artifact inventory](evidence/artifact-manifest.json) verifies publication files; the [pre-editorial inventory](evidence/artifact-manifest.pre-editorial.json) preserves the prior snapshot. The [analysis manifest](evidence/analysis/manifest.json) records the numerical execution's source, method, and code fingerprints. Internal hashes and audit checks do not independently authenticate the election sources.
