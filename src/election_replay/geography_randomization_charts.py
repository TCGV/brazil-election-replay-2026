"""Scientific figures for observed section order versus permutation references.

The envelopes shown here are pointwise random-order references. The formal
curve decision is recorded separately after the primary Holm adjustment.
"""
from __future__ import annotations

import csv
import math
import os
from pathlib import Path
import tempfile

if not os.environ.get('MPLCONFIGDIR'):
    os.environ['MPLCONFIGDIR'] = str(Path(tempfile.gettempdir())/'election-replay-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

PRIMARY = 'first_partial_totalization'
CANDIDATES = [('13', 'Lula', '#c62828'), ('22', 'Flávio Bolsonaro', '#1565c0')]
CAPITALS = [('capital', 'Capitais', '#7952a8'), ('non_capital', 'Demais municípios', '#00897b')]
SIZES = [('<=10k', 'Até 10 mil', '#2a9d8f'), ('10k-50k', '10–50 mil', '#d15b24'),
         ('50k-200k', '50–200 mil', '#7952a8'), ('200k-1m', '200 mil–1 milhão', '#386cb0'),
         ('>1m', 'Mais de 1 milhão', '#9b7b36')]


def _number(value):
    if value in (None, ''):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _series(rows, election, turn, model, dimension, group, metric, candidate=''):
    selected = [row for row in rows if row['election_code']==election and row['turno']==turn
                and row['null_model']==model and row['dimension']==dimension
                and row['group']==group and row['metric']==metric and row.get('candidate', '')==candidate]
    selected.sort(key=lambda r: float(r['requested_sections_percentage']))
    return [row for row in selected if all(_number(row.get(key)) is not None for key in
            ('actual_sections_percentage','observed','reference_mean','lower_2_5','upper_97_5'))]


def _finish(ax):
    ax.spines[['top','right']].set_visible(False)
    ax.grid(axis='y', color='#dde3e9', linewidth=.7)
    ax.set_axisbelow(True)
    ax.set_xticks([10,25,50,75,90,99])
    ax.set_xlim(8,101)
    ax.set_xlabel('Seções nacionais contabilizadas (%)')
    ax.tick_params(labelsize=9)


def _save(fig, output_dir, stem, caption):
    folder = output_dir/'figures'
    folder.mkdir(parents=True, exist_ok=True)
    fig.text(.025,.014,caption+'\nEnvelopes ponto a ponto de 2,5–97,5%: não são bandas simultâneas nem IC populacionais. Decisão formal: teste da curva + Holm.',
             ha='left',va='bottom',fontsize=8,color='#536273')
    paths=[]
    for suffix in ('png','svg'):
        path=folder/f'{stem}.{suffix}'
        metadata={'Date':None,'Creator':'Election replay randomization analysis'} if suffix=='svg' else {'Software':'Election replay randomization analysis'}
        with matplotlib.rc_context({'svg.hashsalt':'election-replay-randomization'}):
            fig.savefig(path,dpi=180,bbox_inches='tight',facecolor='white',metadata=metadata)
        if suffix=='svg':
            path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n')
        paths.append(str(path.relative_to(output_dir)))
    plt.close(fig)
    return paths


def _candidate_figure(rows, elections, output_dir, permutations):
    fig,axes=plt.subplots(len(elections),2,figsize=(13,4.0*len(elections)+1),squeeze=False,sharey='row')
    for ri,(election,turn) in enumerate(elections):
        for ci,(model,label) in enumerate([('global','Embaralhamento nacional'),('within_uf','Embaralhamento dentro da UF')]):
            ax=axes[ri,ci]
            plotted=False
            for candidate,_,color in CANDIDATES:
                points=_series(rows,election,turn,model,'candidate','BR','candidate_percentage',candidate)
                if not points:
                    continue
                x=[float(r['actual_sections_percentage']) for r in points]
                observed=[float(r['observed']) for r in points]
                mean=[float(r['reference_mean']) for r in points]
                low=[float(r['lower_2_5']) for r in points]
                high=[float(r['upper_97_5']) for r in points]
                ax.fill_between(x,low,high,color='#8b97a5',alpha=.22,linewidth=.6,edgecolor=color)
                ax.plot(x,mean,color=color,linestyle='--',linewidth=1.1,alpha=.65)
                ax.plot(x,observed,color=color,linewidth=2.3,marker='o',markersize=3.5)
                plotted=True
            if not plotted:
                ax.text(.5,.5,'Sem percentuais definidos para este recorte',transform=ax.transAxes,ha='center',va='center')
            ax.set_title(f'{turn}º turno · {label}',fontsize=11,fontweight='bold')
            if ci==0:
                ax.set_ylabel('Votos nominais acumulados (%)')
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_:f'{v:g}%'))
            _finish(ax)
    legend=[Line2D([],[],color=color,lw=2.3,marker='o',markersize=3,label=f'{number} — {label}') for number,label,color in CANDIDATES]
    legend += [Line2D([],[],color='#536273',lw=1.1,linestyle='--',label='Centro conjunto (B+1 curvas)'),
               Patch(facecolor='#8b97a5',alpha=.25,label='Envelope ponto a ponto')]
    fig.legend(handles=legend,loc='upper center',bbox_to_anchor=(.5,.925),ncol=4,frameon=False,fontsize=9)
    fig.suptitle('Percentuais observados versus ordens embaralhadas das seções',fontsize=17,fontweight='bold',y=.99)
    fig.subplots_adjust(top=.85,bottom=.12,hspace=.36,wspace=.14)
    count=f'{permutations:,}'.replace(',','.')
    caption=f'Primeira totalização · {count} permutações · marcos de 10–99% · centro = média do observado + permutações · votos e atributos da seção permanecem juntos.'
    return _save(fig,output_dir,'randomization-candidate-reference',caption)


