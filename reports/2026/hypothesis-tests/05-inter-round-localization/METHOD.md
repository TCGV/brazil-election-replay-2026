# H5 — Method and interpretation

[Main report](REPORT.md) · [Reproduction and evidence](README.md)

This English guide explains the published analysis. The [original execution protocol](METHOD.pt-BR.md), in Portuguese, remains unchanged because its hash is part of the numerical provenance. This guide does not replace that frozen record or introduce new tests.

## Two distinct questions

1. **Section screening:** does a section's conditional preference change differ by at least 10 percentage points from the median change of comparable sections at its own polling place?
2. **Place concentration:** are the observed section changes concentrated between polling places beyond two specified allocation references?

The first is a descriptive magnitude screen. The second is a formal allocation test that retains the distribution of changes. Neither establishes the naturalness of all inter-round gains or reconstructs individual voter transitions.

## Pairing and eligible cohort

Original nationwide voting and detail CSVs are paired by `UF + municipality + electoral zone + section`, within the same year and presidential contest. Election code and round remain source identifiers. The analysis diagnoses ambiguous keys and missing counterparts rather than inventing changes. A missing candidate row can represent zero only after category reconciliation; a missing numeric quantity never becomes zero.

The main cohort requires, in both rounds, an installed, uncancelled section with at least 50 registered voters, positive turnout and at least 50 nominal votes. It also requires at least 50 votes for the finalists combined in round 1, the same known polling place, and a symmetric electorate ratio no greater than 1.25.

| Pairing or exclusive exclusion | Pairs |
|---|---:|
| Matched physical keys | 499,248 |
| Unmatched keys | 0 |
| Section status | 41 |
| Registered electorate below 50 | 258 |
| Nonpositive turnout | 1 |
| Nominal votes below 50 | 532 |
| Initial finalist votes below 50 | 146 |
| Missing place | 0 |
| Changed place | 430 |
| Electorate ratio above 1.25 | 7 |
| **Eligible cohort** | **497,833** |

The exclusions are applied in the published order and are mutually exclusive. The same key, place and electorate count do not prove that the same people voted. Registered-electorate equality is a descriptive sensitivity, rather than a primary requirement.

## Conditional change and peer contrast

For each section and round, define `q = votes_13 / (votes_13 + votes_22)`. The outcome is `delta = 100 × (q_round2 − q_round1)`, in percentage points. Candidate 22's conditional change is exactly `−delta`, so the formal family is not duplicated for the complementary candidate.

This denominator is comparable across rounds despite the other first-round candidates. Changes over all nominal votes and absolute gains remain separate diagnostics. Section-weighted averages of `delta` are not changes in aggregate national vote shares.

Strict peers share UF, municipality, zone, polling place, initial-electorate band and initial-preference band. The section itself is excluded. With at least four other peers, the contrast is its `delta` minus their median `delta`. An absolute contrast of at least **10 p.p.**, allowing `1e−12` p.p. numerical tolerance, receives descriptive priority. Insufficient peers mean insufficient support, not normality.

Electorate bands use `floor(log(A1)/log(1.25))`. Initial-preference bands use exact integer counts, `min(19, floor(20 × votes_13,1/F1))`, giving five-point intervals with 100% in the last band. An additional descriptive context drops only the preference band. Its results overlap the strict context and do not constitute additional independent incidents.

## Conditional allocation between places

Both references keep each section's two rounds and their counts inseparable:

| Reference | Fixed stratum fields |
|---|---|
| `zone_size` | UF, municipality, zone and initial-electorate band |
| `zone_size_baseline` | The same fields plus initial-preference band |

Within each stratum, subtract its equal-section mean change to obtain residual `r_i`. Complete paired records move among fixed place slots within that stratum; target sizes stay fixed. Moving residuals is equivalent for these scores because the stratum mean is invariant.

Targets have at least five original cohort sections. Sections at smaller places remain available to the allocations. For target place `l`, let `n_l` be its fixed section count and `S_l` its residual sum:

```text
RMS = sqrt(sum_l(S_l² / n_l) / sum_l(n_l))
MAX = max_l abs(S_l) / sqrt(n_l)
```

`RMS` is the section-weighted root-mean-square of place residual means, in p.p. `MAX` is the largest absolute place residual mean multiplied by `sqrt(n_l)`, in p.p. × square root of section count. It is not a z-score or a variance-standardized statistic. The maximum already includes the search across targets; its p-value does not belong to the single maximizing place.

Coverage is separate from the section screen. [coverage.csv](evidence/analysis/coverage.csv) records all strata, targets and informative exchange support. A place may be informative for allocation while none of its sections has four strict peers.

## Simulation and family adjustment

Each reference uses **4,999 allocations**, PCG64 and base seed `20261029`. Realization `rep` uses `SeedSequence([20261029, model_id], spawn_key=(rep,))`, with reference IDs 0 and 1. Both scores use the same assignment; results are independent of worker count.

The upper-tail p-value is `(1 + exceedances)/(4,999 + 1)`, using `score >= observed − 1e−12` in the score's units. Its minimum is **0.0002**, never zero. Holm at 5% covers the fixed family of four tests. References and scores are dependent; they are not independent irregularities. Simulated 2.5%–97.5% quantiles describe the conditional reference, not election confidence intervals.

Applicability requires demonstrated score variation or a resolved finite/structural check. Unresolved variation is diagnosed rather than converted into nondetection. Proven constant references are nonapplicable and use p=1 only internally in conservative family adjustment. All four published scores had demonstrated variability.

## Sensitivities and validation scope

The ten published sensitivity rows include the two primary references and predefined alternatives: initial bands of 2.5 or 10 p.p.; unchanged electorate; at least 100 initial finalist votes; or at least ten sections per target. They change one choice at a time, recompute affected cohorts/targets, and add no formal p-values. See [sensitivity.csv](evidence/analysis/sensitivity.csv).

The original run passed **56 implementation tests**. Its independent parser reconstructed all **14 numerical CSVs**, including the sensitivity rows, with **32,563,485 integrity comparisons and zero mismatches**. Realizations 0 and 1 were independently repeated for each reference: four full assignments. The retained simulation scores were audited, but all **9,998 assignments were not independently regenerated**. Integrity-check counts are not independent statistical observations.

The original [report](REPORT.pt-BR.md), [protocol](METHOD.pt-BR.md), [analysis manifest](evidence/analysis/manifest.json) and [audit](evidence/independent-validation.json) remain historical execution records. Neither their internal hashes nor this English editorial guide independently authenticates the election records against external ballot reports or a voter register.
