# Study decisions

[Study stages](../reports/2026/README.md) · [Hypothesis index](../reports/2026/hypothesis-tests/README.md) · [Editorial review record](editorial-review.md)

This record explains the choices behind the published analyses. Findings and detailed formulas belong in each report and method guide. The editorial review records delivery-by-delivery wording changes; this page does not duplicate those results.

## Scope and source priority

- The user's chat instructions take precedence over the attached `Election-replay-instructions.md`. The attachment supplies requirements and methodological context, not evidence that the CSV contents are authentic.
- The study proceeds from retrospective reconstruction to counting-composition analysis and then statistical hypothesis tests. Refutation is not assumed in advance; an analysis may remain inconclusive.
- Bash and Python replace the attachment's PowerShell examples. Only rounds present in the files are processed; absent rounds are not invented.
- Each hypothesis keeps its report, code, evidence, and figures together. Individual reports discuss their own findings; the central index carries cross-hypothesis status.

## Inputs and provenance

The main inputs are the nationwide `votacao_secao_2026_BR.csv` and `detalhe_votacao_secao_2026_BR.csv`. Overlapping state or `BRASIL` files are not concatenated with them. Originals are read-only, and synthetic fixtures never replace election records.

Each execution records source hashes, sizes, headers, observed extraction fields, selected scope, and status. Collection time remains unknown when not supplied; filesystem modification time is not treated as collection. Unresolved Git LFS pointers are rejected before processing.

The selected year is explicit, with 2026 as the default. Presidential role and scope fields are checked; inconsistent presidential codes/names cause failure rather than silent exclusion. Numeric location and section codes are normalized for matching, while raw name variants remain available.

Initial Git access worked while Git LFS returned `Resource not accessible by integration`. Download succeeded after the user granted the Codex GitHub App access to the repository. Both source hashes matched the versioned LFS pointers. This was an access correction, not a change of dataset or credentials.

## Reconstruction: records, time, and denominators

- The replay key includes election, round, state, municipality, zone, section, and role. Names do not identify a candidate; the candidate number does. Display-name selection is deterministic, with raw variants inventoried.
- Repeated vote rows for the same section/candidate are summed and reported. The replay does not infer whether a repetition is a source error. H1 separately checks duplicate keys before aggregation.
- Every duplicate detail key is excluded from timelines, even if its rows look identical. Final vote totals remain intact. Vote-only sections remain in final totals and outside timelines; detail-only sections add coverage information without invented votes.
- The primary timestamp is first partial totalization; BU receipt is the alternative. Generation/extraction fields are provenance, never counting events.
- Full dates and the source's “Hora TSE” clock are preserved. No UTC offset or timezone conversion is inferred. Unknown formats and explicit offsets are invalid under the documented parser rules; missing and invalid timestamps remain distinct reasons.
- A minute represents `[M, M + 1 minute)`, with its accumulated value at the minute's end. All usable minutes, including empty intervals, are exported. A section's complete vote payload enters together; no within-section interpolation is used.
- The timeline denominator is accumulated nominal votes with usable timing. Blank (`95`), null (`96`), and separate (`97`) categories are excluded. Other positive presidential candidate numbers are operationally nominal; this does not certify each vote's legal status.
- Conservation is checked separately for each election/round/candidate/reference: timeline votes plus votes without usable timing equal final votes. Missing detail metrics are not converted to zero during reconciliation.
- Receipt-to-totalization differences describe recorded intervals, not publication latency. Negative intervals remain diagnostic information rather than being silently removed.

Annulled/uninstalled sections and unusual origins are reported without automatically discarding their votes from the reconstruction. The final snapshots do not reconstruct intermediate edits, retotalizations, or the complete public-dashboard history. Internally matching hashes and totals do not independently authenticate the election records.

## Execution and presentation

SQLite, batched ingestion, and reduced plotting series keep the replay disk-based. CSVs retain every minute; charts can reduce points while preserving endpoints and block extrema. The interactive HTML is self-contained, and SVGs are exportable without an external service.

Nonempty output directories are rejected. Execution manifests distinguish completed runs from failed runs with partial outputs. Reproducible databases, large exports, caches, and scratch work remain in ignored `output/` or hypothesis-local `.work/` directories. Compact evidence is versioned for repository reading; inventories distinguish that selection from the original full run.

Candidate 13, Lula, uses red `#c62828`; candidate 22, Flávio Bolsonaro, uses blue `#1565c0`. The mapping is explicit by number across rounds, references, and measures. Other candidates use a separate palette; software does not infer political affiliation. Symmetric statistics may use neutral colors.

## Stage 2: counting composition

The geographic workflow opens the replay database read-only, checks the original source hashes, and writes a separate analysis database. Data preparation, calculations, controls, figures, and report generation remain separate modules. NumPy and Matplotlib are optional analysis dependencies; the replay itself uses the Python standard library. Optional PDF export uses Playwright/Chromium without changing calculations.

Capital status uses an explicit list matched by normalized name and state. Brasília/DF has no noncapital counterpart within the Federal District. Overseas voting remains in national analysis but outside domestic capital/size groups.