def _city_figure(rows, elections, output_dir, permutations):
    fig,axes=plt.subplots(len(elections),2,figsize=(13.2,4.1*len(elections)+1.2),squeeze=False,sharey='col')
    for ri,(election,turn) in enumerate(elections):
        for ci,(dimension,title,groups) in enumerate([('capital_status','Capitais e demais municípios',CAPITALS),('size_band','Porte pelo eleitorado municipal',SIZES)]):
            ax=axes[ri,ci]
            ax.axhline(0,color='#697887',linewidth=1,linestyle='--')
            for group,label,color in groups:
                points=_series(rows,election,turn,'within_uf',dimension,group,'section_completion_percentage')
                if not points:
                    continue
                x=[float(r['actual_sections_percentage']) for r in points]
                mean=[float(r['reference_mean']) for r in points]
                deviation=[float(r['observed'])-m for r,m in zip(points,mean)]
                low=[float(r['lower_2_5'])-m for r,m in zip(points,mean)]
                high=[float(r['upper_97_5'])-m for r,m in zip(points,mean)]
                ax.fill_between(x,low,high,color='#8b97a5',alpha=.17,linewidth=.4,edgecolor=color)
                ax.plot(x,deviation,color=color,linewidth=1.8,marker='o',markersize=3,label=label)
            ax.set_title(f'{turn}º turno · {title}',fontsize=11,fontweight='bold')
            if ci==0:
                ax.set_ylabel('Conclusão do grupo: observado − referência (pp)')
            _finish(ax)
            if ri==len(elections)-1:
                ax.legend(loc='upper center',bbox_to_anchor=(.5,-.21),ncol=2 if ci==0 else 3,frameon=False,fontsize=8)
    fig.suptitle('Padrões urbanos além da composição entre UFs',fontsize=17,fontweight='bold',y=.99)
    fig.text(.5,.935,'Positivo = mais seções do grupo concluídas que na referência; negativo = menos. A referência preserva o ritmo de cada UF.',
             ha='center',va='top',fontsize=10,color='#496078')
    fig.subplots_adjust(top=.86,bottom=.22,hspace=.36,wspace=.14)
    count=f'{permutations:,}'.replace(',','.')
    caption=f'Primeira totalização · {count} permutações dentro de cada UF · porte = eleitores aptos, não população · comparação descritiva, não causal.'
    return _save(fig,output_dir,'randomization-city-reference',caption)


def generate_charts(output_dir:Path)->list[str]:
    """Render the primary-source permutation references when evidence is present."""
    output_dir=Path(output_dir)
    path=output_dir/'randomization-bands.csv'
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig',newline='') as stream:
        rows=[r for r in csv.DictReader(stream) if r['source_timestamp']==PRIMARY]
    if not rows:
        raise ValueError('Randomization bands contain no primary-source curves')
    elections=sorted({(r['election_code'],r['turno']) for r in rows},key=lambda p:(int(p[1]),p[0]))
    counts={int(r['permutations']) for r in rows}
    if len(counts)!=1:
        raise ValueError('Inconsistent permutation counts in chart evidence')
    permutations=next(iter(counts))
    with plt.rc_context({'font.family':'DejaVu Sans','font.size':10,'axes.labelcolor':'#25364b',
                         'text.color':'#25364b','xtick.color':'#536273','ytick.color':'#536273',
                         'axes.edgecolor':'#536273'}):
        return (_candidate_figure(rows,elections,output_dir,permutations)
                +_city_figure(rows,elections,output_dir,permutations))
