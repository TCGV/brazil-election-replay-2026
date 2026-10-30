# H1 — Method and interpretation

[Main report](REPORT.md) · [Evidence and reproduction](README.md)

This English guide describes the published accounting audit. It introduces no new calculations. The [original report](REPORT.pt-BR.md) remains a frozen execution record in Portuguese; its numerical results and the original evidence are unchanged.

## Sources and scope

The audit reads the two original nationwide 2026 CSVs for the presidential contest (`CD_CARGO=1`, electoral unit `BR`). It includes both rounds, all 27 domestic federative units, and overseas records (`ZZ`), without concatenating overlapping source files.

The sources contain 5,731,614 vote rows and 998,496 detail rows. The [execution manifest](evidence/accounting/manifest.json) records their hashes, the analysis code, environment, and declared extraction times. Hash agreement establishes continuity with the study inputs, not independent source authenticity.

## Keys, quantities, and comparisons

The section key is election code, round, state, municipality, electoral zone, polling section, and office. Vote keys additionally include `NR_VOTAVEL`, the candidate-or-vote-category code. Numeric codes are normalized as integers and state abbreviations as uppercase text.

Duplicate keys are examined before aggregation, distinguishing identical rows from repeated keys with conflicting content. Ambiguous detail records are not selected arbitrarily for reconciliation.

All checks are exhaustive and deterministic, using exact integer arithmetic. A difference of one vote is a mismatch. Checks operate at section level so that opposite errors cannot disappear in a national sum. They use no sampling, simulations, or p-values.

The vote [source layout, page 5](../../../../data/votacao_secao_2026_BR/leiame.pdf#page=5) identifies codes 95, 96, and 97 as blank, null, and annulled votes counted separately. Other positive codes are treated operationally as nominal candidate votes in this presidential dataset. This classification does not certify the legal validity of each vote. Separately counted votes enter the total once. Party-list votes are audited explicitly and must be zero for this office.

The detail [source layout, pages 4–5](../../../../data/detalhe_votacao_secao_2026/leiame.pdf#page=4) defines electorate, turnout, abstentions, and vote categories. The audit checks:

```text
nominal + blank + null + party-list + separately counted annulled votes = turnout
registered electorate = turnout + abstentions
```

Empty values, `#NULO`, `#NE`, `-1`, and `-3` are unavailable information, not zero. Invalid and negative quantities receive separate diagnostics. None occurred in the published inputs.

A detail record without vote rows is a coverage condition, not a missing numeric field: its source vote total can be compared as zero while retaining that condition in the evidence. Missing quantities are never filled with zero.

## Check catalogue

The 22 check identifiers in [checks.csv](evidence/accounting/checks.csv) cover:

| Check family | What it establishes |
|---|---|
| Completeness and nonnegativity | Detail and vote quantities are available and nonnegative |
| Electorate bounds | Turnout and abstentions do not exceed the registered electorate |
| Electorate identity | Electorate equals turnout plus abstentions, both overall and by installation status |
| Detail consistency | Installation status is known; vote categories equal turnout; presidential party-list votes are zero |
| Unique keys and coverage | No duplicate detail/vote keys; vote sections have unique details; active details have vote rows |
| Source vote totals | Source votes do not exceed turnout and equal it |
| Category reconciliation | Nominal, blank, null, and separately counted votes agree between the files |

The CSV retains each check's `universe`, `eligible`, `compared`, `violations`, and `not_comparable` counts. The checks overlap, as do national and state summaries. Their rows must not be summed as independent incidents. No eligible comparison was unavailable.

## Exception handling

The electorate-identity exception occurs in 41 uninstalled overseas sections per round. The original values are retained: 423 registered voters per round, with zero turnout, abstentions, and votes. Installation status supplies context but does not establish an externally verified exception to the identity. The analysis does not reclassify these records as abstentions.

Each section-round exception appears under the general identity and the uninstalled-section check. Consequently, 164 violation rows describe 82 section-round occurrences involving the same 41 physical sections. The `difference` sign follows the formula of the named check; `record_json` retains the source values and row reference.

## Independent validation

The primary implementation uses temporary SQLite joins. An independent implementation uses a separate original-CSV parser and in-memory dictionaries without importing primary calculations. Their comparison covers counts, denominators, totals, exceptions, source hashes, and implementation fingerprints.

The published validation records 4,478 exact comparisons without differences, covering all 22 identifiers in each of 58 national/state-round scopes. The 20 implementation tests include synthetic errors that would cancel in totals, missing data, duplicates, and altered evidence. These are integrity checks, not statistical observations or external authentication.

## Reading the result

The three original core signals—votes above turnout, turnout above electorate, and duplicate keys—were absent. The broader accounting assessment includes the additional electorate identity and therefore retains the overseas qualification.

The 1/10 assessment is a post-analysis qualitative summary under the [shared rubric](../README.md#assessment-scale). It is not a p-value conversion, a probability of manipulation, or the proportion of problematic records. Internal consistency cannot rule out changes that preserve these identities or establish the accuracy of unauthenticated source records.
