#!/usr/bin/env python3
"""H2: local joint-tail screening and a conditional-independence benchmark."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from multiprocessing import get_context
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
EPS = 1e-12
BASE = dict(name='primary', ratio=1.25, phase=0.0, min_sections=30, tail_denominator=20, min_nominal=50)
SCENARIOS = [BASE,
    dict(BASE,name='tail_2_5_percent',tail_denominator=40),
    dict(BASE,name='tail_10_percent',tail_denominator=10),
    dict(BASE,name='min20',min_sections=20),
    dict(BASE,name='band1_5',ratio=1.5),
    dict(BASE,name='shift_half_band',phase=0.5),
    dict(BASE,name='nominal_100',min_nominal=100)]
STRATA_COLUMNS = ['election_code','turno','candidate','uf','municipality','zone','size_band','n',
    'min_aptos','max_aptos','turnout_tail_count','candidate_tail_count','joint_count','expected_joint',
    'variance','priority_count','median_turnout','median_candidate_share']
CASE_COLUMNS = ['election_code','turno','candidate','uf','municipality','municipality_name','zone','section',
    'place','source_line','aptos','turnout','nominal','candidate_votes','turnout_rate','candidate_share','size_band',
    'stratum_n','turnout_upper_count','candidate_upper_count','turnout_tail_fraction','candidate_tail_fraction',
    'median_turnout','median_candidate_share','turnout_delta_pp','share_delta_pp','priority','local_peer_count',
    'local_median_turnout','local_median_share','local_turnout_delta_pp','local_share_delta_pp','local_status']
COVERAGE_COLUMNS = ['election_code','turno','uf','raw_details','eligible','excluded_status','excluded_electorate',
    'excluded_turnout','excluded_nominal','no_peer_support','covered','n_strata_all','n_strata_supported']


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path,obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def write_csv(path,columns,rows):
    with Path(path).open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns,lineterminator='\n',extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def upper_counts(values):
    """Exact inclusive ranks for represented ratios; ties never broken by section ID."""
    _,inverse,counts=np.unique(values,return_inverse=True,return_counts=True)
    upper=np.cumsum(counts[::-1])[::-1]
    return upper[inverse]


def eligibility(data,min_nominal=50):
    reasons=np.zeros(len(data['aptos']),dtype=np.int8)
    reasons[~data['installed'] | data['cancelled']]=1
    reasons[(reasons==0)&(data['aptos']<50)]=2
    reasons[(reasons==0)&(data['turnout']<=0)]=3
    reasons[(reasons==0)&(data['nominal']<min_nominal)]=4
    return reasons==0,reasons


def strata_groups(data,eligible,ratio=1.25,phase=0.0):
    ids=np.flatnonzero(eligible)
    if not len(ids):
        return []
    bands=np.floor(np.log(data['aptos'][ids])/math.log(ratio)+phase).astype(np.int32)
    order=np.lexsort((bands,data['zone'][ids],data['municipality'][ids],data['uf'][ids]))
    ids,bands=ids[order],bands[order]
    cuts=np.flatnonzero((data['uf'][ids[1:]]!=data['uf'][ids[:-1]])|
        (data['municipality'][ids[1:]]!=data['municipality'][ids[:-1]])|
        (data['zone'][ids[1:]]!=data['zone'][ids[:-1]])|(bands[1:]!=bands[:-1]))+1
    starts=np.r_[0,cuts];ends=np.r_[cuts,len(ids)]
    return [(ids[a:b],int(bands[a])) for a,b in zip(starts,ends)]


def screening(data,config,names=None,detailed=False):
    eligible,reasons=eligibility(data,config['min_nominal'])
    all_groups=strata_groups(data,eligible,config['ratio'],config['phase'])
    supported=[(ids,band) for ids,band in all_groups if len(ids)>=config['min_sections']]
    covered=np.zeros(len(eligible),dtype=bool)
    rates=data['turnout']/np.maximum(data['aptos'],1)
    prepared=[]
    for ids,band in supported:
        covered[ids]=True
        upper=upper_counts(rates[ids])
        prepared.append((ids,band,upper,upper*config['tail_denominator']<=len(ids),float(np.median(rates[ids]))))
    coverage=[]
    for uf in [*sorted(set(map(str,data['uf']))),'BR']:
        mask=np.ones(len(eligible),dtype=bool) if uf=='BR' else data['uf']==uf
        row=dict(election_code=int(data['election_code']),turno=int(data['turno']),uf=uf,
                 raw_details=int(mask.sum()),eligible=int((mask&eligible).sum()),
                 excluded_status=int((mask&(reasons==1)).sum()),excluded_electorate=int((mask&(reasons==2)).sum()),
                 excluded_turnout=int((mask&(reasons==3)).sum()),excluded_nominal=int((mask&(reasons==4)).sum()),
                 covered=int((mask&covered).sum()),no_peer_support=int((mask&eligible&~covered).sum()),
                 n_strata_all=sum(uf=='BR' or str(data['uf'][ids[0]])==uf for ids,_ in all_groups),
                 n_strata_supported=sum(uf=='BR' or str(data['uf'][ids[0]])==uf for ids,_ in supported))
        coverage.append(row)
    outputs=[]
    for col,candidate in enumerate(data['candidate_numbers']):
        shares=data['candidate_votes'][:,col]/np.maximum(data['nominal'],1)
        rows,cases=[],[]
        priorities=set()
        for ids,band,t_upper,t_high,t_median in prepared:
            n=len(ids)
            c_upper=upper_counts(shares[ids]);c_high=c_upper*config['tail_denominator']<=n
            c_median=float(np.median(shares[ids]))
            joint=t_high&c_high
            priority=joint&(rates[ids]-t_median+EPS>=.05)&(shares[ids]-c_median+EPS>=.10)
            priorities.update(map(int,ids[priority]))
            a,b=int(t_high.sum()),int(c_high.sum())
            variance=float(a)*b*(n-a)*(n-b)/(float(n)*n*(n-1))
            row=dict(election_code=int(data['election_code']),turno=int(data['turno']),candidate=int(candidate),
                uf=str(data['uf'][ids[0]]),municipality=int(data['municipality'][ids[0]]),zone=int(data['zone'][ids[0]]),
                size_band=band,n=n,min_aptos=int(data['aptos'][ids].min()),max_aptos=int(data['aptos'][ids].max()),
                turnout_tail_count=a,candidate_tail_count=b,joint_count=int(joint.sum()),expected_joint=a*b/n,
                variance=variance,priority_count=int(priority.sum()),median_turnout=t_median,median_candidate_share=c_median)
            rows.append(row)
            if detailed:
                for position in np.flatnonzero(joint):
                    i=int(ids[position]);uf=str(data['uf'][i]);municipality=int(data['municipality'][i])
                    cases.append(dict(election_code=int(data['election_code']),turno=int(data['turno']),candidate=int(candidate),
                        uf=uf,municipality=municipality,municipality_name=(names or {}).get(f'{uf}:{municipality}',''),
                        zone=int(data['zone'][i]),section=int(data['section'][i]),place=int(data['place'][i]),
                        source_line=int(data['source_line'][i]),aptos=int(data['aptos'][i]),turnout=int(data['turnout'][i]),
                        nominal=int(data['nominal'][i]),candidate_votes=int(data['candidate_votes'][i,col]),
                        turnout_rate=float(rates[i]),candidate_share=float(shares[i]),size_band=band,stratum_n=n,
                        turnout_upper_count=int(t_upper[position]),candidate_upper_count=int(c_upper[position]),
                        turnout_tail_fraction=int(t_upper[position])/n,candidate_tail_fraction=int(c_upper[position])/n,
                        median_turnout=t_median,median_candidate_share=c_median,
                        turnout_delta_pp=100*(float(rates[i])-t_median),share_delta_pp=100*(float(shares[i])-c_median),
                        priority=int(priority[position]),local_peer_count='',local_median_turnout='',local_median_share='',
                        local_turnout_delta_pp='',local_share_delta_pp='',local_status='not_priority_not_assessed',_index=i))
        outputs.append(dict(candidate=int(candidate),strata=rows,cases=cases,priority_indices=priorities,
                            joint_count=sum(r['joint_count'] for r in rows),expected_joint=sum(r['expected_joint'] for r in rows),
                            variance=sum(r['variance'] for r in rows),priority_count=len(priorities)))
    return dict(config=config,coverage=coverage,covered_mask=covered,eligible_mask=eligible,candidates=outputs)


def local_context(data,screen):
    eligible=screen['eligible_mask'];ids=np.flatnonzero(eligible)
    order=np.lexsort((data['place'][ids],data['zone'][ids],data['municipality'][ids],data['uf'][ids]))
    ids=ids[order]
    cuts=np.flatnonzero((data['uf'][ids[1:]]!=data['uf'][ids[:-1]])|
        (data['municipality'][ids[1:]]!=data['municipality'][ids[:-1]])|
        (data['zone'][ids[1:]]!=data['zone'][ids[:-1]])|(data['place'][ids[1:]]!=data['place'][ids[:-1]]))+1
    groups={}
    for part in np.split(ids,cuts):
        if len(part):
            i=part[0];groups[(str(data['uf'][i]),int(data['municipality'][i]),int(data['zone'][i]),int(data['place'][i]))]=part
    rates=data['turnout']/np.maximum(data['aptos'],1)
    for col,result in enumerate(screen['candidates']):
        shares=data['candidate_votes'][:,col]/np.maximum(data['nominal'],1)
        for case in result['cases']:
            if not case['priority']:
                continue
            if case['place']<0:
                case['local_peer_count']=0
                case['local_status']='insufficient_peers'
                continue
            i=case['_index'];a=int(data['aptos'][i])
            peers=groups[(case['uf'],case['municipality'],case['zone'],case['place'])]
            peers=peers[(peers!=i)&(data['aptos'][peers].astype(np.int64)*5>=a*4)&(data['aptos'][peers].astype(np.int64)*4<=a*5)]
            case['local_peer_count']=int(len(peers))
            if len(peers)<4:
                case['local_status']='insufficient_peers'
                continue
            tm,cm=float(np.median(rates[peers])),float(np.median(shares[peers]))
            td,cd=float(rates[i])-tm,float(shares[i])-cm
            case.update(local_median_turnout=tm,local_median_share=cm,local_turnout_delta_pp=100*td,
                        local_share_delta_pp=100*cd,local_status='persists_both' if td+EPS>=.05 and cd+EPS>=.10 else 'attenuated_one_or_both')


def holm(values):
    order=sorted(range(len(values)),key=lambda i:values[i])
    adjusted=[0.0]*len(values);running=0.0
    for rank,i in enumerate(order):
        running=max(running,(len(values)-rank)*values[i]);adjusted[i]=min(1.0,running)
    return adjusted


def _simulate_task(task):
    n,a,b=(np.asarray(task[f],dtype=np.int64) for f in ['n','a','b'])
    cache=Path(task['cache']);meta=cache.with_suffix('.json')
    signature=hashlib.sha256(json.dumps({k:v for k,v in task.items() if k!='cache'},sort_keys=True).encode()).hexdigest()
    if cache.exists() or meta.exists():
        if not (cache.exists() and meta.exists()):
            raise ValueError(f'Incomplete reference cache: {cache}')
        saved=json.loads(meta.read_text())
        if saved['signature']!=signature or saved['sha256']!=sha256(cache):
            raise ValueError(f'Reference cache fingerprint mismatch: {cache}')
        counts=np.load(cache,allow_pickle=False)
        if counts.shape!=(task['simulations'],) or counts.dtype!=np.int64:
            raise ValueError('Invalid simulation count cache')
    else:
        rng=np.random.default_rng(np.random.SeedSequence([task['seed'],task['turno'],task['candidate']]))
        counts=np.zeros(task['simulations'],dtype=np.int64)
        informative=(a>0)&(b>0)
        n,a,b=n[informative],a[informative],b[informative]
        for start in range(0,len(counts),500):
            stop=min(start+500,len(counts))
            if len(n):
                counts[start:stop]=rng.hypergeometric(b,n-b,a,size=(stop-start,len(n))).sum(axis=1)
        cache.parent.mkdir(parents=True,exist_ok=True)
        np.save(cache,counts,allow_pickle=False)
        write_json(meta,dict(signature=signature,sha256=sha256(cache),simulations=task['simulations'],
                            seed=task['seed'],turno=task['turno'],candidate=task['candidate']))
    return dict(turno=task['turno'],candidate=task['candidate'],cache=str(cache),sha256=sha256(cache),
                low=float(np.quantile(counts,.025)),high=float(np.quantile(counts,.975)),
                exceedances=int(np.sum(counts>=task['observed'])))


def association(screens,cache,simulations=19999,seed=20261028,workers=4):
    if simulations<1 or seed<0 or workers<1:
        raise ValueError('Positive simulations/workers and nonnegative seed required')
    tasks=[];results=[]
    code_hash=sha256(__file__)
    for data,screen in screens:
        for candidate in screen['candidates']:
            rows=candidate['strata']
            tasks.append(dict(n=[r['n'] for r in rows],a=[r['turnout_tail_count'] for r in rows],
                b=[r['candidate_tail_count'] for r in rows],observed=candidate['joint_count'],
                turno=int(data['turno']),candidate=candidate['candidate'],seed=seed,simulations=simulations,
                code_sha256=code_hash,numpy=np.__version__,
                cache=str(cache/f'turn-{data["turno"]}-candidate-{candidate["candidate"]}.npy')))
            results.append(dict(election_code=int(data['election_code']),turno=int(data['turno']),candidate=candidate['candidate'],
                n_strata=len(rows),n_sections=sum(r['n'] for r in rows),observed_joint=candidate['joint_count'],
                expected_joint=candidate['expected_joint'],variance=candidate['variance'],priority_count=candidate['priority_count'],
                excess_joint=candidate['joint_count']-candidate['expected_joint'],
                observed_expected_ratio=candidate['joint_count']/candidate['expected_joint'] if candidate['expected_joint'] else '',
                simulations=simulations,seed=seed))
    if workers==1:
        references=list(map(_simulate_task,tasks))
    else:
        with ProcessPoolExecutor(max_workers=min(workers,len(tasks)),mp_context=get_context('spawn')) as pool:
            references=list(pool.map(_simulate_task,tasks))
    for result,reference in zip(results,references):
        result.update(reference_low_2_5=reference['low'],reference_high_97_5=reference['high'],exceedances=reference['exceedances'])
        applicable=result['variance']>0
        result['p_raw']=(1+reference['exceedances'])/(1+simulations) if applicable else ''
    adjusted=holm([r['p_raw'] if r['p_raw']!='' else 1.0 for r in results])
    for result,p in zip(results,adjusted):
        result['p_holm']=p if result['p_raw']!='' else ''
        result['status']='not_applicable' if result['p_raw']=='' else 'excess_detected' if p<=.05 else 'not_detected'
    return results,references


def run(root,out,cache,reference_cache,simulations=19999,seed=20261028,workers=4):
    from load_data import load_data
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'Refusing nonempty output: {out}')
    if simulations<1 or seed<0 or workers<1:
        raise ValueError('Invalid simulation settings')
    out.mkdir(parents=True,exist_ok=True)
    manifest=dict(status='running',started_at_utc=datetime.now(timezone.utc).isoformat(),hypothesis='H2',
        method_sha256=sha256(HERE/'METHOD.pt-BR.md'),
        implementation_sha256={p.name:sha256(p) for p in [Path(__file__),Path(__file__).with_name('load_data.py')]},
        numpy_version=np.__version__,python=sys.version,scenarios=SCENARIOS,
        simulations=simulations,seed=seed,workers=workers,primary_family_size=15)
    base_commit=subprocess.run(['git','rev-parse','HEAD'],cwd=root,text=True,capture_output=True)
    manifest['git_base_commit']=base_commit.stdout.strip() if base_commit.returncode==0 else None
    write_json(out/'manifest.json',manifest)
    try:
        dataset=load_data(root,cache)
        manifest['source_inputs']=dataset['source_inputs'];manifest['source_counts']=dataset['source_counts']
        manifest['data_cache_fingerprint']=dataset['cache_fingerprint']
        screens=[];all_strata=[];all_cases=[];coverage=[];sensitivity=[];uf_rows=[]
        for data in dataset['rounds']:
            print(f'Round {data["turno"]}: local screening',flush=True)
            primary=screening(data,BASE,dataset['names'],True)
            local_context(data,primary)
            screens.append((data,primary));coverage.extend(primary['coverage'])
            for candidate in primary['candidates']:
                all_strata.extend(candidate['strata']);all_cases.extend(candidate['cases'])
                for uf in sorted(set(map(str,data['uf']))):
                    groups=[r for r in candidate['strata'] if r['uf']==uf]
                    cases=[r for r in candidate['cases'] if r['uf']==uf]
                    uf_rows.append(dict(election_code=int(data['election_code']),turno=int(data['turno']),candidate=candidate['candidate'],uf=uf,
                        covered=sum(r['n'] for r in groups),n_strata=len(groups),joint_count=sum(r['joint_count'] for r in groups),
                        expected_joint=sum(r['expected_joint'] for r in groups),priority_count=sum(r['priority'] for r in cases),
                        local_persists=sum(r['local_status']=='persists_both' for r in cases),
                        local_attenuated=sum(r['local_status']=='attenuated_one_or_both' for r in cases),
                        local_insufficient=sum(r['local_status']=='insufficient_peers' for r in cases)))
            for config in SCENARIOS:
                other=primary if config['name']=='primary' else screening(data,config)
                for original,alternative in zip(primary['candidates'],other['candidates']):
                    shared=sum(bool(other['covered_mask'][i]) for i in original['priority_indices'])
                    retained=len(original['priority_indices']&alternative['priority_indices'])
                    sensitivity.append(dict(election_code=int(data['election_code']),turno=int(data['turno']),candidate=original['candidate'],
                        scenario=config['name'],ratio=config['ratio'],phase=config['phase'],min_sections=config['min_sections'],
                        tail_denominator=config['tail_denominator'],min_nominal=config['min_nominal'],
                        covered=int(other['covered_mask'].sum()),n_strata=len(alternative['strata']),joint_count=alternative['joint_count'],
                        expected_joint=alternative['expected_joint'],priority_count=alternative['priority_count'],
                        primary_priority_still_covered=shared,retained_primary_priority=retained))
        write_csv(out/'coverage.csv',COVERAGE_COLUMNS,coverage)
        write_csv(out/'strata.csv',STRATA_COLUMNS,all_strata)
        write_csv(out/'cases.csv',CASE_COLUMNS,all_cases)
        write_csv(out/'uf-summary.csv',list(uf_rows[0]),uf_rows)
        write_csv(out/'sensitivity.csv',list(sensitivity[0]),sensitivity)
        print(f'Conditional reference: {simulations} draws for 15 candidate-round comparisons',flush=True)
        tests,references=association(screens,reference_cache,simulations,seed,workers)
        if len(tests)!=15:
            raise ValueError('Expected the predeclared 15 candidate-round comparisons')
        write_csv(out/'association-tests.csv',list(tests[0]),tests)
        summary=dict(coverage=[r for r in coverage if r['uf']=='BR'],association_tests=tests,
            total_joint_cases=len(all_cases),total_priority_cases=sum(r['priority'] for r in all_cases),
            local_context={s:sum(r['local_status']==s for r in all_cases) for s in ['persists_both','attenuated_one_or_both','insufficient_peers','not_priority_not_assessed']},
            candidate_names=dataset['candidate_names'],scenarios=SCENARIOS,
            interpretation='Joint tails are descriptive. Rejection concerns conditional independence, not naturalness or manipulation.')
        write_json(out/'summary.json',summary)
        manifest.update(status='completed',completed_at_utc=datetime.now(timezone.utc).isoformat(),
            simulation_caches=references,artifact_sha256={p.name:sha256(p) for p in sorted(out.iterdir()) if p.is_file() and p.name!='manifest.json'})
        write_json(out/'manifest.json',manifest)
        return summary
    except Exception as error:
        manifest.update(status='failed',error=str(error));write_json(out/'manifest.json',manifest)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cache',type=Path,default=HERE/'.work/data')
    parser.add_argument('--reference-cache',type=Path,default=HERE/'.work/reference')
    parser.add_argument('--simulations',type=int,default=19999)
    parser.add_argument('--seed',type=int,default=20261028)
    parser.add_argument('--workers',type=int,default=min(4,os.cpu_count() or 1))
    args=parser.parse_args()
    summary=run(args.root.resolve(),args.output.resolve(),args.cache.resolve(),args.reference_cache.resolve(),args.simulations,args.seed,args.workers)
    print(json.dumps({k:summary[k] for k in ['total_joint_cases','total_priority_cases','local_context']},ensure_ascii=False))


if __name__=='__main__':
    main()
