#!/usr/bin/env python3
"""H6: paired turnout changes and finalist preference gains.

Output/cache guards and deterministic process orchestration adapted from
../05-inter-round-localization/code/run_analysis.py at commit
 a3362b3ec72c0c567fcf80c5b6761b6cc1cc52c2. Statistical definitions are H6-specific.
"""
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

from load_data import load_data, sha256
from turnout_statistics import (MODELS, STATISTICS, EPS, pair_sections, eligibility,
    measures, prepare, score, score_variability, holm)

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
METHOD_SHA256 = '6a63f96ead6de3641c53cc123d7258282b506f160494fd228b257a02dba51687'
REGIONS = {'AC':'Norte','AP':'Norte','AM':'Norte','PA':'Norte','RO':'Norte','RR':'Norte','TO':'Norte',
    'AL':'Nordeste','BA':'Nordeste','CE':'Nordeste','MA':'Nordeste','PB':'Nordeste','PE':'Nordeste','PI':'Nordeste','RN':'Nordeste','SE':'Nordeste',
    'DF':'Centro-Oeste','GO':'Centro-Oeste','MT':'Centro-Oeste','MS':'Centro-Oeste',
    'ES':'Sudeste','MG':'Sudeste','RJ':'Sudeste','SP':'Sudeste','PR':'Sul','RS':'Sul','SC':'Sul','ZZ':'Exterior'}
COUNT_FIELDS = ['aptos','turnout','abstentions','nominal','blank','null_votes','legend','separate','v13','v22','other_nominal']
PAIR_FIELDS = ['place','source_line','installed','cancelled','aptos','turnout','abstentions','nominal',
    'blank','null_votes','legend','separate','v13','v22','f']
PAIR_COLUMNS = ['uf','municipality','municipality_name','zone','section','election_1','election_2',
    *[f'{field}_{turn}' for turn in (1,2) for field in PAIR_FIELDS], 'eligible','exclusion_reason']
MEASURE_FIELDS = ['x','y','q1','q2','delta_q','turnout_rate1','turnout_rate2','abstention_rate1','abstention_rate2','other_1','other_2',
    *[key for c in (13,22) for key in [f'gain{c}_count',f'gain{c}_nominal_pp',f'gain{c}_aptos_pp',
        f'turnout{c}_component_pp',f'composition{c}_component_pp',f'gain{c}_equiv_votes',
        f'turnout{c}_equiv_votes',f'composition{c}_equiv_votes']],
    'x_numerator','x_denominator','y_numerator','y_denominator']
MEASURE_COLUMNS = ['uf','municipality','zone','section','place',*MEASURE_FIELDS,
    *[f'support_{model}' for model in MODELS]]
GROUP_COLUMNS = ['model','uf','municipality','zone','place','size_band','initial_turnout_bin',
    'initial_preference_bin','initial_other_bin','n','status','variable_x','variable_y','informative',
    'mean_x','mean_y','ss_x','ss_y','covariance']
COVERAGE_COLUMNS = ['model','uf','cohort_pairs','groups','singleton_groups','singleton_pairs',
    'constant_both_groups','constant_both_pairs','constant_x_only_groups','constant_x_only_pairs',
    'constant_y_only_groups','constant_y_only_pairs','informative_groups','informative_pairs']
TEST_COLUMNS = ['model','statistic','observed_signed','observed_abs','beta','simulation_mean_abs',
    'simulation_q025_abs','simulation_q975_abs','exceedances','simulations','p_raw','p_holm',
    'detected','status','applicability_reason']
SENSITIVITY_COLUMNS = ['scenario','model','bins','finalist_floor','unchanged_aptos','domestic_only',
    'outcome','cohort_pairs','groups','informative_groups','informative_pairs','rho_linear','rho_rank','beta']
TOTAL_COLUMNS = ['scope_type','scope','sections_1','sections_2',
    *[f'{field}_{suffix}' for field in COUNT_FIELDS for suffix in (1,2,'change')],
    'finalist_gain','other_and_special_change','identity_residual','aptos_identity_residual_1',
    'aptos_identity_residual_2','turnout_rate_1','turnout_rate_2','turnout_rate_change']
