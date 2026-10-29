# Stage 3 — Hypothesis tests

**English (US)** · [Português (Brasil)](README.pt-BR.md) · [Study stages](../README.md)

Each hypothesis has its own folder containing a primary Markdown report, analysis code, tests, and evidence. Hypotheses are evaluated one at a time. A result may identify an inconsistency, find no signal under the stated checks, or remain inconclusive; refutation is not assumed in advance.

| ID | Hypothesis | Identification difficulty | Assessment (0–10) | Status and result |
|---|---|---|---|---|
| **H1** | Inconsistencies between votes, turnout, and registered electorate; duplicate records | Low | **1/10** | [Completed: no core signals, with electorate-identity exceptions](01-accounting-integrity/REPORT.pt-BR.md#avaliação-na-escala) |
| **H2** | Atypical combinations of turnout and candidate concentration in comparable sections | Medium | **6/10** | [Completed: partial support for statistical association, without an established artificial cause](02-turnout-concentration/REPORT.pt-BR.md#avaliação-na-escala) |
| **H3** | Excessive repetition of complete section results | Medium | **5/10 — inconclusive** | [Completed: no local detection with limited informative support](03-result-repetition/REPORT.pt-BR.md#avaliação-na-escala) |
| **H4** | Counting trends unexplained by section composition, including subtle, gradual residual drift | High | **6/10** | [Completed: partial support for residual patterns; polling-place controls attenuate deviations](04-temporal-residuals/REPORT.pt-BR.md#avaliação-na-escala) |
| **H5** | Exceptionally concentrated changes in particular sections between rounds | High | **6/10** | [Completed: local contrasts and between-place concentration; incomplete screening coverage](05-inter-round-localization/REPORT.pt-BR.md#avaliação-na-escala) |
| **H6** | Exceptional association between increased turnout and a finalist's gains | High | **6/10** | [Completed: weak positive conditional association, without an established artificial cause](06-turnout-gains/REPORT.pt-BR.md#avaliação-na-escala) |
| **H7** | Inter-round vote redistribution with implausible regularities or discontinuities | Very high | **6/10** | [Completed: no detected excess prevalence/uniformity; initial-profile contrasts detected](07-inter-round-regularity/REPORT.pt-BR.md#avaliação-na-escala) |

Difficulty means the effort needed to identify and interpret a signal from the available data. It does not estimate the likelihood of manipulation. Internal consistency does not independently authenticate the source files or establish individual voter transitions.

## Assessment scale

**0 — Fully refuted → 10 — Fully confirmed.** The score is a qualitative, ordinal summary of support for the stated statistical hypothesis, considering findings, coverage, and limitations across both rounds. It was assigned after the analyses; it is not a statistic computed by the protocols, a probability of manipulation, a share of suspicious votes, or a transformation of a p-value.

| Score | Interpretation |
|---|---|
| 0 | Fully refuted within the defined, verifiable scope |
| 1–2 | Predominantly refuted, with qualifications or bounded exceptions |
| 3–4 | Weak or inconsistent support for the hypothesis |
| 5 | Inconclusive: insufficient information to place the conclusion in either direction |
| 6–7 | Partial support for the statistical hypothesis, with material limitations |
| 8–9 | Strong support for the statistical hypothesis within the analyzed scope |
| 10 | Fully confirmed within the defined, verifiable scope |

**5 means neither a 50% probability nor positive evidence of an anomaly.** Each score requires its explanation; differences between scores have no comparable statistical magnitude and must not be added or averaged into a “risk” measure. Unevaluated hypotheses receive no score. The endpoints concern the tested hypothesis and scope, without independently authenticating the sources or establishing the cause of a pattern.

The H1 score also includes the additional identity between electorate, turnout, and abstentions: no approved core signal appeared, but that relation retains 41 exceptions per round. H2 finds the anticipated associations in some tests and persistent local contrasts, without establishing an artificial cause. H3 detects no excess under its reference, but restricted informative support prevents a conclusion about the broad hypothesis. H4 finds small gradual and cumulative signals under the polling-place reference in round 1; no signal is detected under that reference in round 2 after Holm. H5 finds two large descriptive contrasts among comparable sections and formal between-place concentration, without testing the naturalness of the marginal distribution of changes. H6 finds a weak positive association between increased turnout and relative preference change toward Lula, with four rejections after Holm; its reference neither distinguishes legitimate mobilization from an artificial cause nor identifies voter transitions. H7 detects no excess directional prevalence or uniformity under its references, but finds adjacent initial-profile contrasts; none of the raw municipal-census definitions reaches 99%, and no artificial cause is established. Each report provides its own rationale.

## Reports and reproduction

Start with the [H1 report in Portuguese](01-accounting-integrity/REPORT.pt-BR.md). Its [reproduction instructions](01-accounting-integrity/README.md) require only Python's standard library and the two original nationwide CSVs; neither a previously generated replay database nor the stage 2 numerical libraries are required.

The [H2 report](02-turnout-concentration/REPORT.pt-BR.md) adds comparisons within municipality, electoral zone, and section-electorate bands, across all candidates in both rounds. Its [protocol](02-turnout-concentration/METHOD.pt-BR.md) distinguishes descriptive cases from a formal conditional-independence benchmark. H2 uses NumPy and Matplotlib, reports incomplete peer coverage, and does not equate statistical association with manipulation.

The [H3 report](03-result-repetition/REPORT.pt-BR.md) inventories identical complete result vectors on distinct section keys, with a separate local block-pairing reference. Its [protocol](03-result-repetition/METHOD.pt-BR.md) uses exact rational moments and conservative Cantelli bounds, reports extremely limited informative support in round 1, and does not certify naturalness. Large evidence tables are supplied as compressed CSVs.

The [H4 report](04-temporal-residuals/REPORT.pt-BR.md) examines gradual trends, cumulative excursions, and abrupt minute-level contributions after conditioning on electoral zone, polling place, and section electorate. Its [protocol](04-temporal-residuals/METHOD.pt-BR.md) defines two references, 4,999 permutations per round/reference, and Holm across the fixed family of 90 tests covering all candidates. The report distinguishes magnitude, significance, and coverage without assigning an artificial cause; its [reproduction commands](04-temporal-residuals/README.md) preserve published evidence.

The [H5 report](05-inter-round-localization/REPORT.pt-BR.md) pairs the same section keys across rounds and separates changes conditional on the finalists from the effect of other candidates leaving the race. Its [protocol](05-inter-round-localization/METHOD.pt-BR.md) distinguishes local-peer screening from a between-place concentration reference, with 4,999 permutations per reference and Holm across four tests. Permutations preserve the observed changes: the test does not establish whether their nationwide count or magnitude is natural. Its [reproduction instructions](05-inter-round-localization/README.md) include complete compressed evidence.

The [H6 report](06-turnout-gains/REPORT.pt-BR.md) separates net turnout growth, vote gains, and preference changes between finalists. Its [protocol](06-turnout-gains/METHOD.pt-BR.md) defines linear and pooled-rank correlations under two baseline-controlled references, with 4,999 permutations per reference and Holm across four tests. Count balances and decomposition are arithmetic and do not attribute gains to individual voters. Its [reproduction instructions](06-turnout-gains/README.md) include every section, 14 descriptive sensitivity rows, and all 9,998 published simulation scores.

The [H7 report](07-inter-round-regularity/REPORT.pt-BR.md) distinguishes absolute gains, nominal-share gains, and relative growth in a municipal census. Its [protocol](07-inter-round-regularity/METHOD.pt-BR.md) defines section and whole-polling-place territorial-allocation references, with ten Holm-adjusted tests of prevalence, low residual dispersion, and adjacent initial-profile contrasts. The hypothetical 99% threshold uses exact denominators without a 50%/50% sign assumption. Its [reproduction instructions](07-inter-round-regularity/README.md) include complete evidence and all 9,998 simulated score sets.
