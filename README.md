# Brazil Presidential Election Replay 2026

**English (US)** | [Português (Brasil)](README.pt-BR.md)

A **retrospective, approximate reconstruction** of the minute-by-minute vote count using the two nationwide CSV files in `data/`. Votes available in the source snapshot are assigned to each polling section's recorded timestamp. This does not necessarily reproduce revisions or the sequence of updates published on the TSE dashboard.

The pipeline discovers the rounds and election codes present in the files, includes overseas voting (`ZZ`), and produces two separate timelines: **first partial totalization** and **ballot report (BU) receipt**. It does not create rounds absent from the input.

## Published results

The compact results from the validated two-round run are versioned in [reports/2026/](reports/2026/):

- [Interactive report](reports/2026/replay-report.html): download the HTML file and open it in a browser. It is self-contained; GitHub's file viewer does not run the interactive page.
- [First-totalization minute CSV](reports/2026/replay-first-totalization-minute.csv) and [BU-receipt minute CSV](reports/2026/replay-bu-received-minute.csv).
- [Final totals](reports/2026/final-results.csv), [run report (Portuguese)](reports/2026/report.md), and [input manifest](reports/2026/input-manifest.json).
- Exportable charts: [round 1](reports/2026/charts/election-6257-turn-1-first_partial_totalization.svg) and [round 2](reports/2026/charts/election-6258-turn-2-first_partial_totalization.svg).

Candidate **13 (Lula) is red** and candidate **22 (Flávio Bolsonaro) is blue**, consistently across rounds, timestamp references, and chart metrics. Other candidates use a separate palette. Colors are explicitly mapped to candidate numbers; the software does not infer political affiliation.

The findings and validation evidence are summarized in [docs/results-2026.md (Portuguese)](docs/results-2026.md).

## Run locally

Requirements: Python **3.12+**, SQLite **3.39+** (bundled with Python in this environment), and Git LFS to retrieve the input files. There are no external Python packages or services to install. Run commands from the existing repository root; a Git worktree is not required.

```bash
# Initialize LFS for this checkout, then retrieve only the two required inputs:
git lfs install --local
git lfs pull --include='data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv,data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv' --exclude=''

# Generate results in a new directory, preserving previous runs:
PYTHONPATH=src python3 -m election_replay --output output/replay

# Run integration tests with small, explicitly synthetic fixtures:
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Open `output/replay/replay-report.html` in a browser to explore the curves. It is self-contained and requires no CDN or web server. The text report is `output/replay/report.md`; exportable charts are in `output/replay/charts/*.svg`.

The two input CSV files total approximately **1.92 GB**. Allow additional disk space for the LFS cache, intermediate SQLite database, and outputs. Ingestion uses batches; joins and aggregations use SQLite on disk. Charts retain at most 2,400 points per candidate/reference, while CSVs preserve **every minute**. Runtime depends on CPU and disk performance.

Use a new output directory for subsequent runs, such as `--output output/replay-02`. Nonempty directories are rejected. A failure after output creation leaves a manifest with `status: failed`; partial files are not completed results. Unresolved LFS pointers are rejected before output generation.

Additional options:

```bash
PYTHONPATH=src python3 -m election_replay --help
PYTHONPATH=src python3 -m election_replay --year 2026 \
  --votes data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv \
  --details data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv \
  --output output/new-run
```

`--max-minutes` defaults to 600,000 minutes per election/round/reference. Exceeding the limit **aborts** the run rather than truncating the timeline. Inspect timestamps before increasing it. Use `--synthetic` to label demonstrations visually; test fixtures are not election results.

## Outputs

| File | Contents |
|---|---|
| `input-manifest.json` | Paths, sizes, SHA-256 hashes, observed extraction dates, scope, status, and checks |
| `report.md` | Run summary, coverage, totals, and limitations |
| `replay-report.html`, `charts/*.svg` | Interactive visualization and exports by election/round/reference |
| `replay-first-totalization-minute.csv` | Timeline based on first partial totalization |
| `replay-bu-received-minute.csv` | Timeline based on BU receipt |
| `final-results.csv` | Totals by election/round/candidate or vote category, including `ZZ` when present |
| `final-results-uf.csv`, `final-results-municipality.csv`, `final-results-section.csv` | The same totals by state, municipality, and polling section |
| `untimed-votes.csv` | Votes outside each timeline: missing detail, duplicate detail, missing or invalid timestamp |
| `data-quality.csv`, `section-coverage.csv` | Coverage and join diagnostics |
| `duplicate-details.csv`, `vote-aggregation.csv`, `candidate-names.csv` | Duplicates, aggregated vote rows, and name variants |
| `reconciliation.csv` | Internal differences between vote rows and detail totals by category |
| `section-exceptions.csv` | Timestamp issues, exceptional circumstances, missing flags, and auxiliary inconsistencies |
| `timestamp-latency.csv` | Interval from receipt to first totalization; not public-release latency |
| `replay.sqlite` | Persistent intermediate database for auditing and further queries |

Generated runs stay in Git-ignored `output/`. Selected compact artifacts from the validated run are versioned separately in `reports/2026/`; the large intermediate database and section-level exports are not included there.

Output CSVs use **UTF-8 and commas**. Input CSVs are read as **Latin-1 with semicolons**, following the local TSE layout PDFs. `election_code` maps to `CD_ELEICAO`; `turno` maps to `NR_TURNO`. Numeric location and section codes are normalized. `minute` is `YYYY-MM-DD HH:MM:00` in **Hora TSE**, without assigning an unverified UTC offset. Timeline `uf_scope=BR` denotes nationwide aggregation, not a filter on `SG_UF`.

`sections_in_minute` and `cumulative_sections` are global section counts for that election/round/reference, repeated for each candidate: **do not sum them across candidates**. `percentage_valid_votes` is the share of accumulated nominal votes **within the timeline** and excludes votes without usable timestamps. It is blank for special vote categories or when the nominal denominator is zero.

## Methodology and decisions

See [docs/decisions.md (Portuguese)](docs/decisions.md). Nationwide `BRASIL` files and state files are not concatenated with the selected nationwide presidential file, avoiding overlapping counts. Final results come from the vote file regardless of temporal matching. All duplicate detail keys are quarantined from timelines; no timestamp is chosen arbitrarily.

Vote conservation is checked for each election/round/candidate/reference: **timeline votes + votes without usable timestamps = final total**. Reconciliation only compares the two inputs. No discrepancies do not establish agreement when metrics are missing, nor do they certify the result externally.

Expected sources: [TSE — 2026 results](https://dadosabertos.tse.jus.br/dataset/resultados-2026) and the two `leiame.pdf` files in `data/`. This software does not independently certify the authenticity of the source snapshots.
