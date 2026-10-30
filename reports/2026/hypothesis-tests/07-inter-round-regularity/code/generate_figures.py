#!/usr/bin/env python3
"""H7 figures from completed, fingerprinted municipal and allocation evidence.

Plotting/provenance utilities adapt the H6 generator at repository commit
cb32076a0eea70a35782fbabba7777a5e49c94fc. Display transformations below do
not create additional hypothesis tests or infer individual voter transitions.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from fractions import Fraction
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
from matplotlib.ticker import FuncFormatter, MaxNLocator
import matplotlib.pyplot as plt
import numpy as np

METHOD_SHA256 = '7212a1f6941c2357b751bb3b44dae60e931e2cdba5801c7dc231bd86bcb44066'
MODELS = ('section', 'place_block')
MODEL_NAMES = {'section': 'Seções pareadas', 'place_block': 'Blocos de locais'}
STATISTICS = ('Ucount', 'Unominal', 'Uconditional', 'Rlow', 'Jhigh')
TAILS = {'Ucount': 'upper', 'Unominal': 'upper', 'Uconditional': 'upper',
         'Rlow': 'lower', 'Jhigh': 'upper'}
INPUTS = ('municipal-census.csv', 'gain-directions.csv', 'tests.csv',
          'coverage.csv', 'adjacent-profiles.csv')
RED = '#c62828'
BLUE = '#1565c0'
DARK = '#37474f'
GRAY = '#8c969e'
TEAL = '#287b77'
PALE = '#e3e7ea'


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read_csv(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f'Invalid numerical CSV header: {path}')
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f'Malformed numerical CSV row: {path}')
    return rows


def select(rows, **criteria):
    found = [row for row in rows if all(str(row[key]) == str(value) for key, value in criteria.items())]
    if not found:
        raise ValueError(f'Missing figure evidence: {criteria}')
    return found


def number(value, places=3):
    return f'{float(value):.{places}f}'.replace('.', ',')


def integer(value):
    return f'{int(value):,}'.replace(',', '.')


def boolean(value):
    if value not in {'True', 'False'}:
        raise ValueError(f'Expected published boolean, got {value!r}')
    return value == 'True'


def style(ax, grid='y'):
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis=grid, color=PALE, lw=.8)
    ax.set_axisbelow(True)


def save(fig, output, stem):
    paths = []
    for extension in ('png', 'svg'):
        path = output / f'{stem}.{extension}'
        fig.savefig(path, dpi=180, facecolor='white', bbox_inches='tight',
                    metadata={'Creator': 'Brazil election replay — H7'})
        if extension == 'svg':
            path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()) + '\n', encoding='utf-8')
        paths.append(path)
    plt.close(fig)
    return paths


def definitions_figure(directions, output):
    metrics = ('count', 'nominal', 'relative')
    labels = ['Ganho absoluto de votos', 'Ganho em pontos percentuais\nsobre todos os nominais',
              'Crescimento relativo\nao próprio primeiro turno']
    fig, axes = plt.subplots(1, 2, figsize=(13.8, 7.8), sharex=True, sharey=True)
    for ax, universe, title in zip(axes, ('raw', 'cohort'),
                                   ('Todos os registros originais', 'Mesma coorte de seções nos dois turnos')):
        for position, metric in enumerate(metrics):
            row, = select(directions, universe=universe, scope_type='BR', scope='BR', metric=metric)
            total, defined = int(row['units']), int(row['defined_units'])
            n13, n22, ties, undefined = (int(row[key]) for key in ('advantage13', 'advantage22', 'ties', 'undefined_units'))
            if total <= 0 or n13+n22+ties != defined or defined+undefined != total:
                raise ValueError('Municipal direction counts do not reconcile')
            for candidate, count in ((13, n13), (22, n22)):
                if abs(float(row[f'fraction{candidate}_all'])-count/total) > 1e-12:
                    raise ValueError('Municipal fraction differs from its counts')
            for offset, count, color in [(-.16, n13, RED), (.16, n22, BLUE)]:
                pct = 100*count/total
                ax.barh(position+offset, pct, height=.27, color=color)
                ax.annotate(f'{number(pct, 2)}% · {integer(count)}', (pct, position+offset),
                            xytext=(5, 0), textcoords='offset points', va='center', fontsize=9, color=DARK)
            ax.text(1.03, position, f'Empates: {integer(ties)}\nIndef.: {integer(undefined)}',
                    transform=ax.get_yaxis_transform(), va='center', fontsize=8, color=GRAY)
        ax.set_xlim(0, 126)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_ylim(2.55, -.55)
        ax.set_yticks(range(3), labels, fontsize=9)
        ax.set_xlabel('Municípios com maior melhora para o candidato (% de todos)')
        ax.set_title(f'{title}\nN = {integer(total)} municípios', loc='left', fontsize=11.2, pad=16)
        style(ax, 'x')
    fig.suptitle('“Melhorou mais” depende da definição', x=.12, y=.99, ha='left', fontsize=16)
    fig.legend(handles=[Line2D([0], [0], color=RED, lw=7, label='Lula'),
                        Line2D([0], [0], color=BLUE, lw=7, label='Flávio Bolsonaro')],
               loc='lower center', bbox_to_anchor=(.56, .125), ncol=2, frameon=False, fontsize=9)
    fig.text(.12, .018,
             'Um município, um peso; somente território nacional. Empates e indefinições permanecem no denominador.\n'
             'Crescimento relativo é indefinido com base inicial zero. Onde as duas medidas são definidas, sua direção coincide com a mudança condicional entre finalistas.\n'
             'Percentuais descritivos: a avaliação estatística depende das referências de alocação, apresentadas em gráfico separado.',
             fontsize=8.3, color='#515c65')
    fig.subplots_adjust(left=.12, right=.89, top=.86, bottom=.30, wspace=.47)
    return save(fig, output, 'municipal-improvement-definitions')


def composition_figure(census, output):
    rows = [row for row in census if row['universe'] == 'raw' and boolean(row['domestic'])]
    q1, advantage, mechanical, exited = [], [], [], []
    for row in rows:
        if not boolean(row['present_1']) or not boolean(row['present_2']):
            continue
        n1, n2, v1, v2, w1, w2 = (int(row[key]) for key in
                                 ('nominal_1', 'nominal_2', 'v13_1', 'v13_2', 'v22_1', 'v22_2'))
        f1, f2 = v1+w1, v2+w2
        if not n1 or not n2 or not f1 or not f2:
            continue
        if f2 != n2:
            raise ValueError('Second-round nominal votes are not exhausted by the finalists')
        initial, final = Fraction(v1, f1), Fraction(v2, f2)
        observed = Fraction(v2-w2, n2)-Fraction(v1-w1, n1)
        base = (1-Fraction(f1, n1))*(2*initial-1)
        if observed != base+2*(final-initial):
            raise ArithmeticError('Municipal initial-composition identity failed')
        q1.append(100*float(initial));advantage.append(100*float(observed))
        mechanical.append(100*float(base));exited.append(100*(1-f1/n1))
    if not q1:
        raise ValueError('No defined nationwide municipal composition identities')
    q1, advantage, mechanical, exited = map(np.asarray, (q1, advantage, mechanical, exited))
    fig, axes = plt.subplots(1, 2, figsize=(13.8, 7.5), sharey=True)
    ax = axes[0]
    points = ax.scatter(q1, advantage, c=exited, cmap='viridis', s=8, alpha=.55, linewidths=0,
                        rasterized=True)
    ax.axvline(50, color=GRAY, lw=.9, ls='--')
    ax.axhline(0, color=GRAY, lw=.9)
    ax.set_xlabel('Participação inicial de Lula entre os finalistas (%)')
    ax.set_ylabel('Diferença entre os ganhos de participação nominal (p.p.)\nLula menos Flávio Bolsonaro')
    ax.set_title('Ponto de partida e melhora nominal', loc='left', fontsize=12, pad=14)
    cb = fig.colorbar(points, ax=ax, fraction=.044, pad=.02)
    cb.set_label('Outras candidaturas no 1º turno (% dos nominais)', fontsize=8)
    ax = axes[1]
    ax.scatter(mechanical, advantage, s=8, color=TEAL, alpha=.45, linewidths=0, rasterized=True)
    limits = [min(float(mechanical.min()), float(advantage.min())),
              max(float(mechanical.max()), float(advantage.max()))]
    ax.plot(limits, limits, color=GRAY, ls='--', lw=1, label='Mudança condicional igual a zero')
    ax.axhline(0, color=GRAY, lw=.7);ax.axvline(0, color=GRAY, lw=.7)
    ax.set_xlabel('Componente do ponto de partida e da saída de candidaturas (p.p.)')
    ax.set_title('Identidade: vantagem nominal = componente inicial + 2Δq', loc='left', fontsize=10.5, pad=14)
    ax.legend(loc='best', frameon=False, fontsize=8)
    for ax in axes:
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: number(value, 0)))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: number(value, 0)))
        style(ax)
    fig.suptitle('A saída das demais candidaturas altera a comparação', x=.085, y=.99, ha='left', fontsize=16)
    fig.text(.085, .018,
             f'Todos os {integer(len(q1))} municípios brasileiros com denominadores definidos nos registros originais; sem amostragem ou ajuste de regressão.\n'
             'Componente inicial = 100 × (1 − F₁/N₁) × (2q₁ − 1), com q em proporções; Δq é a mudança de Lula condicional aos finalistas.\n'
             'Os pontos e a identidade são descrições agregadas. Não identificam a origem individual dos votos nem uma causa artificial.',
             fontsize=8.5, color='#515c65')
    fig.subplots_adjust(left=.085, right=.985, top=.85, bottom=.24, wspace=.35)
    return save(fig, output, 'initial-composition-identity')


def reference_figure(tests, coverage, output):
    target_counts = {int(select(coverage, model=model, uf='BR')[0]['targets']) for model in MODELS}
    if len(target_counts) != 1:
        raise ValueError('Formal references unexpectedly differ in their fixed target universe')
    targets, = target_counts
    titles = {'Ucount': 'Prevalência: ganho absoluto · cauda superior ↑',
              'Unominal': 'Prevalência: ganho nominal · cauda superior ↑',
              'Uconditional': 'Prevalência: mudança condicional · cauda superior ↑',
              'Rlow': 'Dispersão residual municipal · cauda inferior ↓',
              'Jhigh': 'Contraste máximo de perfis adjacentes · cauda superior ↑'}
    units = {'Ucount': 'Maior frequência direcional (% dos alvos)',
             'Unominal': 'Maior frequência direcional (% dos alvos)',
             'Uconditional': 'Maior frequência direcional (% dos alvos)',
             'Rlow': 'Pontos percentuais', 'Jhigh': 'Pontos percentuais × raiz de seção'}
    fig, axes = plt.subplots(5, 1, figsize=(11.8, 12.4))
    for ax, stat in zip(axes, STATISTICS):
        largest = 0.
        for y, model in enumerate(MODELS):
            row, = select(tests, model=model, statistic=stat)
            if row['tail'] != TAILS[stat]:
                raise ValueError('Formal score tail differs from the frozen method')
            applicable = row['status'] in {'detected', 'not_detected'}
            if not row['observed'] or not row['simulation_q025'] or not row['simulation_q975']:
                if applicable:
                    raise ValueError('Applicable test lacks numerical display values')
                ax.text(.015, y, 'Sem suporte · sem decisão formal', transform=ax.get_yaxis_transform(),
                        va='center', fontsize=9, color=GRAY)
                continue
            scale = 100 if stat.startswith('U') else 1
            observed = float(row['observed'])*scale
            lo, hi = (float(row[key])*scale for key in ('simulation_q025', 'simulation_q975'))
            if (not all(np.isfinite([observed, lo, hi])) or min(observed, lo, hi) < 0 or lo > hi or
                    (stat.startswith('U') and max(observed, lo, hi) > 100+1e-10)):
                raise ValueError('Invalid formal-score display values')
            color = GRAY if model == 'section' else TEAL
            ax.hlines(y, lo, hi, color=color, lw=7, alpha=.5)
            ax.plot([lo, hi], [y, y], '|', color=color, ms=11)
            ax.plot(observed, y, 'o', color=DARK, ms=6,
                    markerfacecolor=DARK if applicable else 'white')
            p = 'sem decisão' if not applicable else f'pH={number(row["p_holm"], 4)}'
            annotation = f'{number(observed, 3)}\n{p}'
            ax.annotate(annotation, (max(observed, hi), y), xytext=(7, 0),
                        textcoords='offset points', va='center', fontsize=8.8, color=DARK)
            largest = max(largest, observed, hi)
        ax.set_yticks([0, 1], [MODEL_NAMES[model] for model in MODELS], fontsize=9)
        ax.set_ylim(1.55, -.55)
        ax.set_xlim(0, 125 if stat.startswith('U') else max(largest*1.35, .001))
        ax.set_title(titles[stat], loc='left', fontsize=10.5, pad=8)
        ax.set_xlabel(units[stat], fontsize=9)
        decimals = 0 if stat.startswith('U') else 2
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _, places=decimals: number(value, places)))
        if stat.startswith('U'):
            ax.set_xticks([0, 25, 50, 75, 100])
        else:
            ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
        style(ax, 'x')
    fig.suptitle('Referências condicionais de alocação entre municípios', x=.19, y=.99, ha='left', fontsize=15)
    fig.legend(handles=[Line2D([0], [0], color=DARK, marker='o', lw=0, label='Escore observado'),
                        Line2D([0], [0], color=GRAY, lw=7, alpha=.5, label='Quantis 2,5–97,5% simulados'),
                        Line2D([0], [0], color=DARK, marker='o', mfc='white', lw=0, label='Sem decisão formal')],
               loc='lower center', bbox_to_anchor=(.59, .065), ncol=3, frameon=False, fontsize=8)
    fig.text(.19, .012,
             f'Alvos fixos: {integer(targets)} municípios com pelo menos cinco seções da coorte original. 4.999 atribuições por referência; pH: Holm em dez testes dependentes.\n'
             'Os quantis não são intervalos de confiança. Rlow procura dispersão baixa; seu excesso superior não foi testado.\n'
             'Os demais escores procuram excesso. Jhigh não é escore-z nem teste causal de descontinuidade.\n'
             'A referência preserva trajetórias observadas e testa sua alocação; não define todos os mecanismos de uma eleição natural.',
             fontsize=8.1, color='#515c65')
    fig.subplots_adjust(left=.19, right=.98, top=.94, bottom=.13, hspace=.95)
    return save(fig, output, 'conditional-allocation-reference')


def coverage_figure(coverage, edges, output):
    national = {model: select(coverage, model=model, uf='BR')[0] for model in MODELS}
    fig, axes = plt.subplots(1, 2, figsize=(13.8, 7.5), gridspec_kw={'width_ratios':[.85, 1.15]})
    ax = axes[0]
    for j, model in enumerate(MODELS):
        row = national[model]
        total, movable, targets, reached = (int(row[key]) for key in ('units', 'movable_units', 'targets', 'reachable_targets'))
        if not 0 <= movable <= total or not 0 <= reached <= targets or total <= 0 or targets <= 0:
            raise ValueError('Invalid municipal allocation-support counts')
        for offset, count, denominator, label in [(-.18, movable, total, 'Unidades permutáveis'),
                                                 (.18, reached, targets, 'Alvos alcançáveis')]:
            pct = 100*count/denominator
            color = GRAY if model == 'section' else TEAL
            ax.barh(j+offset, pct, height=.29, color=color, alpha=1 if offset < 0 else .55)
            ax.annotate(f'{number(pct, 2)}%\n{integer(count)}/{integer(denominator)}', (pct, j+offset),
                        xytext=(6, 0), textcoords='offset points', va='center', fontsize=8.4, color=DARK)
    ax.set_xlim(0, 128)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_yticks([0, 1], [MODEL_NAMES[m] for m in MODELS], fontsize=9)
    ax.set_ylim(1.7, -.7)
    ax.set_xlabel('Suporte estrutural (%)')
    ax.set_title('Trocas possíveis entre municípios', loc='left', fontsize=12, pad=14)
    style(ax, 'x')
    ax = axes[1]
    for position, (model, color) in enumerate([('section', GRAY), ('place_block', TEAL)]):
        selected = [row for row in edges if row['model'] == model]
        if not selected:
            ax.text(.02, .96-position*.07, f'{MODEL_NAMES[model]}: sem pares adjacentes',
                    transform=ax.transAxes, va='top', fontsize=9, color=color)
            continue
        x, y = [], []
        for row in selected:
            q = float(row['original_q1_left'])
            signed, component = float(row['signed_contrast_pp']), float(row['J_component'])
            nl, nr = int(row['left_sections']), int(row['right_sections'])
            if (not np.isfinite([q, signed, component]).all() or component < 0 or nl <= 0 or nr <= 0 or
                    abs(component-abs(signed)/np.sqrt(1/nl+1/nr)) > 1e-9):
                raise ValueError('Invalid adjacent-profile contrast')
            x.append(q);y.append(component*np.sign(signed))
        ax.scatter(x, y, s=6, alpha=.35, color=color, linewidths=0, rasterized=True,
                   label=MODEL_NAMES[model])
    ax.axhline(0, color=GRAY, lw=.9)
    ax.set_xlabel('Preferência inicial do perfil à esquerda (% entre finalistas)')
    ax.set_ylabel('Contraste assinado escalado (p.p. × raiz de seção)')
    ax.set_title('Todos os pares de perfis adjacentes', loc='left', fontsize=12, pad=14)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(loc='best', frameon=False, fontsize=8.5)
    style(ax)
    fig.suptitle('Suporte de alocação e contrastes de perfis', x=.085, y=.99, ha='left', fontsize=16)
    fig.text(.085, .018,
             'Barras escuras: unidades em estratos com mais de um município; claras: municípios-alvo com algum slot alcançável.\n'
             'Seções e blocos são unidades distintas. Suporte estrutural não prova variabilidade de cada escore ou classifica normalidade.\n'
             'À direita, ordem fixa pela preferência inicial dentro da UF, não por vizinhança geográfica ou tempo. Cada par não recebe valor-p individual.',
             fontsize=8.3, color='#515c65')
    fig.subplots_adjust(left=.085, right=.985, top=.85, bottom=.24, wspace=.39)
    return save(fig, output, 'allocation-coverage')


def generate(analysis, output):
    analysis, output = Path(analysis), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Refusing a nonempty figure output directory')
    if digest(HERE/'METHOD.pt-BR.md') != METHOD_SHA256:
        raise ValueError('Frozen H7 method hash differs')
    manifest = json.loads((analysis/'manifest.json').read_text())
    if manifest.get('status') != 'completed' or manifest.get('method_sha256') != METHOD_SHA256:
        raise ValueError('A completed analysis using the frozen H7 method is required')
    if manifest['parameters'].get('simulations') != 4999 or manifest['parameters'].get('family_size') != 10:
        raise ValueError('H7 published figures require 4,999 permutations and the fixed ten-test family')
    paths = [analysis/name for name in INPUTS]
    for path in paths:
        expected = manifest['artifacts'].get(path.name, {})
        if (not path.is_file() or expected.get('sha256') != digest(path) or
                expected.get('size_bytes') != path.stat().st_size):
            raise ValueError(f'Missing or inconsistent numerical artifact: {path.name}')
    census, directions, tests, coverage, edges = map(read_csv, paths)
    family = {(model, stat) for model in MODELS for stat in STATISTICS}
    if len(tests) != 10 or {(row['model'], row['statistic']) for row in tests} != family:
        raise ValueError('Incomplete or repeated ten-test family')
    if any(int(row['simulations']) != 4999 for row in tests):
        raise ValueError('Simulation count differs from the published protocol')
    for stat in STATISTICS[:3]:
        recorded = [select(tests, model=model, statistic=stat)[0]['observed'] for model in MODELS]
        if ((not recorded[0]) != (not recorded[1]) or
                (recorded[0] and abs(float(recorded[0])-float(recorded[1])) > 1e-12)):
            raise ValueError('Observed municipal prevalence differs between references')
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':10, 'axes.labelcolor':DARK,
                         'text.color':'#263238', 'xtick.color':'#515c65', 'ytick.color':'#515c65',
                         'svg.fonttype':'none', 'svg.hashsalt':'election-replay-h7'})
    figures = []
    figures += definitions_figure(directions, output)
    figures += composition_figure(census, output)
    figures += reference_figure(tests, coverage, output)
    figures += coverage_figure(coverage, edges, output)
    result = dict(status='completed', created_at_utc=datetime.now(timezone.utc).isoformat(),
        generator_sha256=digest(Path(__file__)), analysis_manifest_sha256=digest(analysis/'manifest.json'),
        presentation_revision=dict(path='METHOD-REVISION.pt-BR.md',
                                   sha256=digest(HERE/'METHOD-REVISION.pt-BR.md')),
        inputs=[dict(path=path.name, sha256=digest(path), size_bytes=path.stat().st_size) for path in paths],
        source_inputs=manifest.get('source_inputs', {}),
        source_verification='Numerical inputs verified against completed analysis manifest; original source hashes carried from that manifest.',
        figures=[dict(path=path.name, sha256=digest(path), size_bytes=path.stat().st_size) for path in figures],
        scope='Municipal improvement definitions, exact initial-composition identities, fixed ten-test allocation references, and structural support/profile contrasts.',
        interpretation='No individual voter flows, causal attribution, natural-election certification, geographic or temporal ordering of adjacent profiles, or independent external source authentication.')
    (output/'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
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
