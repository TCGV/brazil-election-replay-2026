#!/usr/bin/env python3
"""H5 scientific figures from completed, fingerprinted paired-section evidence."""
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

METHOD_SHA256 = 'b654515cd18021c05fd855d4c01dc0cf976299ebe247446fd5828b30d5bd843f'
MODELS = ('zone_size', 'zone_size_baseline')
MODEL_NAMES = {'zone_size': 'Zona + porte', 'zone_size_baseline': 'Zona + porte + preferência inicial'}
RED = '#c62828'
BLUE = '#1565c0'
DARK = '#37474f'
GRAY = '#8c969e'
TEAL = '#287b77'
PALE = '#e3e7ea'
INPUTS = ('transition-grid.csv', 'histograms.csv', 'tests.csv', 'coverage.csv', 'case-summary.csv')


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read_csv(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def number(value, places=3):
    return f'{float(value):.{places}f}'.replace('.', ',')


def integer(value):
    return f'{int(value):,}'.replace(',', '.')


def select(rows, **criteria):
    found = [row for row in rows if all(str(row[key]) == str(value) for key, value in criteria.items())]
    if not found:
        raise ValueError(f'Missing figure evidence: {criteria}')
    return found


def style(ax, grid='y'):
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis=grid, color=PALE, lw=.8)
    ax.set_axisbelow(True)


def save(fig, output, stem):
    result = []
    for extension in ('png', 'svg'):
        path = output / f'{stem}.{extension}'
        fig.savefig(path, dpi=180, facecolor='white', bbox_inches='tight',
                    metadata={'Creator': 'Brazil election replay — H5'})
        if extension == 'svg':
            path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()) + '\n', encoding='utf-8')
        result.append(path)
    plt.close(fig)
    return result


def histogram(rows, metric):
    found = sorted(select(rows, metric=metric), key=lambda row: int(row['left_pp']))
    denominator, = {int(row['denominator']) for row in found}
    edges = np.r_[[int(row['left_pp']) for row in found], int(found[-1]['right_pp'])]
    counts = np.array([int(row['sections']) for row in found])
    if counts.sum() != denominator or np.any(np.diff(edges) != 1):
        raise ValueError(f'Invalid complete one-percentage-point histogram: {metric}')
    percentage = 100 * counts / denominator if denominator else np.zeros_like(counts, dtype=float)
    return edges, counts, percentage, denominator


def change_figure(grid_rows, histograms, cohort, output):
    grid = np.zeros((100, 100), dtype=np.int64)
    keys = set()
    for row in grid_rows:
        i, j = int(row['q1_low_pp']), int(row['q2_low_pp'])
        if (i, j) in keys or not (0 <= i < 100 and 0 <= j < 100):
            raise ValueError('Repeated or invalid transition-grid cell')
        keys.add((i, j))
        grid[i, j] = int(row['sections'])
    if len(keys) != 10000 or grid.sum() != cohort:
        raise ValueError('Transition grid does not cover the full paired cohort')
    fig, axes = plt.subplots(1, 2, figsize=(13.4, 6.5))
    ax = axes[0]
    mesh = ax.pcolormesh(np.arange(101), np.arange(101), np.ma.masked_equal(grid.T, 0),
                         cmap='viridis', norm=LogNorm(vmin=1, vmax=max(int(grid.max()), 2)), rasterized=True)
    ax.plot([0, 100], [0, 100], ls='--', lw=1.1, color='#cfd8dc')
    ax.set(xlim=(0, 100), ylim=(0, 100), xlabel='Lula entre os dois finalistas · 1º turno (%)',
           ylabel='Lula entre os dois finalistas · 2º turno (%)')
    ax.set_title('Mesma seção, dois resultados agregados', loc='left', fontsize=11, pad=10)
    ax.set_aspect('equal')
    colorbar = fig.colorbar(mesh, ax=ax, pad=.025, fraction=.048)
    colorbar.set_label('Seções por célula de 1 p.p. × 1 p.p.', fontsize=9)
    ax = axes[1]
    for metric, color, linestyle, label in (
        ('delta_pp', RED, '-', 'Lula · participação entre os dois finalistas'),
        ('dp13_pp', RED, '--', 'Lula · participação em todos os nominais'),
    ):
        edges, _, percentage, denominator = histogram(histograms, metric)
        if denominator != cohort:
            raise ValueError('Change histogram cohort differs from transition grid')
        ax.stairs(np.where(percentage > 0, percentage, np.nan), edges, color=color,
                  ls=linestyle, lw=1.7, label=label)
    ax.axvline(0, color=GRAY, lw=.8)
    ax.set_yscale('log')
    ax.set(xlim=(-100, 100), xlabel='Mudança do 1º para o 2º turno (p.p.)',
           ylabel='Seções por faixa de 1 p.p. (% da coorte)')
    ax.set_title('O denominador muda a interpretação', loc='left', fontsize=11, pad=10)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: number(value, 3)))
    style(ax, 'both')
    ax.legend(loc='upper left', fontsize=8.8, frameon=False)
    fig.suptitle('Mudanças entre turnos nas seções pareadas', x=.075, y=.99, ha='left', fontsize=16)
    fig.text(.075, .022,
             f'Coorte: {integer(cohort)} seções; mapas e distribuições usam peso igual por seção. Cada célula representa seções, não eleitores.\n'
             'A medida condicional evita o efeito mecânico da saída das outras candidaturas; não identifica transferências individuais. Escalas de frequência logarítmicas.',
             fontsize=8.5, color='#515c65')
    fig.subplots_adjust(left=.075, right=.985, top=.88, bottom=.20, wspace=.37)
    return save(fig, output, 'paired-change-distribution')


