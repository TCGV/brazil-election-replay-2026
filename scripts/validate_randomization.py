"""Independent audits of observed curves and cached Monte Carlo statistics.

Uses the original replay database for section counts, votes and timestamps.
Capital/size labels are fixed covariates reused from municipality_metadata, not
independently rebuilt here. No analysis implementation or NumPy is imported.
The retained .npy draw-curve caches are required to audit simulation statistics;
this does not independently regenerate or verify the permutation assignments.
"""
from __future__ import annotations

import argparse
import array
import ast
from collections import defaultdict
import csv
import hashlib
from itertools import groupby
import json
import math
from pathlib import Path
import sqlite3
import struct
import sys

KEY=('election_code','turno','uf','municipality','zone','section','cargo')
SOURCES={'first_partial_totalization':'first_time','bu_received':'bu_time'}
STAGES=(10,25,50,75,90,99)
REGIONS={uf:region for region,ufs in {
    'Nordeste':'AL BA CE MA PB PE PI RN SE','Norte':'AC AP AM PA RO RR TO',
    'Sudeste':'ES MG RJ SP','Sul':'PR RS SC','Centro-Oeste':'DF GO MT MS','Exterior':'ZZ',
}.items() for uf in ufs.split()}
IDS=('source_timestamp','election_code','turno','null_model','dimension','group','candidate','metric')


def _ratio(value,total):
    return 100*value/total if total else None


def _capital(value):
    return 'exterior' if value is None else ('capital' if value else 'non_capital')


def observed_curves(replay_db:Path,analysis_db:Path):
    """Compute original-data observations directly, retaining checkpoint summaries."""
    db=sqlite3.connect(replay_db.resolve().as_uri()+'?mode=ro',uri=True)
    db.execute('PRAGMA cache_size=-65536')
    db.execute('PRAGMA temp_store=FILE')
    db.execute('ATTACH DATABASE ? AS classification',(analysis_db.resolve().as_uri()+'?mode=ro',))
    baseline={}
    try:
        join13=' AND '.join(f's.{key}=v.{key}' for key in KEY)
        join22=' AND '.join(f's.{key}=f.{key}' for key in KEY)
        for election,turn in db.execute('SELECT DISTINCT election_code,turno FROM sections ORDER BY election_code,turno').fetchall():
            totals={dimension:defaultdict(int) for dimension in ('region','uf','capital_status','size_band')}
            for uf,capital,size,n in db.execute('''SELECT s.uf,m.is_capital,m.size_band,COUNT(*)
                FROM sections s JOIN classification.municipality_metadata m USING(election_code,turno,uf,municipality)
                WHERE s.election_code=? AND s.turno=? GROUP BY s.uf,m.is_capital,m.size_band''',(election,turn)):
                for dimension,label in [('uf',uf),('region',REGIONS[uf]),('capital_status',_capital(capital)),('size_band',size)]:
                    totals[dimension][label]+=n
            n=sum(totals['uf'].values())
            expected=db.execute('SELECT COUNT(*) FROM sections WHERE election_code=? AND turno=?',(election,turn)).fetchone()[0]
            if n!=expected:raise AssertionError('Classification join changed section count')
            for source,column in SOURCES.items():
                groups={dimension:defaultdict(lambda:[0,0,0,0]) for dimension in totals}
                national=[0,0,0,0]
                pending=list(STAGES)
                own_pending={uf:list(STAGES) for uf in totals['uf']}
                found={}
                def record(dimension,label,metric,candidate,stage,value,time,actual):
                    found[(dimension,label,metric,candidate,stage)]={'observed':value,'cutoff_timestamp':time,'actual_sections_percentage':actual}
                def national_snapshot(stage,time):
                    actual=100*national[0]/n
                    for dimension,labels in totals.items():
                        for label,total in labels.items():
                            current=groups[dimension][label]
                            record(dimension,label,'section_completion_percentage','',stage,100*current[0]/total,time,actual)
                            record(dimension,label,'nominal_weight_percentage','',stage,_ratio(current[1],national[1]),time,actual)
                    for candidate,index in [('13',2),('22',3)]:
                        record('candidate','BR','candidate_percentage',candidate,stage,_ratio(national[index],national[1]),time,actual)
                sql=f'''SELECT d.{column},s.uf,m.is_capital,m.size_band,COUNT(*),SUM(s.nominal_votes),
                    SUM(COALESCE(v.votes,0)),SUM(COALESCE(f.votes,0))
                    FROM sections s JOIN details d USING({','.join(KEY)})
                    JOIN classification.municipality_metadata m USING(election_code,turno,uf,municipality)
                    LEFT JOIN votes v ON {join13} AND v.nr_votavel=13
                    LEFT JOIN votes f ON {join22} AND f.nr_votavel=22
                    WHERE s.election_code=? AND s.turno=? AND d.{column} IS NOT NULL
                    GROUP BY d.{column},s.uf,m.is_capital,m.size_band ORDER BY d.{column}'''
                for timestamp,batch in groupby(db.execute(sql,(election,turn)),key=lambda row:row[0]):
                    changed=set()
                    for _,uf,capital,size,count,nominal,lula,flavio in batch:
                        changed.add(uf)
                        for target in [national,*[groups[d][label] for d,label in
                            [('uf',uf),('region',REGIONS[uf]),('capital_status',_capital(capital)),('size_band',size)]]]:
                            for index,value in enumerate((count,nominal,lula,flavio)):target[index]+=value
                    while pending and national[0]>=math.ceil(n*pending[0]/100):
                        national_snapshot(pending.pop(0),timestamp)
                    for uf in changed:
                        current=groups['uf'][uf]
                        while own_pending[uf] and current[0]>=math.ceil(totals['uf'][uf]*own_pending[uf][0]/100):
                            stage=own_pending[uf].pop(0)
                            for candidate,index in [('13',2),('22',3)]:
                                record('candidate',uf,'candidate_percentage',candidate,stage,_ratio(current[index],current[1]),timestamp,100*current[0]/totals['uf'][uf])
                if national[0]!=n or pending or any(own_pending.values()):
                    raise AssertionError('Observed source coverage is incomplete')
                baseline[(source,str(election),str(turn))]=found
        return baseline
    finally:
        db.close()


