# H4 — Method and interpretation guide

[Report](REPORT.md) · [Evidence and reproduction](README.md) · [Frozen execution protocol, Portuguese](METHOD.pt-BR.md)

This English guide describes the published analysis. The original protocol was fixed before votes were compared with counting order and is preserved byte-for-byte because its hash is part of the execution record. It is not an external preregistration. This editorial edition adds no calculations or tests.

## Data and cohort

The unit is a polling section in one presidential round. The analysis reads the original nationwide vote and detail CSVs, checks their hashes, reconciles vote categories, and treats the rounds separately. It includes Brazil's 27 federative units (states and the Federal District) and overseas voting (`ZZ`).

Eligibility requires an installed, non-annulled section, at least 50 registered voters, positive turnout, at least 50 nominal votes, an identified polling place, and both valid timestamps. Exclusions are exclusive and applied in that order. They do not depend on a candidate's vote total. A missing candidate row may represent zero only after section/category reconciliation; a missing numeric value is not silently replaced with zero.

| Coverage | Round 1 | Round 2 |
|---|---:|---:|
| Original detail records | 499,248 | 499,248 |
| Excluded: section status | 41 | 41 |
| Excluded: fewer than 50 registered voters | 256 | 256 |
| Excluded: nonpositive turnout | 1 | 1 |
| Excluded: fewer than 50 nominal votes | 466 | 422 |
| Additional exclusions for place or timestamps | 0 | 0 |
| Eligible sections | 498,484 | 498,528 |
| Eligible nominal votes | 119,279,111 | 124,057,722 |

The cohort excludes 26,923 / 24,551 nominal votes, so its final shares can differ from the all-section national totals. [eligibility.csv](evidence/analysis/eligibility.csv) provides the state-level detail.

## Time and ties

The fields are first partial totalization and BU receipt, not a complete public update history. Seconds are truncated to the minute. All sections in a tied minute enter together, without vote-based or input-order tie-breaking. Full dates and the source's “Hora TSE” convention are retained without an unverified timezone conversion.

First totalization is primary. BU receipt uses the same cohort and paired assignments as a descriptive sensitivity, without another p-value family.

## Two conditional references

| Identifier | Grouping held fixed |
|---|---|
| `zone_size` | State + municipality + electoral zone + registered-electorate band |
| `place_size` | The same fields, with polling place added |

The electorate band is `floor(log(registered voters) / log(1.25))`. It describes section electorate, not resident population or individual demographics.

Whole section records move between fixed timestamp pairs only within their group. Candidate counts, nominal totals, and special-vote categories travel together. Group and national totals and the number of section slots per minute remain fixed. Geographic section counts are preserved at the levels included in the grouping; nominal-vote weights can vary and are recomputed.

Singleton groups remain in curves and denominators with zero residual. Informative timing support additionally requires different arrival minutes and nonconstant candidate residuals. Coverage is reported by group, candidate, round, and state; an uninformative group is not classified as natural.

The polling-place reference holds more local composition fixed but often permits comparisons across very short time spans. It can exclude a movement shared by all sections of a place. Comparing the references changes both conditioning and support, so it is not a causal decomposition of polling-place effects.

## Composition and residuals

For candidate `c` in group `g`, the final observed preference and section residual are:

```text
p_gc = group candidate votes / group nominal votes
r_ic = section candidate votes − p_gc × section nominal votes
```

Residuals sum to zero in each group. The composition curve accumulates the predicted counts `p_gc × section nominal votes`. It uses the same final results being analyzed; it is not an independently fitted prediction or a causal counterfactual.

Descriptive current-share curves divide accumulated candidate or predicted counts by the **current accumulated nominal total**. Their residual differences therefore have a different denominator from the formal scores below. The final residual is zero by construction, not an independent confirmation.

## Scores

Let `N` be the cohort's final nominal total and `x_i` the centered midpoint rank of the section's minute in national section-count progress. All ties share the same rank:

```text
x_i = (sections before the minute + sections through the minute) / (2 × cohort sections) − 0.5
G   = 100 × abs(sum(x_i × r_ic)) / N
C   = 100 × max_minute abs(cumulative residual) / N
M   = 100 × max_minute abs(residual arriving in that minute) / N
```

G measures gradual association; its signed version distinguishes relatively early from late positive residuals. It is a normalized covariance score, not a slope or start-to-finish share change. C measures a cumulative excursion, and M a one-minute contribution. C and M use percentage points of the **final** nominal total. They do not estimate artificial votes.

All minutes from the first through last arrival are considered, including empty ones. The maxima account for the search across minutes; their locations are descriptive and receive no individual-minute p-values. In round 2 the finalists exhaust nominal votes, making their residuals opposites and their absolute scores equal.

## Permutations and decisions

Each round/reference uses **4,999 assignments**, with NumPy/PCG64 and deterministic streams from `SeedSequence([20261028, round, model_id], spawn_key=(rep,))`. Model IDs are 0 for zone and 1 for polling place; `rep` runs from 0 to 4,998. All candidates and both timestamp sources share each complete-section assignment.

Primary upper-tail p-values compare absolute scores using `(1 + exceedances) / 5000`, with the recorded `1e-12` tolerance. Their minimum resolution is **0.0002**, never zero. Holm at 5% covers a fixed family of **90 tests**: 15 candidate/round combinations × three scores × two references. The tests are dependent; Holm does not require independence.

Possible score variability must be demonstrated or resolved by structural and exact finite checks. Proven constancy or unresolved variability is not a non-detection or evidence of naturalness; nonapplicable comparisons use p = 1 only internally to preserve the adjustment family. All 90 published primary tests have demonstrated variability.

Pointwise 2.5–97.5% simulation bands use a fixed 0–100% section-progress grid. At each positive point, the first minute reaching that progress includes all ties. The bands are conditional references, not simultaneous bands or election confidence intervals. C still examines every minute rather than just that grid.

## Descriptive alternatives and state summaries

Predefined alternatives use BU receipt, polling place without the electorate band, or a floor of 100 nominal votes. They do not generate additional formal decisions or replace the primary design. State summaries also remain descriptive, with state-final nominal denominators rather than national ones.

The complete results and support tables are linked from the [evidence guide](README.md). Rejection identifies time-order association beyond a specified reference, not its cause. Non-rejection cannot exclude movements conditioned out of that reference, and hashes establish internal continuity rather than independent source authenticity.
