# H3 — Method guide

[Main report](REPORT.md) · [Evidence and reproduction](README.md) · [Frozen execution protocol](METHOD.pt-BR.md)

This English guide explains the published analysis. It does not replace the original, hash-recorded protocol or describe a new calculation. The protocol was fixed before H3 repetition frequencies were calculated, using the schema and coverage already known; it was not externally preregistered.

## Inputs and units

The two original nationwide CSVs are read independently of the replay database. Their hashes and totals are matched to the prior source records, and vote categories reconcile within sections. The source-key uniqueness audit applies to those same source hashes. A missing candidate row may represent zero only for an existing section and an actual candidate in that round; missing numerical quantities do not become zero.

Each round is analyzed separately. A section is identified by its state, municipality, electoral zone, and section code. Identical results on different keys are distinct from duplicate records for the same section.

## Exact-match inventory

The primary signature is the integer vector of all candidate votes, blank and null votes, party-list votes, separately recorded invalidated votes, and turnout. The extended signature adds registered electorate and abstentions. No rounded percentages or winner-only summaries are used.

A group of `m` equal signatures contributes `m*(m−1)/2` unordered pairs. These pairs overlap and are not independent events or additional votes. The inventory reports groups, members, pairs, largest multiplicity, and distributions by exact turnout.

The populations are all detail records; eligible sections; small positive-turnout sections; zero-activity sections; and other positive-turnout sections excluded by status. Eligible sections are installed, non-annulled, with at least 50 registered voters, positive turnout, and at least 50 nominal votes. Small sections fail either size floor; this is not a municipality-size category. The all-record population overlaps the others and must not be added to them.

## Restricted conditional reference

Primary strata combine round, state, municipality, electoral zone, **exact nominal-vote total**, and electorate band `floor(log(electorate)/log(1.25))`.

Each result has two blocks:

- **A:** the complete integer candidate-count vector.
- **B:** turnout and special-vote categories, attached to the fixed registration record.

The reference reassigns A as a whole within its stratum, leaving B fixed. Equal nominal totals keep the accounting coherent. The marginal frequency of each block is preserved: the analysis tests the **pairing of blocks**, rather than the marginal repetition of candidate vectors.

The statistic `X` counts equal complete pairs **within strata**, not nationwide pairs across strata. For a stratum with `n` sections, `P_A` matching pairs in A, and `P_B` in B:

```text
Expected complete matching pairs = P_A * P_B / choose(n, 2)
```

Singleton strata contribute zero. Exact rational moments account for pairs sharing a section and pairs on four distinct positions. Moments are summed across independently reassigned strata. Published implementation tests compare the formulas with independent enumeration of small examples.

## Conservative decision rule

Let `E` and `V` be the exact reference mean and variance of the total pair count. Cantelli gives the following upper bound for the upper-tail probability:

```text
bound = V / (V + (X−E)^2), if X > E
bound = 1,                 if X ≤ E
```

This is a conservative bound, **not an exact tail probability or exact p-value**. A bound near one is not a probability that the results are natural. No simulation, seed, or Monte Carlo error is involved.

The fixed family has two primary tests, one per round, with Holm adjustment at 5%. If `V=0`, the reference must satisfy `X=E` and is nonapplicable; constancy is not evidence of naturalness. Such outcomes receive 1 only internally for conservative adjustment. Stratum coverage distinguishes singleton strata, strata with pairs, and strata with positive variance.

## Predefined descriptive alternatives

The alternatives remove the electorate band; remove zone while retaining municipality and band; remove both zone and band; widen the band ratio to 1.5; or raise the nominal-vote floor to 100. All retain exact nominal total and municipality context. They report observed pairs, moments, and coverage without selecting new p-values or replacing the primary result.

## Scope and validation

The reference preserves each block's repetition. It therefore cannot rule out changes confined to one block or shared throughout a stratum. Legitimate relationships between preferences and invalid votes may also depart from the pairing reference. Approximate matches and national matches across different contexts are outside its formal scope.

The independent implementation reads the original files with its own parser and reconstructs primary signatures, members, strata, exact moments, and adjusted bounds. It does not independently recalculate the alternative sensitivity scenarios. Small artificial tests cover zero activity, exact ties, equal percentages with different counts, constant references, inserted signals, and changes that the reference conditions out.

The [original protocol](METHOD.pt-BR.md) and [original report](REPORT.pt-BR.md) remain unchanged historical records. The English report is the current reading version. Source and artifact hashes establish internal continuity, not external authentication or voter-level transitions.
