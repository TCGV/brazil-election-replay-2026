"""Random-order references for section arrivals, with paired timestamp sensitivity.

A draw assigns complete section payloads to fixed timestamp slots, nationally or
within each UF. Tests concern this exchangeability reference for the observed
census; they are not causal tests or population-sampling confidence intervals.
"""
from __future__ import annotations

import csv
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import logging
import multiprocessing
import os
from pathlib import Path
import sqlite3

import numpy as np

STAGES = (10, 25, 50, 75, 90, 99)
SOURCES = ('first_partial_totalization', 'bu_received')
MODELS = ('global', 'within_uf')
ALPHA = 0.05
VERSION = 'section-slot-permutation-v1'
TOLERANCE = 1e-12
LOG = logging.getLogger(__name__)


def holm_adjust(p_values):
    """Holm family-wise adjusted p-values, preserving None positions."""
    values = list(p_values)
    indexed = []
    for index, value in enumerate(values):
        if value is None:
            continue
        value = float(value)
        if not np.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('p-values must be finite values in [0,1], or None')
        indexed.append((value, index))
    indexed.sort()
    result = [None] * len(values)
    previous = 0.0
    count = len(indexed)
    for rank, (value, index) in enumerate(indexed):
        previous = max(previous, min(1.0, (count-rank)*value))
        result[index] = previous
    return result


def curve_test(observed, permutations):
    """Symmetric pooled-center maximum-deviation Monte Carlo curve test.

    All checkpoints in all realizations must be defined. An invariant pooled
    curve is N/A, even if a numerical mean has tiny rounding error. Equal maximum
    statistics alone do not imply invariance. Ties in S are counted conservatively.
    """
    observed = np.asarray(observed, dtype=float)
    permutations = np.asarray(permutations, dtype=float)
    if observed.ndim != 1 or permutations.ndim != 2 or permutations.shape[1:] != observed.shape:
        raise ValueError('observed must be 1D and permutations B-by-checkpoints')
    if not len(observed) or not len(permutations):
        raise ValueError('At least one checkpoint and one permutation are required')
    pooled = np.concatenate((observed[None, :], permutations), axis=0)
    if not np.all(np.isfinite(pooled)):
        return {'status':'not_applicable','reason':'undefined_checkpoint',
                'observed_statistic_pp':None,'p_value':None,'exceedance_count':None,
                'reference_mean':np.full(observed.shape,np.nan),'statistics':np.full(len(pooled),np.nan)}
    center = pooled.mean(axis=0)
    statistics = np.max(np.abs(pooled-center), axis=1)
    if np.max(np.ptp(pooled,axis=0)) <= TOLERANCE:
        return {'status':'not_applicable','reason':'invariant_reference',
                'observed_statistic_pp':None,'p_value':None,'exceedance_count':None,
                'reference_mean':center,'statistics':statistics}
    exceeded = int(np.count_nonzero(statistics[1:] >= statistics[0]-TOLERANCE))
    return {'status':'tested','reason':'','observed_statistic_pp':float(statistics[0]),
            'p_value':(1+exceeded)/(len(permutations)+1),'exceedance_count':exceeded,
            'reference_mean':center,'statistics':statistics}


def _ratio(numerator, denominator):
    numerator, denominator = np.broadcast_arrays(numerator, denominator)
    result = np.full(numerator.shape,np.nan,dtype=np.float64)
    np.divide(100.0*numerator,denominator,out=result,where=denominator!=0)
    return result


def _time(value):
    if value is None:
        raise ValueError('Randomization requires complete timestamps; missing events must not be silently omitted')
    moment=datetime.fromisoformat(value)
    if moment.tzinfo is not None:
        raise ValueError('Hora TSE must be a naive wall-clock timestamp; an explicit UTC offset requires a documented conversion')
    return moment.isoformat(sep=' ',timespec='microseconds').encode('ascii')