def _load_npy(path):
    """Read NumPy's documented .npy container using only the standard library."""
    with path.open('rb') as stream:
        if stream.read(6)!=b'\x93NUMPY':raise ValueError(f'Not an NPY file: {path}')
        major,minor=stream.read(2)
        if major==1:length=struct.unpack('<H',stream.read(2))[0]
        elif major in {2,3}:length=struct.unpack('<I',stream.read(4))[0]
        else:raise ValueError(f'Unsupported NPY version: {major}.{minor}')
        header=ast.literal_eval(stream.read(length).decode('utf8' if major==3 else 'latin1').strip())
        if header['fortran_order'] or header['descr'] not in {'<f8','>f8','=f8'}:
            raise ValueError(f'Unsupported draw array: {header}')
        shape=tuple(header['shape'])
        values=array.array('d')
        values.fromfile(stream,math.prod(shape))
        if header['descr']=='>f8' and sys.byteorder=='little' or header['descr']=='<f8' and sys.byteorder=='big':values.byteswap()
        if stream.read(1):raise ValueError('Unexpected NPY trailing bytes')
        return shape,values


def _holm(values):
    order=sorted(range(len(values)),key=values.__getitem__)
    adjusted=[None]*len(values);previous=0.0
    for rank,index in enumerate(order):
        previous=min(1.0,max(previous,(len(values)-rank)*values[index]))
        adjusted[index]=previous
    return adjusted