Municipality size means registered electorate from the first available round, held fixed across rounds. The published bands are up to 10,000; over 10,000–50,000; over 50,000–200,000; over 200,000–1 million; and over 1 million. No external resident-population or individual-demographic dataset was added.

National and state progress are measured by section counts, including whole tied arrivals. Geographic voting weights and candidate shares use nominal votes. Absolute clock time and relative progress answer different questions. Fixed clock cuts include events through `HH:MM:00`, whereas minute curves include that entire minute.

The composition decomposition replaces each group's current internal preference with its final preference while retaining current group weights. It is an accounting identity, not a causal explanation. Interpreted municipal contributions are centered on the final state share. Municipality-level correlations and regressions give each municipality equal weight; they differ from section-weighted summaries. Comparisons between capitals and similarly sized noncapitals have limited support.

Stage 2 uses 4,999 permutations per round/reference, seed `20261027`, and fixed progress milestones. Complete sections move between timestamp slots. The global reference permits nationwide exchange; the within-state reference preserves observed state progress. Candidate shares in round 1 are calculated separately rather than treated as complementary.

The statistic is the maximum absolute deviation from the pointwise mean of all `B + 1` realizations, including the observation, applied symmetrically to every realization. Plus-one p-values and Holm control the fixed primary family across both rounds at 5%. BU receipt reuses assignments as a sensitivity, without a second selected decision family.

Pointwise simulation envelopes are not simultaneous bands or population confidence intervals. The formal decision concerns the curve, not an isolated point outside an envelope. Non-rejection does not prove randomness or equivalence. Different rejection outcomes across rounds do not constitute a test of the difference between rounds. Permutations preserve temporal batch sizes, not every operational or geographic dependency within a batch.

## Stage 3: common rules

Protocols were fixed before the hypothesis-specific comparisons, with prior knowledge of the source schema, totals, or cohort explicitly disclosed. They are not external preregistrations. Direct source parsing and hash checks maintain continuity with earlier evidence; adaptations of previous loaders are attributed.

Eligibility, descriptive screening, formal reference tests, and sensitivity analyses remain distinct. Insufficient peer support is not classified as normality. Candidates, rounds, nested geographic summaries, and alternative references are dependent views of records, not independent incidents or voters.

Arithmetic decompositions do not identify voter transitions. Reduced abstention is a net change, not the number of new entrants: entries and exits can occur together. Geographic proxies do not identify income, age, education, or individual urban/rural characteristics. Statistical association and reference rejection do not identify an artificial cause.

Where simulated tests are used, plus-one p-values are never zero. Multiple testing is handled in the predefined family, without selecting candidates, references, tails, or time windows after inspecting results. Constant references and unresolved variability cannot be published as ordinary non-detections. Independent audits distinguish checking retained scores from independently regenerating every assignment.

## H1: accounting integrity

H1 uses exhaustive integer checks without sampling or significance tests. Duplicate keys are identified before summation, and opposite discrepancies in different sections cannot cancel. A separate parser and accumulation validate the primary implementation.

Categories include nominal, blank, null, party-list, and separate votes once each. Missing metrics stay missing; detail-only keys are compared with an empty vote vector and retain their own coverage diagnosis. The additional identity between electorate, turnout, and abstentions retains its observed exceptions rather than normalizing them away.

Those exceptions concern the same 41 uninstalled overseas sections in both rounds, with 423 registered voters per round and no recorded votes, turnout, or abstentions. Their status supplies context but does not independently resolve the recording convention. They are not additional votes or distinct electorates to sum across rounds.

## H2: turnout and candidate concentration

The primary comparison uses municipality, electoral zone, and section-electorate bands with ratio 1.25, requiring at least 30 eligible sections. Joint upper-tail membership includes conservative ties; additional magnitude thresholds define descriptive priorities, not individual-section p-values or artificial votes.

The formal conditional-independence reference preserves tail margins within strata. It uses 19,999 realizations per candidate/round, seed `20261028`, and Holm across all 15 candidate/round comparisons. Local context excludes the section itself and requires four eligible peers; persistence, attenuation, and insufficient context remain descriptive categories. The independent audit's published scope distinguishes primary screening from alternative sensitivities that were not independently recalculated.

## H3: complete-result repetition

H3 distinguishes repeated complete values on different keys from duplicate records. Full integer signatures retain all candidate and special-vote categories and turnout; an extended signature adds electorate and abstentions. Zero-activity and small positive sections remain separate inventories.

The national inventory and restricted local test answer different questions. The formal reference pairs whole candidate vectors with turnout/special-vote blocks within exact nominal totals and local electorate bands. It preserves observed candidate-vector repetitions and does not test every national coincidence. Exact rational moments support conservative one-sided Cantelli bounds, followed by Holm across the two rounds. These are not exact p-values; no simulation or seed is used. Informative support limits the broad conclusion.

## H4: residual timing

