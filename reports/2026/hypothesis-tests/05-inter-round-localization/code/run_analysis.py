#!/usr/bin/env python3
"""H5: paired section contrasts and allocation of changes between polling places."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import multiprocessing
from pathlib import Path
import subprocess

import numpy as np

from load_data import load_data,sha256
from pair_statistics import (MODELS,STATISTICS,EPS,PRIORITY_PP,MIN_PEERS,pair_sections,
    eligibility,changes,screening,prepare,concentration,score_variability,holm)

HERE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[5]
METHOD_SHA256='b654515cd18021c05fd855d4c01dc0cf976299ebe247446fd5828b30d5bd843f'
PAIR_COLUMNS=['uf','municipality','municipality_name','zone','section','source_line_1','source_line_2',
    'place_1','place_2','aptos_1','aptos_2','turnout_1','turnout_2','nominal_1','nominal_2',
    'v13_1','v22_1','v13_2','v22_2','f_1','f_2','other_nominal_1','q1','q2','delta_pp',
    'dp13_pp','dp22_pp','gain_v13','gain_v22','eligible','exclusion_reason']
SECTION_COLUMNS=['uf','municipality','zone','section','place','q1','q2','delta_pp','dp13_pp','dp22_pp',
    'strict_peer_count','strict_median','strict_contrast','strict_priority','priority_candidate',
    'broad_peer_count','broad_median','broad_contrast','broad_priority']
GROUP_COLUMNS=['model','uf','municipality','zone','size_band','baseline_bin','n','places','target_slots',
    'delta_mean','delta_min','delta_max','variable_delta','potential']
PLACE_COLUMNS=['model','uf','municipality','zone','place','n','target','delta_mean','expected_delta_mean',
    'residual_sum','residual_mean','rms_component','max_component','strict_supported','strict_priorities',
    'aptos_1_total','nominal_1_total','nominal_2_total']
COVERAGE_COLUMNS=['model','uf','cohort_pairs','places','targets','target_pairs','groups','groups_with_peers',
    'peer_pairs','multi_place_groups','multi_place_pairs','potential_groups','potential_pairs',
    'target_pairs_in_potential_groups','reachable_targets']
TEST_COLUMNS=['model','statistic','observed','simulation_mean','simulation_q025','simulation_q975',
    'exceedances','simulations','p_raw','p_holm','detected','status','applicability_reason']
SENSITIVITY_COLUMNS=['scenario','model','bins','finalist_floor','unchanged_aptos','min_target',
    'cohort_pairs','targets','target_pairs','RMS','MAX','strict_supported','strict_priorities',
    'broad_supported','broad_priorities','potential_pairs','target_pairs_in_potential_groups']
_WORKER=None


def json_write(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


@contextmanager
def csv_writer(path,columns):
    path=Path(path)
    with path.open('wb') as raw:
        compressed=gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) if path.suffix=='.gz' else raw
        with io.TextIOWrapper(compressed,encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns,lineterminator='\n',extrasaction='ignore')
            writer.writeheader();yield writer


def write_csv(path,columns,rows):
    with csv_writer(path,columns) as writer:
        writer.writerows(rows)


def finite(value):
    return float(value) if np.isfinite(value) else ''


def pairing_rows(joined):
    first,second=joined['rounds'];p=joined['pairs']
    for uf in ['BR',*sorted(set(first['uf'].tolist())|set(second['uf'].tolist()))]:
        count=lambda array:int(len(array)) if uf=='BR' else int(np.count_nonzero(array==uf))
        yield dict(uf=uf,round1_records=count(first['uf']),round2_records=count(second['uf']),matched_pairs=count(p['uf']),
            only_round1=count(first['uf'][joined['unmatched'][0][2]]),only_round2=count(second['uf'][joined['unmatched'][1][2]]))


def eligibility_rows(pairs):
    mask,reasons,basic=eligibility(pairs)
    names=['section_status','aptos_below_50','nonpositive_turnout','nominal_below_50','finalists_below_floor',
           'missing_place','changed_place','aptos_ratio']
    for uf in ['BR',*sorted(set(pairs['uf'].tolist()))]:
        use=np.ones(len(mask),dtype=bool) if uf=='BR' else pairs['uf']==uf
        chosen=use&mask
        row=dict(uf=uf,matched_pairs=int(use.sum()),basic_eligible=int((use&basic).sum()),cohort_pairs=int(chosen.sum()))
        row.update({f'excluded_{name}':int((use&(reasons==name)).sum()) for name in names})
        row.update(changed_aptos_cohort=int((chosen&(pairs['aptos_1']!=pairs['aptos_2'])).sum()),
            nominal_1=int(pairs['nominal_1'][chosen].sum(dtype=np.int64)),nominal_2=int(pairs['nominal_2'][chosen].sum(dtype=np.int64)))
        yield row


def raw_pair_rows(pairs,names):
    mask,reasons,_=eligibility(pairs)
    for i in range(len(mask)):
        row={field:str(pairs[field][i]) if field=='uf' else int(pairs[field][i]) for field in
            ['uf','municipality','zone','section','source_line_1','source_line_2','place_1','place_2',
             'aptos_1','aptos_2','turnout_1','turnout_2','nominal_1','nominal_2','v13_1','v22_1','v13_2','v22_2','f_1','f_2']}
        row['municipality_name']=names.get(f'{row["uf"]}:{row["municipality"]}','')
        f1,f2=row['f_1'],row['f_2'];n1,n2=row['nominal_1'],row['nominal_2']
        row.update(other_nominal_1=n1-f1,q1=100*row['v13_1']/f1 if f1 else '',q2=100*row['v13_2']/f2 if f2 else '',
            delta_pp=100*(row['v13_2']/f2-row['v13_1']/f1) if f1 and f2 else '',
            dp13_pp=100*(row['v13_2']/n2-row['v13_1']/n1) if n1 and n2 else '',
            dp22_pp=100*(row['v22_2']/n2-row['v22_1']/n1) if n1 and n2 else '',
            gain_v13=row['v13_2']-row['v13_1'],gain_v22=row['v22_2']-row['v22_1'],
            eligible=bool(mask[i]),exclusion_reason=str(reasons[i]))
        yield row


def section_rows(pairs,ids,screen):
    for j,i in enumerate(ids):
        row={field:str(pairs[field][i]) if field=='uf' else int(pairs[field][i]) for field in ['uf','municipality','zone','section']}
        row.update(place=int(pairs['place_1'][i]),q1=float(screen['q1'][j]),q2=float(screen['q2'][j]),
            delta_pp=float(screen['delta'][j]),dp13_pp=float(screen['dp13'][j]),dp22_pp=float(screen['dp22'][j]))
        for context in ('strict','broad'):
            row.update({f'{context}_peer_count':int(screen[f'{context}_peer_count'][j]),
                f'{context}_median':finite(screen[f'{context}_median'][j]),
                f'{context}_contrast':finite(screen[f'{context}_contrast'][j]),
                f'{context}_priority':bool(screen[f'{context}_priority'][j])})
        row['priority_candidate']=13 if row['strict_priority'] and screen['strict_contrast'][j]>0 else 22 if row['strict_priority'] else ''
        yield row


def case_summary_rows(pairs,ids,screen):
    ufs=pairs['uf'][ids]
    for uf in ['BR',*sorted(set(ufs.tolist()))]:
        use=np.ones(len(ids),dtype=bool) if uf=='BR' else ufs==uf
        row=dict(uf=uf,cohort_pairs=int(use.sum()))
        for context in ('strict','broad'):
            priority=screen[f'{context}_priority']&use
            row.update({f'{context}_supported':int((use&(screen[f'{context}_peer_count']>=MIN_PEERS)).sum()),
                f'{context}_priorities':int(priority.sum()),
                f'{context}_priorities_13':int((priority&(screen[f'{context}_contrast']>0)).sum()),
                f'{context}_priorities_22':int((priority&(screen[f'{context}_contrast']<0)).sum())})
        yield row


def distribution_rows(pairs,ids,screen):
    ufs=pairs['uf'][ids]
    fields={'delta_pp':screen['delta'],'dp13_pp':screen['dp13'],'dp22_pp':screen['dp22'],
            'strict_contrast':screen['strict_contrast'],'broad_contrast':screen['broad_contrast']}
    for uf in ['BR',*sorted(set(ufs.tolist()))]:
        use=np.ones(len(ids),dtype=bool) if uf=='BR' else ufs==uf
        for metric,values in fields.items():
            chosen=values[use&np.isfinite(values)]
            q=np.quantile(chosen,[0,.025,.25,.5,.75,.975,1]) if len(chosen) else ['']*7
            yield dict(uf=uf,metric=metric,n=len(chosen),**dict(zip(['min','q025','q25','median','q75','q975','max'],q)),
                mean=float(chosen.mean()) if len(chosen) else '')


def histograms(screen):
    for metric,values in [('delta_pp',screen['delta']),('dp13_pp',screen['dp13']),('dp22_pp',screen['dp22']),
                          ('strict_contrast',screen['strict_contrast']),('broad_contrast',screen['broad_contrast'])]:
        chosen=values[np.isfinite(values)];limit=200 if 'contrast' in metric else 100
        counts,edges=np.histogram(chosen,bins=np.arange(-limit,limit+1))
        if counts.sum()!=len(chosen):
            raise ArithmeticError('Histogram lost values outside mathematical bounds')
        for i,count in enumerate(counts):
            yield dict(metric=metric,left_pp=int(edges[i]),right_pp=int(edges[i+1]),sections=int(count),denominator=len(chosen))


def group_rows(prepared):
    pairs,ids,group=prepared['pairs'],prepared['ids'],prepared['group']
    for g,size in enumerate(group['sizes']):
        j=group['first'][g];i=ids[j];members=group['order'][group['starts'][g]:group['starts'][g+1]]
        yield dict(model=prepared['model'],uf=str(pairs['uf'][i]),municipality=int(pairs['municipality'][i]),zone=int(pairs['zone'][i]),
            size_band=int(prepared['band'][j]),baseline_bin=int(prepared['initial_band'][j]) if prepared['model']=='zone_size_baseline' else -1,
            n=int(size),places=int(prepared['group_place_count'][g]),target_slots=int(prepared['group_target_slots'][g]),
            delta_mean=float(prepared['mean'][g]),delta_min=float(prepared['change']['delta'][members].min()),
            delta_max=float(prepared['change']['delta'][members].max()),variable_delta=bool(prepared['variable'][g]),potential=bool(prepared['potential'][g]))


def place_rows(prepared,screen):
    pairs,ids,places=prepared['pairs'],prepared['ids'],prepared['place']
    _,sums=concentration(prepared)
    total_d=np.bincount(places['labels'],weights=prepared['change']['delta'])
    strict_support=np.bincount(places['labels'],weights=screen['strict_peer_count']>=MIN_PEERS).astype(np.int64)
    strict_cases=np.bincount(places['labels'],weights=screen['strict_priority']).astype(np.int64)
    totals={field:np.bincount(places['labels'],weights=pairs[field][ids]).astype(np.int64) for field in ['aptos_1','nominal_1','nominal_2']}
    for l,n in enumerate(places['sizes']):
        i=ids[places['first'][l]];s=float(sums[l])
        yield dict(model=prepared['model'],uf=str(pairs['uf'][i]),municipality=int(pairs['municipality'][i]),zone=int(pairs['zone'][i]),
            place=int(pairs['place_1'][i]),n=int(n),target=bool(prepared['targets'][l]),delta_mean=float(total_d[l]/n),
            expected_delta_mean=float((total_d[l]-s)/n),residual_sum=s,residual_mean=s/n,rms_component=s*s/n,
            max_component=abs(s)/np.sqrt(n),strict_supported=int(strict_support[l]),strict_priorities=int(strict_cases[l]),
            **{f'{field}_total':int(value[l]) for field,value in totals.items()})


def coverage_rows(prepared):
    p,ids,group,places=prepared['pairs'],prepared['ids'],prepared['group'],prepared['place']
    uf_g=p['uf'][ids[group['first']]];uf_l=p['uf'][ids[places['first']]]
    for uf in ['BR',*sorted(set(p['uf'][ids].tolist()))]:
        guse=np.ones(len(group['sizes']),dtype=bool) if uf=='BR' else uf_g==uf
        luse=np.ones(len(places['sizes']),dtype=bool) if uf=='BR' else uf_l==uf
        use=np.ones(len(ids),dtype=bool) if uf=='BR' else p['uf'][ids]==uf
        potential=guse&prepared['potential'];pids=potential[group['labels']]
        reachable=np.unique(places['labels'][pids&prepared['targets'][places['labels']]])
        yield dict(model=prepared['model'],uf=uf,cohort_pairs=int(use.sum()),places=int(luse.sum()),targets=int((luse&prepared['targets']).sum()),
            target_pairs=int(places['sizes'][luse&prepared['targets']].sum()),groups=int(guse.sum()),
            groups_with_peers=int((guse&(group['sizes']>1)).sum()),peer_pairs=int(group['sizes'][guse&(group['sizes']>1)].sum()),
            multi_place_groups=int((guse&(prepared['group_place_count']>1)).sum()),
            multi_place_pairs=int(group['sizes'][guse&(prepared['group_place_count']>1)].sum()),
            potential_groups=int(potential.sum()),potential_pairs=int(group['sizes'][potential].sum()),
            target_pairs_in_potential_groups=int(np.sum(prepared['group_target_slots'][potential])),reachable_targets=len(reachable))


def worker_init(state,directory):
    global _WORKER
    _WORKER=dict(state);_WORKER['scores']=np.load(Path(directory)/'scores.npy',mmap_mode='r+')


def simulate_chunk(bounds):
    state=_WORKER;n=len(state['residual']);prefix={}
    for rep in range(*bounds):
        rng=np.random.default_rng(np.random.SeedSequence([state['seed'],state['model_id']],spawn_key=(rep,)))
        assignment=np.arange(n,dtype=np.int32)
        for bucket in state['buckets']:
            assignment[bucket.ravel()]=rng.permuted(bucket,axis=1).ravel()
        sums=np.bincount(state['place_labels'],weights=state['residual'][assignment],minlength=len(state['place_sizes']))
        target=state['targets'];sizes=state['place_sizes']
        if np.any(target):
            state['scores'][rep]=[np.sqrt(np.sum(sums[target]**2/sizes[target])/sizes[target].sum()),
                                  np.max(np.abs(sums[target])/np.sqrt(sizes[target]))]
        else:
            state['scores'][rep]=0.0
        if rep<2:
            prefix[str(rep)]=hashlib.sha256(assignment.astype('<i4').tobytes()).hexdigest()
    state['scores'].flush()
    return dict(done=bounds[1]-bounds[0],assignment_prefix=prefix)


def simulations(prepared,directory,b,seed,workers,fingerprint):
    directory=Path(directory)
    if directory.exists() and any(directory.iterdir()):
        path=directory/'metadata.json'
        if not path.exists():
            raise ValueError('Unknown simulation cache; choose a new directory')
        meta=json.loads(path.read_text())
        if meta.get('status')!='completed' or meta.get('fingerprint')!=fingerprint or meta.get('scores_sha256')!=sha256(directory/'scores.npy'):
            raise ValueError('Incomplete, different or corrupted simulation cache; choose a new directory')
        return meta
    directory.mkdir(parents=True,exist_ok=True)
    meta=dict(status='running',fingerprint=fingerprint,model=prepared['model'],model_id=MODELS[prepared['model']],
        simulations=b,seed=seed,statistics=STATISTICS,assignment_prefix={})
    json_write(directory/'metadata.json',meta)
    array=np.lib.format.open_memmap(directory/'scores.npy',mode='w+',dtype=np.float64,shape=(b,2));array.flush();del array
    state=dict(residual=prepared['residual'],buckets=prepared['buckets'],place_labels=prepared['place']['labels'],
               place_sizes=prepared['place']['sizes'],targets=prepared['targets'],seed=seed,model_id=MODELS[prepared['model']])
    chunks=[(start,min(start+50,b)) for start in range(0,b,50)];done=0
    if workers==1:
        worker_init(state,str(directory))
        for chunk in chunks:
            result=simulate_chunk(chunk);done+=result['done'];meta['assignment_prefix'].update(result['assignment_prefix'])
            if done%500==0 or done==b:print(f'{prepared["model"]}: {done}/{b}',flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn'),initializer=worker_init,initargs=(state,str(directory))) as pool:
            for task in as_completed([pool.submit(simulate_chunk,chunk) for chunk in chunks]):
                result=task.result();done+=result['done'];meta['assignment_prefix'].update(result['assignment_prefix'])
                if done%500==0 or done==b:print(f'{prepared["model"]}: {done}/{b}',flush=True)
    meta.update(status='completed',scores_sha256=sha256(directory/'scores.npy'))
    json_write(directory/'metadata.json',meta)
    return meta


def sensitivity_row(prepared,screen,scenario,finalist_floor=50,unchanged=False):
    score,_=concentration(prepared);potential=prepared['potential']
    return dict(scenario=scenario,model=prepared['model'],bins=prepared['bins'],finalist_floor=finalist_floor,
        unchanged_aptos=unchanged,min_target=prepared['min_target'],cohort_pairs=len(prepared['ids']),
        targets=int(prepared['targets'].sum()),target_pairs=int(prepared['place']['sizes'][prepared['targets']].sum()),RMS=float(score[0]),MAX=float(score[1]),
        strict_supported=int((screen['strict_peer_count']>=MIN_PEERS).sum()),strict_priorities=int(screen['strict_priority'].sum()),
        broad_supported=int((screen['broad_peer_count']>=MIN_PEERS).sum()),broad_priorities=int(screen['broad_priority'].sum()),
        potential_pairs=int(prepared['group']['sizes'][potential].sum()),target_pairs_in_potential_groups=int(prepared['group_target_slots'][potential].sum()))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT);parser.add_argument('--output',type=Path,default=HERE/'evidence/analysis')
    parser.add_argument('--cache',type=Path,default=HERE/'.work/data');parser.add_argument('--simulation-cache',type=Path,default=HERE/'.work/simulations')
    parser.add_argument('--simulations',type=int,default=4999);parser.add_argument('--seed',type=int,default=20261029);parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    if args.simulations<1 or not 1<=args.workers<=4:parser.error('Use positive simulations and 1–4 workers')
    if sha256(HERE/'METHOD.pt-BR.md')!=METHOD_SHA256:parser.error('Frozen H5 method hash differs; review/version the protocol')
    if args.output.exists() and any(args.output.iterdir()):parser.error('Refusing a nonempty output directory')
    args.output.mkdir(parents=True,exist_ok=True)
    core={name:sha256(HERE/'code'/name) for name in ['load_data.py','pair_statistics.py','run_analysis.py']}
    manifest=dict(status='running',started_at_utc=datetime.now(timezone.utc).isoformat(),method_sha256=METHOD_SHA256,implementation_sha256=core,
        git_base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.root,text=True).strip(),
        parameters=dict(simulations=args.simulations,seed=args.seed,workers=args.workers,models=MODELS,statistics=STATISTICS,family_size=4,
            epsilon_pp=EPS,priority_pp=PRIORITY_PP,min_other_peers=MIN_PEERS,baseline_bins=20,min_target=5,
            paired_payload='Both rounds move together; observed marginal changes are preserved',
            rng='PCG64; SeedSequence([seed,model_id],spawn_key=(repetition,))'),simulation_caches=[])
    json_write(args.output/'manifest.json',manifest)
    loaded=load_data(args.root,args.cache);joined=pair_sections(loaded['rounds']);pairs=joined['pairs']
    mask,_,_=eligibility(pairs);ids=np.flatnonzero(mask);screen=screening(pairs,ids)
    print(f'Paired {len(pairs["uf"])} physical keys; cohort {len(ids)}',flush=True)
    manifest.update(source_inputs=loaded['source_inputs'],source_counts=loaded['source_counts'],data_fingerprint=loaded['cache_fingerprint'])
    pairing=list(pairing_rows(joined));elig=list(eligibility_rows(pairs));cases=list(case_summary_rows(pairs,ids,screen))
    write_csv(args.output/'pairing.csv',list(pairing[0]),pairing)
    write_csv(args.output/'eligibility.csv',list(elig[0]),elig)
    unmatched=[]
    for turn,rd,indices in joined['unmatched']:
        for i in indices:
            unmatched.append(dict(present_in_round=turn,**{field:str(rd[field][i]) if field=='uf' else int(rd[field][i]) for field in ['uf','municipality','zone','section']},source_line=int(rd['source_line'][i])))
    write_csv(args.output/'unmatched.csv',['present_in_round','uf','municipality','zone','section','source_line'],unmatched)
    write_csv(args.output/'paired-sections.csv.gz',PAIR_COLUMNS,raw_pair_rows(pairs,loaded['names']))
    write_csv(args.output/'section-screening.csv.gz',SECTION_COLUMNS,section_rows(pairs,ids,screen))
    write_csv(args.output/'case-summary.csv',list(cases[0]),cases)
    distributions=list(distribution_rows(pairs,ids,screen));write_csv(args.output/'distribution.csv',list(distributions[0]),distributions)
    hist=list(histograms(screen));write_csv(args.output/'histograms.csv',list(hist[0]),hist)
    x=np.minimum(99,100*pairs['v13_1'][ids]//pairs['f_1'][ids]);y=np.minimum(99,100*pairs['v13_2'][ids]//pairs['f_2'][ids])
    grid=np.bincount(x*100+y,minlength=10000).reshape(100,100)
    write_csv(args.output/'transition-grid.csv',['q1_low_pp','q1_high_pp','q2_low_pp','q2_high_pp','sections'],
        (dict(q1_low_pp=i,q1_high_pp=i+1,q2_low_pp=j,q2_high_pp=j+1,sections=int(grid[i,j])) for i in range(100) for j in range(100)))
    tests=[];coverage=[];sens=[]
    with csv_writer(args.output/'concentration-groups.csv.gz',GROUP_COLUMNS) as group_writer,csv_writer(args.output/'place-results.csv.gz',PLACE_COLUMNS) as place_writer:
        for model in MODELS:
            prepared=prepare(pairs,model);observed,_=concentration(prepared)
            print(f'Observed {model}: {len(prepared["group"]["sizes"])} strata, {int(prepared["targets"].sum())} targets',flush=True)
            group_writer.writerows(group_rows(prepared));place_writer.writerows(place_rows(prepared,screen));coverage.extend(coverage_rows(prepared))
            sens.append(sensitivity_row(prepared,screen,'primary'))
            fingerprint=hashlib.sha256(json.dumps(dict(core=core,method=METHOD_SHA256,data=loaded['cache_fingerprint'],model=model,
                simulations=args.simulations,seed=args.seed),sort_keys=True).encode()).hexdigest()
            directory=args.simulation_cache/model
            meta=simulations(prepared,directory,args.simulations,args.seed,args.workers,fingerprint)
            manifest['simulation_caches'].append(dict(path=str(directory.relative_to(args.root)) if directory.is_relative_to(args.root) else str(directory),
                metadata=meta,metadata_sha256=sha256(directory/'metadata.json')))
            draws=np.load(directory/'scores.npy',mmap_mode='r');possible,reasons=score_variability(prepared,draws,observed)
            quantiles=np.quantile(draws,[.025,.975],axis=0);means=draws.mean(axis=0)
            for k,stat in enumerate(STATISTICS):
                exceed=int(np.count_nonzero(draws[:,k]>=observed[k]-EPS))
                tests.append(dict(model=model,statistic=stat,observed=float(observed[k]),simulation_mean=float(means[k]),
                    simulation_q025=float(quantiles[0,k]),simulation_q975=float(quantiles[1,k]),exceedances=exceed,simulations=args.simulations,
                    p_raw=(1+exceed)/(1+args.simulations) if possible[k] else '',p_holm='',detected='',
                    status='applicable' if possible[k] else 'not_applicable',applicability_reason=reasons[k]))
    adjusted=holm([r['p_raw'] if r['status']=='applicable' else 1 for r in tests])
    for row,p in zip(tests,adjusted):
        if row['status']=='applicable':row.update(p_holm=float(p),detected=bool(p<=.05),status='detected' if p<=.05 else 'not_detected')
    write_csv(args.output/'tests.csv',TEST_COLUMNS,tests);write_csv(args.output/'coverage.csv',COVERAGE_COLUMNS,coverage)
    configs=[('baseline_2_5pp','zone_size_baseline',40,50,False,5),('baseline_10pp','zone_size_baseline',10,50,False,5)]
    configs += [(scenario,model,20,floor,unchanged,target) for scenario,floor,unchanged,target in
                [('unchanged_aptos',50,True,5),('finalists_100',100,False,5),('targets_10',50,False,10)] for model in MODELS]
    screen_cache={(20,50,False):screen}
    for scenario,model,bins,floor,unchanged,target in configs:
        prepared=prepare(pairs,model,bins=bins,finalist_floor=floor,unchanged_aptos=unchanged,min_target=target)
        key=bins,floor,unchanged
        if key not in screen_cache:screen_cache[key]=screening(pairs,prepared['ids'],bins)
        sens.append(sensitivity_row(prepared,screen_cache[key],scenario,floor,unchanged))
    write_csv(args.output/'sensitivity.csv',SENSITIVITY_COLUMNS,sens)
    overall=next(row for row in cases if row['uf']=='BR')
    summary=dict(matched_pairs=len(pairs['uf']),cohort_pairs=len(ids),family_size=4,
        primary_detected=sum(r['status']=='detected' for r in tests),primary_not_detected=sum(r['status']=='not_detected' for r in tests),
        primary_not_applicable=sum(r['status']=='not_applicable' for r in tests),case_summary=overall,
        paired_elections=[pairs['election_1'],pairs['election_2']],
        interpretation='Section screening is descriptive; formal tests concern allocation between places and preserve marginal changes',
        sensitivity_validation='See independent-validation.json for separate verification scope')
    json_write(args.output/'summary.json',summary)
    for source in loaded['source_inputs'].values():
        if sha256(args.root/source['path'])!=source['sha256']:raise ValueError('Original input changed during analysis')
    manifest.update(status='completed',completed_at_utc=datetime.now(timezone.utc).isoformat(),numpy_version=np.__version__,
        artifacts={p.name:dict(size_bytes=p.stat().st_size,sha256=sha256(p)) for p in sorted(args.output.iterdir()) if p.name!='manifest.json'})
    json_write(args.output/'manifest.json',manifest)
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
