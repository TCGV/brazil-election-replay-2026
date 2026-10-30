# Stage 2 — Method and interpretation

[Main report](REPORT.md) · [Evidence and reproduction](README.md)

This guide describes the published run. It introduces no new calculations or tests. The [original Portuguese report](REPORT.pt-BR.md), numerical evidence, manifests, and validation records remain unchanged as execution provenance.

## Population, clocks, and denominators

The analysis uses the completed stage 1 replay: **499,206 section/round records with votes in round 1**, **499,205 in round 2**, with **119,306,034** and **124,082,273 nominal votes**. A physical section may appear in both rounds. The supplied data cover all 27 domestic units and overseas voting (`ZZ`), which is reported separately from domestic city classes.

First partial totalization is the primary timestamp; BU receipt is a sensitivity. Recorded Hora TSE is retained without assuming a UTC offset. Final section payloads are assigned retrospectively to their timestamps, rather than reconstructing a certified history of public updates.

| Measure | Denominator |
|---|---|
| National progress | All voting sections in that round |
| A group's own completion | Voting sections in that group |
| A group's nominal-vote weight | All nominal votes accumulated nationally |
| A candidate's share in a group | Nominal votes accumulated within that group |
| Municipal timing correlations and regression | Equal weight per municipality |

Blank, null, and separately reported votes are excluded from candidate-share denominators. Both first-round finalists are calculated from their own votes; candidate 22 is not treated as the complement of candidate 13 when other candidates are present.

A progress milestone includes the full timestamp tie that first reaches the requested threshold, so actual section progress can exceed it slightly. A group's `t50` is the first timestamp reaching half its sections. Fixed-clock comparisons include events through the exact clock cutoff; minute CSVs include the complete minute.

## Geographic groups and municipality size

Geography is observed composition, not an individual demographic profile. Municipality size means registered electorate aggregated in the first available round, with bands held fixed across rounds: up to 10,000; over 10,000–50,000; over 50,000–200,000; over 200,000–1 million; and over 1 million. Resident population is not used.

Brasília is classified as a capital. DF has no within-state noncapital comparison, leaving 26 capital-versus-other-state comparisons. Aggregate section timing and equally weighted municipality timing use different weights and should not be read as interchangeable estimates.

The descriptive municipal controls relate median timing to log10 electorate, capital status, and state intercepts. The adjusted rank comparison removes state means from global ranks; it is not an average of state-specific Spearman correlations. The regression has limited same-size capital/noncapital overlap and does not identify causal effects.

## Accounting decomposition

At a fixed milestone, let `w_g` be a group's share of accumulated nominal votes, `p_g` Lula's accumulated share within it, `p_g_final` his final share within it, `P` the accumulated overall share, and `P_final` the final overall share. The published decomposition is:

```text
reference = sum(w_g * p_g_final)
between-group component = reference - P_final
within-group component = P - reference
total distance = P - P_final
```

The two components sum to the total distance and are expressed in percentage points. Region, state, and municipality groupings yield different decompositions. Components are accounting identities, not causal explanatory shares. Centered municipal contributions use `(w_g - w_g_final) * (p_g_final - P_final)`; uncentered contributions should not be interpreted individually.

## Section-order references

The published run uses **4,999 permutations per configuration**, seed **20261027**, and a joint primary family of **198 curves across both rounds**, adjusted by Holm at 5%.

- **National (`global`):** complete section payloads exchange timestamp slots across the country. Votes, geography, capital status, and size stay together.
- **Within-state (`within_uf`):** exchanges are limited to a state, preserving its observed section-progress schedule while changing the composition entering its slots.

Timestamp slots and ties are fixed, preserving temporal batch sizes. The original geographic and operational clustering within batches is not preserved. These are stated exchangeability references, not complete models of natural election administration.

Formal milestones are 10%, 25%, 50%, 75%, 90%, and 99%. Country curves use national section progress; state candidate curves use their own state's progress. BU sensitivity reuses the same assignment indices and is not an independent sample or a second opportunity to choose a smaller p-value.

Each observed or permuted curve is centered symmetrically on the pointwise mean of all `B+1` curves, including the observation. Its statistic `S` is the largest absolute deviation across milestones. Monte Carlo p-values use `(1 + exceedances)/(B+1)`, with minimum resolution **0.0002**. `S` is a reference deviation, not the candidate's start-to-finish change.

The 2.5%–97.5% plotting envelopes are pointwise permutation references, not simultaneous bands or population confidence intervals. Formal conclusions use the curve statistic and Holm adjustment. Nondetection is not proof of randomness or equivalence; rejection identifies a difference from the specified ordering reference, without identifying its cause.

## Original validation and reading scope

The retained independent checks found no discrepancies in **864 milestone values** and **1,632 fixed-clock values**. The randomization audit checked **396 Monte Carlo p-values**, **396 observed statistics**, and **198 Holm adjustments**, among other retained-curve checks, without discrepancies at the stated numerical tolerance. It audited retained simulated curves rather than generating a second complete sequence of assignments.

These validation counts concern overlapping implementation and integrity comparisons. They are not independent statistical observations or external authentication of TSE results. The [evidence guide](README.md) links the full records.
