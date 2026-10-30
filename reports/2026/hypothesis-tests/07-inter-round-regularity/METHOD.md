# H7 — Method guide

[Main report](REPORT.md) · [Evidence and reproduction](README.md) · [Frozen execution protocol](METHOD.pt-BR.md)

This English guide explains the published calculation and incorporates the later [interpretation revision](METHOD-REVISION.pt-BR.md). The frozen protocol, executed code, and numerical evidence are unchanged. No fixed percentage of municipalities is a normality or anomaly benchmark; historical `reaches99_*` fields do not enter the scores, simulations, p-values, or assessment.

## Sources, pairing, and populations

The two original nationwide CSVs are read directly. Source hashes, totals, category reconciliation, and section-detail uniqueness are checked; vote-row uniqueness relies explicitly on the accounting audit of those same source hashes. No replay or geography database is needed. The protocol was fixed before the municipal calculations, with the source schema, national totals, and prior cohort already known; it was not externally preregistered.

Sections are paired by state, municipality code, electoral zone, and section. The ordered exclusions are uninstalled/annulled status; electorate below 50; nonpositive turnout; nominal votes below 50; first-round finalist total below 50; missing place; changed place; and a symmetric electorate ratio above 1.25. Included records must satisfy electorate identity and category reconciliation; failure is not silently excluded.

Publish both raw municipal sums and sums over identical eligible paired sections, retaining original presence and coverage fields. Missing denominators remain undefined, without pseudocounts. Domestic units are the source municipal codes in the 27 domestic federative units; `ZZ` units are a separate overseas population. Neither source-key continuity nor unchanged electorate proves the same people voted.

The complete paired cohort contains 497,833 sections, including 1,268 overseas sections. The formal domestic population is 496,565. The raw accounting residual for 423 registered voters per round remains preserved in excluded overseas records.

## Measures and accounting identities

For municipality-level counts, let `Vc,t` be candidate votes, `N_t` all nominal votes, `F_t=V13,t+V22,t`, and `q_t=V13,t/F_t`.

| Measure | Definition | Direction compared |
|---|---|---|
| Absolute gain | `Gc=Vc,2−Vc,1` | `G13−G22` |
| Nominal-share gain | `Pc=100*(Vc,2/N2−Vc,1/N1)` | `P13−P22` |
| Relative growth | `Rc=100*(Vc,2/Vc,1−1)` | `R13−R22` |
| Conditional change | `d=100*(q2−q1)` | `d`, with candidate 22's change equal to `−d` |

Where both are defined with positive initial candidate counts, relative-growth advantage and conditional change have exactly the same direction. They are not independent findings. Signs and ties use integer/rational arithmetic, rather than rounded percentages. Municipalities have equal weight; vote-weighted coverage is a different descriptive summary.

Because round 2 contains only the finalists, the following identities hold where defined:

```text
P13/100 − P22/100 = 2*(q2−q1) + (1−F1/N1)*(2*q1−1)
G13 − G22 = 2*F2*(q2−q1) + (F2−F1)*(2*q1−1)
```

They show why starting preference and other candidates' departure affect gain comparisons. They are arithmetic identities, not estimates of individual vote transfers. A 50/50 sign-binomial reference is not justified by this setup.

## Allocation references

Both references reassign complete two-round trajectories within state and initial-composition strata before aggregating destination municipalities. Candidate counts and denominators move together; original full candidate records remain traceable by physical keys. The numerical representation uses the aggregate `O=N−F` for other candidates where sufficient, and publishes all original candidate totals separately.

- **`section` (ID 0):** the unit is a complete paired section.
- **`place_block` (ID 1):** the unit contains all cohort sections sharing state, municipality, zone, and polling place. Blocks are never split.

Strata combine state, initial electorate band `floor(log(A1)/log(1.25))`, and five-point bands for turnout `T1/A1`, finalist preference `V13,1/F1`, and other-candidate share `(N1−F1)/T1`. Block controls use aggregate block counts. Proportion bands use exact integer calculations, with 100% in the last band. Only strata containing at least two origin municipalities can exchange units.