def peer_figure(histograms, cases, output):
    fig, ax = plt.subplots(figsize=(12.4, 6.6))
    broad_edges, _, broad_pct, broad_n = histogram(histograms, 'broad_contrast')
    strict_edges, _, strict_pct, strict_n = histogram(histograms, 'strict_contrast')
    if strict_n != int(cases['strict_supported']) or broad_n != int(cases['broad_supported']):
        raise ValueError('Peer histogram denominators differ from the case summary')
    ax.stairs(np.where(broad_pct > 0, broad_pct, np.nan), broad_edges, color=GRAY, lw=1.6,
              label=f'Sem faixa inicial · {integer(broad_n)} comparáveis')
    centers = (strict_edges[:-1] + strict_edges[1:]) / 2
    for use, color in [(centers < 0, BLUE), (centers >= 0, RED)]:
        values = np.where(use & (strict_pct > 0), strict_pct, np.nan)
        ax.stairs(values, strict_edges, color=color, lw=1.8)
    ax.axvline(-10, color=BLUE, ls='--', lw=1.1)
    ax.axvline(10, color=RED, ls='--', lw=1.1)
    ax.axvline(0, color=DARK, lw=.7)
    ax.set_xscale('symlog', linthresh=10, linscale=1)
    ax.set_yscale('log')
    ax.set_xlim(-200, 200)
    ticks = [-200, -50, -10, 0, 10, 50, 200]
    ax.set_xticks(ticks, [str(value).replace('-', '−') for value in ticks])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: number(value, 3)))
    ax.set_xlabel('Mudança da seção − mediana das outras seções comparáveis (p.p.)')
    ax.set_ylabel('Seções por faixa de 1 p.p. (% das comparáveis)')
    ax.set_title('Quanto uma mudança difere de seus pares locais?', loc='left', fontsize=16, pad=24)
    style(ax, 'y')
    handles, labels = ax.get_legend_handles_labels()
    handles += [Line2D([0], [0], color=DARK, lw=1.8),
                Line2D([0], [0], color=GRAY, lw=1.1, ls='--')]
    labels += [f'Com faixa inicial · {integer(strict_n)} comparáveis', 'Cortes descritivos: −10 e +10 p.p.']
    ax.legend(handles, labels, loc='upper right', fontsize=9, frameon=False)
    fig.text(.09, .024,
             f'Com preferência inicial: {integer(cases["strict_priorities"])} prioridades; contraste positivo relativo a Lula: {integer(cases["strict_priorities_13"])}; '
             f'negativo relativo a Flávio: {integer(cases["strict_priorities_22"])}.\n'
             'Cada contexto exige quatro outras seções no mesmo local e faixa de aptos. Cor indica o sinal do contraste, não necessariamente aumento próprio.\n'
             'Eixo horizontal linear entre −10 e +10 p.p., logarítmico fora; frequência logarítmica. Prioridade é triagem, sem valor-p por seção.',
             fontsize=8.6, color='#515c65')
    fig.subplots_adjust(left=.09, right=.985, top=.86, bottom=.25)
    return save(fig, output, 'local-peer-contrasts')