DESCRIPTIVE_MEANS = [key for key in MEASURE_FIELDS if key not in {'x_numerator','x_denominator','y_numerator','y_denominator'}]
DESCRIPTION_COLUMNS = ['scope_type','scope','cohort_pairs','increased_turnout_pairs','unchanged_turnout_pairs',
    'decreased_turnout_pairs','changed_aptos_pairs','raw_rho','raw_beta',
    *[f'mean_{key}' for key in DESCRIPTIVE_MEANS],
    *[f'sum_{key}' for c in (13,22) for key in (f'gain{c}_count',f'gain{c}_equiv_votes',f'turnout{c}_equiv_votes',f'composition{c}_equiv_votes')],
    *[f'{model}_{key}' for model in MODELS for key in ('supported_pairs','rho_linear','rho_rank','beta')]]
BIN_EDGES = np.array([-np.inf,*range(-10,11,2),np.inf],dtype=float)
XBINS_COLUMNS = ['scope_type','scope','bin','left_pp','right_pp','sections',
    *[f'mean_{key}' for key in ('x','y','gain13_count','gain22_count','gain13_aptos_pp','gain22_aptos_pp',
        'turnout13_component_pp','turnout22_component_pp','composition13_component_pp','composition22_component_pp')]]
HEATMAP_COLUMNS = ['x_bin','x_left_pp','x_right_pp','y_bin','y_left_pp','y_right_pp','sections']
PERMUTATION_COLUMNS = ['model','repetition','rho_linear','rho_rank']
_WORKER = None


def json_write(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


@contextmanager
def csv_writer(path, columns):
    path = Path(path)
    with path.open('wb') as raw:
        compressed = gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) if path.suffix=='.gz' else raw
        with io.TextIOWrapper(compressed,encoding='utf-8',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=columns,lineterminator='\n',extrasaction='raise')
            writer.writeheader()
            yield writer


def write_csv(path, columns, rows):
    with csv_writer(path,columns) as writer:
        writer.writerows(rows)


def scalar(value):
    if isinstance(value,(bool,np.bool_)):
        return bool(value)
    if isinstance(value,(int,np.integer)):
        return int(value)
    if value is None or not np.isfinite(value):
        return ''
    return float(value)


def region_array(ufs):
    try:
        return np.asarray([REGIONS[str(uf)] for uf in ufs])
    except KeyError as error:
        raise ValueError(f'Unmapped UF: {error.args[0]}') from error


def scopes(ufs):
    """National, individual UFs, then named regions; scopes intentionally overlap."""
    regions = region_array(ufs)
    yield 'BR','BR',np.ones(len(ufs),dtype=bool)
    for uf in sorted(set(ufs.tolist())):
        yield 'UF',str(uf),ufs==uf
    for region in sorted(set(regions.tolist())):
        yield 'region',str(region),regions==region


def pairing_rows(joined):
    first,second = joined['rounds']
    pairs = joined['pairs']
    for uf in ['BR',*sorted(set(first['uf'].tolist())|set(second['uf'].tolist()))]:
        def count(values):
            return len(values) if uf=='BR' else int(np.count_nonzero(values==uf))
        yield dict(uf=uf,round1_records=count(first['uf']),round2_records=count(second['uf']),
            matched_pairs=count(pairs['uf']),only_round1=count(first['uf'][joined['unmatched'][0][2]]),
            only_round2=count(second['uf'][joined['unmatched'][1][2]]))


def eligibility_rows(pairs):
    mask,reasons,basic = eligibility(pairs)
    for uf in ['BR',*sorted(set(pairs['uf'].tolist()))]:
        use = np.ones(len(mask),dtype=bool) if uf=='BR' else pairs['uf']==uf
        chosen = use&mask
        row = dict(uf=uf,matched_pairs=int(use.sum()),basic_eligible=int((use&basic).sum()),
            cohort_pairs=int(chosen.sum()))
        for reason in ('section_status','aptos_below_50','nonpositive_turnout','nominal_below_50',
            'finalists_below_floor','missing_place','changed_place','aptos_ratio'):
            row[f'excluded_{reason}'] = int((use&(reasons==reason)).sum())
        row['changed_aptos_cohort'] = int((chosen&(pairs['aptos_1']!=pairs['aptos_2'])).sum())
        yield row


