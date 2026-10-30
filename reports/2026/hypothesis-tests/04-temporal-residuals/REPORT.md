# H4 — Does counting order retain a signal after local composition is considered?

[Hypothesis index](../README.md) · [Method](METHOD.md) · [Evidence and reproduction](README.md)

**Answer:** residual associations with counting order appear under the electoral-zone reference in both rounds. Adding polling place reduces their national magnitudes. Gradual and cumulative signals remain detectable in round 1; none of the three finalist signals is detected in round 2 under that finer reference.

This is evidence of association beyond the specified references. It does not establish an artificial cause.

## What was tested

**Hypothesis:** candidate votes retain gradual, cumulative, or abrupt associations with counting order beyond the observed composition preserved by the local references. **Identification difficulty: high.**

The analysis compares sections within the same municipality, electoral zone, and registered-electorate band. A second reference also fixes polling place. It asks whether the remaining vote differences arrive in an unusual order relative to permutations within those groups.

All **13 nominal candidates in round 1 and both candidates in round 2** receive the same procedure. First partial totalization is the primary timestamp; ballot-report (BU) receipt is a paired sensitivity.

## The main finding: magnitude changes with the reference

The largest cumulative residual for Lula, expressed as percentage points of the cohort's **final national nominal-vote total**, is:

| Round | Zone and section size | Polling place and section size | Holm-adjusted p, zone / place |
|---|---:|---:|---:|
| 1 | 0.236859 p.p. | 0.010273 p.p. | 0.018 / 0.018 |
| 2 | 0.066855 p.p. | 0.001487 p.p. | 0.018 / 1.000 |

The round 1 residual remains detectable despite its lower magnitude. The round 2 residual does not. Moving between references changes both the composition held fixed and the temporal comparisons available; these reductions are not percentages causally explained by polling place.

![Observed shares and retrospective composition curves](figures/observed-composition.png)

The composition curves use each group's own final voting preference. Their fit is retrospective, rather than a prediction from independent data.

## What remains within polling places?

Three scores examine different aspects of the residual curve:

| Score | Question |
|---|---|
| **G — gradual association** | Do positive or negative residuals systematically arrive earlier or later? |
| **C — cumulative excursion** | How far does the accumulated residual depart from zero? |
| **M — one-minute contribution** | What is the largest residual contribution from one minute's arrivals? |

For both finalists, the results after Holm adjustment across the fixed family of 90 tests are:

| Round and reference | G | C | M |
|---|---|---|---|
| Round 1, zone | Detected | Detected | Detected |
| Round 1, polling place | Detected | Detected | Not detected |
| Round 2, zone | Detected | Detected | Detected |
| Round 2, polling place | Not detected | Not detected | Not detected |

In round 1 within polling places, Lula's signed G is **+0.005956** and Flávio Bolsonaro's is **−0.004711**, both with adjusted p = **0.018**. The signs indicate relatively later positive residuals for Lula and earlier ones for Flávio. G is a normalized covariance score: those numbers are not changes in candidate vote share from the beginning to the end.

In round 2, the polling-place one-minute score has raw p = **0.0042**, but adjusted p = **0.2016**. It therefore does not count as a detected result in the planned family. The two finalists' round 2 residuals are exact opposites, so their matching absolute scores are not independent evidence.

Across all candidates, **40 of 90 tests detect association**, 50 do not, and none is nonapplicable. The zone reference accounts for 30 detections. The polling-place reference accounts for ten: G and C for candidates **13, 14, 22, 55, and 70**, all in round 1. These are dependent tests of national curves, not 40 anomalous sections or incidents. Full results are in [tests.csv](evidence/analysis/tests.csv).

![Cumulative residuals against the conditional reference](figures/conditional-residuals.png)

The bands are pointwise simulation references. Formal decisions use the scores and the family adjustment, rather than individual points outside a band.

## Why coverage limits the conclusion

The eligible cohort contains **498,484 sections in round 1** and **498,528 in round 2**, including overseas voting. The polling-place reference has **258,072 / 284,480 sections informative for Lula's timing comparison**.

More sections do not necessarily mean a wider temporal comparison. Among polling-place groups with at least two sections, the median span between first and last arrivals is **one minute in each round**. Only **32,668 / 9,568 sections** belong to such groups spanning at least an hour. A movement shared by an entire polling place can therefore be held fixed or fall outside the temporal contrasts this reference examines.

The São Paulo summaries illustrate why denominators also matter. Lula's cumulative score is **0.15690 / 0.09031 p.p.** under the zone reference and **0.00383 / 0.00265 p.p.** under the polling-place reference, for rounds 1 / 2. These use the **state's final nominal total**, carry no additional state-level tests, and do not establish what caused the change in São Paulo's curve.

BU-receipt timestamps and the predefined eligibility alternatives retain the difference in magnitude between the two references. They are descriptive checks, not additional opportunities to select a significant result; see [sensitivity.csv](evidence/analysis/sensitivity.csv).

## Assessment

**6/10 — partial support for the statistical hypothesis.** Scale: **0 — Fully refuted → 10 — Fully confirmed**.

Gradual and cumulative associations persist within polling places in round 1. Support remains partial because magnitudes decrease under that reference, round 2 has no detections there, and temporal coverage limits the question that can be answered. The score is an ordinal assessment, not a probability of manipulation; the [index](../README.md#assessment-scale) provides the rubric.

The findings do not identify the source of the residual association. Operational grouping, unobserved section composition, and other legitimate differences can produce it. Non-detection does not establish naturalness, and the supplied final snapshots do not reveal intermediate section edits or certify the public update history.

Read the [method guide](METHOD.md) for the exact references and score definitions, or the [evidence guide](README.md) for complete tables and validation records. This English edition reviews the published results without recalculating them; the original execution documents remain frozen for provenance.