def _load_round(db, election, turn):
    uf_regions = db.execute('''SELECT uf,MIN(region),COUNT(DISTINCT region) FROM section_events
        WHERE election_code=? AND turno=? GROUP BY uf ORDER BY uf''',(election,turn)).fetchall()
    if any(count!=1 for _,_,count in uf_regions):
        raise ValueError('A UF has inconsistent regions')
    ufs = [uf for uf,_,_ in uf_regions]
    regions = sorted({region for _,region,_ in uf_regions})
    sizes = [row[0] for row in db.execute('''SELECT DISTINCT size_band FROM section_events
        WHERE election_code=? AND turno=? ORDER BY size_band''',(election,turn))]
    ui,ri,si = ({v:i for i,v in enumerate(values)} for values in (ufs,regions,sizes))
    dtype = np.dtype([('uf','i2'),('region','i2'),('capital','i1'),('size','i2'),
                      ('nominal','i8'),('lula','i8'),('flavio','i8'),('first','S26'),('bu','S26')])
    rows = db.execute('''SELECT uf,region,is_capital,size_band,nominal_votes,lula_votes,flavio_votes,first_time,bu_time
        FROM section_events WHERE election_code=? AND turno=? ORDER BY uf,municipality,zone,section''',(election,turn))
    def records():
        for uf,region,capital,size,nominal,lula,flavio,first,bu in rows:
            if min(nominal,lula,flavio)<0 or lula+flavio>nominal:
                raise ValueError('Candidate and nominal vote counts are inconsistent')
            yield ui[uf],ri[region],2 if capital is None else int(capital),si[size],nominal,lula,flavio,_time(first),_time(bu)
    data = np.fromiter(records(),dtype=dtype)
    if not len(data):
        raise ValueError('No section records in election/round')
    uf_region = np.array([ri[region] for _,region,_ in uf_regions])
    region_matrix = np.eye(len(regions),dtype=float)[:,uf_region]
    uf_counts = np.bincount(data['uf'],minlength=len(ufs))
    boundaries = np.r_[0,np.cumsum(uf_counts)]
    # Random gathers from structured fields stride across timestamp bytes. Compact
    # hot arrays reduce memory traffic, and one payload gather serves both sources.
    numeric={name:np.ascontiguousarray(data[name]) for name in ('uf','nominal','lula','flavio')}
    numeric['city']=np.ascontiguousarray(data['capital'].astype(np.int64)*len(sizes)+data['size'])
    return {'data':data,'numeric':numeric,'ufs':ufs,'regions':regions,'sizes':sizes,'region_matrix':region_matrix,
            'uf_counts':uf_counts,'region_counts':region_matrix@uf_counts,
            'capital_counts':np.bincount(data['capital'],minlength=3),
            'size_counts':np.bincount(data['size'],minlength=len(sizes)),
            'strata':[(int(boundaries[i]),int(boundaries[i+1])) for i in range(len(ufs))]}


def _slot_stages(times, indices):
    order = indices[np.argsort(times[indices],kind='stable')]
    ordered = times[order]
    targets = (len(order)*np.asarray(STAGES)+99)//100
    counts = np.searchsorted(ordered,ordered[targets-1],side='right')
    labels = np.searchsorted(counts,np.arange(len(order)),side='right').astype(np.int64)
    info = [{'cutoff_timestamp':ordered[count-1].decode('ascii'),
             'actual_sections_percentage':100*int(count)/len(order)} for count in counts]
    return order,labels,info


def _sources(round_data):
    data=round_data['data'];n=len(data);u=len(round_data['ufs']);j=3*len(round_data['sizes'])
    result=[]
    for field in ('first','bu'):
        order,labels,info = _slot_stages(data[field],np.arange(n))
        stage=np.empty(n,dtype=np.int64);stage[order]=labels
        own=np.empty(n,dtype=np.int64);own_info={}
        for uf,(start,stop) in enumerate(round_data['strata']):
            ordering,labels_,information=_slot_stages(data[field],np.arange(start,stop))
            own[ordering]=labels_;own_info[uf]=information
        result.append({'stage':stage,'uf_offsets':stage*u,'city_offsets':stage*j,
                       'own_uf_bins':own*u+data['uf'],'info':info,'own_info':own_info})
    return result