def pair_rows(pairs, names):
    mask,reasons,_ = eligibility(pairs)
    for i in range(len(mask)):
        row = {key:str(pairs[key][i]) if key=='uf' else int(pairs[key][i])
            for key in ('uf','municipality','zone','section')}
        row.update(municipality_name=names.get(f'{row["uf"]}:{row["municipality"]}',''),
            election_1=int(pairs['election_1']),election_2=int(pairs['election_2']))
        for turn in (1,2):
            for field in PAIR_FIELDS:
                value = pairs[f'{field}_{turn}'][i]
                row[f'{field}_{turn}'] = bool(value) if field in {'installed','cancelled'} else int(value)
        row.update(eligible=bool(mask[i]),exclusion_reason=str(reasons[i]))
        yield row


def measure_rows(pairs, ids, measured, references):
    for j,i in enumerate(ids):
        row = {key:str(pairs[key][i]) if key=='uf' else int(pairs[key][i])
            for key in ('uf','municipality','zone','section')}
        row['place'] = int(pairs['place_1'][i])
        row.update({key:scalar(measured[key][j]) for key in MEASURE_FIELDS})
        row.update({f'support_{model}':bool(ref['support'][j]) for model,ref in references.items()})
        yield row


def group_rows(prepared):
    pairs,ids,group = prepared['pairs'],prepared['ids'],prepared['group']
    for g,n in enumerate(group['sizes']):
        j = group['first'][g]
        i = ids[j]
        yield dict(model=prepared['model'],uf=str(pairs['uf'][i]),municipality=int(pairs['municipality'][i]),
            zone=int(pairs['zone'][i]),place=int(pairs['place_1'][i]) if prepared['model']=='place_baseline' else -1,
            size_band=int(prepared['band'][j]),initial_turnout_bin=int(prepared['initial_turnout_band'][j]),
            initial_preference_bin=int(prepared['initial_preference_band'][j]),initial_other_bin=int(prepared['initial_other_band'][j]),
            n=int(n),status=str(prepared['group_status'][g]),variable_x=bool(prepared['variable_x'][g]),
            variable_y=bool(prepared['variable_y'][g]),informative=bool(prepared['informative'][g]),
            mean_x=scalar(prepared['mean_x'][g]),mean_y=scalar(prepared['mean_y'][g]),
            ss_x=scalar(prepared['ss_x'][g]),ss_y=scalar(prepared['ss_y'][g]),covariance=scalar(prepared['covariance'][g]))


def coverage_rows(prepared):
    pairs,ids,group = prepared['pairs'],prepared['ids'],prepared['group']
    group_uf = pairs['uf'][ids[group['first']]]
    statuses = dict(singleton=group['sizes']==1,
        constant_both=(group['sizes']>1)&~prepared['variable_x']&~prepared['variable_y'],
        constant_x_only=(group['sizes']>1)&~prepared['variable_x']&prepared['variable_y'],
        constant_y_only=(group['sizes']>1)&prepared['variable_x']&~prepared['variable_y'],
        informative=prepared['informative'])
    if not np.all(sum(status.astype(int) for status in statuses.values())==1):
        raise ArithmeticError('Coverage categories are not an exclusive group partition')
    for uf in ['BR',*sorted(set(pairs['uf'][ids].tolist()))]:
        use = np.ones(len(ids),dtype=bool) if uf=='BR' else pairs['uf'][ids]==uf
        guse = np.ones(len(group['sizes']),dtype=bool) if uf=='BR' else group_uf==uf
        row = dict(model=prepared['model'],uf=uf,cohort_pairs=int(use.sum()),groups=int(guse.sum()))
        for name,status in statuses.items():
            chosen = guse&status
            row[f'{name}_groups'] = int(chosen.sum())
            row[f'{name}_pairs'] = int(group['sizes'][chosen].sum())
        yield row


