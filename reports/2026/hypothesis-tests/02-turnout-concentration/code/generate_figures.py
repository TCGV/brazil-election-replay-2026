#!/usr/bin/env python3
"""Standalone H2 scientific figures from the published evidence CSVs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR', str(HERE / '.work' / 'mplconfig'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator
import numpy as np


COLORS = {13: '#c62828', 22: '#1565c0'}
OTHER = '#737b83'
TEAL = '#287b77'
PALE = '#e1e5e8'
STATUS_COLORS = {
    'persists_both': '#287b77',
    'attenuated_one_or_both': '#d8a24b',
    'insufficient_peers': '#a8b0b8',
}
SHORT_NAMES = {
    13: 'Lula', 14: 'Renan Santos', 16: 'Hertz Dias', 21: 'Edmilson Costa',
    22: 'Flávio Bolsonaro', 27: 'Clariana Barão', 28: 'Leonardo Araújo',
    29: 'Rui Costa Pimenta', 30: 'Romeu Zema', 35: 'Wilson Grassi',
    55: 'Ronaldo Caiado', 70: 'Augusto Cury', 80: 'Samara Martins',
}


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def read_csv(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def label(candidate):
    candidate = int(candidate)
    return f'{candidate} · {SHORT_NAMES.get(candidate, str(candidate))}'


def integer(value):
    return f'{int(value):,}'.replace(',', '.')


def decimal(value, places=1):
    return f'{value:.{places}f}'.replace('.', ',')


def style_axis(ax):
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis='x', color='#e3e6e9', linewidth=.7)
    ax.set_axisbelow(True)


def save_figure(fig, output, stem):
    paths = []
    for extension in ('png', 'svg'):
        path = output / f'{stem}.{extension}'
        fig.savefig(path, dpi=180, facecolor='white', bbox_inches='tight',
                    metadata={'Creator': 'Brazil election replay — H2'})
        if extension == 'svg':
            # Matplotlib writes trailing spaces into SVG path data; trim whitespace
            # without changing the vector geometry or text.
            path.write_text('\n'.join(line.rstrip() for line in path.read_text(encoding='utf-8').splitlines()) + '\n', encoding='utf-8')
        paths.append(path)
    plt.close(fig)
    return paths


def coverage_figure(coverage, output):
    states = sorted({row['uf'] for row in coverage if row['uf'] != 'BR'})
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 11.6), sharey=True)
    for turn, ax in zip((1, 2), axes):
        rows = {row['uf']: row for row in coverage if int(row['turno']) == turn}
        percentages = []
        for uf in states:
            eligible = int(rows[uf]['eligible'])
            percentages.append(100 * int(rows[uf]['covered']) / eligible if eligible else 0)
        y = np.arange(len(states))
        ax.barh(y, percentages, color=TEAL, height=.7)
        ax.barh(y, 100 - np.array(percentages), left=percentages, color=PALE, height=.7)
        for yi, uf, percentage in zip(y, states, percentages):
            ax.text(102, yi, f'{decimal(percentage)}%', va='center', fontsize=8.5,
                    color='#3e474f')
        national = rows['BR']
        national_percent = 100 * int(national['covered']) / int(national['eligible'])
        ax.set_title(f'{turn}º turno · Brasil: {decimal(national_percent, 2)}%\n'
                     f'{integer(national["covered"])} de {integer(national["eligible"])} elegíveis',
                     fontsize=12, loc='left', pad=12)
        ax.set_xlim(0, 115)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_xlabel('Seções elegíveis (%)')
        ax.set_yticks(y, states)
        style_axis(ax)
    axes[0].invert_yaxis()
    fig.suptitle('Cobertura das comparações locais por UF', x=.09, ha='left', fontsize=17, y=.985)
    fig.legend(handles=[Patch(facecolor=TEAL, label='Com pelo menos 30 seções no estrato'),
                        Patch(facecolor=PALE, label='Sem pares suficientes')],
               loc='lower center', bbox_to_anchor=(.5, .045), ncol=2, frameon=False, fontsize=10)
    fig.text(.09, .014,
             'Estrato: município + zona eleitoral + faixa de aptos (razão 1,25). '
             'Denominador: todas as seções elegíveis de cada UF.\n'
             'ZZ = exterior. Ausência de cobertura não equivale à ausência de um padrão.',
             fontsize=9, color='#515c65')
    fig.subplots_adjust(left=.09, right=.93, top=.92, bottom=.12, wspace=.2)
    return save_figure(fig, output, 'coverage-by-uf')


def association_figure(tests, output):
    fig, axes = plt.subplots(2, 1, figsize=(12.8, 10.1),
                             gridspec_kw={'height_ratios': [4.2, 1.35]})
    for turn, ax in zip((1, 2), axes):
        rows = sorted((row for row in tests if int(row['turno']) == turn), key=lambda row: int(row['candidate']))
        y = np.arange(len(rows))
        for yi, row in zip(y, rows):
            candidate = int(row['candidate'])
            low, high = float(row['reference_low_2_5']), float(row['reference_high_97_5'])
            observed, expected = int(row['observed_joint']), float(row['expected_joint'])
            ax.hlines(yi, low, high, color='#b9c0c6', linewidth=7, zorder=1)
            ax.scatter(expected, yi, marker='D', color='#39434d', s=30, zorder=3)
            ax.scatter(observed, yi, color=COLORS.get(candidate, OTHER), edgecolor='white', linewidth=.5,
                       s=55, zorder=4)
        ax.set_yticks(y, [label(row['candidate']) for row in rows])
        for tick, row in zip(ax.get_yticklabels(), rows):
            tick.set_color(COLORS.get(int(row['candidate']), '#39434d'))
        ax.invert_yaxis()
        ax.set_ylim(len(rows) - .5, -.5)
        maximum = max([float(row['observed_joint']) for row in rows] +
                      [float(row['reference_high_97_5']) for row in rows] + [1])
        ax.set_xlim(0, maximum * 1.08)
        ax.set_title(f'{turn}º turno', loc='left', fontsize=12, pad=9)
        ax.set_xlabel('Coincidências das caudas de 5% (seção/candidato)')
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=9))
        style_axis(ax)
    fig.suptitle('Coincidências observadas e referência de independência', x=.24, ha='left', fontsize=16, y=.985)
    fig.legend(handles=[Line2D([], [], marker='o', linestyle='', color='#39434d', markersize=7, label='Observado'),
                        Line2D([], [], marker='D', linestyle='', color='#39434d', markersize=6, label='Esperado'),
                        Line2D([], [], color='#b9c0c6', linewidth=7, label='Faixa simulada de 2,5% a 97,5%')],
               loc='lower center', bbox_to_anchor=(.59, .052), ncol=3, frameon=False, fontsize=9.5)
    fig.text(.24, .014,
             '19.999 realizações, preservando as margens de cada estrato. '
             'A faixa representa o total de coincidências sob a referência.\n'
             'Independência condicional não é uma definição de voto natural; '
             'a faixa não é um intervalo de confiança da eleição.', fontsize=8.8, color='#515c65')
    fig.subplots_adjust(left=.24, right=.97, top=.93, bottom=.16, hspace=.5)
    return save_figure(fig, output, 'association-reference')


def scatter_figure(cases, output):
    fig, axes = plt.subplots(1, 2, figsize=(13.4, 5.9), sharex=True, sharey=True)
    x = [float(row['turnout_delta_pp']) for row in cases]
    y = [float(row['share_delta_pp']) for row in cases]
    x_min, x_max = min([0, *x]), max([5, *x])
    y_min, y_max = min([0, *y]), max([10, *y])
    x_pad = max(1, (x_max - x_min) * .05)
    y_pad = max(1, (y_max - y_min) * .05)
    for turn, ax in zip((1, 2), axes):
        rows = [row for row in cases if int(row['turno']) == turn]
        for candidate in (None, 13, 22):
            selected = [row for row in rows if (int(row['candidate']) not in COLORS if candidate is None else int(row['candidate']) == candidate)]
            ax.scatter([float(row['turnout_delta_pp']) for row in selected],
                       [float(row['share_delta_pp']) for row in selected],
                       color=OTHER if candidate is None else COLORS[candidate],
                       s=11 if candidate is None else 15, alpha=.4, linewidths=0)
        ax.axvline(5, color='#39434d', linestyle='--', linewidth=1)
        ax.axhline(10, color='#39434d', linestyle='--', linewidth=1)
        ax.set_title(f'{turn}º turno · {integer(len(rows))} coincidências', fontsize=12, loc='left')
        ax.set_xlim(x_min - x_pad, x_max + x_pad)
        ax.set_ylim(y_min - y_pad, y_max + y_pad)
        ax.set_xlabel('Comparecimento acima da mediana do estrato (p.p.)')
        ax.grid(color='#e5e8eb', linewidth=.7)
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].set_ylabel('Votação do candidato acima da mediana (p.p.)')
    fig.suptitle('Magnitude das coincidências de comparecimento e votação altos',
                 x=.08, ha='left', fontsize=16, y=.985)
    fig.legend(handles=[Line2D([], [], marker='o', linestyle='', color=COLORS[13], label='13 · Lula'),
                        Line2D([], [], marker='o', linestyle='', color=COLORS[22], label='22 · Flávio Bolsonaro'),
                        Line2D([], [], marker='o', linestyle='', color=OTHER, label='Demais candidatos'),
                        Line2D([], [], color='#39434d', linestyle='--', label='Cortes de 5 e 10 p.p.')],
               loc='lower center', bbox_to_anchor=(.5, .066), ncol=4, frameon=False, fontsize=9)
    fig.text(.08, .014,
             'Todos os casos das duas caudas de 5%, sem recorte dos extremos. '
             'Cada ponto é uma combinação seção/candidato.\n'
             'Prioridade exige ambos os cortes de magnitude; a triagem não atribui origem artificial aos votos.',
             fontsize=8.8, color='#515c65')
    fig.subplots_adjust(left=.08, right=.98, top=.9, bottom=.25, wspace=.14)
    return save_figure(fig, output, 'joint-tail-magnitudes')


def local_context_figure(tests, cases, output):
    rows = sorted(tests, key=lambda row: (int(row['turno']), int(row['candidate'])))
    statuses = list(STATUS_COLORS)
    counts = {status: [] for status in statuses}
    for row in rows:
        selected = [case for case in cases if int(case['turno']) == int(row['turno']) and
                    int(case['candidate']) == int(row['candidate']) and int(case['priority'])]
        for status in statuses:
            counts[status].append(sum(case['local_status'] == status for case in selected))
        if sum(counts[status][-1] for status in statuses) != int(row['priority_count']):
            raise ValueError('Local-context inventory does not match the priority total')
    y = np.arange(len(rows), dtype=float)
    first_second = next((i for i, row in enumerate(rows) if int(row['turno']) == 2), len(rows))
    y[first_second:] += .6
    fig, ax = plt.subplots(figsize=(12.7, 9.1))
    left = np.zeros(len(rows))
    for status in statuses:
        ax.barh(y, counts[status], left=left, color=STATUS_COLORS[status], height=.65)
        left += np.array(counts[status])
    for yi, total in zip(y, left):
        ax.text(total + max(1, left.max() * .012), yi, integer(total), va='center', fontsize=9)
    ax.set_yticks(y, [f'{row["turno"]}º · {label(row["candidate"])}' for row in rows])
    for tick, row in zip(ax.get_yticklabels(), rows):
        tick.set_color(COLORS.get(int(row['candidate']), '#39434d'))
    ax.invert_yaxis()
    ax.set_xlim(0, max(1, left.max()) * 1.13)
    ax.set_xlabel('Casos prioritários (seção/candidato)')
    ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=9))
    style_axis(ax)
    fig.suptitle('Casos prioritários: comparação com o mesmo local de votação',
                 x=.24, ha='left', fontsize=16, y=.985)
    fig.legend(handles=[Patch(facecolor=STATUS_COLORS['persists_both'], label='Mantém ambos os cortes'),
                        Patch(facecolor=STATUS_COLORS['attenuated_one_or_both'], label='Atenua pelo menos um corte'),
                        Patch(facecolor=STATUS_COLORS['insufficient_peers'], label='Menos de quatro outros pares')],
               loc='lower center', bbox_to_anchor=(.6, .065), frameon=False, ncol=1, fontsize=9)
    fig.text(.24, .014,
             'Pares elegíveis do mesmo local, com aptos entre 0,8 e 1,25 vez o valor da seção; '
             'a própria seção é excluída.\n'
             'Cortes: +5 p.p. de comparecimento e +10 p.p. de votação. '
             'As categorias são descritivas, não conclusões sobre manipulação.', fontsize=8.8, color='#515c65')
    fig.subplots_adjust(left=.24, right=.96, top=.93, bottom=.21)
    return save_figure(fig, output, 'priority-local-context')


def generate(analysis, output):
    analysis, output = Path(analysis).resolve(), Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(f'Refusing nonempty figure output: {output}')
    manifest = json.loads((analysis / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status') != 'completed':
        raise ValueError('A completed H2 analysis is required')
    inputs = ['coverage.csv', 'association-tests.csv', 'cases.csv']
    for name in inputs:
        expected = manifest['artifact_sha256'][name]
        if digest(analysis / name) != expected:
            raise ValueError(f'Analysis evidence hash mismatch: {name}')
    coverage = read_csv(analysis / 'coverage.csv')
    tests = read_csv(analysis / 'association-tests.csv')
    cases = read_csv(analysis / 'cases.csv')
    if {int(row['turno']) for row in tests} != {1, 2} or len(tests) != 15:
        raise ValueError('Expected both rounds and fifteen candidate-round comparisons')
    if {int(row['simulations']) for row in tests} != {19999}:
        raise ValueError('Figure annotations require the published 19,999-draw configuration')
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.titleweight': 'medium', 'axes.labelcolor': '#39434d',
                         'text.color': '#263238', 'xtick.color': '#515c65', 'ytick.color': '#515c65',
                         'svg.fonttype': 'none', 'svg.hashsalt': 'election-replay-h2'})
    paths = []
    paths.extend(coverage_figure(coverage, output))
    paths.extend(association_figure(tests, output))
    paths.extend(scatter_figure(cases, output))
    paths.extend(local_context_figure(tests, cases, output))
    details = dict(status='completed', created_at_utc=datetime.now(timezone.utc).isoformat(),
                   code_sha256=digest(Path(__file__)), matplotlib_version=matplotlib.__version__,
                   numpy_version=np.__version__, input_sha256={name: digest(analysis / name) for name in inputs},
                   figures=[dict(path=path.name, size_bytes=path.stat().st_size, sha256=digest(path)) for path in paths],
                   conventions={'candidate_13': COLORS[13], 'candidate_22': COLORS[22],
                                'other_candidates': OTHER, 'language': 'pt-BR',
                                'reference_band': 'Total joint count under conditional independence; not an election confidence interval'})
    (output / 'manifest.json').write_text(json.dumps(details, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis-dir', type=Path, default=HERE / 'evidence' / 'analysis')
    parser.add_argument('--output', type=Path, default=HERE / 'figures')
    args = parser.parse_args()
    result = generate(args.analysis_dir, args.output)
    print(json.dumps({'status': result['status'], 'figures': [row['path'] for row in result['figures']]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