Section assignments retain section counts per municipal slot. Block assignments retain place-slot counts but may change section counts and vote totals, which are reaggregated. Municipal starting totals are not fixed exactly within bands. Differences between models change the unit, controls, residual adjustment, and coverage; they do not isolate a causal effect of preserving blocks.

Formal targets have at least five original eligible domestic sections. The **5,564 target municipalities** are fixed before allocation and are not reselected when block assignments change section counts. The other seven cohort municipalities remain donors/destinations. The raw census contains 5,571 domestic codes; the formal score population is different.

## Five scores and planned tails

Three symmetric prevalence scores use `max(n_direction13,n_direction22)/M`, with the fixed target count `M` and ties in the denominator: `Ucount` for absolute-gain advantage, `Unominal` for nominal-share advantage, and `Uconditional` for conditional direction. All test **excess prevalence in the upper tail**. Relative-growth direction is not duplicated in another test.

For each section, let `d_i=100*(q2−q1)`. A unit carries `n_u` sections and `D_u=sum(d_i)`. In stratum `g`, set `mu_g=sum(D_u)/sum(n_u)` and `r_u=D_u−mu_g*n_u`. For municipality `m`, `n_m=sum(n_u)` and `R_m=sum(r_u)/n_m`.

```text
Rlow = sqrt(sum_targets(n_m*R_m²) / sum_targets(n_m))
Jhigh = max_pairs |R_left−R_right| / sqrt(1/n_left+1/n_right)
```

`Rlow` tests unusually **low** residual dispersion, in percentage points. It uses equal-section changes, not changes calculated from aggregate municipal vote shares. `Jhigh` tests the **upper** tail of the largest residual contrast, in percentage points times the square root of section count; it is not a z-score.

Profile pairs are fixed before simulation: targets are ordered within state by exact original aggregate `q1`, with code tie-breaks, and consecutive targets are paired. This is neither geographic nor temporal adjacency or a causal discontinuity design. The global-maximum p-value does not belong individually to the pair attaining the maximum.

## Simulation, adjustment, and applicability

Each model uses **4,999** NumPy/PCG64 allocations with `SeedSequence([20261029,7,model_id], spawn_key=(rep,))`, `rep=0..4998`. Units and strata have deterministic sorting, and exchangeable buckets are processed by increasing size with `rng.permuted(..., axis=1)`. Every allocation supplies all five scores; all **9,998** vectors are published.

Plus-one p-values have minimum resolution 0.0002. Exceedances use `>= observed−1e−12` in upper tails and `<= observed+1e−12` for `Rlow`. Holm at 5% adjusts the fixed family of ten dependent tests. There are no additional municipality, region, state, pair, or sensitivity p-values. Simulation quantiles are conditional references, not confidence intervals for an election.

Score variability must be demonstrated, or resolved by structural proof/small-orbit enumeration up to 40,320 assignments. Proven constancy and unresolved variability are distinct nonapplicable outcomes; neither becomes a nondetection. Both use 1 only internally for conservative Holm adjustment. All ten published scores had demonstrated variability.

The planned tails remain fixed. Observed prevalence below every simulation and observed dispersion above every simulation therefore produce no excess-prevalence/low-dispersion detection; they do not imply observations sit inside reference intervals. No opposite-tail test is added afterward.

## Sensitivity and validation scope

Fourteen descriptive rows cover both primary models and six alternatives: 2.5/10-point bands; unchanged electorate; at least 100 initial finalist votes; and target floors of one/ten sections. Changed cohorts or target floors recompute targets and profile order for that scenario, without replacing the primary result or generating new p-values.

The published independent implementation reconstructs all 17 numerical CSVs and 14 sensitivity rows, checks retained scores and Holm, and regenerates allocations 0 and 1 for each model. It does not regenerate every allocation. Implementation tests and integrity comparisons are not independent electoral observations or a complete power assessment.

The references preserve empirical trajectories. They cannot determine their nationwide naturalness, identify voter-level transitions, or distinguish legitimate mobilization from an artificial cause. Preserved [protocol](METHOD.pt-BR.md), [interpretation revision](METHOD-REVISION.pt-BR.md), and [original report](REPORT.pt-BR.md) document the historical execution and revisions. Current reading guidance is this method guide and the English report.
