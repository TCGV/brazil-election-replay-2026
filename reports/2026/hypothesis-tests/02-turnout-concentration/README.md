# H2 — Turnout and candidate concentration

[Main report (Portuguese)](REPORT.pt-BR.md) · [Frozen method (Portuguese)](METHOD.pt-BR.md) · [Hypothesis index](../README.md)

This hypothesis asks whether some polling sections combine unusually high turnout and unusually high support for a candidate compared with sections in the same municipality, electoral zone, and registered-electorate size band. Both rounds and all nominal candidates are included: 13 candidates in the first round and two in the second.

The formal benchmark concerns **conditional independence of two upper-tail indicators**. It does not test whether an election is natural or manipulated. Legitimate mobilization, social composition, and local geography can associate turnout and voting even within the comparison groups. The report separates aggregate statistical evidence, descriptive magnitude, local context, and limits of coverage.

**Assessment: 6/10 — partial support for the statistical hypothesis.** Scale: **0 — Fully refuted → 10 — Fully confirmed**. Five of 15 candidate/round combinations show excess association under the primary reference, and 165 priority contrasts persist within the polling place. Attenuation, insufficient peers, partial coverage, and sensitivity to the definition of an extreme limit the conclusion. This qualitative, post-analysis assessment across both rounds is not a 60% probability or evidence of an artificial cause. See the [scale rubric](../README.md#assessment-scale) and the [report rationale](REPORT.pt-BR.md#avaliação-na-escala).

## Files

| Path | Purpose |
|---|---|
| [REPORT.pt-BR.md](REPORT.pt-BR.md) | Hypothesis, difficulty, method, actual results, figures, and interpretation |
| [METHOD.pt-BR.md](METHOD.pt-BR.md) | Protocol fixed before calculating H2 tails and outcomes; not an external preregistration |
| [code/load_data.py](code/load_data.py) | Original-source parser, section-level reconciliation, and fingerprinted array cache |
| [code/run_analysis.py](code/run_analysis.py) | Primary screening, local context, conditional reference, Holm adjustment, and sensitivity scenarios |
| [code/validate_independently.py](code/validate_independently.py) | Separate source parser and exact-ratio checks, including regeneration of simulation references |
| [code/generate_figures.py](code/generate_figures.py) | Reproduce the four PNG/SVG figures from analysis evidence |
| [code/](code/) | Analysis code and implementation tests |
| [evidence/analysis/](evidence/analysis/) | Coverage, strata, joint-tail cases, UF summaries, formal tests, sensitivities, summary, and run manifest |
| [evidence/independent-validation.json](evidence/independent-validation.json) | Independent validation results |
| [evidence/publication-validation.json](evidence/publication-validation.json) | Aggregate summaries reconstructed from validated tables and figure-integrity checks |
| [evidence/test-results.txt](evidence/test-results.txt) | Automated test output; artificial cases are separate from election observations |
| [evidence/artifact-manifest.json](evidence/artifact-manifest.json) | SHA-256 inventory of published report, code, and evidence |
| [figures/](figures/) | Coverage by UF, conditional reference, joint-tail magnitudes, and local context |

`cases.csv` includes every primary joint-tail case, not only the cases passing the additional magnitude screen. A candidate/section/round is one record; do not count different candidates or rounds as distinct physical sections. `strata.csv` repeats group sizes for each candidate, and national (`BR`) coverage rows repeat the aggregate of UF rows. These repetitions must not be summed as additional observations.

## Reproduce

Run from the repository root with Python 3.12+ and the versions of NumPy and Matplotlib in [requirements-analysis.txt](../../../../requirements-analysis.txt). Retrieve the two original nationwide CSVs with Git LFS as described in the [project README](../../../../README.md). The stage 1 and H1 manifests and their matching source snapshots are prerequisites; a replay SQLite database is not needed.

Use a virtual environment if necessary:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt
```

Choose **new output directories and files**. The following commands preserve the published evidence:

```bash
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

Source hashes are checked against stage 1 and the H1 audit. The loader also reconciles candidate and special-vote totals section by section. All detail records are retained in the cache; eligibility exclusions belong to the analysis. Missing source quantities never become zero. An absent candidate row can become zero only for an existing section after source reconciliation.

`.work/` is ignored by Git. Its compressed array cache and simulation vectors can be reused only when their fingerprints match. After a relevant code, protocol, source, or simulation-parameter change, use new cache directories if the existing cache is rejected. Preserve simulation vectors for the independent audit; the compact published CSVs do not replace them. A fresh run can take several minutes and requires sufficient memory for both original-source parsers.

The final inventory command verifies the **published H2 files**. Reproduction regenerates numerical evidence and figures in `.work/reproduction/`; the Markdown report is a reviewed narrative of this snapshot and must be reviewed before applying it to new data. No HTML/PDF export is required.