def totals_rows(rounds):
    """Raw source totals, including sections excluded from the paired cohort."""
    r1,r2 = sorted(rounds,key=lambda rd:int(rd['turno']))
    all_uf = np.unique(np.r_[r1['uf'],r2['uf']])
    for scope_type,scope,_ in scopes(all_uf):
        row = dict(scope_type=scope_type,scope=scope)
        for turn,rd in ((1,r1),(2,r2)):
            use = np.ones(len(rd['uf']),dtype=bool) if scope_type=='BR' else rd['uf']==scope if scope_type=='UF' else region_array(rd['uf'])==scope
            row[f'sections_{turn}'] = int(use.sum())
            values = {key:rd[key] for key in COUNT_FIELDS if key not in {'v13','v22','other_nominal'}}
            for c in (13,22):
                values[f'v{c}'] = rd['candidate_votes'][:,rd['candidate_numbers'].index(c)]
            values['other_nominal'] = rd['nominal'].astype(np.int64)-values['v13']-values['v22']
            for key in COUNT_FIELDS:
                row[f'{key}_{turn}'] = int(values[key][use].sum(dtype=np.int64))
            row[f'aptos_identity_residual_{turn}'] = row[f'aptos_{turn}']-row[f'turnout_{turn}']-row[f'abstentions_{turn}']
            row[f'turnout_rate_{turn}'] = 100*row[f'turnout_{turn}']/row[f'aptos_{turn}'] if row[f'aptos_{turn}'] else ''
        for key in COUNT_FIELDS:
            row[f'{key}_change'] = row[f'{key}_2']-row[f'{key}_1']
        row['finalist_gain'] = row['v13_change']+row['v22_change']
        row['other_and_special_change'] = sum(row[f'{key}_change'] for key in ('other_nominal','blank','null_votes','legend','separate'))
        row['identity_residual'] = row['finalist_gain']-row['turnout_change']+row['other_and_special_change']
        row['turnout_rate_change'] = row['turnout_rate_2']-row['turnout_rate_1'] if row['aptos_1'] and row['aptos_2'] else ''
        if row['identity_residual']:
            raise ArithmeticError('Raw-snapshot counts do not satisfy the finalist gain identity')
        yield row


def correlation(x,y):
    if not len(x):
        return '', ''
    rx = np.asarray(x,dtype=float)-np.mean(x)
    ry = np.asarray(y,dtype=float)-np.mean(y)
    xx,yy,xy = np.dot(rx,rx),np.dot(ry,ry),np.dot(rx,ry)
    return (float(xy/np.sqrt(xx*yy)) if xx>0 and yy>0 else '',float(xy/xx) if xx>0 else '')


def conditional_scope(prepared,use):
    chosen = use&prepared['support']
    if not np.any(chosen):
        return dict(supported_pairs=0,rho_linear='',rho_rank='',beta='')
    rx,ry = prepared['rx'][chosen],prepared['ry'][chosen]
    rank_x,rank_y = prepared['rank_x'][chosen],prepared['rank_y'][chosen]
    xx,yy,xy = np.dot(rx,rx),np.dot(ry,ry),np.dot(rx,ry)
    denominator = np.sqrt(np.dot(rank_x,rank_x)*np.dot(rank_y,rank_y))
    return dict(supported_pairs=int(chosen.sum()),rho_linear=float(xy/np.sqrt(xx*yy)) if xx>0 and yy>0 else '',
        rho_rank=float(np.dot(rank_x,rank_y)/denominator) if denominator>0 else '',beta=float(xy/xx) if xx>0 else '')


