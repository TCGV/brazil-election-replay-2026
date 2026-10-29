# H6 — Turnout changes and finalists' gains

[Main report (Portuguese)](REPORT.pt-BR.md) · [Method (Portuguese)](METHOD.pt-BR.md) · [Hypothesis index](../README.md)

This analysis asks whether sections with a larger increase in turnout also show a larger change in preference between the two finalists after conditioning on observed initial characteristics. It separates raw vote gains, an exact count balance, an arithmetic turnout/composition decomposition, and two conditional-association references. Aggregate records do not reveal individual voter transitions.

The formal reference tests conditional independence. It is not a complete model of a natural election: rejection may reflect legitimate mobilization, campaign effects, unobserved composition, or imperfect conditioning. Neither rejection nor nonrejection independently authenticates the supplied files.

**Assessment: 6/10 — partial support for the statistical hypothesis.** Scale: **0 — Fully refuted → 10 — Fully confirmed**. All four dependent tests detect a small positive association after Holm (`p = 0.0008`); linear correlations are +0.0184 within the zone reference and +0.0319 within the polling-place reference. The latter covers 39.28% of the cohort, and territorial signs vary. No artificial cause is established. This qualitative ordinal score is not a 60% probability of manipulation, a share of suspicious votes, or a p-value transformation; see the [scale rubric](../README.md#assessment-scale) and [report rationale](REPORT.pt-BR.md#avaliação-na-escala).

Lula gains 10,376,694 votes and Flávio Bolsonaro 3,721,538 across the complete snapshots. Their combined gain of 14,098,232 equals net turnout growth of 2,960,239 plus the disappearance of 9,321,993 other-candidate votes and a reduction of 1,816,000 blank/null votes. This exact balance does not allocate individual transitions or identify the choices of additional voters.

## Files

| Path | Purpose |
|---|---|
| [REPORT.pt-BR.md](REPORT.pt-BR.md) | Hypothesis, difficulty, assessment, findings, figures, and limits |
| [METHOD.pt-BR.md](METHOD.pt-BR.md) | Frozen protocol, defined before H6 association calculations |
| [code/load_data.py](code/load_data.py) | Original-source parsing, provenance checks, and category reconciliation |
| [code/turnout_statistics.py](code/turnout_statistics.py) | Pairing, cohort, measures, decomposition, grouping, and statistics |
| [code/run_analysis.py](code/run_analysis.py) | Evidence tables, deterministic simulations, and sensitivities |
| [code/validate_independently.py](code/validate_independently.py) | Separate source parser and independent numerical reconstruction |
| [code/generate_figures.py](code/generate_figures.py) | PNG/SVG figures from completed evidence |
| [code/inventory_artifacts.py](code/inventory_artifacts.py) | Create or verify the complete published-file inventory |
| [code/](code/) | Analysis code and explicitly artificial implementation tests |
| [evidence/analysis/](evidence/analysis/) | Full numerical evidence, compressed where large |
| [paired-sections.csv.gz](evidence/analysis/paired-sections.csv.gz) | Every matched physical key, original counts, source lines, and cohort decision |
| [section-measures.csv.gz](evidence/analysis/section-measures.csv.gz) | Every eligible pair, rate changes, arithmetic components, and model support |
| [association-groups.csv.gz](evidence/analysis/association-groups.csv.gz) | All strata in both references, variability, means, and covariance components |
| [totals.csv](evidence/analysis/totals.csv) | Original round totals and exact count balances by Brazil, UF, and region |
| [descriptive.csv](evidence/analysis/descriptive.csv) | Cohort summaries, raw and conditional associations, and decomposition totals |
| [x-bins.csv](evidence/analysis/x-bins.csv) | Section means within fixed turnout-change bands |
| [heatmap.csv](evidence/analysis/heatmap.csv) | Complete binned section-count grid of turnout and preference changes |
| [coverage.csv](evidence/analysis/coverage.csv) | Informative and excluded support by model and UF |
| [tests.csv](evidence/analysis/tests.csv) | Four predeclared association tests with signed effects and Holm adjustment |
| [permutation-scores.csv.gz](evidence/analysis/permutation-scores.csv.gz) | All 9,998 retained signed simulation scores, indexed by model and realization |
| [sensitivity.csv](evidence/analysis/sensitivity.csv) | Fourteen predefined descriptive reference/scenario combinations |
| [evidence/independent-validation.json](evidence/independent-validation.json) | Independent validation result and its stated scope |
| [evidence/test-results.txt](evidence/test-results.txt) | Automated implementation-test output |
| [evidence/artifact-manifest.json](evidence/artifact-manifest.json) | Published-file SHA-256 inventory |
| [figures/](figures/) | Four standalone figures in PNG and SVG |

Each pair is one physical section observed in both rounds. National, regional, and UF summaries overlap the same records; models and sensitivity scenarios also overlap. Their counts must not be added as independent sections or voters.

## Reproduce

Run from the repository root with Python 3.12+ and NumPy/Matplotlib from [requirements-analysis.txt](../../../../requirements-analysis.txt). Retrieve the original nationwide files through Git LFS as described in the [project README](../../../../README.md). A replay or geography SQLite database is not required. Source manifests and the completed accounting audit must correspond to the same supplied snapshot.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt
```

Choose new output paths to preserve the published evidence. Single-threaded BLAS prevents nested numerical threads from competing with the analysis workers:

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

The inventory command verifies the published H6 folder, including its documents and code. It is separate from reproducing numerical outputs in a new `.work/` directory.

The original files are Latin-1, semicolon-delimited CSVs:

| Source | SHA-256 |
|---|---|
| `data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv` | `9c35200e1c613d8cc76b255a1d6c824cf5dba63a995c1e86b893c348722fcad8` |
| `data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv` | `bb25a47159af3c628e3e7d0b78819f9c43a11eda66ed36f22ef0a2c2d5caf5bd` |

The loader is an attributed local adaptation from commit `a3362b3ec72c0c567fcf80c5b6761b6cc1cc52c2`. It rereads the original files, verifies their hashes and totals, checks detail-key uniqueness directly, and relies on the completed hash-matched accounting audit for vote-key uniqueness. It does not use H5's numerical results. Source-hash continuity is not independent authentication against external bulletins.

Raw totals retain the electorate-identity residual of 423 registered voters in each round, from the same 41 overseas uninstalled sections with zero recorded turnout, abstentions, and votes. These sections are excluded by cohort status; all included pairs satisfy the identity. The supplied values are preserved rather than normalized.

## Measures and statistical scope

Pairs use `UF + municipality + electoral zone + section`, retaining the election codes and rounds as provenance. The cohort requires installation, no cancellation, at least 50 registered voters and nominal votes, and positive turnout in both rounds; at least 50 first-round votes for the finalists combined; the same known polling place; and a symmetric electorate ratio no greater than 1.25. The electorate/turnout/abstention identity must hold for every included section. Identical keys and electorate counts do not identify identical people.

For candidate 13, define `x = 100*(turnout_2/electorate_2 - turnout_1/electorate_1)` and `y = 100*(q_2 - q_1)`, where `q = votes_13/(votes_13+votes_22)`. Both changes are in percentage points. Candidate 22's conditional change is exactly `-y`, so no duplicated candidate family is created. A positive association favors candidate 13 in the conditional comparison; it does not identify the choices of additional voters.

The exact raw-count identity is `gain_13 + gain_22 = turnout_gain - change_in_other_nominal_and_non_nominal_votes`. It is a balance, not a voter-flow reconstruction. Net turnout growth does not count all entrants because people may enter and leave the voting population between rounds.

The symmetric identity `100*Δ(votes/electorate) = 100*mean(votes/turnout)*Δ(turnout/electorate) + 100*mean(turnout/electorate)*Δ(votes/turnout)` separates arithmetic turnout and vote-composition components. These are descriptive components, not causal effects or transfers of people. Sums weighted by the first-round electorate are electorate-equivalent quantities; when electorate sizes differ, they are not observed vote-count gains.

`zone_baseline` conditions on UF, municipality, zone, initial electorate bands of ratio 1.25, and five-percentage-point bands of initial turnout, finalist preference, and other-candidate share of turnout. `place_baseline` additionally conditions on polling place. Only strata with at least two sections and exact variation in both `x` and `y` contribute. Missing support is not a finding of normality.

The linear statistic is the absolute pooled correlation of within-stratum-centered `x` and `y`. The rank statistic uses exact-tie midranks within each stratum, then pools the centered ranks. It is not the nationwide Spearman correlation or an average of stratum correlations. Larger strata can have greater influence because their ranks span a wider scale. The descriptive slope has units of finalist-preference percentage points per turnout percentage point, not a fraction of added voters.

Each reference uses 4,999 assignments. NumPy/PCG64 realization `rep` uses `SeedSequence([20261029, 6, model_id], spawn_key=(rep,))`, with model IDs 0 and 1. Informative strata are ordered lexicographically, members by physical key, and buckets by ascending size. Preference trajectories move together across rounds relative to fixed turnout trajectories within their stratum. This independence reference does not construct physically feasible synthetic ballot records.

The same assignment evaluates both statistics. The plus-one p-value has minimum resolution 0.0002; Holm controls the fixed family of four tests at 5%. Models and statistics are dependent, not four independent irregularities. Conditional simulation quantiles are not election confidence intervals. The code proves score variability by witnesses or small finite enumeration; it does not turn an unresolved constant-looking simulation into nonrejection.

The published `permutation-scores.csv.gz` retains every signed score, so simulation ranks, means, quantiles, and family adjustment can be audited without the private binary simulation cache. Those numerical checks differ from independently regenerating all assignments.

Fourteen descriptive sensitivity rows cover both primary references and six alternatives: initial bands of 2.5 or 10 points; unchanged electorate; at least 100 first-round finalist votes; domestic sections only; and final-round preference instead of preference change. They create no additional p-values. Finer controls alter support as well as comparability; none eliminates all baseline measurement noise, regression to the mean, or legitimate unobserved heterogeneity.

To read large compressed tables without extracting them:

```python
import csv
import gzip

with gzip.open("path/to/table.csv.gz", "rt", encoding="utf-8", newline="") as stream:
    for row in csv.DictReader(stream):
        pass
```

Generated CSVs use UTF-8, commas, and full stored numerical precision. Compressed tables preserve all rows rather than a sample. Caches and scratch runs belong under `.work/`, which is excluded from publication. Use new output paths when reproducing the analysis to preserve the published evidence.

## Validation

The published run passes **65 implementation tests** and an independent original-source audit with **51,488,243 checks and zero mismatches**. The maximum absolute numerical difference is `4.66e-10`. The audit covers all 14 numerical CSVs, the 14 descriptive sensitivity rows, the execution summary, and provenance. Its separate parser reconstructs electoral measures, pairing, eligibility, decomposition, groups, and summaries without importing primary analysis helpers.

Realizations 0 and 1 were independently regenerated for each reference, giving **four complete assignment checks** with assignment hashes and recomputed statistics. All **9,998 retained signed-score rows** were audited for publication, moments, quantiles, exceedances, and Holm adjustment; all 9,998 assignments were **not** independently regenerated. Integrity-check counts are not independent statistical observations. The exact audit scope is recorded in [independent-validation.json](evidence/independent-validation.json).
