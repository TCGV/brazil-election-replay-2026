# H4 — Temporal evolution after accounting for composition

[Main report (Portuguese)](REPORT.pt-BR.md) · [Method (Portuguese)](METHOD.pt-BR.md) · [Hypothesis index](../README.md)

This analysis asks whether candidate votes retain gradual or abrupt associations with counting order after conditioning on observed local composition. Both presidential rounds are processed separately, including all 13 nominal candidates in round 1 and both candidates in round 2. The procedure treats either direction and every candidate consistently.

Two references are evaluated together: municipality/electoral zone/section-electorate band (`zone_size`), and the same grouping with polling place added (`place_size`). The latter controls polling-place composition more closely, but can also condition an entire place's movement out of the comparison. Neither reference supplies an external prediction of voter preferences.

**Assessment: 6/10 — partial support for the statistical hypothesis.** Scale: **0 — Fully refuted → 10 — Fully confirmed**. Forty of the 90 predeclared tests detect residual time-order association after Holm. For the finalists, gradual and cumulative associations persist within polling places in round 1, with small national magnitudes. In round 2, all three zone-level signals cease to be detected after conditioning on polling place. Local temporal support is incomplete and legitimate unobserved factors may generate association; no artificial cause has been established. The qualitative score is not a 60% probability of manipulation or a transformation of a p-value. See the [scale rubric](../README.md#assessment-scale) and [report rationale](REPORT.pt-BR.md#avaliação-na-escala).

## Files

| Path | Purpose |
|---|---|
| [REPORT.pt-BR.md](REPORT.pt-BR.md) | Hypothesis, difficulty, assessment, results, figures, and interpretation |
| [METHOD.pt-BR.md](METHOD.pt-BR.md) | Protocol fixed before comparing candidate votes with counting order |
| [code/load_data.py](code/load_data.py) | Direct original-source parsing, timestamp handling, reconciliation, and array cache |
| [code/temporal_statistics.py](code/temporal_statistics.py) | Cohort, local residuals, temporal scores, permutation assignments, and Holm adjustment |
| [code/run_analysis.py](code/run_analysis.py) | Primary analysis, simulation, coverage, curves, and descriptive sensitivities |
| [code/validate_independently.py](code/validate_independently.py) | Separate original-source parser and independent numerical audit |
| [code/generate_figures.py](code/generate_figures.py) | Companion PNG/SVG figures from published evidence |
| [code/](code/) | Implementation and tests using artificial controls |
| [evidence/analysis/](evidence/analysis/) | Group totals, minute curves, reference tests, coverage, and sensitivities |
| [evidence/independent-validation.json](evidence/independent-validation.json) | Independent verification of the primary calculations |
| [evidence/test-results.txt](evidence/test-results.txt) | Automated implementation-test output |
| [evidence/artifact-manifest.json](evidence/artifact-manifest.json) | SHA-256 inventory of published files |
| [figures/](figures/) | Composition curves, residual references, and score comparisons |

The unit is a section within one round. National (`BR`) coverage rows summarize the UF rows; do not sum them as additional sections. The two grouping references and two timestamp sources describe the same cohort. Candidates and rounds must not be counted as distinct physical sections or voters.

## Reproduce

Run from the repository root with Python 3.12+ and NumPy/Matplotlib from [requirements-analysis.txt](../../../../requirements-analysis.txt). Retrieve the two original nationwide CSVs with Git LFS as described in the [project README](../../../../README.md). The stage 1 and accounting-audit manifests, their evidence, and the same source snapshot are prerequisites. Neither the replay SQLite database nor a processed geographic database is required.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt
```

Choose **new output directories and files** so the published evidence remains preserved:

```bash
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

For each group, `p = group candidate votes / group nominal votes` and `r = section candidate votes - p * section nominal votes`. These final observed group preferences are reused retrospectively; they are not estimates learned independently of the analyzed results. Their sums, every candidate's votes, nominal totals, and special-vote categories remain fixed under complete-section assignments within each group.

Three two-sided scores summarize each national residual curve: `G` measures gradual association with the tied counting-order rank; `C` is the maximum absolute cumulative residual; `M` is the largest absolute contribution of one minute. They are normalized by the cohort's final nominal total. `G` is a normalized covariance score, not an ordinary slope or a start-to-finish percentage-point change. Current-share residuals in the descriptive curves instead use the current cumulative nominal denominator.

In round 2, the two candidate residuals are exact opposites because they exhaust nominal votes. Their absolute scores therefore coincide; these are dependent tests rather than separate independent findings. This complementarity does not hold for the finalists among 13 round 1 candidates. Holm does not require independence.

There are 4,999 permutations per round/reference, with deterministic per-realization child streams from seed `20261028`. The same complete-section assignment is applied to all candidates and the paired first-totalization/BU-receipt slots. First totalization is primary: plus-one p-values and Holm at 5% cover the fixed family of 90 comparisons. BU receipt is a paired descriptive sensitivity, without a second selected p-value family.

`.work/` is ignored by Git. Array and simulation caches are reused only when fingerprints match. Retain the simulation files for the independent audit; published quantiles do not replace their underlying vectors. Fresh parsing and permutations require several minutes, memory, and local disk. The numerical outputs preserve source hashes and do not modify the original files or earlier study artifacts.

Timestamp seconds are truncated to whole minutes, with all tied sections included together. The source convention is retained as “Hora TSE” without an unverified timezone conversion. The reconstruction uses the final snapshots' first-totalization and BU-receipt fields; it is not a complete history of publicly displayed updates or intermediate edits to section records.

## Reading compressed evidence

Large `.csv.gz` tables contain all rows with gzip compression, without sampling. Read them with Python's standard library:

```python
import csv
import gzip

path = "reports/2026/hypothesis-tests/04-temporal-residuals/evidence/analysis/curves.csv.gz"
with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
    row = next(csv.DictReader(stream))
    print(row)
```

For an uncompressed local copy, write into the ignored `.work/` directory and use exclusive creation to avoid overwriting a published artifact:

```python
from pathlib import Path
import gzip
import shutil

source = Path("reports/2026/hypothesis-tests/04-temporal-residuals/evidence/analysis/curves.csv.gz")
target = source.parents[2] / ".work" / "curves.csv"
target.parent.mkdir(parents=True, exist_ok=True)
with gzip.open(source, "rb") as compressed, target.open("xb") as expanded:
    shutil.copyfileobj(compressed, expanded)
```

The inventory command verifies the **published H4 files**. Reproduction writes new numerical evidence and figures into `.work/reproduction/`; the report remains a reviewed narrative of this source snapshot. Pointwise simulation envelopes are neither simultaneous bands nor confidence intervals for the election. Association beyond a conditional reference does not identify an artificial cause, and non-detection does not certify naturalness or externally authenticate the sources.

The published run passed 55 implementation tests and an independent original-source audit with 6,676,231 checks and zero mismatches. The audit reconstructs all numerical tables, including descriptive alternatives, and recomputes ranks, quantiles, and Holm from retained simulation arrays. It also repeats eight complete assignments independently: realizations 0 and 1 for each round/reference. It does **not** independently repeat all 19,996 assignments. Check counts are integrity comparisons, not independent statistical observations.
