# Stage 2 — Counting composition and the vote-share curves

[Study stages](../README.md) · [Reconstruction](../REPORT.md) · [Method](METHOD.md) · [Evidence and reproduction](README.md)

**Question:** Did regions, states, capitals, and municipalities of different sizes enter the count in a consistent order, and how did that order relate to the candidates' accumulated shares?

**Answer:** The order had a territorial structure in both rounds. The Northeast was less underrepresented at the national halfway point in round 2. Capitals reached their midpoint earlier in aggregate, but municipality size did not follow a simple national rule. In São Paulo, Lula's share rose as the mix of municipalities changed and as different sections entered within those municipalities.

These are observations about the supplied files. “Demographic composition” here means geography and registered electorate, not the age, income, education, or individual behavior of voters.

## The Northeast entered at a different stage of the national count

When half of Brazil's sections had entered, **39.07%** of the Northeast's own sections had entered in round 1, compared with **48.97%** in round 2. Its share of accumulated nominal votes was correspondingly closer to its final weight in round 2.

| Region | Round 1: share at national halfway / final | Round 2: share at national halfway / final |
|---|---:|---:|
| North | 10.60% / 8.54% | 13.30% / 8.10% |
| Northeast | 21.34% / 28.25% | 27.96% / 28.41% |
| Central-West | 11.51% / 7.61% | 11.25% / 7.53% |
| Southeast | 34.52% / 40.64% | 24.93% / 41.01% |
| South | 21.65% / 14.68% | 22.17% / 14.66% |
| Overseas | 0.38% / 0.28% | 0.40% / 0.30% |

The Northeast's final Lula share was **63.77%** in round 1 and **69.37%** in round 2. Its changing representation therefore matters when reading the national curve. But regional representation is only part of the picture: the mix of sections within each region also changes.

![Northeast representation at equivalent national progress; dotted lines show final weights.](figures/northeast-composition.png)

“Earlier” means earlier **relative to national progress**. The Northeast reached its own halfway point at 19:03:52 in round 1 and 20:27:31 in round 2. These recorded clock times were later in round 2, even though its relative representation was closer to completion.

## States within a region did not move together

The regional averages conceal different state trajectories. The following examples show the share of each state's sections already counted at national halfway:

| State | Round 1 | Round 2 |
|---|---:|---:|
| Alagoas (AL) | 20.73% | 73.62% |
| Maranhão (MA) | 40.51% | 74.64% |
| Paraíba (PB) | 80.75% | 90.03% |
| Bahia (BA) | 30.59% | 28.00% |
| Rio de Janeiro (RJ) | 28.03% | 7.58% |
| São Paulo (SP) | 44.07% | 27.14% |

Candidate-share trajectories also differed. Between each state's own 10% milestone and its final result in round 2, Lula rose from **64.54% to 68.93% in Ceará**, but fell from **73.33% to 69.20% in Pernambuco** and **64.11% to 52.88% in Amapá**. A national or regional curve should not be read as a uniform movement across states.

All 27 domestic units, both candidates, both rounds, and the full progress milestones remain available in [uf-milestones.csv](uf-milestones.csv); [milestone-composition.csv](milestone-composition.csv) records state representation at national milestones.

## Capitals were earlier in aggregate; size alone gave no simple rule

| Comparison | Round 1 | Round 2 |
|---|---:|---:|
| Capital sections counted at national halfway | 57.94% | 51.42% |
| Other domestic sections counted at national halfway | 47.91% | 49.59% |
| Capitals' aggregate halfway point occurred earlier by | 11.92 minutes | 2.13 minutes |
| States where the capital reached halfway first | 19 of 26 | 16 of 26 |

The aggregate capital advantage narrowed in round 2 and was not universal within states. Brasília is a capital, but the Federal District has no noncapital counterpart in the within-state comparison.

Municipality-size bands were not ordered consistently from small to large:

| Registered electorate | Own sections counted at national halfway, round 1 | Round 2 |
|---|---:|---:|
| Up to 10,000 | 51.44% | 58.78% |
| Over 10,000–50,000 | 51.59% | 57.47% |
| Over 50,000–200,000 | 44.09% | 42.82% |
| Over 200,000–1 million | 49.60% | 44.81% |
| Over 1 million | 54.60% | 46.41% |

