#!/usr/bin/env python3
"""H4: minute-level residual ordering under two explicit local references."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
import csv
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
import multiprocessing
from pathlib import Path
import subprocess

import numpy as np

from load_data import load_data, sha256
from temporal_statistics import (MODELS, SOURCES, STATISTICS, P_TOLERANCE,
    RESIDUAL_CLOSURE_VOTES, prepare, cohort, minute_values, scores_from_minutes,
    gradual_variance, timing, holm, score_variability)

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
METHOD_SHA256 = '8848241e631bf8f714877d215a5276bc46afa1fc59042b66815a06122bb476e9'
CURVE_COLUMNS = ['model','election_code','turno','source','candidate','minute',
    'sections_cumulative','nominal_cumulative','votes_cumulative','expected_cumulative',
    'residual_cumulative','share','composition_share','residual_current_pp',
    'residual_final_pp','minute_residual_pp_final']
GROUP_COLUMNS = ['model','election_code','turno','uf','municipality','zone','place','size_band',
    'n','nominal_total','candidate_votes_json','min_aptos','max_aptos','first_minute_min',
    'first_minute_max','bu_minute_min','bu_minute_max','first_distinct_minutes','bu_distinct_minutes']
COVERAGE_COLUMNS = ['model','election_code','turno','source','candidate','uf','detail_sections',
    'eligible_basic','cohort_sections','groups','sections_with_peers','sections_time_varied',
    'informative_groups','informative_sections','nominal_total']
TEST_COLUMNS = ['model','election_code','turno','candidate','statistic','observed','signed_observed',
    'peak_minute','simulations','exceedances','p_raw','p_holm','detected','status',
    'simulation_mean','simulation_q025','simulation_q975','informative_sections','applicability_reason']
BAND_COLUMNS = ['model','election_code','turno','source','candidate','stage','cutoff_minute',
    'progress_actual','observed','simulation_mean','simulation_q025','simulation_q975']
SENSITIVITY_COLUMNS = ['scenario','model','election_code','turno','source','candidate',
    'G_signed','G','C','M','C_minute','M_minute','cohort_sections','nominal_total','informative_sections']
MILESTONE_COLUMNS = ['model','election_code','turno','source','candidate','stage','cutoff_minute',
    'progress_actual','sections_cumulative','nominal_cumulative','share','composition_share',
    'residual_current_pp','residual_final_pp']
UF_COLUMNS = ['model','election_code','turno','source','candidate','uf','sections','nominal_total',
    'final_share','G_signed','C','M','C_minute','M_minute']
_WORKER = None


def json_write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


@contextmanager
def csv_writer(path, columns):
    path = Path(path)
    with path.open('wb') as raw:
        compressed = gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) if path.suffix == '.gz' else raw
        with io.TextIOWrapper(compressed, encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n', extrasaction='ignore')
            writer.writeheader()
            yield writer


def write_csv(path, columns, rows):
    with csv_writer(path, columns) as writer:
        writer.writerows(rows)


def minute_text(value):
    return (datetime(1970,1,1)+timedelta(minutes=int(value))).strftime('%Y-%m-%d %H:%M:00')


def common(prepared):
    data = prepared['data']
    return dict(model=prepared['model'], election_code=int(data['election_code']), turno=int(data['turno']))


def informative(prepared, source):
    return prepared['variable'] & prepared['sources'][source]['time_varied'][:,None]


def group_rows(prepared):
    data, ids = prepared['data'], prepared['ids']
    for g, size in enumerate(prepared['sizes']):
        members = ids[prepared['order'][prepared['starts'][g]:prepared['starts'][g+1]]]
        i = members[0]
        yield dict(common(prepared), uf=str(data['uf'][i]), municipality=int(data['municipality'][i]),
            zone=int(data['zone'][i]), place=int(data['place'][i]) if prepared['model']!='zone_size' else -1,
            size_band=int(prepared['band'][prepared['first'][g]]), n=int(size),
            nominal_total=int(prepared['group_n'][g]),
            candidate_votes_json=json.dumps(prepared['group_v'][g].tolist(), separators=(',',':')),
            min_aptos=int(data['aptos'][members].min()), max_aptos=int(data['aptos'][members].max()),
            first_minute_min=int(prepared['sources']['first_time']['group_min'][g]),
            first_minute_max=int(prepared['sources']['first_time']['group_max'][g]),
            bu_minute_min=int(prepared['sources']['bu_time']['group_min'][g]),
            bu_minute_max=int(prepared['sources']['bu_time']['group_max'][g]),
            first_distinct_minutes=int(prepared['sources']['first_time']['group_distinct'][g]),
            bu_distinct_minutes=int(prepared['sources']['bu_time']['group_distinct'][g]))


def coverage_rows(prepared):
    data, ids, sizes = prepared['data'], prepared['ids'], prepared['sizes']
    uf_groups = data['uf'][ids[prepared['first']]]
    for source in SOURCES:
        time = prepared['sources'][source]
        info = informative(prepared, source)
        for uf in ['BR', *sorted(set(data['uf'].tolist()))]:
            all_rows = np.ones(len(data['uf']),dtype=bool) if uf=='BR' else data['uf']==uf
            group_use = np.ones(len(sizes),dtype=bool) if uf=='BR' else uf_groups==uf
            selected = all_rows[ids]
            for k, candidate in enumerate(data['candidate_numbers']):
                yield dict(common(prepared),source=source,candidate=int(candidate),uf=uf,
                    detail_sections=int(all_rows.sum()),eligible_basic=int((all_rows & prepared['basic']).sum()),
                    cohort_sections=int(selected.sum()), groups=int(group_use.sum()),
                    sections_with_peers=int(sizes[group_use & (sizes>1)].sum()),
                    sections_time_varied=int(sizes[group_use & time['time_varied']].sum()),
                    informative_groups=int((group_use & info[:,k]).sum()),
                    informative_sections=int(sizes[group_use & info[:,k]].sum()),
                    nominal_total=int(prepared['nominal'][selected].sum()))


def observed(prepared, curve_writer=None, milestone_rows=None, uf_rows=None):
    result = {}
    for source in SOURCES:
        time = prepared['sources'][source]
        arrival = minute_values(prepared['residual'],time)
        scores, signed, ci, mi, cumulative = scores_from_minutes(arrival,time,prepared['final_nominal'])
        result[source] = dict(scores=scores,signed=signed,ci=ci,mi=mi,cumulative=cumulative,arrival=arrival)
        cum_nominal = minute_values(prepared['nominal'],time)[:,0].cumsum().astype(np.int64)
        cum_votes = minute_values(prepared['votes'],time).cumsum(axis=0).astype(np.int64)
        for k, candidate in enumerate(prepared['data']['candidate_numbers']):
            for m in range(len(time['counts'])):
                denominator = int(cum_nominal[m])
                residual = float(cumulative[m,k])
                share = 100*int(cum_votes[m,k])/denominator
                expected = float(cum_votes[m,k]-residual)
                row = dict(common(prepared),source=source,candidate=int(candidate),
                    minute=minute_text(time['minute_min']+m),sections_cumulative=int(time['cumulative'][m]),
                    nominal_cumulative=denominator,votes_cumulative=int(cum_votes[m,k]),
                    expected_cumulative=expected,residual_cumulative=residual,share=share,
                    composition_share=100*expected/denominator,residual_current_pp=100*residual/denominator,
                    residual_final_pp=100*residual/prepared['final_nominal'],
                    minute_residual_pp_final=100*float(arrival[m,k])/prepared['final_nominal'])
                if curve_writer is not None:
                    curve_writer.writerow(row)
            if milestone_rows is not None:
                for stage in (1,5,10,25,50,75,90,95,99,100):
                    m = int(time['checkpoints'][stage]); denominator = int(cum_nominal[m])
                    residual = float(cumulative[m,k]); v = int(cum_votes[m,k])
                    milestone_rows.append(dict(common(prepared),source=source,candidate=int(candidate),stage=stage,
                        cutoff_minute=minute_text(time['minute_min']+m),
                        progress_actual=100*int(time['cumulative'][m])/len(prepared['ids']),
                        sections_cumulative=int(time['cumulative'][m]),nominal_cumulative=denominator,
                        share=100*v/denominator,composition_share=100*(v-residual)/denominator,
                        residual_current_pp=100*residual/denominator,residual_final_pp=100*residual/prepared['final_nominal']))
        if uf_rows is not None:
            ufs = prepared['data']['uf'][prepared['ids']]
            for uf in sorted(set(ufs.tolist())):
                use = ufs==uf; nt = int(prepared['nominal'][use].sum())
                ut = timing(time['minutes'][use])
                us, sign, uc, um, _ = scores_from_minutes(minute_values(prepared['residual'][use],ut),ut,nt)
                for k, candidate in enumerate(prepared['data']['candidate_numbers']):
                    uf_rows.append(dict(common(prepared),source=source,candidate=int(candidate),uf=uf,
                        sections=int(use.sum()),nominal_total=nt,final_share=100*int(prepared['votes'][use,k].sum())/nt,
                        G_signed=float(sign[k,0]),C=float(us[k,1]),M=float(us[k,2]),
                        C_minute=minute_text(ut['minute_min']+uc[k]),M_minute=minute_text(ut['minute_min']+um[k])))
    return result


def worker_init(state, directory):
    global _WORKER
    _WORKER = dict(state)
    _WORKER['scores_file'] = np.load(Path(directory)/'scores.npy',mmap_mode='r+')
    _WORKER['curves_file'] = np.load(Path(directory)/'grid-curves.npy',mmap_mode='r+')


def simulate_chunk(bounds):
    state = _WORKER
    n = state['residual_t'].shape[1]
    for rep in range(*bounds):
        rng = np.random.default_rng(np.random.SeedSequence([state['seed'],state['turn'],state['model_id']],spawn_key=(rep,)))
        permutation = np.arange(n,dtype=np.int32)
        for bucket in state['buckets']:
            permutation[bucket.ravel()] = rng.permuted(bucket,axis=1).ravel()
        payload = np.take(state['residual_t'],permutation,axis=1)
        for s, source in enumerate(SOURCES):
            time = state['sources'][source]
            arrival = np.column_stack([np.bincount(time['index'],weights=payload[k],minlength=len(time['counts']))
                                       for k in range(payload.shape[0])])
            scores, _, _, _, cumulative = scores_from_minutes(arrival,time,state['final_nominal'])
            state['scores_file'][rep,s] = scores
            grid = np.zeros((101,payload.shape[0]),dtype=np.float64)
            grid[1:] = cumulative[time['checkpoints'][1:]]*(100/state['final_nominal'])
            state['curves_file'][rep,s] = grid
    state['scores_file'].flush();state['curves_file'].flush()
    return bounds[1]-bounds[0]


def simulations(prepared, directory, simulations, seed, workers, fingerprint):
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        meta_path = directory/'metadata.json'
        if not meta_path.exists():
            raise ValueError('Unknown simulation cache; choose a new directory')
        meta = json.loads(meta_path.read_text())
        if meta.get('status')!='completed' or meta.get('fingerprint')!=fingerprint:
            raise ValueError('Incomplete or different simulation cache; choose a new directory')
        for name in ('scores.npy','grid-curves.npy'):
            if sha256(directory/name)!=meta['sha256'][name]:
                raise ValueError('Simulation cache hash mismatch')
        return meta
    directory.mkdir(parents=True,exist_ok=True)
    meta = dict(status='running',fingerprint=fingerprint,simulations=simulations,seed=seed,
        turno=int(prepared['data']['turno']),model=prepared['model'],candidate_numbers=prepared['data']['candidate_numbers'],
        sources=list(SOURCES),statistics=list(STATISTICS),grid_stages=list(range(101)))
    json_write(directory/'metadata.json',meta)
    k = prepared['votes'].shape[1]
    for name,shape in [('scores.npy',(simulations,2,k,3)),('grid-curves.npy',(simulations,2,101,k))]:
        array=np.lib.format.open_memmap(directory/name,mode='w+',dtype=np.float64,shape=shape)
        array.flush();del array
    state = dict(residual_t=np.ascontiguousarray(prepared['residual'].T),buckets=prepared['buckets'],
        sources={source:{key:time[key] for key in ('index','counts','weights','checkpoints')} for source,time in prepared['sources'].items()},
        final_nominal=prepared['final_nominal'],seed=seed,turn=int(prepared['data']['turno']),model_id=MODELS[prepared['model']])
    chunks = [(start,min(start+50,simulations)) for start in range(0,simulations,50)]
    done=0
    if workers==1:
        worker_init(state,str(directory))
        for chunk in chunks:
            done+=simulate_chunk(chunk)
            if done%500==0 or done==simulations:
                print(f'{prepared["model"]}/turn {state["turn"]}: {done}/{simulations}',flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn'),
                                 initializer=worker_init,initargs=(state,str(directory))) as pool:
            for task in as_completed([pool.submit(simulate_chunk,chunk) for chunk in chunks]):
                done+=task.result()
                if done%500==0 or done==simulations:
                    print(f'{prepared["model"]}/turn {state["turn"]}: {done}/{simulations}',flush=True)
    meta.update(status='completed',sha256={name:sha256(directory/name) for name in ('scores.npy','grid-curves.npy')})
    json_write(directory/'metadata.json',meta)
    return meta


def simulated_rows(prepared, observed_results, directory, meta, test_rows, band_rows, mc_rows):
    scores=np.load(Path(directory)/'scores.npy',mmap_mode='r')
    grid=np.load(Path(directory)/'grid-curves.npy',mmap_mode='r')
    b=len(scores)
    for s,source in enumerate(SOURCES):
        obs=observed_results[source];time=prepared['sources'][source]
        info=informative(prepared,source)
        quantiles=np.quantile(scores[:,s],[0.025,0.975],axis=0)
        means=np.mean(scores[:,s],axis=0)
        gq=np.quantile(grid[:,s],[0.025,0.975],axis=0)
        gm=np.mean(grid[:,s],axis=0)
        for k,candidate in enumerate(prepared['data']['candidate_numbers']):
            support=int(prepared['sizes'][info[:,k]].sum())
            possible, reasons=score_variability(prepared,source,k,scores[:,s,k,:],obs['scores'][k])
            for j,stat in enumerate(STATISTICS):
                peak='' if stat=='G' else minute_text(time['minute_min']+int(obs['ci' if stat=='C' else 'mi'][k]))
                row=dict(common(prepared),source=source,candidate=int(candidate),statistic=stat,
                    observed=float(obs['scores'][k,j]),signed_observed=float(obs['signed'][k,j]),peak_minute=peak,
                    simulation_mean=float(means[k,j]),simulation_q025=float(quantiles[0,k,j]),simulation_q975=float(quantiles[1,k,j]),
                    informative_sections=support)
                mc_rows.append(row.copy())
                if source=='first_time':
                    exceed=int(np.count_nonzero(scores[:,s,k,j]>=obs['scores'][k,j]-P_TOLERANCE))
                    row.pop('source')
                    row.update(simulations=b,exceedances=exceed,p_raw=(exceed+1)/(b+1) if possible[j] else '',
                        p_holm='',detected='',status='applicable' if possible[j] else 'not_applicable',
                        applicability_reason=reasons[j])
                    test_rows.append(row)
            for stage in range(101):
                m=int(time['checkpoints'][stage])
                band_rows.append(dict(common(prepared),source=source,candidate=int(candidate),stage=stage,
                    cutoff_minute='' if stage==0 else minute_text(time['minute_min']+m),
                    progress_actual=0.0 if stage==0 else 100*int(time['cumulative'][m])/len(prepared['ids']),
                    observed=0.0 if stage==0 else 100*float(obs['cumulative'][m,k])/prepared['final_nominal'],
                    simulation_mean=float(gm[stage,k]),simulation_q025=float(gq[0,stage,k]),simulation_q975=float(gq[1,stage,k])))


def descriptive_rows(prepared, results, scenario):
    for source in SOURCES:
        obs=results[source];time=prepared['sources'][source];info=informative(prepared,source)
        for k,candidate in enumerate(prepared['data']['candidate_numbers']):
            yield dict(common(prepared),scenario=scenario,source=source,candidate=int(candidate),
                G_signed=float(obs['signed'][k,0]),**{name:float(obs['scores'][k,j]) for j,name in enumerate(STATISTICS)},
                C_minute=minute_text(time['minute_min']+obs['ci'][k]),M_minute=minute_text(time['minute_min']+obs['mi'][k]),
                cohort_sections=len(prepared['ids']),nominal_total=prepared['final_nominal'],
                informative_sections=int(prepared['sizes'][info[:,k]].sum()))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,default=HERE/'evidence/analysis')
    parser.add_argument('--cache',type=Path,default=HERE/'.work/data')
    parser.add_argument('--simulation-cache',type=Path,default=HERE/'.work/simulations')
    parser.add_argument('--simulations',type=int,default=4999)
    parser.add_argument('--seed',type=int,default=20261028)
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    if args.simulations<1 or not 1<=args.workers<=4:
        parser.error('Use positive simulations and 1–4 workers')
    if sha256(HERE/'METHOD.pt-BR.md')!=METHOD_SHA256:
        parser.error('Frozen H4 method hash differs; review and version the protocol')
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('Refusing a nonempty output directory; preserve published evidence')
    args.output.mkdir(parents=True,exist_ok=True)
    core={name:sha256(HERE/'code'/name) for name in ('load_data.py','temporal_statistics.py','run_analysis.py')}
    manifest=dict(status='running',started_at_utc=datetime.now(timezone.utc).isoformat(),method_sha256=METHOD_SHA256,
        implementation_sha256=core,git_base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.root,text=True).strip(),
        parameters=dict(simulations=args.simulations,seed=args.seed,workers=args.workers,models=MODELS,
            sources=SOURCES,statistics=STATISTICS,primary_source='first_time',family_size=90,
            p_tolerance=P_TOLERANCE,residual_closure_votes=RESIDUAL_CLOSURE_VOTES,
            rng='PCG64; SeedSequence([seed,turno,model_id],spawn_key=(repetition,))',
            time_convention='Hora TSE, naive local wall clock; no timezone conversion',
            cohort='installed, not cancelled, aptos>=50, turnout>0, nominal>=50, known place, both timestamps',
            pointwise_grid=list(range(101))),simulation_caches=[])
    json_write(args.output/'manifest.json',manifest)
    data=load_data(args.root,args.cache)
    manifest.update(source_inputs=data['source_inputs'],source_counts=data['source_counts'],data_fingerprint=data['cache_fingerprint'])
    tests=[];bands=[];coverage=[];milestones=[];uf_rows=[];sensitivity=[];spans=[];span_summary=[];eligibility=[];mc_rows=[]
    with csv_writer(args.output/'group-totals.csv.gz',GROUP_COLUMNS) as groups, csv_writer(args.output/'curves.csv.gz',CURVE_COLUMNS) as curves:
        for rd in data['rounds']:
            mask,reasons,basic=cohort(rd)
            for uf in ['BR',*sorted(set(rd['uf'].tolist()))]:
                select=np.ones(len(mask),dtype=bool) if uf=='BR' else rd['uf']==uf
                row=dict(election_code=int(rd['election_code']),turno=int(rd['turno']),uf=uf,detail_sections=int(select.sum()),
                    eligible_basic=int((select&basic).sum()),cohort_sections=int((select&mask).sum()))
                row.update({f'excluded_{name}':int((select&(reasons==name)).sum()) for name in
                            ('section_status','aptos_below_50','nonpositive_turnout','nominal_below_floor','missing_place','missing_time')})
                eligibility.append(row)
            for model in MODELS:
                prep=prepare(rd,model)
                print(f'Observed {model}/turn {rd["turno"]}: {len(prep["ids"])} sections, {len(prep["sizes"])} groups',flush=True)
                groups.writerows(group_rows(prep));coverage.extend(coverage_rows(prep))
                obs=observed(prep,curves,milestones,uf_rows)
                sensitivity.extend(descriptive_rows(prep,obs,'primary'))
                for source in SOURCES:
                    time=prep['sources'][source];use=prep['sizes']>1
                    span=time['group_max']-time['group_min']
                    for threshold in (0,1,5,15,30,60):
                        chosen=use&(span>=threshold)
                        spans.append(dict(common(prep),source=source,threshold_minutes=threshold,
                                          groups=int(chosen.sum()),sections=int(prep['sizes'][chosen].sum())))
                    values=span[use]
                    span_summary.append(dict(common(prep),source=source,nonsingleton_groups=int(use.sum()),
                        span_min=float(values.min()) if len(values) else '',
                        span_q25=float(np.quantile(values,.25)) if len(values) else '',
                        span_median=float(np.median(values)) if len(values) else '',
                        span_q75=float(np.quantile(values,.75)) if len(values) else '',
                        span_q95=float(np.quantile(values,.95)) if len(values) else '',
                        span_max=float(values.max()) if len(values) else ''))
                fingerprint=hashlib.sha256(json.dumps(dict(core=core,method=METHOD_SHA256,data=data['cache_fingerprint'],
                    model=model,turno=int(rd['turno']),simulations=args.simulations,seed=args.seed),sort_keys=True).encode()).hexdigest()
                cache=args.simulation_cache/f'{model}-{rd["turno"]}'
                meta=simulations(prep,cache,args.simulations,args.seed,args.workers,fingerprint)
                manifest['simulation_caches'].append(dict(path=str(cache.relative_to(args.root)) if cache.is_relative_to(args.root) else str(cache),
                                                          metadata=meta,metadata_sha256=sha256(cache/'metadata.json')))
                simulated_rows(prep,obs,cache,meta,tests,bands,mc_rows)
            for model,floor,scenario in [('place_no_size',50,'place_no_size'),('zone_size',100,'nominal_100'),('place_size',100,'nominal_100')]:
                prep=prepare(rd,model,min_nominal=floor)
                sensitivity.extend(descriptive_rows(prep,observed(prep),scenario))
    if len(tests)!=90:
        raise ValueError('Expected the predeclared family of 90 tests')
    adjusted=holm([row['p_raw'] if row['status']=='applicable' else 1.0 for row in tests])
    for row,p in zip(tests,adjusted):
        if row['status']=='applicable':
            row.update(p_holm=float(p),detected=bool(p<=.05),status='detected' if p<=.05 else 'not_detected')
    write_csv(args.output/'tests.csv',TEST_COLUMNS,tests)
    write_csv(args.output/'coverage.csv',COVERAGE_COLUMNS,coverage)
    write_csv(args.output/'bands.csv',BAND_COLUMNS,bands)
    write_csv(args.output/'sensitivity.csv',SENSITIVITY_COLUMNS,sensitivity)
    write_csv(args.output/'milestones.csv',MILESTONE_COLUMNS,milestones)
    write_csv(args.output/'uf-summary.csv',UF_COLUMNS,uf_rows)
    for name,rows in [('group-spans.csv',spans),('span-summary.csv',span_summary),('eligibility.csv',eligibility),('mc-quantiles.csv',mc_rows)]:
        write_csv(args.output/name,list(rows[0]),rows)
    summary=dict(family_size=90,primary_detected=sum(row['status']=='detected' for row in tests),
        primary_not_detected=sum(row['status']=='not_detected' for row in tests),
        primary_not_applicable=sum(row['status']=='not_applicable' for row in tests),
        candidate_numbers={str(rd['turno']):rd['candidate_numbers'] for rd in data['rounds']},
        primary_source='first_time',paired_sensitivity='bu_time; no additional p-values',
        models=MODELS,source_counts=data['source_counts'],
        interpretation='Conditional time-order associations, not causal attribution or external authenticity',
        sensitivity_validation='See independent-validation.json for the scope of separate validation of descriptive alternatives')
    json_write(args.output/'summary.json',summary)
    for name,source in data['source_inputs'].items():
        if sha256(args.root/source['path'])!=source['sha256']:
            raise ValueError('Original input changed during analysis')
    manifest.update(status='completed',completed_at_utc=datetime.now(timezone.utc).isoformat(),
        numpy_version=np.__version__,artifacts={p.name:dict(size_bytes=p.stat().st_size,sha256=sha256(p))
                                               for p in sorted(args.output.iterdir()) if p.name!='manifest.json'})
    json_write(args.output/'manifest.json',manifest)
    print(json.dumps({key:summary[key] for key in ('family_size','primary_detected','primary_not_detected','primary_not_applicable')}),flush=True)


if __name__=='__main__':
    main()
