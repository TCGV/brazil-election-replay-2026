# H2 — Method and interpretation

[Main report](REPORT.md) · [Evidence and reproduction](README.md)

This English guide describes the published analysis. The [original execution protocol](METHOD.pt-BR.md), written before the H2 tail calculations, remains unchanged as historical provenance. Its hash is recorded in the [run manifest](evidence/analysis/manifest.json); it was not an external preregistration. Identification difficulty is **medium**: finding contrasts is easier than interpreting their source.

## Population and comparison groups

The two original nationwide CSVs are read directly, with source hashes checked against the reconstruction and accounting-audit manifests. Vote categories are reconciled section by section. A missing candidate row can represent zero only for an existing section after reconciliation; a missing numerical field never becomes zero.

Eligibility requires an installed, non-annulled section with at least 50 registered voters, positive turnout, and at least 50 nominal votes. Exclusions are exclusive and ordered: section status, electorate size, turnout, then nominal votes. Both rounds include overseas records where supported.

The primary stratum is state + municipality + electoral zone + registered-electorate band, with band `floor(log(electorate)/log(1.25))`. At least 30 eligible sections are required. The analysis does not silently widen a band or cross a municipality boundary to find peers. [coverage.csv](evidence/analysis/coverage.csv) reports the resulting support.

## Three distinct comparisons

| Comparison | Definition | Interpretation |
|---|---|---|
| Joint-tail inventory | Upper 5% of turnout and candidate share within the stratum | Descriptive overlap |
| Priority screen | Joint-tail case at least 5 turnout points and 10 candidate-share points above the stratum medians | Descriptive magnitude filter |
| Polling-place context | Same magnitude thresholds against at least four other eligible local peers | Persistence, attenuation, or insufficient context |

Turnout is attendance/electorate; candidate share is candidate votes/nominal votes. Upper-tail membership requires `count(values >= own value)/group size <= 1/20`. Ties are retained, not broken to fill a quota. A constant group has no upper tail. Supported strata can therefore contribute zero overlap for a particular candidate; [strata.csv](evidence/analysis/strata.csv) records the effective tails.

Primary medians include the section being screened. The closer local comparison excludes it and uses the same municipality, zone, and polling place, with peer electorates between 0.8 and 1.25 times its electorate. Neither screen supplies an individual p-value.

## Formal conditional-independence reference

For a stratum with `n` sections, `a` high-turnout sections, and `b` high-candidate-share sections, the expected overlap under independence is `a*b/n`. The test compares the total observed overlap with sums of conditional hypergeometric draws preserving those three quantities in every stratum.

The published execution uses **19,999 draws per candidate/round**, seed `20261028`, and independent `SeedSequence([seed, round, candidate])` streams. The upper-tail p-value is `(1 + draws at least as large as observed)/20,000`. Holm adjusts the fixed family of **15 candidate/round tests** at 5%. A degenerate reference is nonapplicable and uses p=1 only internally for conservative family adjustment; none occurred in this execution.

Simulated ranges describe this overlap reference, not election confidence intervals or section-level thresholds. The reference tests independence of two indicators; it does not define how a natural election must behave. Its rejection can reflect legitimate dependence within strata.

## Sensitivity and verification

Six descriptive alternatives change one primary choice: 2.5% or 10% tails; a 20-section minimum; electorate bands with ratio 1.5; a half-band shift; or at least 100 nominal votes. Together with the primary scenario, these form seven configurations. They add no formal p-values. Published tables retain coverage, overlap, priority cases, and retention among cases that remain covered.

The original independent audit reparses the source files and checks groups, exact-ratio tails, medians, cases, and local context. It regenerates all **299,985 simulated overlap counts** and verifies p-values and Holm. The six alternative sensitivity scenarios are **not independently recalculated** in that audit. The publication check separately reconstructs summaries from the validated tables. The original run passed **28 implementation tests**; these are functionality checks, not a power estimate against every possible alteration.

The full execution records remain in [evidence/](evidence/). This editorial edition changes no source data, calculations, simulation output, or numerical validation. Partial coverage, unobserved composition, and changes shared by a whole comparison group bound the conclusion. Source hashes establish internal continuity, not independent external authenticity.
