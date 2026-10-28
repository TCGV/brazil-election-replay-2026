#!/usr/bin/env python3
"""Standalone H3 figures from completed, hash-checked primary evidence."""
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
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np

TEAL = '#287b77'
GRAY = '#8c969e'
DARK = '#37474f'
AMBER = '#c58b2d'
PALE = '#e3e7ea'
VIEWS = [('eligible', 'Elegíveis'), ('small_positive', 'Pequenas positivas'),
         ('zero_activity', 'Sem atividade')]


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def read_csv(path):
    opener = gzip.open if Path(path).suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def value(row, *names):
    for name in names:
        if name in row:
            return row[name]
    raise ValueError(f'Missing figure field: {names}')


def integer(number):
    return f'{int(number):,}'.replace(',', '.')


def decimal(number, places=4):
    return f'{float(number):.{places}f}'.replace('.', ',')


def view_name(row):
    name = value(row, 'view', 'population')
    return {'all': 'all_details', 'other_positive': 'other_excluded_positive'}.get(name, name)


def style_axis(ax, grid='y'):
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis=grid, color=PALE, linewidth=.8)
    ax.set_axisbelow(True)


def save_figure(fig, output, stem):
    paths = []
    for extension in ('png', 'svg'):
        path = output / f'{stem}.{extension}'
        fig.savefig(path, dpi=180, facecolor='white', bbox_inches='tight',
                    metadata={'Creator': 'Brazil election replay — H3'})
        if extension == 'svg':
            path.write_text('\n'.join(line.rstrip() for line in path.read_text(encoding='utf-8').splitlines()) + '\n', encoding='utf-8')
        paths.append(path)
    plt.close(fig)
    return paths


def inventory_figure(inventory, output):
    indexed = {(int(row['turno']), view_name(row), row['signature_type']): row for row in inventory}
    shown = list(VIEWS)
    if any(int(indexed[(turn, 'other_excluded_positive', 'full')]['sections']) for turn in (1, 2)):
        shown.append(('other_excluded_positive', 'Outras positivas excluídas'))
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.3), sharey=True, sharex=True)
    maximum = max(int(indexed[(turn, view, kind)]['collision_pairs'])
                  for turn in (1, 2) for view, _ in shown for kind in ('full', 'extended'))
    for turn, ax in zip((1, 2), axes):
        y = np.arange(len(shown), dtype=float)
        for kind, shift, color in [('full', -.17, TEAL), ('extended', .17, GRAY)]:
            pairs = [int(indexed[(turn, view, kind)]['collision_pairs']) for view, _ in shown]
            ax.barh(y + shift, pairs, height=.3, color=color)
            for position, number in zip(y + shift, pairs):
                ax.annotate(integer(number), (number, position), xytext=(5, 0),
                            textcoords='offset points', va='center', fontsize=9, color=DARK)
        ax.set_title(f'{turn}º turno · {13 if turn == 1 else 2} candidaturas nominais', fontsize=12, loc='left', pad=12)
        ax.set_yticks(y, [label for _, label in shown])
        ax.set_xscale('symlog', linthresh=1)
        ax.set_xlim(0, max(12, maximum * 3.5))
        ax.set_xticks([0, 1, 10, 100, 1000, 10000, 100000])
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: integer(x)))
        ax.set_xlabel('Pares de seções com resultados iguais\n(escala linear até 1; logarítmica acima de 1)')
        style_axis(ax, 'x')
    axes[0].invert_yaxis()
    fig.suptitle('Inventário nacional de assinaturas repetidas', x=.15, ha='left', fontsize=16, y=.985)
    fig.legend(handles=[Patch(facecolor=TEAL, label='Completa: votos e comparecimento'),
                        Patch(facecolor=GRAY, label='Estendida: acrescenta aptos e abstenções')],
               loc='lower center', bbox_to_anchor=(.54, .09), ncol=2, frameon=False, fontsize=9)
    fig.text(.15, .018,
             'Cada grupo de m seções gera m(m−1)/2 pares; pares se sobrepõem e não representam votos adicionais.\n'
             'A assinatura tem dimensões diferentes entre turnos. Contagens maiores não demonstram origem artificial.',
             color='#515c65', fontsize=8.5)
    fig.subplots_adjust(left=.15, right=.96, top=.86, bottom=.3, wspace=.17)
    return save_figure(fig, output, 'repetition-inventory')


def coverage_figure(tests, output):
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 6.1), sharey=True)
    labels = ['Elegíveis', 'Em estratos\ncom ≥2 seções', 'Em estratos\ncom variância >0']
    for turn, ax in zip((1, 2), axes):
        row = next(row for row in tests if int(row['turno']) == turn)
        n = int(value(row, 'sections', 'n_sections'))
        pair_sections = int(value(row, 'nonsingleton_sections', 'pair_sections'))
        informative = int(row['informative_sections'])
        counts = [n, pair_sections, informative]
        ax.bar(np.arange(3), [max(number, .5) for number in counts], color=[GRAY, TEAL, AMBER], width=.58)
        for x, number in enumerate(counts):
            ax.annotate(integer(number), (x, max(number, .5)), xytext=(0, 6),
                        textcoords='offset points', ha='center', fontsize=10, color=DARK)
        percent = 100 * informative / n if n else 0
        ax.set_title(f'{turn}º turno · suporte informativo: {decimal(percent)}%', loc='left', fontsize=11, pad=12)
        ax.set_yscale('log')
        ax.set_ylim(.7, max(1, n) * 3.0)
        ax.set_yticks([1, 10, 100, 1000, 10000, 100000, 1000000])
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: integer(x)))
        ax.set_xticks(np.arange(3), labels, fontsize=9)
        style_axis(ax)
    axes[0].set_ylabel('Seções (escala logarítmica)')
    fig.suptitle('Quanto da referência local pode variar?', x=.085, ha='left', fontsize=16, y=.985)
    fig.text(.085, .02,
             'Estratos: UF + município + zona + total nominal exato + faixa de aptos (razão 1,25).\n'
             'Ter pares não garante variação possível. O suporte informativo não equivale ao inventário nacional completo.',
             color='#515c65', fontsize=8.7)
    fig.subplots_adjust(left=.085, right=.98, top=.86, bottom=.2, wspace=.24)
    return save_figure(fig, output, 'reference-coverage')