def concentration_figure(tests, output):
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 6.0))
    labels = [MODEL_NAMES[model] for model in MODELS]
    for ax, statistic in zip(axes, ('RMS', 'MAX')):
        for y, model in enumerate(MODELS):
            row, = select(tests, model=model, statistic=statistic)
            lo, hi = float(row['simulation_q025']), float(row['simulation_q975'])
            observed = float(row['observed'])
            color = GRAY if model == 'zone_size' else TEAL
            ax.hlines(y, lo, hi, color=color, lw=6, alpha=.4)
            ax.plot([lo, hi], [y, y], '|', color=color, ms=11, mew=1.2)
            ax.plot(observed, y, 'o', color=DARK, ms=7)
            label = 'n/a' if not row['p_holm'] else f'pH={number(row["p_holm"], 4)}'
            ax.annotate(label, (max(observed, hi), y), xytext=(6, 0), textcoords='offset points',
                        va='center', color=DARK, fontsize=9)
        ax.set_yticks([0, 1], labels if statistic == 'RMS' else ['', ''], fontsize=9)
        ax.set_ylim(1.6, -.6)
        ax.set_xlim(left=0)
        ax.set_xlim(0, max(ax.get_xlim()[1] * 1.45, 1e-6))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: number(value, 2)))
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.set_title('RMS · dispersão das médias locais' if statistic == 'RMS' else 'MAX · maior contraste ponderado',
                     loc='left', fontsize=11, pad=12)
        ax.set_xlabel('Pontos percentuais' if statistic == 'RMS' else 'Pontos percentuais × √seção')
        style(ax, 'x')
    fig.suptitle('Concentração entre locais e referência de permutação', x=.225, y=.99, ha='left', fontsize=15)
    fig.legend(handles=[Line2D([0], [0], color=DARK, marker='o', lw=0, label='Escore observado'),
                        Line2D([0], [0], color=GRAY, lw=6, alpha=.5, label='Quantis simulados de 2,5–97,5%')],
               loc='lower center', bbox_to_anchor=(.59, .12), ncol=2, frameon=False, fontsize=9)
    fig.text(.225, .018,
             '4.999 permutações por referência; pH: Holm na família fixa de quatro testes. As faixas não são intervalos de confiança.\n'
             'Os pares e a distribuição de mudanças são preservados. O teste examina sua alocação entre locais, sem provar causa artificial.\n'
             'MAX não é um escore-z nem um teste individual de seção ou local.', fontsize=8.5, color='#515c65')
    fig.subplots_adjust(left=.225, right=.985, top=.82, bottom=.30, wspace=.18)
    return save(fig, output, 'concentration-reference')