With equal weight per municipality, the size–median-time Spearman correlations were **0.117** and **0.136**. After removing state means from the global ranks, the correlations were **−0.002** and **0.087**. The observed association with size was therefore limited and depended on how geography was considered; this is not evidence that counting order was random.

![Section timing by capital status and electorate-size band; dots mark halfway and intervals mark 10%–90%.](figures/capital-size-timing.png)

## São Paulo's rise was broader than the capital

At equivalent progress within São Paulo, the candidates' accumulated shares were:

| SP section progress | Round 1: Lula / Flávio Bolsonaro | Round 2: Lula / Flávio Bolsonaro |
|---|---:|---:|
| 10% | 33.55% / 57.36% | 40.91% / 59.09% |
| 50% | 36.65% / 53.59% | 44.03% / 55.97% |
| Final | 38.20% / 51.93% | 46.15% / 53.85% |

The capital was initially underrepresented: its nominal-vote weight rose from **14.60% to 26.33%** in round 1 and **13.11% to 26.51%** in round 2. Lula's final capital share was above his statewide share. Yet his share outside the capital also rose, from **31.85% to 35.20%** and **38.84% to 42.78%**. The capital–other-municipalities distinction alone does not describe the full trajectory.

An accounting decomposition separates the changing municipality mix from changes within municipalities. At SP's 10% milestone, Lula's distance from his own final result was:

| Round | Total distance | Municipality-composition component | Within-municipality component |
|---|---:|---:|---:|
| 1 | −4.651 pp | −3.701 pp | −0.950 pp |
| 2 | −5.240 pp | −4.762 pp | −0.478 pp |

These components add to the observed distance; they are not estimates of causal effects or percentages of votes “explained.” A rising overall curve also need not rise at every event.

## National shares reflected both regional mix and ordering within regions

At national halfway, Lula stood at **41.68% versus a final 45.16%** in round 1, and **50.12% versus 51.79%** in round 2. The same accounting decomposition gives:

| Round, national halfway | Distance from Lula's final share | Between-region component | Within-region component |
|---|---:|---:|---:|
| 1 | −3.478 pp | −2.417 pp | −1.061 pp |
| 2 | −1.661 pp | −0.955 pp | −0.706 pp |

Thus regional weights alone do not reproduce the accumulated result. The remaining component records which sections had entered within each region. Changing the geographic grouping changes the decomposition.

## What the statistical comparisons establish

The primary analysis compared **198 curves** with explicit section-order randomization references. After Holm adjustment at 5%, **191 differed detectably** and **7 did not**. The seven nondetections concern specific curves:

| Round | Curve without a detected difference | Reference |
|---|---|---|
| 1 | Amapá section progress | National shuffle |
| 1 | Both candidates' shares in DF and Tocantins | Within-state shuffle |
| 2 | Both candidates' shares in DF | Within-state shuffle |

These results support structured ordering under the tested references, not a cause for it. Nondetection does not establish randomness. A small municipality-size correlation and a detectable difference for a size-band curve answer different questions and can coexist.

For the national Lula curve, the maximum reference deviation under a within-state shuffle was **1.708 pp** in round 1 and **0.586 pp** in round 2, both with Holm-adjusted **p = 0.0396**. Preserving state progress therefore did not remove every detectable association. A difference in test outcomes or magnitudes between rounds is not itself a formal test of the difference between rounds.

## Scope and evidence

Progress counts **sections**; candidate shares and territorial weights use **nominal votes**. The main reference is first partial totalization. BU receipt is a paired sensitivity, with similar Northeast weights at halfway: **21.34% / 21.42%** for the two clocks in round 1 and **27.96% / 27.95%** in round 2.

The initial flat clock segment in round 2 represented only **0.374% of sections at 19:00**, compared with **58.456%** in round 1. Visual stability there should not be mistaken for broad coverage. All times remain in recorded Hora TSE, without an independently confirmed UTC offset.

The replay assigns final section votes retrospectively to recorded timestamps. It does not recover every public update, identify voter transitions, or independently authenticate the sources. Existing figures retain the labels from the original publication.

See the [method guide](METHOD.md) for definitions and statistical scope, and the [evidence guide](README.md) for the complete tables, original validation records, and reproduction commands. This English edition is a textual revision of the published analysis; no calculations were rerun.