def descriptive_rows(pairs, ids, measured, references):
    for scope_type,scope,use in scopes(pairs['uf'][ids]):
        raw_rho,raw_beta = correlation(measured['x'][use],measured['y'][use])
        # Exact reduced numerators determine the sign, including exact zero.
        xn = measured['x_numerator'][use]
        row = dict(scope_type=scope_type,scope=scope,cohort_pairs=int(use.sum()),
            increased_turnout_pairs=int((xn>0).sum()),unchanged_turnout_pairs=int((xn==0).sum()),
            decreased_turnout_pairs=int((xn<0).sum()),changed_aptos_pairs=int(np.count_nonzero(pairs['aptos_1'][ids][use]!=pairs['aptos_2'][ids][use])),
            raw_rho=raw_rho,raw_beta=raw_beta)
        row.update({f'mean_{key}':scalar(np.mean(measured[key][use])) for key in DESCRIPTIVE_MEANS})
        for c in (13,22):
            for key in (f'gain{c}_count',f'gain{c}_equiv_votes',f'turnout{c}_equiv_votes',f'composition{c}_equiv_votes'):
                row[f'sum_{key}'] = scalar(np.sum(measured[key][use]))
        for model,ref in references.items():
            row.update({f'{model}_{key}':value for key,value in conditional_scope(ref,use).items()})
        yield row


def bin_ids(values):
    return np.searchsorted(BIN_EDGES[1:-1],values,side='right')


def boundary(value):
    return '-inf' if np.isneginf(value) else 'inf' if np.isposinf(value) else int(value)


def xbin_rows(pairs, ids, measured):
    bins = bin_ids(measured['x'])
    keys = [column.removeprefix('mean_') for column in XBINS_COLUMNS if column.startswith('mean_')]
    for scope_type,scope,use in scopes(pairs['uf'][ids]):
        for b in range(len(BIN_EDGES)-1):
            chosen = use&(bins==b)
            row = dict(scope_type=scope_type,scope=scope,bin=b,left_pp=boundary(BIN_EDGES[b]),
                right_pp=boundary(BIN_EDGES[b+1]),sections=int(chosen.sum()))
            row.update({f'mean_{key}':scalar(np.mean(measured[key][chosen])) if np.any(chosen) else '' for key in keys})
            yield row


def heatmap_rows(measured):
    n = len(BIN_EDGES)-1
    counts = np.bincount(n*bin_ids(measured['x'])+bin_ids(measured['y']),minlength=n*n).reshape(n,n)
    if int(counts.sum())!=len(measured['x']):
        raise ArithmeticError('Heatmap lost section pairs')
    for x in range(n):
        for y in range(n):
            yield dict(x_bin=x,x_left_pp=boundary(BIN_EDGES[x]),x_right_pp=boundary(BIN_EDGES[x+1]),
                y_bin=y,y_left_pp=boundary(BIN_EDGES[y]),y_right_pp=boundary(BIN_EDGES[y+1]),sections=int(counts[x,y]))


def worker_init(state,directory):
    global _WORKER
    _WORKER = dict(state)
    _WORKER['scores'] = np.load(Path(directory)/'scores.npy',mmap_mode='r+')


def simulate_chunk(bounds):
    state = _WORKER
    n = len(state['rx'])
    prefix = {}
    for rep in range(*bounds):
        rng = np.random.default_rng(np.random.SeedSequence([state['seed'],6,state['model_id']],spawn_key=(rep,)))
        assigned = np.arange(n,dtype=np.int32)
        for bucket in state['buckets']:
            assigned[bucket.ravel()] = rng.permuted(bucket,axis=1).ravel()
        state['scores'][rep] = [np.dot(state['rx'],state['ry'][assigned])/state['linear_denominator'] if state['linear_denominator'] else 0.,
            np.dot(state['rank_x'],state['rank_y'][assigned])/state['rank_denominator'] if state['rank_denominator'] else 0.]
        if rep<2:
            prefix[str(rep)] = hashlib.sha256(assigned.astype('<i4').tobytes()).hexdigest()
    state['scores'].flush()
    return dict(done=bounds[1]-bounds[0],assignment_prefix=prefix)


