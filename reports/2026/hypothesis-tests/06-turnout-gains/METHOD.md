# H6 — Method and interpretation

[Main report](REPORT.md) · [Evidence and reproduction](README.md)

This English guide describes the published analysis without new calculations. The [original protocol](METHOD.pt-BR.md) was fixed before the association calculations, when national totals and the pairing structure were already known; it was not externally preregistered. Its bytes, hash, original report, code, and numerical evidence are preserved as execution records.

## Sources and comparable cohort

The local loader rereads the original nationwide vote/detail CSVs and verifies their hashes and totals against the existing manifests. Detail-key uniqueness is checked during loading; vote-key uniqueness relies explicitly on the completed accounting audit of the same source hashes. No replay database or previous hypothesis's numerical results are required.

Physical pairs use state, municipality, electoral zone, and polling section, retaining election codes and rounds as provenance. The original 499,248 keys all have counterparts. The cohort retains 497,833 pairs after the following exclusive, ordered exclusions:

| Exclusion | Pairs |
|---|---:|
| Section uninstalled or cancelled in either round | 41 |
| Fewer than 50 registered voters | 258 |
| Nonpositive turnout | 1 |
| Fewer than 50 nominal votes | 532 |
| Fewer than 50 combined finalist votes in round 1 | 146 |
| Missing polling place | 0 |
| Changed polling place | 430 |
| Symmetric electorate ratio above 1.25 | 7 |

Every included record must reconcile its vote categories and satisfy electorate = turnout + abstentions. Small electorate changes are allowed: 55,602 included pairs have a change, while the unchanged-electorate sensitivity retains 442,231 pairs. Rate denominators use each round's electorate. With changing electorate, reduced abstention counts need not equal increased turnout counts. Matching keys and polling places do not identify individual voters.

The raw national totals retain 423 registered voters per round outside the turnout/abstention identity, in the same 41 uninstalled overseas sections with no votes. They are excluded from the cohort by section status, not silently normalized.

## Measures and accounting identities

For each section and round, let `A` be registered electorate, `T` turnout, `N` nominal votes, `F = V13 + V22` combined finalist votes, and `q = V13/F`:

```text
x = 100 * (T2/A2 - T1/A1)
y = 100 * (q2 - q1)
```

Both changes use percentage points. Candidate 22's conditional change is exactly `-y`; the analysis does not create a duplicate candidate test family. This preference measure differs from absolute gains and changes in shares of all nominal votes.

The raw national count identity is:

```text
gain13 + gain22 = turnout_gain - change(other candidates + non-nominal votes)
```

It reconciles counts without assigning individual transitions. Net turnout growth is not the total number of entrants because entrants and exits can coexist.

The symmetric section decomposition uses `t=T/A`, `s=Vc/T`, and `v=Vc/A`:

```text
100*change(v) = 100*mean(s1,s2)*change(t) + 100*mean(t1,t2)*change(s)
```

The two terms are arithmetic turnout and vote-composition components, not causal effects. Simple means weight sections equally. Sums weighted by initial electorate are electorate-equivalent quantities; when electorate changes, they are not observed vote-count gains. The national count balance is separate.

## References and informative support

`zone_baseline` groups sections by state, municipality, electoral zone, initial electorate bands of ratio 1.25, and five-percentage-point bands of initial turnout `T1/A1`, finalist preference `V13_1/F1`, and other-candidate share of turnout `(N1-F1)/T1`. `place_baseline` adds polling place. Bands use integer ratios, with 100% in the final band; the continuous starting values are not identical within bands.

Only strata with at least two sections and exact variation in both changes contribute. Equality is evaluated using exact rational representations. Informative support covers 359,215 sections under the zone reference and 195,536 under the polling-place reference. Unsupported sections receive no normality classification. Stratum-level mean shifts are conditioned out of the test.

## Statistics, permutations, and adjustment

The linear score is the absolute pooled correlation of `x` and `y` after subtracting their within-stratum means. A descriptive slope reports preference percentage points per turnout percentage point; it is not a fraction of additional voters choosing a candidate.

The rank score first assigns exact-tie midranks within each stratum, then pools the centered ranks. It is neither nationwide Spearman correlation nor an average of stratum correlations. Larger strata may contribute more because their rank scales are wider. Signed correlations accompany both absolute test statistics.

Each reference uses 4,999 permutations. The two-round preference trajectory moves as a block relative to the fixed turnout trajectory within each informative stratum. The marginal trajectories remain intact. This is a conditional-independence reference, not a construction of physically feasible synthetic ballot records.

NumPy/PCG64 uses `SeedSequence([20261029, 6, model_id], spawn_key=(rep,))`, with model IDs 0/1 and realizations 0–4998. The same assignment computes both scores. Deterministic key ordering and size-ordered permutation buckets make assignments independent of worker count.

Plus-one p-values compare simulated absolute scores with the observed absolute score, with tolerance `1e-12`; their minimum resolution is 0.0002. Holm controls the fixed family of four dependent tests at 5%. No additional p-values are assigned to sections, states, regions, candidates, or sensitivities. Simulation quantiles are conditional references, not election confidence intervals.

The implementation requires demonstrated variability of the absolute scores, structural proof, or small finite enumeration; an unresolved constant-looking reference cannot become nondetection. All four published tests had variability confirmed.

## Descriptive sensitivities and validation

Fourteen rows cover both primary references and six predefined alternatives: initial bands of 2.5/10 points, unchanged electorate, at least 100 initial finalist votes, domestic records only, and final preference rather than preference change. They introduce no new significance tests. Changed conditioning also changes support; the final-preference alternative does not remove all baseline measurement effects.

The original publication passed 65 implementation tests and an independent audit of 51,488,243 overlapping integrity comparisons without mismatches; maximum absolute numerical difference was `4.66e-10`. A separate original-source parser reconstructs all 14 numerical CSVs, 14 sensitivity rows, summary, and provenance without importing primary calculation helpers.

Realizations 0 and 1 were independently regenerated for each reference: four complete assignments. All 9,998 retained signed-score rows were audited for publication, moments, quantiles, exceedances, and Holm. Independent regeneration was limited to those four assignments. These integrity-check counts are not independent statistical observations. Full scope appears in [independent-validation.json](evidence/independent-validation.json).

## What the inference supports

Rejection identifies association beyond the specified conditional-independence reference, not an artificial cause. Legitimate mobilization, campaign effects, unobserved composition, regression to the mean, and shared measurement relationships remain possible. The reference does not capture unsupported sections, relationships between stratum means, or every nonlinear pattern. Comparing zone and polling-place results does not isolate a causal contribution because coverage also changes.

The [6/10 assessment](REPORT.md#assessment-and-limits) summarizes partial support for the statistical hypothesis under the shared ordinal rubric. It is not a probability, an effect-size scale, or an estimate of suspicious votes. Neither count balances nor source hashes independently authenticate records or reveal individual voter choices.