Both zone/section-size and polling-place/section-size references are evaluated. Final observed group preferences define section residuals retrospectively. Complete section payloads move among fixed pairs of first-totalization/BU timestamps; all candidates move together. Group means remain fixed, so a whole-group movement can be conditioned out.

G measures covariance with tied section-progress rank, C the maximum cumulative residual, and M the maximum one-minute contribution. Formal scores use the final cohort nominal total; descriptive current-share residuals use current accumulated nominals. G is not a conventional slope or start-to-finish gain. The analysis uses 4,999 assignments per round/reference, seed `20261028`, and Holm across 90 tests. State summaries and predefined alternatives receive no additional selected tests. Temporal reach is reported separately from the number of eligible sections.

## H5: inter-round localization

The paired cohort requires eligibility in both rounds, at least 50 first-round finalist votes, the same known polling place, and an electorate ratio within 1.25. Equal physical keys do not identify the same individual voters. Conditional finalist share separates preference change from nominal-share growth and absolute count gain; the other finalist's conditional change is exactly opposite.

Descriptive section screening excludes the section itself and requires four local peers with compatible size and initial preference. The formal analysis instead tests concentration between polling places while preserving the marginal distribution of observed changes. Complete paired records move within local strata, with and without initial-preference control. Four tests use 4,999 assignments per reference, seed `20261029`, and Holm. RMS and MAX summarize place residuals; MAX is not a z-score, and its global p-value does not belong to the maximum place individually.

A separate post-result source extraction adds names/addresses for all strict priorities and all maximum places, including ties. Its selection and later timing are documented. Such context is not evidence about the people voting or the cause of a contrast.

## H6: turnout and preference change

H6 retains the paired cohort and requires the electorate accounting identity for included records. Vote gains, changes in turnout rate, and changes in conditional finalist preference remain different measures. Symmetric decompositions are arithmetic; electorate-weighted equivalents need not equal observed count gains when registered electorate changes.

The two references condition on initial turnout, finalist preference, other-candidate participation, size, and local geography; one also fixes polling place. Linear and pooled-rank correlations use within-stratum centered measures. Exact rational ordering preserves rank ties. The rank statistic is not an average of local correlations.

Paired preference trajectories are permuted relative to fixed turnout trajectories within strata. This is a conditional association reference, not a construction of physically feasible synthetic ballot reports or a complete natural-election model. Four tests use 4,999 assignments per reference, seed `20261029`, and Holm. The complementary finalist outcome is not tested as independent evidence; regional and sensitivity summaries introduce no new formal decisions.

## H7: municipal prevalence and territorial allocation

The census separates raw municipal records from aggregates of the same paired sections. Domestic municipal codes and overseas source units have separate denominators; code counts are not independently validated against an external municipal register. Undefined measures and missing counterparts remain explicit.

Absolute gain, nominal-share gain, relative growth, and conditional finalist change are distinct definitions. Where both are defined with positive initial bases, relative-growth direction and conditional-change direction coincide exactly. They are not independent confirmations. Municipal frequencies give each municipality one vote; vote-weighted coverage describes another quantity. No 50%/50% sign expectation is assumed.

Two references allocate whole paired sections or complete polling-place blocks across municipalities within initial-composition strata. They preserve observed marginal trajectories while testing territorial allocation. Original target municipalities and profile order remain fixed. Block assignments can change municipal section counts; those totals are recomputed without reselecting targets.

Three directional-prevalence scores have upper tails; residual dispersion has a lower tail; the maximum adjacent-profile contrast has an upper tail. Adjacency follows initial preference within state, not geography or time. The contrast score is not a z-score or a causal discontinuity test, and its p-value is global. There are 4,999 assignments per reference, seed `20261029`, and ten Holm-adjusted tests. No opposite tail is added after results are seen.

The user's illustrative 99% figure has no evaluative role. Historical comparison fields remain provenance only. Observed frequencies are qualified through the specified statistical reference, without treating their magnitude alone as rarity. These allocation tests do not determine the global naturalness of the retained marginal gains or estimate campaign effects.

## Assessment scale and current documentation

The requested scale runs from **0 — Fully refuted** to **10 — Fully confirmed**, within each hypothesis's stated, verifiable scope. Scores are justified ordinal summaries assigned after the analyses, not p-value transformations, probabilities of manipulation, or fractions of suspicious votes. A score of 5 denotes an inconclusive assessment, not 50% probability. Scores are not added or averaged into risk.

Current reading documents use US English: `REPORT.md` for findings, `METHOD.md` for technical guidance, and `README.md` for navigation and reproduction. Hash-bound Portuguese protocols and original generated reports remain unchanged as historical execution records. English editorial reports are maintained separately from generators' original output formats. A future Portuguese branch is outside this editorial delivery.

Publication inventories are refreshed for edited reading documents while pre-editorial inventories remain preserved. Original numerical tables, source files, code, charts, execution manifests, and validation records are not regenerated by the textual review. No new tests are run to rescue an unsupported conclusion; its wording and downstream implications are corrected instead. See the [editorial review record](editorial-review.md) for the completed delivery checks.
