#!/usr/bin/env python3
"""H6 figures from completed, fingerprinted numerical evidence.

Plotting/provenance utilities are adapted from the H5 generator at repository
commit a3362b3ec72c0c567fcf80c5b6761b6cc1cc52c2. All calculations below are
display transformations of published tables, not additional hypothesis tests.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR', str(HERE / '.work' / 'mplconfig'))
os.environ.setdefault('XDG_CACHE_HOME', str(HERE / '.work' / 'cache'))

import matplotlib
matplotlib.use('Agg')
from matplotlib.colors import LogNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator
import matplotlib.pyplot as plt
import numpy as np

METHOD_SHA256 = '6a63f96ead6de3641c53cc123d7258282b506f160494fd228b257a02dba51687'
MODELS = ('zone_baseline', 'place_baseline')
MODEL_NAMES = {'zone_baseline': 'Zona + características iniciais',
               'place_baseline': 'Local + características iniciais'}
INPUTS = ('totals.csv', 'x-bins.csv', 'heatmap.csv', 'tests.csv', 'coverage.csv')
RED = '#c62828'
BLUE = '#1565c0'
DARK = '#37474f'
GRAY = '#8c969e'
TEAL = '#287b77'
PALE = '#e3e7ea'
BIN_LABELS = ['<−10', '−10 a −8', '−8 a −6', '−6 a −4', '−4 a −2', '−2 a 0',
              '0 a 2', '2 a 4', '4 a 6', '6 a 8', '8 a 10', '≥10']
BIN_EDGES = [-np.inf, *range(-10, 11, 2), np.inf]


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read_csv(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def select(rows, **criteria):
    found = [row for row in rows if all(str(row[key]) == str(value) for key, value in criteria.items())]
    if not found:
        raise ValueError(f'Missing figure evidence: {criteria}')
    return found


def number(value, places=3):
    return f'{float(value):.{places}f}'.replace('.', ',')


def integer(value):
    return f'{int(value):,}'.replace(',', '.')


def style(ax, grid='y'):
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis=grid, color=PALE, lw=.8)
    ax.set_axisbelow(True)


def save(fig, output, stem):
    paths = []
    for extension in ('png', 'svg'):
        path = output / f'{stem}.{extension}'
        fig.savefig(path, dpi=180, facecolor='white', bbox_inches='tight',
                    metadata={'Creator': 'Brazil election replay — H6'})
        if extension == 'svg':
            path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()) + '\n', encoding='utf-8')
        paths.append(path)
    plt.close(fig)
    return paths


def balance_figure(totals, output):
    row, = select(totals, scope_type='BR', scope='BR')
    gains = [int(row['v13_change']), int(row['v22_change'])]
    components = [int(row['turnout_change']), -int(row['other_nominal_change']),
                  -sum(int(row[f'{name}_change']) for name in ('blank', 'null_votes', 'legend', 'separate'))]
    if sum(gains) != sum(components) or int(row['identity_residual']) != 0:
        raise ValueError('National finalist-gain identity does not reconcile')
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 6.4), sharey=True)
    ax = axes[0]
    bars = ax.bar([0, 1], np.asarray(gains)/1e6, color=[RED, BLUE], width=.58)
    for rect, value in zip(bars, gains):
        ax.annotate(f'+{number(value/1e6, 3)} mi',
                    (rect.get_x()+rect.get_width()/2, value/1e6), xytext=(0, 7),
                    textcoords='offset points', ha='center', fontsize=11, color=DARK)
    ax.set_xticks([0, 1], ['Lula', 'Flávio Bolsonaro'])
    ax.set_title('Ganhos observados dos finalistas', loc='left', fontsize=12, pad=14)
    ax.set_ylabel('Milhões de votos/comparecimentos')
    ax = axes[1]
    labels = ['Aumento líquido\ndo comparecimento', 'Redução de votos em\noutras candidaturas', 'Redução dos votos\nnão nominais']
    colors = [DARK, TEAL, GRAY]
    bottoms = np.r_[0, np.cumsum(components[:-1])]/1e6
    for i, (value, bottom, color) in enumerate(zip(components, bottoms, colors)):
        ax.bar(0, value/1e6, bottom=bottom, width=.55, color=color, label=labels[i].replace('\n', ' '))
        ax.text(0, bottom+value/2e6, f'+{number(value/1e6, 3)} mi', color='white',
                ha='center', va='center', fontsize=10, fontweight='bold')
    total = sum(gains)
    ax.annotate(f'{number(total/1e6, 3)} mi', (0, total/1e6), xytext=(0, 7),
                textcoords='offset points', ha='center', fontsize=11, color=DARK)
    ax.set_xlim(-.75, .75)
    ax.set_xticks([0], ['Balanço do aumento\nconjunto dos finalistas'])
    ax.set_title('A mesma soma, por identidade contábil', loc='left', fontsize=12, pad=14)
    for ax in axes:
        ax.set_ylim(0, max(total/1e6, max(gains)/1e6)*1.18)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: number(value, 0)))
        style(ax)
    fig.suptitle('O aumento do comparecimento não é todo o ganho dos finalistas',
                 x=.08, y=.99, ha='left', fontsize=16)
    fig.legend(handles=[Patch(facecolor=color, label=label.replace('\n', ' '))
                        for color, label in zip(colors, labels)],
               loc='lower center', bbox_to_anchor=(.55, .12), frameon=False, ncol=1, fontsize=8.7)
    fig.text(.08, .018,
             'Totais de todas as seções dos CSVs originais, incluindo exterior; não se restringem à coorte formal.\n'
             'Balanço de contagens, não transferência de pessoas. Entradas e saídas de votantes podem ocorrer simultaneamente.\n'
             'Votos não nominais: brancos, nulos, legenda e separados, conforme categorias dos arquivos.',
             fontsize=8.5, color='#515c65')
    fig.subplots_adjust(left=.08, right=.98, top=.84, bottom=.34, wspace=.24)
    return save(fig, output, 'national-vote-balance')


def association_figure(bins, heatmap, cohort, output):
    national = sorted(select(bins, scope_type='BR', scope='BR'), key=lambda row: int(row['bin']))
    if len(national) != 12 or {int(row['bin']) for row in national} != set(range(12)):
        raise ValueError('Incomplete fixed twelve-bin turnout table')
    for row in national:
        b = int(row['bin'])
        if float(row['left_pp']) != BIN_EDGES[b] or float(row['right_pp']) != BIN_EDGES[b+1]:
            raise ValueError('Turnout-bin labels differ from the fixed boundaries')
        if int(row['sections']) < 0 or (int(row['sections']) and not row['mean_y']):
            raise ValueError('Missing mean or invalid count in a populated turnout bin')
    grid = np.zeros((12, 12), dtype=np.int64)
    keys = set()
    for row in heatmap:
        x, y = int(row['x_bin']), int(row['y_bin'])
        if not (0 <= x < 12 and 0 <= y < 12) or (x, y) in keys:
            raise ValueError('Invalid or duplicated heatmap cell')
        if any(float(row[f'{axis}_{side}_pp']) != BIN_EDGES[index+offset]
               for axis, index in [('x', x), ('y', y)]
               for side, offset in [('left', 0), ('right', 1)]):
            raise ValueError('Heatmap labels differ from the fixed boundaries')
        if int(row['sections']) < 0:
            raise ValueError('Negative section count in heatmap')
        keys.add((x, y));grid[x, y] = int(row['sections'])
    if len(keys) != 144 or int(grid.sum()) != cohort:
        raise ValueError('Heatmap does not cover the full paired cohort')
    if sum(int(row['sections']) for row in national) != cohort:
        raise ValueError('Turnout-bin table does not cover the full paired cohort')
    fig, axes = plt.subplots(1, 2, figsize=(13.8, 7.0))
    ax = axes[0]
    image = ax.imshow(np.ma.masked_equal(grid.T, 0), origin='lower', interpolation='nearest',
                      cmap='viridis', norm=LogNorm(vmin=1, vmax=max(int(grid.max()), 2)), aspect='equal')
    ax.axvline(5.5, color='#cfd8dc', ls='--', lw=.9)
    ax.axhline(5.5, color='#cfd8dc', ls='--', lw=.9)
    ax.set_xticks(range(12), BIN_LABELS, rotation=70, ha='right', fontsize=7.8)
    ax.set_yticks(range(12), BIN_LABELS, fontsize=7.8)
    ax.set_xlabel('Aumento da taxa de comparecimento (p.p.)')
    ax.set_ylabel('Mudança de Lula entre os finalistas (p.p.)')
    ax.set_title('Distribuição conjunta das seções', loc='left', fontsize=12, pad=12)
    colorbar = fig.colorbar(image, ax=ax, fraction=.048, pad=.025)
    colorbar.set_label('Seções por célula · frequência logarítmica', fontsize=8.8)
    ax = axes[1]
    means = np.array([float(row['mean_y']) if row['mean_y'] else np.nan for row in national])
    ax.plot(range(12), means, color=RED, marker='o', ms=4, lw=1.7, label='Lula · mudança condicional média')
    ax.plot(range(12), -means, color=BLUE, marker='o', ms=4, lw=1.7, label='Flávio · complemento exato')
    ax.axhline(0, color=GRAY, lw=.8)
    ax.set_xticks(range(12), BIN_LABELS, rotation=70, ha='right', fontsize=7.8)
    ax.set_xlabel('Aumento da taxa de comparecimento (p.p.)')
    ax.set_ylabel('Média simples da mudança condicional (p.p.)')
    ax.set_title('Associação bruta por faixa de comparecimento', loc='left', fontsize=12, pad=12)
    ax.legend(loc='best', fontsize=8.6, frameon=False)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: number(value, 1)))
    ax.set_xlim(-.4, 11.4)
    style(ax)
    fig.suptitle('Comparecimento e preferência variam entre os turnos',
                 x=.075, y=.99, ha='left', fontsize=16)
    fig.text(.075, .018,
             f'Coorte: {integer(cohort)} seções; peso igual por seção. Faixas de 2 p.p., com extremos abertos abaixo de −10 e a partir de +10.\n'
             'As curvas são complementares; não são dois resultados independentes. São médias agregadas, sem controle por características iniciais.\n'
             'Cada célula representa seções; branco indica zero. A medida condicional usa somente os votos dos dois finalistas em cada turno.',
             fontsize=8.5, color='#515c65')
    fig.subplots_adjust(left=.075, right=.985, top=.86, bottom=.30, wspace=.37)
    return save(fig, output, 'turnout-preference-association')


def reference_figure(tests, output):
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 6.5), sharey=True)
    applicable = [float(row['observed_abs']) for row in tests if row['observed_abs']]
    for ax, statistic in zip(axes, ('linear', 'rank')):
        largest = 0.0
        for y, model in enumerate(MODELS):
            row, = select(tests, model=model, statistic=statistic)
            if not row['observed_abs'] or not row['observed_signed']:
                ax.text(.03, y, 'Não aplicável · suporte insuficiente',
                        transform=ax.get_yaxis_transform(), va='center', fontsize=9, color=GRAY)
                continue
            lo, hi = float(row['simulation_q025_abs']), float(row['simulation_q975_abs'])
            observed = float(row['observed_abs'])
            signed = float(row['observed_signed'])
            if not (0 <= lo <= hi <= 1+1e-12 and 0 <= observed <= 1+1e-12
                    and abs(abs(signed)-observed) <= 1e-12):
                raise ValueError('Invalid observed correlation or permutation quantiles')
            color = GRAY if model == 'zone_baseline' else TEAL
            ax.hlines(y, lo, hi, color=color, lw=7, alpha=.5)
            ax.plot([lo, hi], [y, y], '|', color=color, ms=12, mew=1.2)
            ax.plot(observed, y, 'o', color=DARK, ms=7)
            p = 'n/a' if not row['p_holm'] else number(row['p_holm'], 4)
            ax.annotate(f'ρ={number(signed, 4)}\npH={p}', (max(observed, hi), y),
                        xytext=(8, 0), textcoords='offset points', va='center', fontsize=9, color=DARK)
            largest = max(largest, observed, hi)
        ax.set_yticks([0, 1], [MODEL_NAMES[model] for model in MODELS], fontsize=9)
        ax.set_ylim(1.55, -.55)
        ax.set_xlim(0, max(largest*1.65, .001))
        ax.set_title('Correlação linear' if statistic == 'linear' else 'Correlação dos postos por estrato',
                     loc='left', fontsize=12, pad=14)
        ax.set_xlabel('Módulo da correlação agrupada · |ρ|')
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: number(value, 3)))
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
        style(ax, 'x')
    fig.suptitle('Associação após considerar as características iniciais',
                 x=.245, y=.99, ha='left', fontsize=15)
    fig.legend(handles=[Line2D([0], [0], color=DARK, marker='o', lw=0, label='Módulo observado'),
                        Line2D([0], [0], color=GRAY, lw=7, alpha=.5,
                                   label='Quantis 2,5–97,5% dos módulos simulados')],
               loc='lower center', bbox_to_anchor=(.6, .145), ncol=2, frameon=False, fontsize=9)
    fig.text(.245, .018,
             (f'Módulos observados: {number(min(applicable), 4)} a {number(max(applicable), 4)}; significância não implica associação forte.\n' if applicable else '') +
             'ρ é exibida com sinal nas anotações: positivo associa maior comparecimento a maior mudança relativa para Lula; negativo, para Flávio.\n'
             '4.999 permutações por referência; pH: Holm na família de quatro testes. Faixas simuladas não são intervalos de confiança.\n'
             'A referência testa independência condicional; mobilização legítima e características não observadas também podem produzir associação.',
             fontsize=8.4, color='#515c65')
    fig.subplots_adjust(left=.245, right=.985, top=.83, bottom=.33, wspace=.18)
    return save(fig, output, 'conditional-association-reference')


def coverage_figure(coverage, output):
    nationwide = {model: select(coverage, model=model, uf='BR')[0] for model in MODELS}
    cohorts = {int(row['cohort_pairs']) for row in nationwide.values()}
    if len(cohorts) != 1:
        raise ValueError('Primary model cohorts differ unexpectedly')
    cohort, = cohorts
    counts = [cohort, *[int(nationwide[model]['informative_pairs']) for model in MODELS]]
    if any(not 0 <= value <= cohort for value in counts):
        raise ValueError('Invalid conditional-support count')
    uf_rows = {model: {row['uf']: row for row in select(coverage, model=model) if row['uf'] != 'BR'}
               for model in MODELS}
    if set(uf_rows[MODELS[0]]) != set(uf_rows[MODELS[1]]):
        raise ValueError('Coverage UF universes differ')
    states = sorted(uf_rows[MODELS[0]],
                    key=lambda uf: -int(uf_rows[MODELS[0]][uf]['informative_pairs'])/int(uf_rows[MODELS[0]][uf]['cohort_pairs']))
    fig, axes = plt.subplots(1, 2, figsize=(13.3, 9.8), gridspec_kw={'width_ratios':[.88, 1.12]})
    ax = axes[0]
    bars = ax.bar(range(3), counts, color=[PALE, GRAY, TEAL], width=.6)
    for rect, value in zip(bars, counts):
        ax.annotate(f'{integer(value)}\n{number(100*value/cohort, 1)}%',
                    (rect.get_x()+rect.get_width()/2, value), xytext=(0, 8), textcoords='offset points',
                    ha='center', color=DARK, fontsize=10)
    ax.set_xticks(range(3), ['Coorte\npareada', 'Suporte\npor zona', 'Suporte\npor local'], fontsize=9)
    ax.set_ylim(0, cohort*1.22)
    ax.set_ylabel('Seções pareadas entre os turnos')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: integer(value)))
    ax.set_title('A associação exige variação e pares', loc='left', fontsize=12, pad=14)
    style(ax)
    ax = axes[1]
    positions = np.arange(len(states))
    for model, offset, color, label in [(MODELS[0], -.13, GRAY, 'Por zona'), (MODELS[1], .13, TEAL, 'Por local')]:
        values = [100*int(uf_rows[model][uf]['informative_pairs'])/int(uf_rows[model][uf]['cohort_pairs']) for uf in states]
        ax.plot(values, positions+offset, 'o', ms=4.6, color=color, label=label)
    ax.set_yticks(positions, states, fontsize=9)
    ax.set_ylim(len(states)-.4, -.6)
    ax.set_xlim(0, 100)
    ax.set_xlabel('Seções com suporte formal (% da coorte da UF)')
    ax.set_title('A cobertura varia entre UFs', loc='left', fontsize=12, pad=14)
    ax.legend(loc='lower left', frameon=False, fontsize=9)
    style(ax, 'x')
    fig.suptitle('Cobertura das comparações condicionais', x=.085, y=.985, ha='left', fontsize=16)
    fig.text(.085, .018,
             'Suporte formal: estrato com pelo menos duas seções e variação exata tanto no comparecimento quanto na preferência.\n'
             'Os controles iniciais usam porte e faixas de 5 p.p. de comparecimento, preferência entre finalistas e presença de outras candidaturas.\n'
             'As coberturas se sobrepõem e não devem ser somadas. Seções sem suporte não são classificadas como normais ou anômalas; ZZ é o exterior.',
             fontsize=8.5, color='#515c65')
    fig.subplots_adjust(left=.085, right=.98, top=.91, bottom=.14, wspace=.32)
    return save(fig, output, 'comparison-coverage')


def generate(analysis, output):
    analysis, output = Path(analysis), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Refusing a nonempty figure output directory')
    if digest(HERE/'METHOD.pt-BR.md') != METHOD_SHA256:
        raise ValueError('Frozen H6 method hash differs')
    manifest = json.loads((analysis/'manifest.json').read_text())
    if manifest.get('status') != 'completed' or manifest.get('method_sha256') != METHOD_SHA256:
        raise ValueError('A completed analysis using the frozen H6 method is required')
    if manifest['parameters'].get('simulations') != 4999 or manifest['parameters'].get('family_size') != 4:
        raise ValueError('H6 published figures require 4,999 permutations and the fixed four-test family')
    paths = [analysis/name for name in INPUTS]
    for path in paths:
        if not path.is_file() or manifest['artifacts'].get(path.name, {}).get('sha256') != digest(path):
            raise ValueError(f'Missing or inconsistent numerical artifact: {path.name}')
    totals, bins, heatmap, tests, coverage = map(read_csv, paths)
    family = {(model, stat) for model in MODELS for stat in ('linear', 'rank')}
    if len(tests) != 4 or {(row['model'], row['statistic']) for row in tests} != family:
        raise ValueError('Incomplete or repeated four-test family')
    if any(int(row['simulations']) != 4999 for row in tests):
        raise ValueError('Simulation count differs from the published protocol')
    national_coverage, = select(coverage, model=MODELS[0], uf='BR')
    cohort = int(national_coverage['cohort_pairs'])
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':10, 'axes.labelcolor':DARK,
                         'text.color':'#263238', 'xtick.color':'#515c65', 'ytick.color':'#515c65',
                         'svg.fonttype':'none', 'svg.hashsalt':'election-replay-h6'})
    figures = []
    figures += balance_figure(totals, output)
    figures += association_figure(bins, heatmap, cohort, output)
    figures += reference_figure(tests, output)
    figures += coverage_figure(coverage, output)
    result = dict(status='completed', created_at_utc=datetime.now(timezone.utc).isoformat(),
        generator_sha256=digest(Path(__file__)), analysis_manifest_sha256=digest(analysis/'manifest.json'),
        inputs=[dict(path=path.name, sha256=digest(path), size_bytes=path.stat().st_size) for path in paths],
        source_inputs=manifest.get('source_inputs', {}),
        source_verification='Numerical inputs verified against completed analysis manifest; original source hashes carried from that manifest.',
        figures=[dict(path=path.name, sha256=digest(path), size_bytes=path.stat().st_size) for path in figures],
        scope='Original-source national count balance, paired-section descriptive association, fixed four-test conditional references, and coverage.',
        interpretation='No individual voter flows, causal attribution, physically reconstructed synthetic elections, or independent external source authentication.')
    (output/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis-dir', type=Path, default=HERE/'evidence/analysis')
    parser.add_argument('--output', type=Path, default=HERE/'figures')
    args = parser.parse_args()
    result = generate(args.analysis_dir, args.output)
    print(f'Generated {len(result["figures"])} figure files; input and output hashes recorded')


if __name__ == '__main__':
    main()