def _descriptors(round_data,model):
    formal=[];weights=[]
    def geography(dimension,label,index):
        formal.append({'dimension':dimension,'group':label,'candidate':'','metric':'section_completion_percentage','index':index})
        weights.append({'dimension':dimension,'group':label,'candidate':'','metric':'nominal_weight_percentage','index':index})
    if model=='global':
        for index,label in enumerate(round_data['regions']):geography('region',label,index)
        for index,label in enumerate(round_data['ufs']):geography('uf',label,index)
    else:
        for index,label in enumerate(('non_capital','capital')):
            if round_data['capital_counts'][index]:geography('capital_status',label,index)
        for index,label in enumerate(round_data['sizes']):
            if label!='exterior' and round_data['size_counts'][index]:geography('size_band',label,index)
    for candidate in ('13','22'):
        formal.append({'dimension':'candidate','group':'BR','candidate':candidate,'metric':'candidate_percentage'})
    if model=='within_uf':
        for index,uf in enumerate(round_data['ufs']):
            if uf=='ZZ':continue
            for candidate in ('13','22'):
                formal.append({'dimension':'candidate','group':uf,'candidate':candidate,'metric':'candidate_percentage','index':index})
    return formal+weights


def _cumulative(bins,weights,groups):
    return np.bincount(bins,weights=weights,minlength=7*groups).reshape(7,groups).cumsum(axis=0)[:6].T


def _payload(round_data,model,assignment):
    keys=('nominal','lula','flavio','uf' if model=='global' else 'city')
    return {name:round_data['numeric'][name][assignment] for name in keys}


def _evaluate(round_data,source,model,assignment,descriptors,payload=None):
    data=round_data['data'];u=len(round_data['ufs']);s=len(round_data['sizes'])
    if payload is None:payload=_payload(round_data,model,assignment)
    nominal,lula,flavio=(payload[name] for name in ('nominal','lula','flavio'))
    result=np.empty((len(descriptors),6),dtype=np.float64)
    if model=='global':
        bins=source['uf_offsets']+payload['uf']
        counts=_cumulative(bins,None,u);votes=_cumulative(bins,nominal,u)
        national=votes.sum(axis=0)
        region_counts=round_data['region_matrix']@counts;region_votes=round_data['region_matrix']@votes
        completions={'uf':_ratio(counts,round_data['uf_counts'][:,None]),
                     'region':_ratio(region_counts,round_data['region_counts'][:,None])}
        weights={'uf':_ratio(votes,national),'region':_ratio(region_votes,national)}
        candidate_br={'13':_ratio(np.bincount(source['stage'],weights=lula,minlength=7).cumsum()[:6],national),
                      '22':_ratio(np.bincount(source['stage'],weights=flavio,minlength=7).cumsum()[:6],national)}
    else:
        bins=source['city_offsets']+payload['city']
        counts=np.bincount(bins,minlength=7*3*s).reshape(7,3,s).cumsum(axis=0)[:6]
        votes=np.bincount(bins,weights=nominal,minlength=7*3*s).reshape(7,3,s).cumsum(axis=0)[:6]
        national=votes.sum(axis=(1,2))
        completions={'capital_status':_ratio(counts.sum(axis=2).T,round_data['capital_counts'][:,None]),
                     'size_band':_ratio(counts.sum(axis=1).T,round_data['size_counts'][:,None])}
        weights={'capital_status':_ratio(votes.sum(axis=2).T,national),
                 'size_band':_ratio(votes.sum(axis=1).T,national)}
        candidate_br={'13':_ratio(np.bincount(source['stage'],weights=lula,minlength=7).cumsum()[:6],national),
                      '22':_ratio(np.bincount(source['stage'],weights=flavio,minlength=7).cumsum()[:6],national)}
        own_nominal=_cumulative(source['own_uf_bins'],nominal,u)
        candidate_uf={'13':_ratio(_cumulative(source['own_uf_bins'],lula,u),own_nominal),
                      '22':_ratio(_cumulative(source['own_uf_bins'],flavio,u),own_nominal)}
    for index,desc in enumerate(descriptors):
        if desc['dimension']=='candidate':
            result[index]=candidate_br[desc['candidate']] if desc['group']=='BR' else candidate_uf[desc['candidate']][desc['index']]
        elif desc['metric']=='section_completion_percentage':result[index]=completions[desc['dimension']][desc['index']]
        else:result[index]=weights[desc['dimension']][desc['index']]
    return result


