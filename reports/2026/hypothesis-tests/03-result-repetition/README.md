# H3 — Repetition of complete section results

[Main report (Portuguese)](REPORT.pt-BR.md) · [Method (Portuguese)](METHOD.pt-BR.md) · [Hypothesis index](../README.md)

This hypothesis examines identical integer result vectors in **different polling-section keys**. It differs from H1, which checked repeated records for the same key. Both rounds are processed separately, including all nominal candidates: 13 in the first round and two in the second.

The exhaustive inventory and the conditional test answer different questions. The inventory records nationwide matches, including zero-activity and small sections. The formal reference tests repeated pairing between a complete candidate-count block and a special-vote/turnout block within strict local strata. It preserves the observed repetition of each block, so it cannot test every possible form of copying or establish that all nationwide matches are natural. Informative coverage and this limitation are central results, not exceptions to omit.

**Assessment: 5/10 — inconclusive.** Scale: **0 — Fully refuted → 10 — Fully confirmed**. No excess was detected under the restricted conditional reference, but informative strata cover only seven sections in round 1 and 12,182 in round 2, and the reference preserves each block's repetitions. Here, 5 is an editorial convention for insufficient information, not a 50% probability, positive evidence of excess, or a measure of manipulation. The assessment covers both rounds after analysis. See the [scale rubric](../README.md#assessment-scale) and the [report rationale](REPORT.pt-BR.md#avaliação-na-escala).

## Files

| Path | Purpose |
|---|---|
| [REPORT.pt-BR.md](REPORT.pt-BR.md) | Hypothesis, identification difficulty, method, results, figures, and limits |
| [METHOD.pt-BR.md](METHOD.pt-BR.md) | Protocol fixed before counting H3 repetitions; not an external preregistration |
| [code/load_data.py](code/load_data.py) | Original-source parsing, per-section reconciliation, and fingerprinted array cache |
| [code/collision_statistics.py](code/collision_statistics.py) | Complete signatures, exact rational moments, Cantelli bounds, and Holm adjustment |
| [code/run_analysis.py](code/run_analysis.py) | Primary inventories, conditional analysis, and descriptive sensitivities |
| [code/validate_independently.py](code/validate_independently.py) | Separate original-source parser and independent collision/moment calculations |
| [code/generate_figures.py](code/generate_figures.py) | Three companion PNG/SVG figures |
| [code/](code/) | Implementation and tests with artificial controls |
| [evidence/analysis/](evidence/analysis/) | Inventories, repeated-vector memberships, local strata, tests, and sensitivities |
| [evidence/independent-validation.json](evidence/independent-validation.json) | Independent validation of the published primary calculations |
| [evidence/test-results.txt](evidence/test-results.txt) | Automated implementation-test output |
| [evidence/artifact-manifest.json](evidence/artifact-manifest.json) | SHA-256 inventory of published files |
| [figures/](figures/) | Repetition inventory, informative coverage, and conditional-reference figures |

The `all_details` population overlaps the other populations. Full and extended signatures are two views of the same section records. A repeated vector with multiplicity `m` contributes `m*(m-1)/2` unordered pairs; those pairs overlap and are not additional votes or independent incidents. Do not sum populations, signature types, or turns as distinct physical sections.

## Reproduce

Run from the repository root with Python 3.12+ and NumPy/Matplotlib from [requirements-analysis.txt](../../../../requirements-analysis.txt). Retrieve the two original nationwide CSVs through Git LFS as described in the [project README](../../../../README.md). The stage 1 and H1 manifests, their evidence files, and the matching original-source snapshot are prerequisites. A replay SQLite database is not required.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt
```

Choose **new output directories and files**; the published results are preserved:

```bash
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

The primary calculations use exact integer signatures and rational moments. Cantelli supplies a conservative upper bound on a conditional tail probability, followed by Holm for the fixed two-round family. There is no Monte Carlo run, seed, or simulation error. The bound can have substantially less power than an exact tail distribution.

Both implementations read the original CSVs independently. Sources are pinned to the stage 1/H1 hashes; quantities and candidate/category totals reconcile before the inventory. Missing source quantities never become zero. Zero-filling an absent candidate row applies only to an existing section and an actual candidate in that round. H1 establishes section/votable-key uniqueness for these exact source hashes; the H3 loader checks detail-key uniqueness directly.

`.work/` is ignored by Git. Array and independent-reference caches are reusable only when their fingerprints match. After a relevant source or code change, choose a new cache path if an existing one is refused. Source parsing and exact inventories may take several minutes and need several GB of memory. Original files and earlier study outputs remain read-only inputs.

## Reading compressed evidence

Large tables use CSV compressed with gzip (`.csv.gz`). They retain every row; compression is not sampling. Download a file from GitHub and read it directly with Python's standard library:

```python
import csv
import gzip

path = "reports/2026/hypothesis-tests/03-result-repetition/evidence/analysis/clusters.csv.gz"
with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
    for row in csv.DictReader(stream):
        print(row)
        break
```

To create an uncompressed local copy without replacing published evidence:

```python
from pathlib import Path
import gzip
import shutil

source = Path("reports/2026/hypothesis-tests/03-result-repetition/evidence/analysis/clusters.csv.gz")
target = Path("reports/2026/hypothesis-tests/03-result-repetition/.work/clusters.csv")
target.parent.mkdir(parents=True, exist_ok=True)
with gzip.open(source, "rb") as compressed, target.open("xb") as expanded:
    shutil.copyfileobj(compressed, expanded)
```

The final inventory command verifies the **published H3 files**. Reproduction regenerates numerical evidence and figures in `.work/reproduction/`; the Markdown report remains a reviewed narrative of this source snapshot. No HTML/PDF export is required.
