# H7 — Municipal gains and territorial regularity

[Hypothesis index](../README.md) · [Method](METHOD.md) · [Evidence and reproduction](README.md)

**Question:** do inter-round gains show excess directional prevalence, unusually low residual dispersion, or contrasts between similar initial municipal profiles under the stated territorial references? **Identification difficulty: very high.**

**Answer:** the references detect profile contrasts, but no excess prevalence or uniformity in the planned tests. In the raw census, Lula's relative growth exceeds Flávio Bolsonaro's in **5,411 of 5,571 municipalities (97.1280%)**. That describes the supplied records; by itself, it does not establish statistical rarity or a cause.

The formal comparison uses **5,564 fixed target municipalities** from the paired eligible cohort. Its conditional-direction prevalence is **97.1064%**, compared with simulated means of **99.2273% by section** and **98.8869% by polling-place block**. Both upper-tail excess-prevalence tests have Holm-adjusted **p=1.000**. These models preserve observed trajectories and test their territorial allocation; they do not establish the global naturalness of the gains or estimate campaign effects.

## Assessment

**6/10 — Partial support for the statistical hypothesis.** Scale: **0 — Fully refuted → 10 — Fully confirmed**.

Both maximum-profile-contrast tests detect differences beyond their references, with **Holm-adjusted p=0.002**. The other eight tests do not detect excess prevalence or excessively low dispersion in their planned tails. The score summarizes this partial result and its coverage limits; it is ordinal, not a probability of manipulation or a conversion of p-values. See the [scale rubric](../README.md#assessment-scale).

## “Improved more” depends on the measure

Absolute vote gains, percentage-point gains among all candidate votes, and growth relative to a candidate's first-round vote count answer different questions. Each municipality receives equal weight in the census.

| Raw domestic census | Lula improves more | Flávio Bolsonaro improves more | Ties | Lula's fraction |
|---|---:|---:|---:|---:|
| Absolute vote gain | 5,228 | 339 | 4 | 93.8431% |
| Gain in nominal-vote share | 5,389 | 182 | 0 | 96.7331% |
| Relative growth / conditional direction | 5,411 | 160 | 0 | 97.1280% |

All three measures are defined for all **5,571 domestic source municipal codes**. These codes were not independently checked against an external municipal register. The **186 overseas source units** are reported separately and are not Brazilian municipalities.

Conditional share means a candidate's share of votes for the two finalists. Where both measures are defined with positive initial counts, its direction of change exactly matches which finalist has greater relative growth. Those are two descriptions of the same direction, not independent confirmations.

The paired-cohort census retains the same 5,571 domestic codes, with relative-growth advantage for Lula in **5,410 (97.1100%)**. The formal target set excludes municipalities with fewer than five original eligible sections, giving the different denominator of 5,564 and observed prevalence of 97.1064%.

![Municipal improvement frequencies under the different definitions](figures/municipal-improvement-definitions.png)

The initial position and the departure of other candidates from the ballot matter. A candidate can gain more nominal-vote share while their conditional share among the finalists stays unchanged. The [composition figure](figures/initial-composition-identity.png) and [method identities](METHOD.md#measures-and-accounting-identities) show this arithmetic without inferring individual vote transfers. No fixed municipal percentage serves as an anomaly benchmark.

### Direction and magnitude differ

The raw municipal changes in Lula's conditional share range from **−8.75297 to +10.18866 percentage points**, with a median of **+2.37083 points**. A common direction does not imply a common-sized change. These descriptive magnitudes, published in [distribution.csv](evidence/analysis/distribution.csv), have no standalone naturalness test.

## What the allocation tests found

Both models keep each section's two-round counts together. One reallocates paired sections; the other reallocates whole polling-place blocks. Reallocation stays within state and initial electorate, turnout, finalist-preference, and other-candidate-share bands, then municipalities are aggregated again.

This asks whether the **observed trajectories are unusually distributed across municipalities**, conditional on those controls. It does not generate an independent model of how votes should change nationally between rounds.

| Planned test | Section reference | Place-block reference | Result after Holm |
|---|---|---|---|
| Excess absolute-gain prevalence | Observed 93.9432%; simulated mean 97.0025% | Observed 93.9432%; mean 95.6348% | p=1.000 in both |
| Excess nominal-share prevalence | Observed 96.8009%; mean 99.1330% | Observed 96.8009%; mean 98.3212% | p=1.000 in both |
| Excess conditional prevalence | Observed 97.1064%; mean 99.2273% | Observed 97.1064%; mean 98.8869% | p=1.000 in both |
| Excessively low residual dispersion | Observed 0.495865 p.p.; mean 0.207065 | Observed 0.419046 p.p.; mean 0.246054 | p=1.000 in both |
| Maximum initial-profile contrast | Observed 39.420189; mean 8.104806 | Observed 35.470432; mean 11.876326 | **p=0.002 in both** |

Prevalence measures are fractions of municipalities, not candidate vote shares. Residual dispersion uses mean changes per section after adjustment to each reference. The contrast score has units of percentage points times the square root of section count; it is not a z-score.

Each reference uses **4,999 allocations**, with five scores evaluated together and Holm adjustment across the fixed ten-test family. The [complete table](evidence/analysis/tests.csv) includes the planned tails and simulated quantiles.

**The eight p=1 results do not mean the observations lie inside the simulated intervals.** Every prevalence score is below all retained simulations. Observed residual dispersion is above all simulations, whereas its planned test looks for unusually *low* dispersion. No opposite-tail test was added after seeing these results, and nondetection does not establish naturalness.

![Observed scores against conditional allocation references and their planned tails](figures/conditional-allocation-reference.png)

## Where the profile contrast appears

Both models locate the maximum between **Belo Monte/AL** and **Quebrangulo/AL**. Their original aggregate Lula shares among finalists are **70.33860% and 70.34876%**, making them adjacent in the fixed initial-preference ordering within Alagoas. Adjacency here means a similar starting profile, not geographic proximity or a counting-time sequence.

| Paired-cohort measure | Belo Monte | Quebrangulo |
|---|---:|---:|
| Original eligible sections | 16 | 37 |
| Change in aggregate municipal conditional share | −8.75297 p.p. | +3.69647 p.p. |
| Mean residual section change, section reference | −10.99963 p.p. | +0.79531 p.p. |
| Mean residual section change, block reference | −9.74426 p.p. | +0.86887 p.p. |

The adjusted p-value belongs to the **global maximum search across 5,537 profile pairs**, not to an individual municipality. The two detections concern the same pair under different residual adjustments; they are not two independent incidents and do not establish an artificial cause. Every pair is published in [adjacent-profiles.csv](evidence/analysis/adjacent-profiles.csv).

## Coverage and sensitivity

The formal cohort has **496,565 domestic paired sections**. Cross-municipality exchange is possible for **470,386 section units (94.73%)**, or **77,682 of 93,298 place blocks (83.26%)** carrying 419,476 sections. These percentages have different unit denominators. Some target municipalities have no exchangeable unit; that is a coverage limitation, not a normality finding. See the [coverage figure](figures/allocation-coverage.png).

Fourteen descriptive sensitivity rows change baseline-band widths, require unchanged electorate, raise the initial finalist-vote floor, or change the target-size floor. Narrower bands reduce residual magnitudes but also change conditioning and exchange coverage. They do not estimate a causally explained fraction and receive no new p-values. Full results are in [sensitivity.csv](evidence/analysis/sensitivity.csv).

## Interpretation and limits

No 50/50 split of municipal improvements is assumed, and no fixed municipal percentage classifies a result as normal or anomalous. Assessment refers to the defined model. Here, prevalence and low-dispersion tests do not detect the planned excesses; profile contrasts do.

The models preserve the empirical section/block trajectories. They therefore cannot establish the global rarity or naturalness of those trajectories, or exclude a change conditioned out of the design. Unobserved composition, geography, mobilization, and campaign effects remain possible explanations, not demonstrated causes. Aggregate counts do not identify individual voter transitions or an amount of artificial votes.

## Evidence and validation

The published run passed **65 implementation tests**. A separate parser and independent calculations reconstructed all **17 numerical CSVs** and **14 sensitivity rows**, with zero mismatches in **47,764,799 integrity comparisons**. Four complete allocations were independently regenerated; all 9,998 retained score vectors were audited, but all 9,998 allocations were not regenerated independently. These checks establish numerical continuity, not independent statistical observations or external authentication.

The [method guide](METHOD.md) gives score definitions and inference limits. The [README](README.md) maps the evidence and reproduction commands. This English edition preserves the prior interpretation revision: historical percentage-comparison fields have no evaluative role. Original figures and frozen execution documents retain their original language.