def _atomic_json(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    temporary.replace(path)


def _draws(round_data,source_data,descriptors,model,election,turn,output_dir,permutations,seed):
    data=round_data['data']
    digest=hashlib.sha256(data.tobytes())
    engine_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    digest.update(json.dumps([VERSION,engine_hash,np.__version__,STAGES,SOURCES,model,
                             str(election),str(turn),permutations,seed,descriptors],sort_keys=True).encode())
    fingerprint=digest.hexdigest()
    cache=output_dir/'.randomization-cache';cache.mkdir(exist_ok=True)
    stem=f'{election}-{turn}-{model}-{permutations}-{seed}'
    samples_path=cache/(stem+'.npy');progress_path=cache/(stem+'.json')
    shape=(permutations+1,len(SOURCES),len(descriptors),len(STAGES))
    rng=np.random.default_rng(np.random.SeedSequence([seed,int.from_bytes(hashlib.sha256(f'{election}:{turn}:{model}'.encode()).digest()[:8],'little')]))
    if progress_path.exists():
        state=json.loads(progress_path.read_text())
        if state['fingerprint']!=fingerprint:raise ValueError(f'Incompatible randomization checkpoint: {progress_path}')
        draws=np.lib.format.open_memmap(samples_path,mode='r+')
        if draws.shape!=shape:raise ValueError('Invalid randomization checkpoint shape')
        completed=state['completed'];rng.bit_generator.state=state['rng_state']
        LOG.info('Resuming %s/%s %s at %s/%s',election,turn,model,completed,permutations)
    else:
        draws=np.lib.format.open_memmap(samples_path,mode='w+',dtype='float64',shape=shape)
        identity=np.arange(len(data))
        payload=_payload(round_data,model,identity)
        for index,source in enumerate(source_data):draws[0,index]=_evaluate(round_data,source,model,identity,descriptors,payload)
        completed=0
        draws.flush()
        _atomic_json(progress_path,{'fingerprint':fingerprint,'completed':0,'rng_state':rng.bit_generator.state})
    for draw in range(completed+1,permutations+1):
        if model=='global':assignment=rng.permutation(len(data))
        else:
            assignment=np.arange(len(data))
            for start,stop in round_data['strata']:assignment[start:stop]=start+rng.permutation(stop-start)
        payload=_payload(round_data,model,assignment)
        for index,source in enumerate(source_data):draws[draw,index]=_evaluate(round_data,source,model,assignment,descriptors,payload)
        if draw%100==0 or draw==permutations:
            draws.flush()
            _atomic_json(progress_path,{'fingerprint':fingerprint,'completed':draw,'rng_state':rng.bit_generator.state})
            LOG.info('Randomization %s/%s %s: %s/%s',election,turn,model,draw,permutations)
    return draws,fingerprint


def _finite(value):
    return float(value) if value is not None and np.isfinite(value) else None


def _workers(task_count,permutations):
    if permutations<100:return 1
    available=len(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else (os.cpu_count() or 1)
    quota_file=Path('/sys/fs/cgroup/cpu.max')
    if quota_file.exists():
        quota,period=quota_file.read_text().split()
        if quota!='max':available=min(available,max(1,int(quota)//int(period)))
    return max(1,min(4,available,task_count))


def _warm_batch(args):
    db_path,output_dir,election,turn,model,permutations,seed=args
    db=sqlite3.connect(Path(db_path).resolve().as_uri()+'?mode=ro',uri=True)
    db.execute('PRAGMA query_only=ON')
    try:
        data=_load_round(db,election,turn)
        sources=_sources(data)
        descriptors=_descriptors(data,model)
        samples,fingerprint=_draws(data,sources,descriptors,model,election,turn,Path(output_dir),permutations,seed)
        del samples
        return fingerprint
    finally:db.close()


def run_randomization(db_path:Path,output_dir:Path,permutations=4999,seed=20261027,workers=None):
    """Write formal curve tests and paired BU sensitivity references.

    Checkpoints permit exact resumption without silently reducing the requested B.
    The Holm family contains only applicable primary first-totalization tests from
    both rounds. BU and nominal-weight bands are explicitly nonprimary.
    """
    if isinstance(permutations,bool) or int(permutations)!=permutations or permutations<1:
        raise ValueError('permutations must be a positive integer')
    if isinstance(seed,bool) or int(seed)!=seed or seed<0:raise ValueError('seed must be a nonnegative integer')
    permutations,seed=int(permutations),int(seed)
    db_path,output_dir=Path(db_path),Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    manifest_path=output_dir/'randomization-manifest.json'
    manifest={'status':'running','algorithm':VERSION,'engine_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'permutations':permutations,'seed':seed,'rng':'NumPy default_rng PCG64',
              'numpy_version':np.__version__,'stages':list(STAGES),'sources':list(SOURCES),'primary_source':SOURCES[0],
              'null_models':{'global':'Exchange complete section payloads nationally over fixed timestamp slots.',
                             'within_uf':'Exchange payloads only within UF; preserve UF section arrivals at every timestamp.'},
              'unit':'section payload including geography, municipal electorate band and all candidate/nominal votes',
              'ties':'Retain timestamp-slot multiset; include all events tied at a checkpoint cutoff.',
              'paired_sensitivity':'The identical section-to-slot permutation is applied to first-totalization and BU-receipt timestamp pairs.',
              'test':'Symmetric pooled observed+B mean at each checkpoint; maximum absolute deviation over the six checkpoints.',
              'p_value':'(1 + null statistics >= observed statistic, tolerance 1e-12 pp) / (B + 1)',
              'multiplicity':'Holm FWER 0.05 across applicable primary curves of both rounds; no checkpoint-by-checkpoint tests.',
              'envelopes':'2.5/97.5 percentiles of permutation curves, pointwise; not simultaneous bands or population confidence intervals.',
              'interpretation':'A census random-order reference, not a population sampling or causal test. Nonrejection does not establish randomness.',
              'not_applicable':'Undefined checkpoint in observed or any draw, or invariant pooled curves. Conditional UF/region count tests are not performed because they are fixed by design.',
              'operational_limit':'Timestamp batch sizes remain fixed, but the geographic/operational membership of batches is not preserved.',
              'source_database':str(db_path),'started_at_utc':datetime.now(timezone.utc).isoformat(),'rounds':[]}
    source_manifest=db_path.parent/'analysis-manifest.json'
    if source_manifest.exists():
        provenance=json.loads(source_manifest.read_text())
        manifest['source_inputs']=provenance.get('source_inputs')
        manifest['analysis_sections']=provenance.get('analysis_sections')
    _atomic_json(manifest_path,manifest)
    rows=[];bands=[]
    db=sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro',uri=True)
    db.execute('PRAGMA query_only=ON')
    try:
        elections=db.execute('SELECT DISTINCT election_code,turno FROM section_events ORDER BY election_code,turno').fetchall()
        jobs=[(str(db_path),str(output_dir),election,turn,model,permutations,seed)
              for election,turn in elections for model in MODELS]
        worker_count=_workers(len(jobs),permutations) if workers is None else int(workers)
        if worker_count<1:raise ValueError('workers must be positive')
        worker_count=min(worker_count,len(jobs))
        manifest['workers']=worker_count
        _atomic_json(manifest_path,manifest)
        if worker_count>1:
            LOG.info('Preparing independent round/null batches with %s workers',worker_count)
            # The CLI may already have initialized NumPy/BLAS or Matplotlib.
            # Fresh interpreters avoid inheriting their native-library locks.
            context=multiprocessing.get_context('spawn')
            with ProcessPoolExecutor(max_workers=worker_count,mp_context=context) as pool:
                # Workers only write their own unique draw/progress checkpoints.
                # The parent subsequently validates and reads each completed batch.
                list(pool.map(_warm_batch,jobs))
        for election,turn in elections:
            round_data=_load_round(db,election,turn);source_data=_sources(round_data)
            manifest['rounds'].append({'election_code':str(election),'turno':str(turn),'sections':len(round_data['data'])})
            for model in MODELS:
                descriptors=_descriptors(round_data,model)
                samples,fingerprint=_draws(round_data,source_data,descriptors,model,election,turn,output_dir,permutations,seed)
                for source_index,source in enumerate(SOURCES):
                    for curve,desc in enumerate(descriptors):
                        observed=np.asarray(samples[0,source_index,curve]);null=np.asarray(samples[1:,source_index,curve])
                        formal=desc['metric']!='nominal_weight_percentage'
                        result=curve_test(observed,null)
                        common={'source_timestamp':source,'election_code':str(election),'turno':str(turn),'null_model':model,
                                'dimension':desc['dimension'],'group':desc['group'],'candidate':desc['candidate'],'metric':desc['metric']}
                        applicable=result['status']=='tested'
                        primary=bool(formal and source_index==0)
                        status='not_applicable' if not applicable else ('pending' if primary else ('sensitivity_only' if formal else 'descriptive_only'))
                        row=dict(common,primary_test=int(primary),observed_statistic_pp=result['observed_statistic_pp'] if formal else None,
                                 p_value=result['p_value'] if formal else None,p_adjusted=None,status=status,reason=result.get('reason',''),
                                 exceedance_count=result['exceedance_count'] if formal else None,effective_permutations=permutations,
                                 permutations=permutations,seed=seed)
                        rows.append(row)
                        if np.all(np.isfinite(null)):
                            lower,median,upper=np.quantile(null,[.025,.5,.975],axis=0)
                        else:lower=median=upper=np.full(len(STAGES),np.nan)
                        info=source_data[source_index]['own_info'][desc['index']] if desc['dimension']=='candidate' and desc['group']!='BR' else source_data[source_index]['info']
                        for stage_index,stage in enumerate(STAGES):
                            bands.append(dict(common,requested_sections_percentage=stage,**info[stage_index],
                                observed=_finite(observed[stage_index]),reference_mean=_finite(result['reference_mean'][stage_index]),
                                reference_median=_finite(median[stage_index]),lower_2_5=_finite(lower[stage_index]),upper_97_5=_finite(upper[stage_index]),
                                deviation_pp=_finite(observed[stage_index]-result['reference_mean'][stage_index]),
                                primary_test=int(primary),permutations=permutations,seed=seed))
                manifest.setdefault('checkpoint_fingerprints',{})[f'{election}:{turn}:{model}']=fingerprint
                del samples
        primary_rows=[row for row in rows if row['primary_test'] and row['p_value'] is not None]
        adjusted=holm_adjust([row['p_value'] for row in primary_rows])
        for row,p in zip(primary_rows,adjusted):
            row['p_adjusted']=p;row['status']='detected' if p<=ALPHA else 'not_detected'
        for filename,records in [('randomization-results.csv',rows),('randomization-bands.csv',bands)]:
            if not records:raise ValueError('No randomization results')
            with (output_dir/filename).open('w',encoding='utf8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(records[0]),lineterminator='\n');writer.writeheader();writer.writerows(records)
        manifest.update(status='completed',primary_hypotheses=len(primary_rows),
                        primary_detected=sum(row['status']=='detected' for row in primary_rows),
                        primary_not_detected=sum(row['status']=='not_detected' for row in primary_rows),
                        not_applicable=sum(row['status']=='not_applicable' for row in rows),
                        minimum_p_value=1/(permutations+1),completed_at_utc=datetime.now(timezone.utc).isoformat(),
                        artifacts=['randomization-results.csv','randomization-bands.csv','randomization-manifest.json'])
        _atomic_json(manifest_path,manifest)
        return manifest
    except Exception as error:
        manifest.update(status='failed',error=str(error));_atomic_json(manifest_path,manifest);raise
    finally:db.close()