def coverage_figure(coverage, cases, output):
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 6.5), sharey=True)
    cohort = int(cases['cohort_pairs'])
    counts = [cohort, int(cases['broad_supported']), int(cases['strict_supported'])]
    ax = axes[0]
    bars = ax.bar(np.arange(3), counts, color=[PALE, GRAY, TEAL], width=.63)
    for rect, value in zip(bars, counts):
        ax.annotate(f'{integer(value)}\n{number(100*value/cohort, 1)}%',
                    (rect.get_x()+rect.get_width()/2, value), xytext=(0, 6), textcoords='offset points',
                    ha='center', color=DARK, fontsize=9)
    ax.set_xticks(np.arange(3), ['Coorte', 'Pares sem\nfaixa inicial', 'Pares com\nfaixa inicial'], fontsize=9)
    ax.set_title('Triagem por seção: quatro outros pares', loc='left', fontsize=11, pad=12)
    ax.set_ylabel('Pares de seções entre os turnos')
    ax = axes[1]
    for offset, field, color in [(-.18, 'target_pairs', GRAY), (.18, 'target_pairs_in_potential_groups', TEAL)]:
        values = []
        for model in MODELS:
            row, = select(coverage, model=model, uf='BR')
            if int(row['cohort_pairs']) != cohort:
                raise ValueError('Concentration coverage cohort differs from section screening')
            values.append(int(row[field]))
        x = np.arange(2)+offset
        ax.bar(x, values, width=.33, color=color)
        for position, value in zip(x, values):
            ax.annotate(integer(value), (position, value), xytext=(0, 6), textcoords='offset points',
                        ha='center', color=DARK, fontsize=8.7)
    ax.set_xticks(np.arange(2), ['Zona + porte', 'Zona + porte +\npreferência inicial'], fontsize=9)
    ax.set_title('Referência formal: alvos e trocas possíveis', loc='left', fontsize=11, pad=12)
    axes[0].set_ylim(0, cohort*1.24)
    for ax in axes:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: integer(value)))
        style(ax)
    fig.suptitle('Onde a comparação tem suporte?', x=.085, y=.99, ha='left', fontsize=16)
    fig.legend(handles=[Patch(facecolor=GRAY, label='Seções em locais-alvo (pelo menos cinco pares)'),
                        Patch(facecolor=TEAL, label='Dessas, em estratos que podem afetar os alvos')],
               loc='lower center', bbox_to_anchor=(.55, .115), ncol=2, frameon=False, fontsize=8.8)
    fig.text(.085, .018,
             'Coberturas são recortes da mesma coorte e não devem ser somadas. A preferência inicial usa faixas de cinco pontos percentuais.\n'
             'Sem suporte na triagem, não se classifica a seção como normal ou anômala. Na referência formal, potencial de troca não garante variação de todo escore.',
             fontsize=8.5, color='#515c65')
    fig.subplots_adjust(left=.085, right=.985, top=.86, bottom=.27, wspace=.20)
    return save(fig, output, 'comparison-coverage')


def generate(analysis, output):
    analysis, output = Path(analysis), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Refusing a nonempty figure output directory')
    manifest = json.loads((analysis/'manifest.json').read_text())
    if manifest.get('status') != 'completed' or manifest.get('method_sha256') != METHOD_SHA256:
        raise ValueError('A completed analysis using the frozen H5 method is required')
    if manifest['parameters'].get('simulations') != 4999 or manifest['parameters'].get('family_size') != 4:
        raise ValueError('H5 published figures require the declared 4,999 permutations and four-test family')
    paths = [analysis/name for name in INPUTS]
    for path in paths:
        if not path.is_file() or manifest['artifacts'].get(path.name, {}).get('sha256') != digest(path):
            raise ValueError(f'Missing or inconsistent numerical artifact: {path.name}')
    grid, histograms, tests, coverage, summaries = map(read_csv, paths)
    expected = {(model, stat) for model in MODELS for stat in ('RMS', 'MAX')}
    if len(tests) != 4 or {(row['model'], row['statistic']) for row in tests} != expected:
        raise ValueError('Incomplete or repeated fixed four-test family')
    if any(int(row['simulations']) != 4999 for row in tests):
        raise ValueError('Simulation count differs from the published protocol')
    cases, = select(summaries, uf='BR')
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':10, 'axes.labelcolor':DARK,
                         'text.color':'#263238', 'xtick.color':'#515c65', 'ytick.color':'#515c65',
                         'svg.fonttype':'none', 'svg.hashsalt':'election-replay-h5'})
    figures = []
    figures += change_figure(grid, histograms, int(cases['cohort_pairs']), output)
    figures += peer_figure(histograms, cases, output)
    figures += concentration_figure(tests, output)
    figures += coverage_figure(coverage, cases, output)
    result = dict(status='completed', created_at_utc=datetime.now(timezone.utc).isoformat(),
        generator_sha256=digest(Path(__file__)), analysis_manifest_sha256=digest(analysis/'manifest.json'),
        inputs=[dict(path=path.name, sha256=digest(path), size_bytes=path.stat().st_size) for path in paths],
        figures=[dict(path=path.name, sha256=digest(path), size_bytes=path.stat().st_size) for path in figures],
        scope='Paired sections; descriptive section screening and four formal tests of allocation between polling places.',
        interpretation='Formal references preserve marginal section changes; no causal attribution, individual voter transitions, or external source authentication.')
    (output/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis-dir',type=Path,default=HERE/'evidence/analysis')
    parser.add_argument('--output',type=Path,default=HERE/'figures')
    args = parser.parse_args()
    result = generate(args.analysis_dir,args.output)
    print(f'Generated {len(result["figures"])} figure files; source and output hashes recorded')


if __name__=='__main__':
    main()
