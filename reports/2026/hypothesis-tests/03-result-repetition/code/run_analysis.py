#!/usr/bin/env python3
"""H3: exhaustive integer-vector repetition inventory and exact local moments."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
from fractions import Fraction
from functools import lru_cache
import gzip
import hashlib
import io
import json
from math import comb
from pathlib import Path
import subprocess
import sys

import numpy as np

from collision_statistics import (cantelli_bound, group_strata, holm_bounds, inventory,
                                  moments, pair_count, population_masks, signature_matrix)
from load_data import load_data

HERE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[5]
SCENARIOS=[
    dict(name='primary',include_zone=True,include_size=True,ratio=1.25,min_nominal=50),
    dict(name='no_size_band',include_zone=True,include_size=False,ratio=1.25,min_nominal=50),
    dict(name='municipality_size',include_zone=False,include_size=True,ratio=1.25,min_nominal=50),
    dict(name='municipality_only',include_zone=False,include_size=False,ratio=1.25,min_nominal=50),
    dict(name='wider_size',include_zone=True,include_size=True,ratio=1.5,min_nominal=50),
    dict(name='nominal_100',include_zone=True,include_size=True,ratio=1.25,min_nominal=100),
]
VIEW_NAMES={'all':'all_details','other_positive':'other_excluded_positive'}
INVENTORY_COLUMNS=['election_code','turno','view','signature_type','sections','unique_vectors',
    'repeated_clusters','repeated_sections','collision_pairs','max_multiplicity']
CLUSTER_COLUMNS=['election_code','turno','view','signature_type','cluster_id','vector_json',
    'multiplicity','collision_pairs','uf_count','municipality_count','zone_count','place_count']
MEMBER_COLUMNS=['election_code','turno','view','signature_type','cluster_id','vector_json',
    'uf','municipality','municipality_name','zone','section','place','source_line','aptos',
    'turnout','abstentions','nominal','installed','cancelled']
STRATA_COLUMNS=['election_code','turno','uf','municipality','zone','nominal','size_band','n',
    'min_aptos','max_aptos','a_unique','b_unique','a_pairs','b_pairs','observed_pairs',
    'expected_pairs','variance','expected_numerator','expected_denominator','variance_numerator','variance_denominator']
DISTRIBUTION_COLUMNS=['election_code','turno','view','signature_type','turnout','sections',
    'unique_vectors','repeated_clusters','repeated_sections','collision_pairs','same_turnout_pairs','collision_rate_same_turnout']


def digest(path):
    sha=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            sha.update(block)
    return sha.hexdigest()


def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


@contextmanager
def table_writer(path,columns):
    path=Path(path)
    with path.open('wb') as raw:
        if path.suffix=='.gz':
            with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=6) as zipped:
                with io.TextIOWrapper(zipped,encoding='utf-8',newline='') as text:
                    writer=csv.DictWriter(text,fieldnames=columns,lineterminator='\n',extrasaction='ignore')
                    writer.writeheader();yield writer
        else:
            with io.TextIOWrapper(raw,encoding='utf-8',newline='') as text:
                writer=csv.DictWriter(text,fieldnames=columns,lineterminator='\n',extrasaction='ignore')
                writer.writeheader();yield writer


def write_table(path,columns,rows):
    with table_writer(path,columns) as writer:
        writer.writerows(rows)


def exact_fields(mean,variance):
    return dict(expected_pairs=float(mean),variance=float(variance),
        expected_numerator=str(mean.numerator),expected_denominator=str(mean.denominator),
        variance_numerator=str(variance.numerator),variance_denominator=str(variance.denominator))


@lru_cache(maxsize=100000)
def cached_moments(a,b):
    return moments(a,b)


def labeled_statistics(a_labels,b_labels,full_labels,ids):
    """Use globally exact vector labels to avoid tiny-matrix sorts per stratum."""
    n=len(ids)
    if n==1:
        return dict(n=1,a_unique=1,b_unique=1,a_pairs=0,b_pairs=0,observed_pairs=0,
                    mean=Fraction(0),var=Fraction(0))
    ac=Counter(a_labels[ids].tolist());bc=Counter(b_labels[ids].tolist())
    ap,bp=pair_count(ac.values()),pair_count(bc.values())
    if not ap or not bp:
        x=0;e=v=Fraction(0)
    elif len(ac)==1:
        x=bp;e=Fraction(bp);v=Fraction(0)
    elif len(bc)==1:
        x=ap;e=Fraction(ap);v=Fraction(0)
    else:
        x=pair_count(Counter(full_labels[ids].tolist()).values())
        e,v=cached_moments(tuple(sorted(ac.values())),tuple(sorted(bc.values())))
    if v==0 and Fraction(x)!=e:
        raise ArithmeticError('Observed count differs from a constant reference')
    return dict(n=n,a_unique=len(ac),b_unique=len(bc),a_pairs=ap,b_pairs=bp,
                observed_pairs=x,mean=e,var=v)


def blank_total():
    return dict(groups=0,sections=0,nonsingleton_groups=0,nonsingleton_sections=0,
        informative_groups=0,informative_sections=0,observed_pairs=0,mean=Fraction(0),var=Fraction(0))


def add_total(total,stats):
    n=stats['n'];informative=stats['var']>0
    total['groups']+=1;total['sections']+=n
    total['nonsingleton_groups']+=int(n>1)
    total['nonsingleton_sections']+=n if n>1 else 0
    total['informative_groups']+=int(informative)
    total['informative_sections']+=n if informative else 0
    total['observed_pairs']+=stats['observed_pairs']
    total['mean']+=stats['mean'];total['var']+=stats['var']


def total_row(data,total):
    row={k:v for k,v in total.items() if k not in {'mean','var'}}
    row.update(election_code=int(data['election_code']),turno=int(data['turno']),
        **exact_fields(total['mean'],total['var']))
    row['excess_pairs']=float(Fraction(total['observed_pairs'])-total['mean'])
    return row


def analyze_scenario(data,a_labels,b_labels,full_labels,config,writer=None):
    selected=population_masks(data,config['min_nominal'])['eligible']
    groups=group_strata(data,selected,config['include_zone'],config['include_size'],config['ratio'])
    total=blank_total();by_uf=defaultdict(blank_total)
    for group in groups:
        ids=group['indices'];uf,municipality,zone,nominal,band=group['key']
        stats=labeled_statistics(a_labels,b_labels,full_labels,ids)
        add_total(total,stats);add_total(by_uf[uf],stats)
        if writer is not None:
            row=dict(election_code=int(data['election_code']),turno=int(data['turno']),uf=uf,
                municipality=municipality,zone=zone,nominal=nominal,size_band=band,
                min_aptos=int(data['aptos'][ids].min()),max_aptos=int(data['aptos'][ids].max()),
                **{k:v for k,v in stats.items() if k not in {'mean','var'}},**exact_fields(stats['mean'],stats['var']))
            writer.writerow(row)
    return total,dict(by_uf)


def emit_inventory(data,names,cluster_writer,member_writer):
    """Yield summary/distribution rows; every repeated vector/member is exported."""
    inventory_rows=[];distributions=[];full_labels=None
    for kind in ['full','extended']:
        matrix=signature_matrix(data,extended=kind=='extended')
        for view,selected in population_masks(data).items():
            result=inventory(matrix,selected)
            identity=dict(election_code=int(data['election_code']),turno=int(data['turno']),
                          view=VIEW_NAMES.get(view,view),signature_type=kind)
            inventory_rows.append(dict(identity,sections=result['rows'],unique_vectors=result['distinct_signatures'],
                repeated_clusters=result['repeated_groups'],repeated_sections=result['repeated_sections'],
                collision_pairs=result['collision_pairs'],max_multiplicity=result['max_multiplicity']))
            if kind=='full' and view=='all':
                full_labels=result['inverse']
            counts=result['counts'];unique=result['unique'];inv=result['inverse']
            bins=defaultdict(lambda:dict(sections=0,unique_vectors=0,repeated_clusters=0,repeated_sections=0,collision_pairs=0))
            for vector,multiplicity in zip(unique,counts):
                m=int(multiplicity);turnout=int(vector[-3] if kind=='extended' else vector[-1])
                bucket=bins[turnout]
                bucket['sections']+=m;bucket['unique_vectors']+=1
                bucket['repeated_clusters']+=int(m>1)
                bucket['repeated_sections']+=m if m>1 else 0
                bucket['collision_pairs']+=comb(m,2)
            for turnout,values in sorted(bins.items()):
                possible=comb(values['sections'],2)
                distributions.append(dict(identity,turnout=turnout,**values,same_turnout_pairs=possible,
                    collision_rate_same_turnout=values['collision_pairs']/possible if possible else ''))
            if not result['repeated_groups']:
                continue
            order=np.argsort(inv,kind='stable');starts=np.r_[0,np.cumsum(counts[:-1])]
            for group in np.flatnonzero(counts>=2):
                m=int(counts[group]);vector=unique[group].tolist()
                text=json.dumps(vector,separators=(',',':'))
                cluster_id=hashlib.sha256(text.encode()).hexdigest()
                ids=result['indices'][order[int(starts[group]):int(starts[group])+m]]
                places=[(str(data['uf'][i]),int(data['municipality'][i]),int(data['zone'][i]),int(data['place'][i])) for i in ids]
                cluster_writer.writerow(dict(identity,cluster_id=cluster_id,vector_json=text,multiplicity=m,
                    collision_pairs=comb(m,2),uf_count=len({p[0] for p in places}),
                    municipality_count=len({p[:2] for p in places}),zone_count=len({p[:3] for p in places}),place_count=len(set(places))))
                for i in ids:
                    uf=str(data['uf'][i]);municipality=int(data['municipality'][i])
                    member_writer.writerow(dict(identity,cluster_id=cluster_id,vector_json=text,uf=uf,municipality=municipality,
                        municipality_name=names.get(f'{uf}:{municipality}',''),
                        **{f:int(data[f][i]) for f in ['zone','section','place','source_line','aptos','turnout','abstentions','nominal']},
                        installed=int(data['installed'][i]),cancelled=int(data['cancelled'][i])))
    return inventory_rows,distributions,full_labels


def coverage_rows(data,by_uf):
    masks=population_masks(data);rows=[]
    for uf in [*sorted(set(map(str,data['uf']))),'BR']:
        selected=np.ones(len(data['aptos']),dtype=bool) if uf=='BR' else data['uf']==uf
        if uf=='BR':
            metrics={k:sum(r[k] for r in by_uf.values()) for k in ['groups','sections','nonsingleton_groups','nonsingleton_sections','informative_groups','informative_sections']}
        else:
            total=by_uf.get(uf,blank_total());metrics={k:total[k] for k in ['groups','sections','nonsingleton_groups','nonsingleton_sections','informative_groups','informative_sections']}
        row=dict(election_code=int(data['election_code']),turno=int(data['turno']),uf=uf,
            raw_details=int(selected.sum()),eligible=int((selected&masks['eligible']).sum()),
            small_positive=int((selected&masks['small_positive']).sum()),zero_activity=int((selected&masks['zero_activity']).sum()),
            other_excluded_positive=int((selected&masks['other_positive']).sum()),**metrics)
        rows.append(row)
    return rows


def run(root,out,cache):
    root,out,cache=map(lambda p:Path(p).resolve(),(root,out,cache))
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'Refusing nonempty output: {out}')
    out.mkdir(parents=True,exist_ok=True)
    manifest=dict(status='running',hypothesis='H3',started_at_utc=datetime.now(timezone.utc).isoformat(),
        method_sha256=digest(HERE/'METHOD.pt-BR.md'),numpy_version=np.__version__,python=sys.version,
        implementation_sha256={name:digest(HERE/'code'/name) for name in ['run_analysis.py','collision_statistics.py','load_data.py']},
        primary_family_size=2,simulation='None; exact rational moments and conservative Cantelli bounds',scenarios=SCENARIOS,
        signature_fields='Sorted nominal candidate counts, blank, null, legend, separate, turnout; extended adds electorate and abstentions')
    git=subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True)
    manifest['git_base_commit']=git.stdout.strip() if git.returncode==0 else None
    write_json(out/'manifest.json',manifest)
    try:
        dataset=load_data(root,cache)
        manifest.update(source_inputs=dataset['source_inputs'],source_counts=dataset['source_counts'],data_cache_fingerprint=dataset['cache_fingerprint'],
            candidates=[dict(election_code=r['election_code'],turno=r['turno'],numbers=r['candidate_numbers']) for r in dataset['rounds']])
        summaries=[];distributions=[];tests=[];sensitivity=[];coverage=[];bounds=[]
        with table_writer(out/'clusters.csv.gz',CLUSTER_COLUMNS) as clusters,table_writer(out/'cluster-members.csv.gz',MEMBER_COLUMNS) as members,table_writer(out/'strata.csv.gz',STRATA_COLUMNS) as strata:
            for data in dataset['rounds']:
                print(f'Round {data["turno"]}: exhaustive signature inventories',flush=True)
                counts,distribution,full_labels=emit_inventory(data,dataset['names'],clusters,members)
                summaries.extend(counts);distributions.extend(distribution)
                a_labels=np.unique(data['candidate_votes'],axis=0,return_inverse=True)[1]
                b_vectors=np.column_stack([data[f] for f in ['blank','null_votes','legend','separate','turnout']])
                b_labels=np.unique(b_vectors,axis=0,return_inverse=True)[1]
                for config in SCENARIOS:
                    print(f'Round {data["turno"]}: {config["name"]} local reference',flush=True)
                    total,by_uf=analyze_scenario(data,a_labels,b_labels,full_labels,config,strata if config['name']=='primary' else None)
                    row=total_row(data,total)
                    sensitivity.append(dict(scenario=config['name'],**{k:v for k,v in config.items() if k!='name'},**row))
                    if config['name']=='primary':
                        p=cantelli_bound(total['observed_pairs'],total['mean'],total['var'])
                        bounds.append(p)
                        row.update(p_bound=float(p) if p is not None else '',p_numerator=str(p.numerator) if p is not None else '',
                            p_denominator=str(p.denominator) if p is not None else '')
                        tests.append(row);coverage.extend(coverage_rows(data,by_uf))
        if len(tests)!=2:
            raise ValueError('Expected the predeclared two-round primary family')
        for row,p in zip(tests,holm_bounds(bounds)):
            row.update(p_holm=float(p) if p is not None else '',holm_numerator=str(p.numerator) if p is not None else '',
                holm_denominator=str(p.denominator) if p is not None else '',
                status='not_applicable' if p is None else 'excess_detected' if p<=Fraction(1,20) else 'not_detected')
        write_table(out/'inventory.csv',INVENTORY_COLUMNS,summaries)
        write_table(out/'turnout-distribution.csv',DISTRIBUTION_COLUMNS,distributions)
        write_table(out/'conditional-tests.csv',list(tests[0]),tests)
        write_table(out/'sensitivity.csv',list(sensitivity[0]),sensitivity)
        write_table(out/'coverage.csv',list(coverage[0]),coverage)
        summary=dict(inventory=summaries,conditional_tests=tests,coverage=[r for r in coverage if r['uf']=='BR'],
            sensitivity=sensitivity,candidates=manifest['candidates'],
            interpretation='National repetition inventory is descriptive; formal reference tests only repeated pairing of candidate/special-vote blocks within strict local/exact-nominal strata. Not a test of naturalness.')
        write_json(out/'summary.json',summary)
        manifest.update(status='completed',completed_at_utc=datetime.now(timezone.utc).isoformat(),
            artifact_sha256={p.name:digest(p) for p in sorted(out.iterdir()) if p.is_file() and p.name!='manifest.json'},
            compressed_csvs='gzip-compressed UTF-8 comma-delimited CSVs; full member and singleton-stratum inventories retained')
        write_json(out/'manifest.json',manifest)
        return summary
    except Exception as error:
        manifest.update(status='failed',error=str(error));write_json(out/'manifest.json',manifest)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cache',type=Path,default=HERE/'.work/data')
    args=parser.parse_args()
    summary=run(args.root,args.output,args.cache)
    print(json.dumps(dict(status='completed',primary=summary['conditional_tests']),ensure_ascii=False))