def conditional_figure(tests, output):
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 5.6))
    for turn, ax in zip((1, 2), axes):
        row = next(row for row in tests if int(row['turno']) == turn)
        observed = int(value(row, 'observed_pairs', 'collision_pairs', 'x'))
        expected = float(value(row, 'expected_pairs', 'expectation'))
        limit = value(row, 'p_bound', 'p_upper_bound', 'cantelli_bound')
        adjusted = value(row, 'p_holm', 'bound_holm')
        ax.bar([0, 1], [observed, expected], color=[TEAL, GRAY], width=.52)
        maximum = max(1, observed, expected)
        for x, number, text in [(0, observed, integer(observed)), (1, expected, decimal(expected))]:
            ax.annotate(text, (x, number), xytext=(0, 7), textcoords='offset points',
                        ha='center', fontsize=11, color=DARK)
        ax.set_ylim(0, maximum * 1.3)
        ax.set_xticks([0, 1], ['Observado', 'Esperança condicional'])
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6, integer=maximum > 10))
        ax.yaxis.set_major_formatter(FuncFormatter(
            (lambda number, _: integer(number)) if maximum > 10 else (lambda number, _: decimal(number, 2))))
        ax.set_title(f'{turn}º turno', loc='left', fontsize=12, pad=12)
        limit_text = 'não aplicável' if limit == '' else decimal(limit)
        adjusted_text = 'não aplicável' if adjusted == '' else decimal(adjusted)
        ax.text(.5, -.2, f'Limite de Cantelli: {limit_text}\nApós Holm: {adjusted_text}',
                transform=ax.transAxes, ha='center', fontsize=10, color=DARK)
        style_axis(ax)
    axes[0].set_ylabel('Pares com assinatura completa igual dentro dos estratos')
    fig.suptitle('Pares locais: observado e referência por blocos', x=.09, ha='left', fontsize=16, y=.985)
    fig.text(.09, .018,
             'Cantelli fornece um limite superior conservador de cauda, não um valor-p exato; não há simulação.\n'
             'Os pares nacionais entre estratos ficam fora deste teste. Não detecção não certifica naturalidade.',
             color='#515c65', fontsize=8.7)
    fig.subplots_adjust(left=.09, right=.98, top=.86, bottom=.31, wspace=.27)
    return save_figure(fig, output, 'conditional-reference')


def generate(analysis, output):
    analysis, output = Path(analysis), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Refusing nonempty figure output directory')
    manifest = json.loads((analysis / 'manifest.json').read_text())
    if manifest.get('status') != 'completed':
        raise ValueError('A completed H3 analysis is required')
    inputs = []
    for basename in ('inventory.csv', 'conditional-tests.csv'):
        path = next((path for path in (analysis / basename, analysis / (basename + '.gz')) if path.exists()), None)
        if path is None or manifest['artifact_sha256'].get(path.name) != digest(path):
            raise ValueError(f'Analysis table missing or hash mismatch: {basename}')
        inputs.append(path)
    inventory, tests = map(read_csv, inputs)
    if len(tests) != 2 or {int(row['turno']) for row in tests} != {1, 2}:
        raise ValueError('Expected the fixed two-round conditional-test family')
    expected_inventory = {(turn, view, kind) for turn in (1, 2)
                          for view in ['all_details', 'eligible', 'small_positive', 'zero_activity', 'other_excluded_positive']
                          for kind in ('full', 'extended')}
    observed_inventory = {(int(row['turno']), view_name(row), row['signature_type']) for row in inventory}
    if observed_inventory != expected_inventory or len(inventory) != len(expected_inventory):
        raise ValueError('Incomplete or repeated inventory table')
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.labelcolor': DARK, 'text.color': '#263238',
                         'xtick.color': '#515c65', 'ytick.color': '#515c65',
                         'svg.fonttype': 'none', 'svg.hashsalt': 'election-replay-h3'})
    paths = []
    paths.extend(inventory_figure(inventory, output))
    paths.extend(coverage_figure(tests, output))
    paths.extend(conditional_figure(tests, output))
    result = dict(status='completed', created_at_utc=datetime.now(timezone.utc).isoformat(),
                  code_sha256=digest(Path(__file__)), matplotlib_version=matplotlib.__version__,
                  numpy_version=np.__version__, input_sha256={path.name: digest(path) for path in inputs},
                  figures=[dict(path=path.name, size_bytes=path.stat().st_size, sha256=digest(path)) for path in paths],
                  conventions={'language': 'pt-BR', 'units': 'Unordered section-pair counts, never extra votes',
                               'formal_reference': 'Within-stratum conditional block pairing only; conservative Cantelli bound, not naturalness',
                               'inventory_scale': 'Linear to one, logarithmic above one',
                               'coverage_scale': 'Logarithmic; exact counts and percentages labeled'})
    (output / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis-dir', type=Path, default=HERE / 'evidence' / 'analysis')
    parser.add_argument('--output', type=Path, default=HERE / 'figures')
    args = parser.parse_args()
    result = generate(args.analysis_dir, args.output)
    print(json.dumps({'status': result['status'], 'figures': [row['path'] for row in result['figures']]}, ensure_ascii=False))
