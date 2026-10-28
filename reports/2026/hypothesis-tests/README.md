# Stage 3 — Hypothesis tests

**English (US)** · [Português (Brasil)](README.pt-BR.md) · [Study stages](../README.md)

Each hypothesis has its own folder containing a primary Markdown report, analysis code, tests, and evidence. Hypotheses are evaluated one at a time. A result may identify an inconsistency, find no signal under the stated checks, or remain inconclusive; refutation is not assumed in advance.

| ID | Hypothesis | Identification difficulty | Assessment (0–10) | Status and result |
|---|---|---|---|---|
| **H1** | Inconsistencies between votes, turnout, and registered electorate; duplicate records | Low | **1/10** | [Completed: no core signals, with electorate-identity exceptions](01-accounting-integrity/REPORT.pt-BR.md#avaliação-na-escala) |
| **H2** | Atypical combinations of turnout and candidate concentration in comparable sections | Medium | **6/10** | [Completed: partial support for statistical association, without an established artificial cause](02-turnout-concentration/REPORT.pt-BR.md#avaliação-na-escala) |
| **H3** | Excessive repetition of complete section results | Medium | **5/10 — inconclusive** | [Completed: no local detection with limited informative support](03-result-repetition/REPORT.pt-BR.md#avaliação-na-escala) |
| H4 | Counting trends unexplained by section composition, including subtle, gradual residual drift | High | — | Not started |
| H5 | Exceptionally concentrated changes in particular sections between rounds | High | — | Not started |
| H6 | Exceptional association between increased turnout and a finalist's gains | High | — | Not started |
| H7 | Inter-round vote redistribution with implausible regularities or discontinuities | Very high | — | Not started |

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

The H1 score also includes the additional identity between electorate, turnout, and abstentions: no approved core signal appeared, but that relation retains 41 exceptions per round. H2 finds the anticipated associations in some tests and persistent local contrasts, without establishing an artificial cause. H3 detects no excess under its reference, but restricted informative support prevents a conclusion about the broad hypothesis. Each report provides its own rationale.

## Reports and reproduction

Start with the [H1 report in Portuguese](01-accounting-integrity/REPORT.pt-BR.md). Its [reproduction instructions](01-accounting-integrity/README.md) require only Python's standard library and the two original nationwide CSVs; neither a previously generated replay database nor the stage 2 numerical libraries are required.

The [H2 report](02-turnout-concentration/REPORT.pt-BR.md) adds comparisons within municipality, electoral zone, and section-electorate bands, across all candidates in both rounds. Its [protocol](02-turnout-concentration/METHOD.pt-BR.md) distinguishes descriptive cases from a formal conditional-independence benchmark. H2 uses NumPy and Matplotlib, reports incomplete peer coverage, and does not equate statistical association with manipulation.

The [H3 report](03-result-repetition/REPORT.pt-BR.md) inventories identical complete result vectors on distinct section keys, with a separate local block-pairing reference. Its [protocol](03-result-repetition/METHOD.pt-BR.md) uses exact rational moments and conservative Cantelli bounds, reports extremely limited informative support in round 1, and does not certify naturalness. Large evidence tables are supplied as compressed CSVs. Hypotheses 4–7 have not been analyzed.
