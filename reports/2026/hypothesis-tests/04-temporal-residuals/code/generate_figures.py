#!/usr/bin/env python3
"""Scientific H4 figures from completed, hash-checked numerical evidence."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR', str(HERE / '.work' / 'mplconfig'))
os.environ.setdefault('XDG_CACHE_HOME', str(HERE / '.work' / 'cache'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np

COLORS = {13: '#c62828', 22: '#1565c0'}
NAMES = {13: 'Lula', 22: 'Flávio Bolsonaro'}
MODELS = ('zone_size', 'place_size')
MODEL_NAMES = {'zone_size': 'Zona + porte da seção', 'place_size': 'Local + porte da seção'}
STAT_NAMES = {'G': 'G · associação gradual', 'C': 'C · excursão acumulada', 'M': 'M · maior lote de um minuto'}
DARK = '#37474f'
GRAY = '#8c969e'
PALE = '#e3e7ea'
TEAL = '#287b77'


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read_csv(path):
    opener = gzip.open if Path(path).suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def number(value, places=4):
    return f'{float(value):.{places}f}'.replace('.', ',')


def integer(value):
    return f'{int(value):,}'.replace(',', '.')


def style(ax, grid='y'):
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis=grid, color=PALE, linewidth=.8)
    ax.set_axisbelow(True)


def save(fig, output, stem):
    paths = []
    for extension in ('png', 'svg'):
        path = output / f'{stem}.{extension}'
        fig.savefig(path, dpi=180, facecolor='white', bbox_inches='tight',
                    metadata={'Creator': 'Brazil election replay — H4'})
        if extension == 'svg':
            text = path.read_text(encoding='utf-8')
            path.write_text('\n'.join(line.rstrip() for line in text.splitlines()) + '\n', encoding='utf-8')
        paths.append(path)
    plt.close(fig)
    return paths


def select(rows, **criteria):
    result = [row for row in rows if all(str(row[key]) == str(value) for key, value in criteria.items())]
    if not result:
        raise ValueError(f'No figure evidence for {criteria}')
    return result


def curve_xy(rows, field):
    rows = sorted(rows, key=lambda row: row['minute'])
    final_sections = max(int(row['sections_cumulative']) for row in rows)
    return (np.array([100 * int(row['sections_cumulative']) / final_sections for row in rows]),
            np.array([float(row[field]) for row in rows]))


def candidate_legend(composition=False):
    handles = [Line2D([0], [0], color=COLORS[candidate], lw=2, label=NAMES[candidate])
               for candidate in (13, 22)]
    if composition:
        handles += [Line2D([0], [0], color=DARK, lw=1.8, label='Votação observada'),
                    Line2D([0], [0], color=DARK, lw=1.8, ls='--', label='Composição final dos grupos')]
    return handles


def composition_figure(curves, output):
    fig, axes = plt.subplots(2, 2, figsize=(12.7, 8.5), sharex=True, sharey='row')
    for row_index, turn in enumerate((1, 2)):
        for column_index, model in enumerate(MODELS):
            ax = axes[row_index, column_index]
            for candidate in (13, 22):
                data = select(curves, turno=turn, model=model, source='first_time', candidate=candidate)
                x, actual = curve_xy(data, 'share')
                _, composition = curve_xy(data, 'composition_share')
                ax.plot(x, actual, color=COLORS[candidate], lw=1.8)
                ax.plot(x, composition, color=COLORS[candidate], lw=1.5, ls='--', alpha=.85)
            ax.set_title(f'{turn}º turno · {MODEL_NAMES[model]}', loc='left', fontsize=11, pad=9)
            ax.set_xlim(0, 100)
            ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: number(value, 0)))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
            style(ax)
            if column_index == 0:
                ax.set_ylabel('Participação nos votos nominais acumulados (%)')
            if row_index == 1:
                ax.set_xlabel('Seções da coorte contabilizadas (%)')
    fig.suptitle('Curvas observadas e composição das seções que chegam', x=.08, ha='left', fontsize=16, y=.99)
    fig.legend(handles=candidate_legend(True), loc='lower center', bbox_to_anchor=(.53, .075),
               ncol=4, frameon=False, fontsize=9)
    fig.text(.08, .012,
             'Primeira totalização; todos os empates de minuto são mantidos. Os dois modelos usam a mesma coorte.\n'
             'A composição usa a votação final dos próprios grupos; é decomposição retrospectiva, sem identificação causal.',
             fontsize=8.5, color='#515c65')
    fig.subplots_adjust(left=.08, right=.985, top=.91, bottom=.18, hspace=.25, wspace=.21)
    return save(fig, output, 'observed-composition')


def residual_figure(curves, bands, output):
    fig, axes = plt.subplots(2, 2, figsize=(12.7, 8.5), sharex=True, sharey='row')
    for row_index, turn in enumerate((1, 2)):
        for column_index, model in enumerate(MODELS):
            ax = axes[row_index, column_index]
            for candidate in (13, 22):
                data = select(curves, turno=turn, model=model, source='first_time', candidate=candidate)
                x, residual = curve_xy(data, 'residual_final_pp')
                reference = sorted(select(bands, turno=turn, model=model, source='first_time', candidate=candidate),
                                   key=lambda row: int(row['stage']))
                # Progress is derived from the fixed cutoffs through the full curves,
                # avoiding any ambiguity between fraction and percentage metadata.
                section_total = max(int(row['sections_cumulative']) for row in data)
                by_minute = {row['minute']: row for row in data}
                bx = np.array([0.0 if int(row['stage']) == 0 else
                               100 * int(by_minute[row['cutoff_minute']]['sections_cumulative']) / section_total
                               for row in reference])
                lo = np.array([float(row['simulation_q025']) for row in reference])
                hi = np.array([float(row['simulation_q975']) for row in reference])
                ax.fill_between(bx, lo, hi, color=COLORS[candidate], alpha=.15, linewidth=0)
                ax.plot(x, residual, color=COLORS[candidate], lw=1.8)
            ax.axhline(0, color=GRAY, lw=.8, zorder=0)
            ax.set_xlim(0, 100)
            ax.set_title(f'{turn}º turno · {MODEL_NAMES[model]}', loc='left', fontsize=11, pad=9)
            ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: number(value, 3)))
            style(ax)
            if column_index == 0:
                ax.set_ylabel('Resíduo acumulado / nominal final (p.p.)')
            if row_index == 1:
                ax.set_xlabel('Seções da coorte contabilizadas (%)')
    handles = candidate_legend() + [Patch(facecolor=GRAY, alpha=.25, label='Referência: quantis 2,5–97,5% ponto a ponto')]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.53, .075), ncol=3, frameon=False, fontsize=9)
    fig.suptitle('Quanto da evolução permanece após considerar a composição?',
                 x=.08, ha='left', fontsize=16, y=.99)
    fig.text(.08, .012,
             'Linhas: todos os minutos da primeira totalização. Envelopes: grade fixa de 0%, 1%, …, 100%, incluindo empates.\n'
             'Os envelopes não são bandas simultâneas nem intervalos de confiança; as decisões usam os testes completos com Holm.',
             fontsize=8.5, color='#515c65')
    fig.subplots_adjust(left=.08, right=.985, top=.91, bottom=.18, hspace=.25, wspace=.21)
    return save(fig, output, 'conditional-residuals')


def test_figure(tests, output):
    fig, axes = plt.subplots(2, 3, figsize=(14.1, 8.6))
    labels = ['Lula · zona', 'Lula · local', 'Flávio · zona', 'Flávio · local']
    for row_index, turn in enumerate((1, 2)):
        for column_index, statistic in enumerate(('G', 'C', 'M')):
            ax = axes[row_index, column_index]
            for y, (candidate, model) in enumerate((c, m) for c in (13, 22) for m in MODELS):
                row, = select(tests, turno=turn, candidate=candidate, model=model, statistic=statistic)
                low, high = float(row['simulation_q025']), float(row['simulation_q975'])
                observed = float(row['observed'])
                ax.hlines(y, low, high, color=COLORS[candidate], lw=5, alpha=.25)
                ax.plot([low, high], [y, y], '|', color=COLORS[candidate], ms=9, mew=1)
                ax.plot(observed, y, 'o', color=COLORS[candidate], ms=6)
                adjusted = row['p_holm']
                label = 'n/a' if adjusted == '' else f'pH={number(adjusted)}'
                ax.annotate(label, (max(high, observed), y), xytext=(5, 0), textcoords='offset points',
                            va='center', fontsize=8, color=DARK)
            ax.set_yticks(np.arange(4), labels if column_index == 0 else [''] * 4, fontsize=9)
            ax.invert_yaxis()
            ax.set_title(f'{turn}º turno · {STAT_NAMES[statistic]}', loc='left', fontsize=10.5, pad=9)
            ax.set_xlabel('Covariância normalizada' if statistic == 'G' else 'Pontos percentuais do nominal final')
            ax.set_xlim(left=0)
            right = ax.get_xlim()[1]
            ax.set_xlim(0, max(right * 1.48, 1e-8))
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: number(value, 4)))
            style(ax, 'x')
    fig.suptitle('Escores dos finalistas e referência de permutação', x=.13, ha='left', fontsize=16, y=.99)
    fig.legend(handles=[Line2D([0], [0], marker='o', color=DARK, lw=0, label='Escore observado (módulo)'),
                        Line2D([0], [0], color=GRAY, lw=5, alpha=.5, label='Quantis 2,5–97,5% dos escores simulados')],
               loc='lower center', bbox_to_anchor=(.55, .07), ncol=2, frameon=False, fontsize=9)
    fig.text(.13, .012,
             '4.999 permutações por turno/modelo; pH = valor-p com Holm na família fixa dos 90 testes de todas as candidaturas.\n'
             'G não é a variação de participação entre início e fim. Associação residual com a ordem não estabelece uma causa artificial.',
             fontsize=8.5, color='#515c65')
    fig.subplots_adjust(left=.13, right=.985, top=.91, bottom=.19, hspace=.35, wspace=.17)
    return save(fig, output, 'temporal-test-reference')


def support_figure(coverage, output):
    fig, axes = plt.subplots(1, 2, figsize=(12.3, 6.0), sharey=True)
    labels = ['Coorte', 'Em estratos\ncom pares', 'Em estratos com\nminutos distintos']
    for turn, ax in zip((1, 2), axes):
        for model, offset, color in [('zone_size', -.18, GRAY), ('place_size', .18, TEAL)]:
            row, = select(coverage, turno=turn, model=model, source='first_time', candidate=13, uf='BR')
            counts = [int(row[field]) for field in ('cohort_sections', 'sections_with_peers', 'sections_time_varied')]
            x = np.arange(3) + offset
            ax.bar(x, counts, width=.33, color=color)
            for position, count in zip(x, counts):
                ax.annotate(integer(count), (position, count), xytext=(0, 5), textcoords='offset points',
                            ha='center', fontsize=8.3, rotation=0, color=DARK)
        ax.set_title(f'{turn}º turno · primeira totalização', loc='left', fontsize=11, pad=12)
        ax.set_xticks(np.arange(3), labels, fontsize=9)
        ax.set_ylim(0, ax.get_ylim()[1] * 1.15)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: integer(value)))
        style(ax)
    axes[0].set_ylabel('Seções')
    fig.suptitle('Suporte temporal das duas referências locais', x=.085, ha='left', fontsize=16, y=.99)
    fig.legend(handles=[Patch(facecolor=GRAY, label=MODEL_NAMES['zone_size']),
                        Patch(facecolor=TEAL, label=MODEL_NAMES['place_size'])],
               loc='lower center', bbox_to_anchor=(.53, .105), ncol=2, frameon=False, fontsize=9)
    fig.text(.085, .018,
             'Contagens estruturais independem da candidatura. Minutos distintos são condição necessária, mas não suficiente,\n'
             'para informação por candidato; muitos locais transmitem em lotes. A cobertura específica está em coverage.csv.',
             fontsize=8.5, color='#515c65')
    fig.subplots_adjust(left=.085, right=.985, top=.86, bottom=.25, wspace=.18)
    return save(fig, output, 'temporal-reference-support')


def generate(analysis, output):
    analysis, output = Path(analysis), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Refusing nonempty figure output directory')
    manifest = json.loads((analysis / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status') != 'completed':
        raise ValueError('A completed H4 analysis is required')
    paths = [analysis / name for name in ('curves.csv.gz', 'bands.csv', 'tests.csv', 'coverage.csv')]
    for path in paths:
        if not path.is_file() or manifest['artifacts'].get(path.name, {}).get('sha256') != digest(path):
            raise ValueError(f'Analysis table missing or hash mismatch: {path.name}')
    curves, bands, tests, coverage = map(read_csv, paths)
    expected = {(model, turn, candidate, statistic) for model in MODELS
                for turn, candidates in [(1, [13,14,16,21,22,27,28,29,30,35,55,70,80]), (2, [13,22])]
                for candidate in candidates for statistic in ('G', 'C', 'M')}
    keys = {(row['model'], int(row['turno']), int(row['candidate']), row['statistic']) for row in tests}
    if len(tests) != 90 or keys != expected:
        raise ValueError('The fixed 90-test H4 family is incomplete or repeated')
    for row in tests:
        if int(row['simulations']) != 4999:
            raise ValueError('Published H4 figures require the specified 4,999 permutations')
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.labelcolor': DARK, 'text.color': '#263238',
                         'xtick.color': '#515c65', 'ytick.color': '#515c65',
                         'svg.fonttype': 'none', 'svg.hashsalt': 'election-replay-h4'})
    figures = []
    figures += composition_figure(curves, output)
    figures += residual_figure(curves, bands, output)
    figures += test_figure(tests, output)
    figures += support_figure(coverage, output)
    result = dict(status='completed', created_at_utc=datetime.now(timezone.utc).isoformat(),
                  generator_sha256=digest(Path(__file__)),
                  analysis_manifest_sha256=digest(analysis / 'manifest.json'),
                  inputs=[dict(path=path.name, sha256=digest(path), size_bytes=path.stat().st_size) for path in paths],
                  figures=[dict(path=path.name, sha256=digest(path), size_bytes=path.stat().st_size) for path in figures],
                  scope='Finalists shown for readability; all 15 candidate/round combinations remain in the fixed 90-test family.',
                  interpretation='Conditional statistical references; no inference of manipulation or independent source authenticity.')
    (output / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis-dir', type=Path, default=HERE / 'evidence' / 'analysis')
    parser.add_argument('--output', type=Path, default=HERE / 'figures')
    args = parser.parse_args()
    result = generate(args.analysis_dir, args.output)
    print(f'Generated {len(result["figures"])} figure files; input and output hashes recorded')


if __name__ == '__main__':
    main()