def simulations(prepared,directory,b,seed,workers,fingerprint):
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        path = directory/'metadata.json'
        if not path.is_file() or not (directory/'scores.npy').is_file():
            raise ValueError('Unknown simulation cache; choose a new directory')
        meta = json.loads(path.read_text())
        if meta.get('status')!='completed' or meta.get('fingerprint')!=fingerprint or meta.get('scores_sha256')!=sha256(directory/'scores.npy'):
            raise ValueError('Incomplete, different or corrupted simulation cache; choose a new directory')
        with_score = np.load(directory/'scores.npy',mmap_mode='r')
        if with_score.shape!=(b,2) or not np.all(np.isfinite(with_score)) or np.any(np.abs(with_score)>1+EPS):
            raise ValueError('Simulation cache contains invalid signed correlation scores')
        return meta
    directory.mkdir(parents=True,exist_ok=True)
    meta = dict(status='running',fingerprint=fingerprint,model=prepared['model'],model_id=MODELS[prepared['model']],
        simulations=b,seed=seed,statistics=list(STATISTICS),score_representation='signed correlations; formal tests use absolute values',assignment_prefix={})
    json_write(directory/'metadata.json',meta)
    array = np.lib.format.open_memmap(directory/'scores.npy',mode='w+',dtype=np.float64,shape=(b,2))
    array.flush();del array
    state = {key:prepared[key] for key in ('rx','ry','rank_x','rank_y','linear_denominator','rank_denominator','buckets')}
    state.update(seed=seed,model_id=MODELS[prepared['model']])
    chunks = [(start,min(start+50,b)) for start in range(0,b,50)]
    done = 0
    if workers==1:
        worker_init(state,str(directory))
        for chunk in chunks:
            result = simulate_chunk(chunk)
            done += result['done'];meta['assignment_prefix'].update(result['assignment_prefix'])
            if done%500==0 or done==b:
                print(f'{prepared["model"]}: {done}/{b}',flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn'),initializer=worker_init,initargs=(state,str(directory))) as pool:
            for task in as_completed([pool.submit(simulate_chunk,chunk) for chunk in chunks]):
                result = task.result()
                done += result['done'];meta['assignment_prefix'].update(result['assignment_prefix'])
                if done%500==0 or done==b:
                    print(f'{prepared["model"]}: {done}/{b}',flush=True)
    values = np.load(directory/'scores.npy',mmap_mode='r')
    if not np.all(np.isfinite(values)) or np.any(np.abs(values)>1+EPS):
        raise ArithmeticError('Invalid simulated signed correlation')
    meta.update(status='completed',scores_sha256=sha256(directory/'scores.npy'))
    json_write(directory/'metadata.json',meta)
    return meta


def sensitivity_row(prepared,scenario,finalist_floor=50,unchanged=False,domestic=False,outcome='change'):
    observed = score(prepared)
    return dict(scenario=scenario,model=prepared['model'],bins=prepared['bins'],finalist_floor=finalist_floor,
        unchanged_aptos=unchanged,domestic_only=domestic,outcome=outcome,cohort_pairs=len(prepared['ids']),
        groups=len(prepared['group']['sizes']),informative_groups=int(prepared['informative'].sum()),
        informative_pairs=int(prepared['support'].sum()),rho_linear=scalar(observed[0]),rho_rank=scalar(observed[1]),beta=scalar(prepared['beta']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,default=HERE/'evidence/analysis')
    parser.add_argument('--cache',type=Path,default=HERE/'.work/data')
    parser.add_argument('--simulation-cache',type=Path,default=HERE/'.work/simulations')
    parser.add_argument('--simulations',type=int,default=4999)
    parser.add_argument('--seed',type=int,default=20261029)
    parser.add_argument('--workers',type=int,default=4)
    args = parser.parse_args()
    if args.simulations<1 or not 1<=args.workers<=4:
        parser.error('Use positive simulations and 1–4 workers')
    if sha256(HERE/'METHOD.pt-BR.md')!=METHOD_SHA256:
        parser.error('Frozen H6 method hash differs; review/version the protocol')
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('Refusing a nonempty output directory')
    args.output.mkdir(parents=True,exist_ok=True)
    core = {name:sha256(HERE/'code'/name) for name in ('load_data.py','turnout_statistics.py','run_analysis.py')}
    manifest = dict(status='running',hypothesis='H6',started_at_utc=datetime.now(timezone.utc).isoformat(),method_sha256=METHOD_SHA256,
        implementation_sha256=core,git_base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.root,text=True).strip(),
        parameters=dict(simulations=args.simulations,seed=args.seed,workers=args.workers,models=MODELS,statistics=list(STATISTICS),family_size=4,
            epsilon_correlation=EPS,baseline_bins=20,score_cache='signed correlations; tests use absolute values',
            trajectory_permutation='Preference trajectories reassigned to turnout slots; not physically feasible synthetic ballot reports',
            rng='PCG64; SeedSequence([seed,6,model_id],spawn_key=(repetition,))'),simulation_caches=[])
    json_write(args.output/'manifest.json',manifest)
    loaded = load_data(args.root,args.cache)
    joined = pair_sections(loaded['rounds']);pairs = joined['pairs']
    mask,_,_ = eligibility(pairs);ids = np.flatnonzero(mask)
    measured = measures(pairs,ids)
    references = {model:prepare(pairs,model) for model in MODELS}
    for ref in references.values():
        if not np.array_equal(ref['ids'],ids):
            raise ArithmeticError('Primary references differ in cohort order')
    print(f'Paired {len(pairs["uf"])} physical keys; cohort {len(ids)}',flush=True)
    manifest.update(source_inputs=loaded['source_inputs'],source_counts=loaded['source_counts'],data_fingerprint=loaded['cache_fingerprint'])
    pairing = list(pairing_rows(joined));eligible = list(eligibility_rows(pairs))
    write_csv(args.output/'pairing.csv',list(pairing[0]),pairing)
    write_csv(args.output/'eligibility.csv',list(eligible[0]),eligible)
    unmatched = []
    for turn,rd,indices in joined['unmatched']:
        for i in indices:
            unmatched.append(dict(present_in_round=turn,**{key:str(rd[key][i]) if key=='uf' else int(rd[key][i]) for key in ('uf','municipality','zone','section')},source_line=int(rd['source_line'][i])))
    write_csv(args.output/'unmatched.csv',['present_in_round','uf','municipality','zone','section','source_line'],unmatched)
    write_csv(args.output/'paired-sections.csv.gz',PAIR_COLUMNS,pair_rows(pairs,loaded['names']))
    write_csv(args.output/'section-measures.csv.gz',MEASURE_COLUMNS,measure_rows(pairs,ids,measured,references))
    raw_totals = list(totals_rows(loaded['rounds']))
    write_csv(args.output/'totals.csv',TOTAL_COLUMNS,raw_totals)
    descriptive = list(descriptive_rows(pairs,ids,measured,references))
    write_csv(args.output/'descriptive.csv',DESCRIPTION_COLUMNS,descriptive)
    write_csv(args.output/'x-bins.csv',XBINS_COLUMNS,xbin_rows(pairs,ids,measured))
    write_csv(args.output/'heatmap.csv',HEATMAP_COLUMNS,heatmap_rows(measured))
    tests,coverage,sens = [],[],[]
    with csv_writer(args.output/'association-groups.csv.gz',GROUP_COLUMNS) as writer, \
            csv_writer(args.output/'permutation-scores.csv.gz',PERMUTATION_COLUMNS) as permutation_writer:
        for model,prepared in references.items():
            observed = score(prepared)
            print(f'Observed {model}: {len(prepared["group"]["sizes"])} strata; {int(prepared["support"].sum())} informative pairs',flush=True)
            writer.writerows(group_rows(prepared));coverage.extend(coverage_rows(prepared))
            sens.append(sensitivity_row(prepared,'primary'))
            fingerprint = hashlib.sha256(json.dumps(dict(core=core,method=METHOD_SHA256,data=loaded['cache_fingerprint'],model=model,
                simulations=args.simulations,seed=args.seed),sort_keys=True).encode()).hexdigest()
            directory = args.simulation_cache/model
            meta = simulations(prepared,directory,args.simulations,args.seed,args.workers,fingerprint)
            manifest['simulation_caches'].append(dict(path=str(directory.relative_to(args.root)) if directory.is_relative_to(args.root) else str(directory),
                metadata=meta,metadata_sha256=sha256(directory/'metadata.json')))
            draws = np.load(directory/'scores.npy',mmap_mode='r')
            permutation_writer.writerows(dict(model=model,repetition=rep,rho_linear=float(values[0]),rho_rank=float(values[1]))
                for rep,values in enumerate(draws))
            possible,reasons = score_variability(prepared,np.abs(draws),np.abs(observed))
            absolute = np.abs(draws)
            quantiles = np.quantile(absolute,[.025,.975],axis=0)
            means = absolute.mean(axis=0)
            for k,stat in enumerate(STATISTICS):
                exceed = int(np.count_nonzero(absolute[:,k]>=abs(observed[k])-EPS))
                tests.append(dict(model=model,statistic=stat,observed_signed=scalar(observed[k]),observed_abs=scalar(abs(observed[k])),
                    beta=scalar(prepared['beta']) if stat=='linear' else '',simulation_mean_abs=float(means[k]),
                    simulation_q025_abs=float(quantiles[0,k]),simulation_q975_abs=float(quantiles[1,k]),
                    exceedances=exceed,simulations=args.simulations,p_raw=(1+exceed)/(1+args.simulations) if possible[k] else '',
                    p_holm='',detected='',status='applicable' if possible[k] else 'not_applicable',applicability_reason=reasons[k]))
    adjusted = holm([row['p_raw'] if row['status']=='applicable' else 1 for row in tests])
    for row,p in zip(tests,adjusted):
        if row['status']=='applicable':
            row.update(p_holm=float(p),detected=bool(p<=.05),status='detected' if p<=.05 else 'not_detected')
    write_csv(args.output/'tests.csv',TEST_COLUMNS,tests)
    write_csv(args.output/'coverage.csv',COVERAGE_COLUMNS,coverage)
    configs = [('baseline_2_5pp',40,50,False,False,'change'),('baseline_10pp',10,50,False,False,'change'),
        ('unchanged_aptos',20,50,True,False,'change'),('finalists_100',20,100,False,False,'change'),
        ('domestic_only',20,50,False,True,'change'),('final_preference',20,50,False,False,'second_share')]
    for scenario,bins,floor,unchanged,domestic,outcome in configs:
        for model in MODELS:
            prepared = prepare(pairs,model,bins=bins,finalist_floor=floor,unchanged_aptos=unchanged,domestic_only=domestic,outcome=outcome)
            sens.append(sensitivity_row(prepared,scenario,floor,unchanged,domestic,outcome))
    write_csv(args.output/'sensitivity.csv',SENSITIVITY_COLUMNS,sens)
    summary = dict(matched_pairs=len(pairs['uf']),cohort_pairs=len(ids),paired_elections=[int(pairs['election_1']),int(pairs['election_2'])],family_size=4,
        primary_detected=sum(row['status']=='detected' for row in tests),primary_not_detected=sum(row['status']=='not_detected' for row in tests),
        primary_not_applicable=sum(row['status']=='not_applicable' for row in tests),national_raw_counts=raw_totals[0],national_cohort_descriptive=descriptive[0],
        interpretation='Conditional association; arithmetic decomposition and aggregate counts do not identify individual transitions or artificial causes')
    json_write(args.output/'summary.json',summary)
    for source in loaded['source_inputs'].values():
        if sha256(args.root/source['path'])!=source['sha256']:
            raise ValueError('Original input changed during H6 analysis')
    manifest.update(status='completed',completed_at_utc=datetime.now(timezone.utc).isoformat(),numpy_version=np.__version__,
        artifacts={path.name:dict(size_bytes=path.stat().st_size,sha256=sha256(path)) for path in sorted(args.output.iterdir()) if path.name!='manifest.json'})
    json_write(args.output/'manifest.json',manifest)
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
