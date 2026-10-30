# H1 — Do the vote counts balance?

[Hypothesis index](../README.md) · [Method](METHOD.md) · [Evidence and reproduction](README.md)

**Answer:** the supplied files contain no votes above turnout, turnout above the registered electorate, or duplicate record keys. Vote categories also reconcile between the two sources and sum to turnout. One additional accounting relationship has an unresolved exception: **41 overseas sections in each round record registered voters but neither turnout nor abstentions**.

These are the same 41 physical sections in both rounds. They were marked as not installed and had no votes. The exception concerns **423 registered voters per round**, not votes assigned to a candidate.

## Question and assessment

**Hypothesis:** some polling sections contain votes above turnout, turnout above the registered electorate, or duplicate records. **Identification difficulty: low.**

**Assessment: 1/10 — predominantly refuted, with an additional accounting qualification.** Scale: **0 — Fully refuted → 10 — Fully confirmed**. None of the three core signals appeared. The additional electorate identity remains unresolved for the sections above, so the broader accounting assessment is not zero.

The score is a qualitative summary of these findings, not a probability of manipulation or a proportion of inconsistent records. See the [assessment scale](../README.md#assessment-scale).

## What was checked

The audit examined both presidential rounds, all 27 domestic federative units, and overseas voting (`ZZ`). It read the two original nationwide CSVs directly and compared exact counts for every eligible section; there was no sampling or statistical significance test.

| Coverage | Round 1 | Round 2 |
|---|---:|---:|
| Section-detail records | 499,248 | 499,248 |
| Sections with vote records | 499,206 | 499,205 |
| Detail records without vote records | 42 | 43 |
| Vote sections without a matching detail record | 0 | 0 |

Duplicate keys were checked before aggregation. A section appearing in both rounds is not a duplicate. Missing quantities were kept distinct from zero.

## Results

| Accounting signal | Round 1 | Round 2 |
|---|---:|---:|
| Votes above turnout | 0 | 0 |
| Turnout above the registered electorate | 0 | 0 |
| Duplicate detail keys | 0 | 0 |
| Duplicate section/candidate-or-vote-category keys | 0 | 0 |
| Vote-category mismatches between sources | 0 | 0 |
| Vote totals different from turnout | 0 | 0 |
| Registered electorate different from turnout plus abstentions | **41** | **41** |

The reconciliation covers all 499,248 section-detail records per round, including zero-vote records without corresponding vote lines. No eligible comparison was unavailable. Full denominators and the overlapping check categories appear in [checks.csv](evidence/accounting/checks.csv).

| National quantity | Round 1 | Round 2 |
|---|---:|---:|
| Registered electorate | 158,745,502 | 158,745,502 |
| Turnout and total votes | 125,275,835 | 128,236,074 |
| Recorded abstentions | 33,469,244 | 30,509,005 |
| Electorate minus turnout and abstentions | **423** | **423** |

### What the overseas exception means

All 41 exceptional sections per round were marked **not installed**. Their turnout, abstentions, and every vote category were zero. This status provides context, but the source layout does not explicitly explain the convention for recording their abstentions. The audit therefore preserves the exception rather than adding abstentions to close the balance.

The violation file contains **164 rows**, because the same exception is listed under both the general identity check and the check restricted to uninstalled sections. Those rows represent **82 section-round occurrences involving 41 physical sections**, not 164 separate sections.

The other detail-only records—one in round 1 and two in round 2—were installed overseas sections with full recorded abstention. Their electorate identity balances; they are not additional exceptions. The complete records are in [zero-vote-details-only.csv](evidence/accounting/zero-vote-details-only.csv) and [violations.csv](evidence/accounting/violations.csv).

## Interpretation and limits

The files pass the core accounting checks across both rounds. The additional exception is confined to uninstalled overseas sections without votes; it does not identify votes added to any candidate. Its recording convention remains unconfirmed by an external source.

This establishes internal consistency for the relationships checked. It does not independently authenticate the files, compare them with authenticated ballot reports, or detect a coordinated alteration that preserves all accounting relationships.

The published independent implementation agreed in **4,478 exact comparisons**, and **20 implementation tests passed**. These are validation checks, not independent observations about election behavior. The [method](METHOD.md) explains the checks; the [reproduction guide](README.md) links the evidence and commands.