def validate(replay_db:Path,analysis_dir:Path,analysis_db:Path|None=None):
    manifest=json.loads((analysis_dir/'randomization-manifest.json').read_text())
    if manifest['status']!='completed':raise ValueError('Completed randomization run required')
    baseline=observed_curves(replay_db,analysis_db or analysis_dir/'analysis.sqlite')
    def read(name):
        with (analysis_dir/name).open(encoding='utf8',newline='') as stream:return list(csv.DictReader(stream))
    results=read('randomization-results.csv');bands=read('randomization-bands.csv')
    expected_ids=set()
    for (source,election,turn),points in baseline.items():
        for dimension,label,metric,candidate,stage in points:
            if stage!=STAGES[0]:continue
            for model in ('global','within_uf'):
                geographic=(dimension in {'region','uf'} if model=='global' else
                            dimension=='capital_status' and label!='exterior' or
                            model=='within_uf' and dimension=='size_band' and label!='exterior')
                political=dimension=='candidate' and (label=='BR' or model=='within_uf' and label!='ZZ')
                if geographic or political:
                    expected_ids.add((source,election,turn,model,dimension,label,candidate,metric))
    actual_ids=[tuple(row[k] for k in IDS) for row in results]
    if len(actual_ids)!=len(set(actual_ids)) or set(actual_ids)!=expected_ids:
        raise AssertionError(f'Incomplete or duplicate curve inventory: actual={len(actual_ids)}, expected={len(expected_ids)}')
    counts=defaultdict(int);maximum=0.0;tolerance=1e-9
    def numeric(actual,expected,category):
        nonlocal maximum
        if expected is None or not math.isfinite(expected):
            if actual not in ('',None):raise AssertionError(f'{category}: expected missing, got {actual}')
            return
        difference=abs(float(actual)-expected);maximum=max(maximum,difference)
        if not math.isfinite(difference) or difference>tolerance:raise AssertionError(f'{category}: {actual} != {expected}')
        counts[category]+=1
    by_id=defaultdict(dict)
    for row in bands:
        key=tuple(row[k] for k in IDS);stage=int(row['requested_sections_percentage'])
        if int(row['permutations'])!=manifest['permutations'] or int(row['seed'])!=manifest['seed']:
            raise AssertionError('Band configuration differs from manifest')
        if stage in by_id[key]:raise AssertionError('Duplicate band checkpoint')
        by_id[key][stage]=row
        expected=baseline[(row['source_timestamp'],row['election_code'],row['turno'])][
            (row['dimension'],row['group'],row['metric'],row['candidate'],stage)]
        numeric(row['observed'],expected['observed'],'observed_curve_values')
        numeric(row['actual_sections_percentage'],expected['actual_sections_percentage'],'observed_progress')
        if row['cutoff_timestamp']!=expected['cutoff_timestamp']:raise AssertionError('Wrong observed cutoff')
        if row['observed'] and row['reference_mean']:
            numeric(row['deviation_pp'],float(row['observed'])-float(row['reference_mean']),'deviation_identity')
        quantiles=[float(row[name]) for name in ('lower_2_5','reference_median','upper_97_5') if row[name]!='']
        if quantiles and not all(a<=b+tolerance for a,b in zip(quantiles,quantiles[1:])):raise AssertionError('Unordered reference quantiles')
    primary=[]
    for row in results:
        key=tuple(row[k] for k in IDS)
        if row['null_model'] not in {'global','within_uf'}:raise AssertionError('Unknown null model')
        if int(row['permutations'])!=manifest['permutations'] or int(row['seed'])!=manifest['seed']:
            raise AssertionError('Result configuration differs from manifest')
        if set(by_id[key])!=set(STAGES):raise AssertionError('Incomplete result curve')
        formal=row['metric']!='nominal_weight_percentage'
        expected_primary=int(formal and row['source_timestamp']=='first_partial_totalization')
        if int(row['primary_test'])!=expected_primary:raise AssertionError('Incorrect primary family membership')
        if row['p_value']:
            b=int(row['permutations']);exceeded=int(row['exceedance_count'])
            if not 0<=exceeded<=b:raise AssertionError('Invalid exceedance count')
            numeric(row['p_value'],(1+exceeded)/(b+1),'plus_one_p')
            if int(row['effective_permutations'])!=b:raise AssertionError('Wrong permutation denominator')
            expected_stat=max(abs(float(point['deviation_pp'])) for point in by_id[key].values())
            numeric(row['observed_statistic_pp'],expected_stat,'observed_score')
            if expected_primary:primary.append(row)
            elif row['p_adjusted'] or row['status']!='sensitivity_only':raise AssertionError('Sensitivity included in primary decisions')
        elif row['p_adjusted']:raise AssertionError('Adjusted p without raw p')
        if not formal and any(row[name] for name in ('p_value','p_adjusted','exceedance_count')):
            raise AssertionError('Descriptive weight curve incorrectly tested')
    if manifest['primary_hypotheses']!=len(primary):raise AssertionError('Primary hypothesis count differs from manifest')
    if manifest['primary_detected']!=sum(row['status']=='detected' for row in primary):raise AssertionError('Detected count differs from manifest')
    if manifest['primary_not_detected']!=sum(row['status']=='not_detected' for row in primary):raise AssertionError('Non-detected count differs from manifest')
    adjusted=_holm([float(row['p_value']) for row in primary])
    for row,value in zip(primary,adjusted):
        numeric(row['p_adjusted'],value,'holm_adjusted_p')
        if row['status']!=('detected' if value<=.05 else 'not_detected'):raise AssertionError('Incorrect Holm decision')
    # Independently audit centers and Monte Carlo ranks from retained simulation curves.
    grouped=defaultdict(list)
    for row in results:grouped[(row['election_code'],row['turno'],row['null_model'])].append(row)
    for (election,turn,model),rows in grouped.items():
        b=int(rows[0]['permutations']);seed=int(rows[0]['seed'])
        stem=f'{election}-{turn}-{model}-{b}-{seed}'
        cache=analysis_dir/'.randomization-cache'
        checkpoint=json.loads((cache/(stem+'.json')).read_text())
        if checkpoint['completed']!=b:raise AssertionError('Incomplete simulation checkpoint')
        if checkpoint['fingerprint']!=manifest['checkpoint_fingerprints'][f'{election}:{turn}:{model}']:
            raise AssertionError('Simulation checkpoint fingerprint differs from manifest')
        shape,values=_load_npy(cache/(stem+'.npy'))
        sources=list(SOURCES);per_source={source:[r for r in rows if r['source_timestamp']==source] for source in sources}
        descriptors=len(per_source[sources[0]])
        if shape!=(b+1,len(sources),descriptors,len(STAGES)):raise AssertionError('Unexpected simulation array shape')
        stride=len(sources)*descriptors*len(STAGES)
        for source_index,source in enumerate(sources):
            if len(per_source[source])!=descriptors:raise AssertionError('Different source descriptor counts')
            for curve,row in enumerate(per_source[source]):
                offset=(source_index*descriptors+curve)*len(STAGES)
                mean=[sum(values[r*stride+offset+j] for r in range(b+1))/(b+1) for j in range(len(STAGES))]
                key=tuple(row[k] for k in IDS)
                finite=all(math.isfinite(x) for x in mean)
                for j,stage in enumerate(STAGES):
                    point=by_id[key][stage]
                    numeric(point['observed'],values[offset+j],'cached_observation')
                    numeric(point['reference_mean'],mean[j] if finite else None,'pooled_center')
                if not row['p_value']:continue
                observed=max(abs(values[offset+j]-mean[j]) for j in range(len(STAGES)))
                numeric(row['observed_statistic_pp'],observed,'cached_score')
                exceeded=0
                for r in range(1,b+1):
                    score=max(abs(values[r*stride+offset+j]-mean[j]) for j in range(len(STAGES)))
                    exceeded+=score>=observed-1e-12
                if exceeded!=int(row['exceedance_count']):raise AssertionError(f'Cached exceedance mismatch: {key}: {exceeded} != {row["exceedance_count"]}')
                counts['cached_exceedance_counts']+=1
        counts['simulation_cache_files']+=1
    result={'status':'passed','replay_database':str(replay_db),'analysis_directory':str(analysis_dir),
        'validation_script':'scripts/validate_randomization.py',
        'validation_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'checks':dict(counts),'primary_hypotheses':len(primary),'mismatches':0,
        'maximum_absolute_numeric_difference':maximum,'absolute_numeric_tolerance':tolerance,
        'classification_scope':'Capital and electorate-size labels reused as fixed covariates from municipality_metadata; original section timestamps and vote counts independently aggregated from replay.sqlite.',
        'simulation_scope':'Pooled centers, observed scores, plus-one ranks and family adjustment audited from retained NPY curve caches using the standard library; permutation assignment generation is not independently repeated.',
        'interpretation':'A reference-order test, not proof of randomness, causal attribution or population-confidence inference.'}
    (analysis_dir/'randomization-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay-db',type=Path,default=Path('output/replay/replay.sqlite'))
    parser.add_argument('--analysis-dir',type=Path,default=Path('output/geography'))
    parser.add_argument('--analysis-db',type=Path,help='Classification database; defaults to analysis-dir/analysis.sqlite.')
    args=parser.parse_args()
    print(json.dumps(validate(args.replay_db,args.analysis_dir,args.analysis_db),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
