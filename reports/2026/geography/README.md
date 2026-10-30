# Stage 2 — Counting composition

[Main report](REPORT.md) · [Method](METHOD.md) · [Study stages](../README.md) · [Project README](../../../README.md)

Start with the English main report for the regional, state, capital, municipality-size, and São Paulo findings. It is the current reading edition. The original [Portuguese report](REPORT.pt-BR.md), [PDF](REPORT.pt-BR.pdf), [HTML](report.html), and figure labels are preserved as historical publication artifacts; they have not been regenerated for this editorial revision.

## Evidence guide

| Evidence | Contents |
|---|---|
| [national-milestones.csv](national-milestones.csv) | Brazil and SP candidate shares, progress, and Northeast representation |
| [uf-milestones.csv](uf-milestones.csv) | Every state's own milestones, both candidates, and denominators |
| [milestone-composition.csv](milestone-composition.csv) | Regions, states, capital status, and size at national milestones |
| [timing-summary.csv](timing-summary.csv) | Group timing, including capital/noncapital comparisons within states |
| [clock-completion.csv](clock-completion.csv) | Coverage and shares at fixed recorded clock times |
| [geographic-minute.csv](geographic-minute.csv) | Complete regional and state minute series |
| [composition-decomposition.csv](composition-decomposition.csv) | Between-group and within-group accounting components |
| [sp-municipality-contributions.csv](sp-municipality-contributions.csv) | SP municipal weights and centered contributions |
| [municipality-controls.json](municipality-controls.json) and [municipality-timing.csv](municipality-timing.csv) | Equal-municipality timing associations and their inputs |
| [randomization-results.csv](randomization-results.csv) and [randomization-bands.csv](randomization-bands.csv) | All curve tests and pointwise reference envelopes |
| [analysis-manifest.json](analysis-manifest.json) and [randomization-manifest.json](randomization-manifest.json) | Original source hashes, implementation fingerprints, scope, and settings |
| [independent-validation.json](independent-validation.json) and [randomization-validation.json](randomization-validation.json) | Original independent numerical checks and their limits |

All evidence remains tied to the supplied snapshot. The English reports reorganize existing findings; no data processing or statistical tests were rerun.

## Reproduce the original analysis

From the repository root, after completing the stage 1 replay:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt
PYTHONPATH=src python3 -m election_replay.geography_run \
  --output output/geography-step2 --randomizations 4999 --seed 20261027
```

Use a new or empty output directory. The default replay database is `output/replay/replay.sqlite`; `--replay-db` selects another completed replay. Without `--randomizations`, the workflow is descriptive only. The command reproduces the original generated Portuguese reports, not the separately edited English reading edition.

The original validation commands are:

```bash
python3 scripts/validate_geography.py --analysis-dir output/geography-step2
python3 scripts/validate_randomization.py --analysis-dir output/geography-step2
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The approximately 301 MB analysis database and private `.randomization-cache/` stay in Git-ignored `output/`. The independent randomization audit needs the retained curve caches; they can be reproduced with the same sources, implementation, seed, and permutation count. Source files are read only. Original manifests describe their execution, not the later English editorial changes.
