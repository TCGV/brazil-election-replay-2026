# H5 — Localized changes between election rounds

[Main report (Portuguese)](REPORT.pt-BR.md) · [Method (Portuguese)](METHOD.pt-BR.md) · [Hypothesis index](../README.md)

This analysis matches the same polling-section keys across the two presidential rounds. It separates descriptive screening of unusually large section changes from a formal reference for concentration **between polling places**. The two procedures answer different questions: the formal permutations preserve the observed distribution of section changes, so they cannot establish whether the nationwide number or magnitude of extreme section changes is natural.

The main outcome is the change in a finalist's share **among the two finalists**, using the same denominator definition in both rounds. Shares of all nominal votes and absolute vote gains are retained as descriptive diagnostics. Neither section matching nor these aggregate changes identify individual voter transitions.

**Assessment: 6/10 — partial support for the statistical hypothesis.** Scale: **0 — Fully refuted → 10 — Fully confirmed**. The strict screen finds two contrasts of at least ten percentage points among 152,003 sections with sufficient peers, both overseas; none among the 151,353 comparable domestic sections. All four concentration tests detect nonexchangeable allocation between places after Holm. The screen covers only 30.53% of the cohort, and the formal tests preserve marginal changes rather than assessing their nationwide extremity. No artificial cause is established. This qualitative score is not a 60% probability of manipulation, a share of suspicious votes, or a transformation of a p-value; see the [scale rubric](../README.md#assessment-scale) and [report rationale](REPORT.pt-BR.md#avaliação-na-escala).

## Files

| Path | Purpose |
|---|---|
| [REPORT.pt-BR.md](REPORT.pt-BR.md) | Hypothesis, difficulty, assessment, findings, figures, and limits |
| [METHOD.pt-BR.md](METHOD.pt-BR.md) | Protocol fixed before calculating between-round vote changes |
| [code/load_data.py](code/load_data.py) | Direct parsing and reconciliation of the original nationwide files |
| [code/pair_statistics.py](code/pair_statistics.py) | Physical-key pairing, cohort, section contrasts, and concentration references |
| [code/run_analysis.py](code/run_analysis.py) | Main analysis, simulations, evidence tables, and descriptive sensitivities |
| [code/validate_independently.py](code/validate_independently.py) | Separate source parser and independent numerical audit |
| [code/generate_figures.py](code/generate_figures.py) | Companion PNG/SVG figures from published evidence |
| [code/extract_context.py](code/extract_context.py) | Original detail rows for all strict priorities and the places attaining MAX |
| [code/](code/) | Implementation and tests using explicitly artificial controls |
| [evidence/analysis/](evidence/analysis/) | Paired sections, screening, concentration, coverage, and sensitivities |
| [paired-sections.csv.gz](evidence/analysis/paired-sections.csv.gz) | Full matched-key inventory, source lines, counts, and cohort decisions |
| [section-screening.csv.gz](evidence/analysis/section-screening.csv.gz) | Every eligible section and both descriptive peer contrasts |
| [tests.csv](evidence/analysis/tests.csv) | Four predeclared concentration tests and family adjustment |
| [coverage.csv](evidence/analysis/coverage.csv) | Group and target coverage by reference and UF |
| [sensitivity.csv](evidence/analysis/sensitivity.csv) | Predefined descriptive alternatives |
| [evidence/independent-validation.json](evidence/independent-validation.json) | Independent audit and its stated scope |
| [evidence/test-results.txt](evidence/test-results.txt) | Automated implementation-test output |
| [selected-source-context.csv](evidence/selected-source-context.csv) | Eighteen original detail rows for the nine automatically selected sections |
| [context-manifest.json](evidence/context-manifest.json) | Selection rule, source provenance, extractor hash, and context-output hash |
| [evidence/artifact-manifest.json](evidence/artifact-manifest.json) | SHA-256 inventory of published files |
| [figures/](figures/) | Distribution, contrasts, concentration-reference, and coverage figures |

A pair is one physical section key observed in both rounds, not two independent sections. National (`BR`) rows summarize the UF rows and must not be summed with them. Screening contexts, formal references, and sensitivity scenarios overlap the same records; their counts are not additional observations or voters.

## Reproduce

Run from the repository root with Python 3.12+ and NumPy/Matplotlib from [requirements-analysis.txt](../../../../requirements-analysis.txt). Retrieve the two original nationwide CSVs through Git LFS as described in the [project README](../../../../README.md). Source-provenance and accounting-audit manifests must match the same supplied snapshot. Neither a replay SQLite database nor a processed geography database is required.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt
```

Choose **new output directories and files** to preserve published results:

```bash
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

Pairing uses `UF + municipality + electoral zone + polling section`; election code and round remain provenance fields rather than part of the cross-round physical key. The cohort requires installation, no cancellation, at least 50 registered voters and nominal votes, and positive turnout in both rounds. It additionally requires at least 50 first-round votes for the two finalists combined, the same known polling place, and a symmetric registered-electorate ratio no greater than 1.25. The same key, place, and electorate count do not prove that the same individuals voted in both rounds.

For candidate 13, `q = votes_13 / (votes_13 + votes_22)` and `delta = 100*(q_round2 - q_round1)`. Candidate 22 has exactly the opposite conditional change, so no duplicate family is created. The strict descriptive comparison uses the median change of at least four **other** cohort sections with the same polling place, electorate band, and initial-preference band of five percentage points. A contrast of at least ten percentage points is a magnitude screen, with no individual p-value or attribution of cause. A positive contrast means a change more favorable to candidate 13 **relative to the peers**; the section's own conditional share may still have decreased. Insufficient peer coverage is reported explicitly.

The formal references use municipality/zone/electorate band (`zone_size`), with initial-preference band additionally held fixed in `zone_size_baseline`. Complete two-round section pairs are reassigned together among fixed polling-place slots within these groups. Targets contain at least five cohort sections; smaller places remain available as donors. `RMS` measures the weighted root-mean-square of residual place means, in percentage points. `MAX` is the largest absolute residual place mean multiplied by the square root of its section count; it is not a z-score or a variance-studentized statistic.

The published cohort contains 497,833 matched section pairs. Its strict peer screen has support for 152,003, while the context without initial-preference bands covers 363,150 and selects 16 priorities. Those contexts overlap and use different references; their priorities are not additional independent incidents. Both strict priorities are in the source's municipality named `PORTO`, UF `ZZ`, zone 1, place 1015, sections 1894 and 3576. The place determining the global `MAX` statistic is instead in `SÃO PAULO/SP`, municipality 71072, zone 2, place 1546, with seven sections. A global maximum does not supply an individual p-value or establish an artificial cause for that place.

There are 4,999 permutations per reference, with deterministic child streams from seed `20261029`. Plus-one p-values and Holm at 5% cover the fixed family of four tests. Quantiles of simulated scores describe the conditional reference, not confidence intervals for the election or individual places.

All four published tests have raw p-values of 0.0002 and Holm-adjusted values of 0.0008. With initial preference conditioned on, observed `RMS` is 0.665688 percentage points, compared with a simulated mean of 0.514994; observed `MAX` is 20.913947 percentage points times the square root of section count, compared with 8.227965. These scores test where the observed changes are allocated; they are not counts of manipulated votes or tests of every extreme section change.

`.work/` is ignored by Git. Source-array and simulation caches are reused only when their fingerprints match. Preserve simulation vectors for the independent audit; published means and quantiles do not replace them. Fresh source scans and permutations require local memory, disk, and several minutes. Original source files and prior study results are read-only inputs.

## Reading compressed evidence

Large `.csv.gz` tables preserve all their rows with gzip compression; compression is not sampling. They can be read directly with Python's standard library:

```python
import csv
import gzip

path = "reports/2026/hypothesis-tests/05-inter-round-localization/evidence/analysis/paired-sections.csv.gz"
with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
    print(next(csv.DictReader(stream)))
```

Write any uncompressed local copy into `.work/` and use exclusive creation to avoid replacing evidence. The inventory command verifies the **published H5 files**; reproduction writes separate numerical outputs and figures. The Markdown report remains a reviewed narrative of this source snapshot.

Statistical concentration or a large section contrast does not establish an artificial cause. Non-detection does not certify naturalness, and internal consistency does not independently authenticate the records against ballot reports or a voter register.

The published run passed **56 implementation tests** and an independent original-source audit with **32,563,485 checks and zero mismatches**. The audit reconstructs all 14 numerical-evidence CSVs, including all ten sensitivity rows, and recomputes simulation ranks, means, quantiles, and Holm. Realizations 0 and 1 were independently repeated for each reference, providing four complete paired-payload assignment checks and proving variability of all four scores. It does **not** independently regenerate all 9,998 assignments. Check counts are integrity comparisons, not independent statistical observations.

The context extraction is a separate descriptive artifact with its own manifest. It selects all strict priorities and every cohort section in the targets attaining the published MAX, then rereads their original detail rows for both rounds. Venue names, addresses, vote origin, and machine-model fields support traceability; they do not establish demographic characteristics, a special class of section, or the cause of its result.
