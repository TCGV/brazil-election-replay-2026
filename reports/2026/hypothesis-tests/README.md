# Stage 3 — Hypothesis tests

**English (US)** · [Português (Brasil)](README.pt-BR.md) · [Study stages](../README.md)

Each hypothesis has its own folder containing a primary Markdown report, analysis code, tests, and evidence. Hypotheses are evaluated one at a time. A result may identify an inconsistency, find no signal under the stated checks, or remain inconclusive; refutation is not assumed in advance.

| ID | Hypothesis | Identification difficulty | Status |
|---|---|---|---|
| **H1** | Inconsistencies between votes, turnout, and registered electorate; duplicate records | Low | [Completed, with documented accounting exceptions](01-accounting-integrity/REPORT.pt-BR.md) |
| **H2** | Atypical combinations of turnout and candidate concentration in comparable sections | Medium | [Completed: local screening and association benchmark](02-turnout-concentration/REPORT.pt-BR.md) |
| H3 | Excessive repetition of complete section results | Medium | Not started |
| H4 | Counting trends unexplained by section composition, including subtle, gradual residual drift | High | Not started |
| H5 | Exceptionally concentrated changes in particular sections between rounds | High | Not started |
| H6 | Exceptional association between increased turnout and a finalist's gains | High | Not started |
| H7 | Inter-round vote redistribution with implausible regularities or discontinuities | Very high | Not started |

Difficulty means the effort needed to identify and interpret a signal from the available data. It does not estimate the likelihood of manipulation. Internal consistency does not independently authenticate the source files or establish individual voter transitions.

Start with the [H1 report in Portuguese](01-accounting-integrity/REPORT.pt-BR.md). Its [reproduction instructions](01-accounting-integrity/README.md) require only Python's standard library and the two original nationwide CSVs; neither a previously generated replay database nor the stage 2 numerical libraries are required.

The [H2 report](02-turnout-concentration/REPORT.pt-BR.md) adds comparisons within municipality, electoral zone, and section-electorate bands, across all candidates in both rounds. Its [protocol](02-turnout-concentration/METHOD.pt-BR.md) distinguishes descriptive cases from a formal conditional-independence benchmark. H2 uses NumPy and Matplotlib, reports incomplete peer coverage, and does not equate statistical association with manipulation. Hypotheses 3–7 have not been analyzed.
