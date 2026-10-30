# Brazil Presidential Election Replay 2026

A study of the supplied public election files: reconstruct the presidential count, examine its territorial composition, and test seven accounting and statistical hypotheses. The results describe the repository's source snapshots; they do not independently authenticate the election records.

## Read the study

| Stage | Question | Report |
|---|---|---|
| 1 — Reconstruction | What minute-by-minute timeline can be recovered from final section votes and recorded timestamps? | [Reconstruction report](reports/2026/REPORT.md) |
| 2 — Counting composition | How did regions, states, capitals, and municipality size relate to the evolving vote shares? | [Composition report](reports/2026/geography/REPORT.md) |
| 3 — Hypothesis tests | Which specified accounting or statistical signals appear, and what remains unresolved? | [Seven-hypothesis index](reports/2026/hypothesis-tests/README.md) |

The main reports give the answer, supporting numbers, and material limits. Each links a method guide and the complete evidence. The [study index](reports/2026/README.md) maps the published outputs; the [editorial review](docs/editorial-review.md) records the English revisions and their separate commits.

For the original interactive replay, download [replay-report.html](reports/2026/replay-report.html) and open it in a browser. The page is self-contained; GitHub displays its source rather than running it. Its original interface labels remain in Portuguese. Candidate 13 (Lula) is red and candidate 22 (Flávio Bolsonaro) is blue, as identified in the supplied files.

## Run locally

Use **Python 3.12+**, SQLite **3.39+**, and Git LFS. The reconstruction uses the Python standard library; the later analyses add the pinned packages in [requirements-analysis.txt](requirements-analysis.txt). Run from the repository root.

```bash
# Retrieve the two original nationwide inputs.
git lfs install --local
git lfs pull --include='data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv,data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv' --exclude=''

# Reconstruct both rounds present in the sources.
PYTHONPATH=src python3 -m election_replay --output output/replay

# Inspect available options.
PYTHONPATH=src python3 -m election_replay --help
```

Open `output/replay/replay-report.html` locally. The inputs total approximately 1.92 GB; allow additional disk space for Git LFS, SQLite, and outputs. Processing uses disk-based batches. CSVs retain every minute, including empty minutes; chart display series may contain fewer points.

Choose a new output directory for each run. Nonempty directories and unresolved LFS pointers are rejected. A failed execution's partial files are not completed results. Generated runs stay in ignored `output/`; the repository includes a compact selection of published evidence.

For Stage 2, first complete the reconstruction, then install the analysis packages:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt
PYTHONPATH=src python3 -m election_replay.geography_run \
  --output output/geography-step2 --randomizations 4999 --seed 20261027
```

The [Stage 2 guide](reports/2026/geography/README.md) explains the replay database dependency and reproduction/validation commands. Hypotheses read the original CSVs directly; each folder README provides its own reproduction and validation commands. Reproduction is optional for reading the published study.

## Interpretation and provenance

- The replay assigns final section votes retrospectively to recorded times. It does not recover every public-dashboard update or intermediate correction.
- Counting progress uses sections; candidate shares use nominal votes. Round 1 includes all candidacies in that denominator. Municipality size means registered electorate, not resident population or individual demographics.
- A statistical departure concerns its stated reference. Detection does not identify manipulation; nondetection does not establish naturalness. Aggregate counts do not identify individual voter transitions.
- Hypothesis scores are ordinal assessments of the statistical question, not probabilities of manipulation or quantities that can be averaged into a risk score.

Current reading documents are maintained in US English. Original generated reports, hash-bound protocols, charts, and companion HTML/PDF files retain their original language as historical evidence. They are not a parallel current Portuguese edition. Generators still emit their original execution formats; use new output directories and preserve the curated English reports.

See the [reconstruction method](reports/2026/METHOD.md), [published validation record](docs/results-2026.md), and [study decisions](docs/decisions.md) for technical details. Source expectations and file fingerprints are documented in the original manifests; internal agreement is not external authentication.
