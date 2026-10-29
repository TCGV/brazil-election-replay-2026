#!/usr/bin/env python3
"""H7 municipal census and conditional allocation of paired trajectories.

Orchestration/cache guards adapt the H6 runner at cb32076a0eea70a35782fbabba7777a5e49c94fc.
All H7 evidence and new implementation live in this hypothesis folder.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
from fractions import Fraction
import gzip
import hashlib
import io
import json
import multiprocessing
from pathlib import Path
import subprocess

import numpy as np

from load_data import load_data, sha256
from regularity_statistics import (MODELS, STATISTICS, TAILS, EPS, COUNT_FIELDS,
    pair_sections, eligibility, section_changes, prepare, aggregate, score,
    assignment, simulation_state, municipality_metrics, score_variability, holm)

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
METHOD_SHA256 = '7212a1f6941c2357b751bb3b44dae60e931e2cdba5801c7dc231bd86bcb44066'
REGIONS = {'AC':'Norte','AP':'Norte','AM':'Norte','PA':'Norte','RO':'Norte','RR':'Norte','TO':'Norte',
    'AL':'Nordeste','BA':'Nordeste','CE':'Nordeste','MA':'Nordeste','PB':'Nordeste','PE':'Nordeste','PI':'Nordeste','RN':'Nordeste','SE':'Nordeste',
    'DF':'Centro-Oeste','GO':'Centro-Oeste','MT':'Centro-Oeste','MS':'Centro-Oeste',
    'ES':'Sudeste','MG':'Sudeste','RJ':'Sudeste','SP':'Sudeste','PR':'Sul','RS':'Sul','SC':'Sul','ZZ':'Exterior'}
BASE_COUNTS = ('aptos','turnout','abstentions','nominal','blank','null_votes','legend','separate','v13','v22','f')
PAIRED_COUNTS = tuple(f'{field}_{turn}' for turn in (1,2) for field in BASE_COUNTS)
METRIC_FIELDS = ('gain13','gain22','count_advantage','nominal_gain13','nominal_gain22','nominal_advantage',
    'relative_gain13','relative_gain22','relative_advantage','q1','q2','delta',
    *[field for metric in ('count','nominal','relative','conditional') for field in (f'sign_{metric}',f'defined_{metric}')],
    *[field for metric in ('nominal','relative','conditional') for field in (f'{metric}_num',f'{metric}_den')])
CENSUS_COLUMNS = ('universe','uf','municipality','municipality_name','region','domestic','present_1','present_2',
    'sections_1','sections_2',*PAIRED_COUNTS,'other_nominal_1','other_nominal_2',
    'raw_sections_1','raw_sections_2','cohort_sections_1','cohort_sections_2',
    'cohort_section_coverage_1','cohort_section_coverage_2','cohort_nominal_coverage_1','cohort_nominal_coverage_2',
    'aptos_identity_residual_1','aptos_identity_residual_2',*METRIC_FIELDS,
    'nominal_shift_term_pp','nominal_exit_term_pp','nominal_identity_residual',
    'count_shift_term','count_exposure_term','count_identity_residual')
CANDIDATE_COLUMNS = ('universe','uf','municipality','turno','candidate','candidate_name','votes','present')
DIRECTION_COLUMNS = ('universe','scope_type','scope','metric','units','defined_units','undefined_units','advantage13','advantage22','ties',
    'fraction13_all','fraction22_all','fraction13_defined','fraction22_defined',
    'reaches99_13_all','reaches99_22_all','reaches99_13_defined','reaches99_22_defined',
    'nominal2_weight_defined','nominal2_weight_13','nominal2_weight_22','fraction13_vote_weighted_defined','fraction22_vote_weighted_defined')
SECTION_COLUMNS = ('uf','municipality','municipality_name','zone','section','place','source_line_1','source_line_2','domestic',
    *PAIRED_COUNTS,'q1','q2','delta','delta_numerator','delta_denominator')
UNIT_COLUMNS = ('model','unit','uf','municipality','zone','place','section','ns',*PAIRED_COUNTS,
    'group','size_band','initial_turnout_bin','initial_preference_bin','initial_other_bin','movable',
    'target_destination','delta_sum','delta_mean','group_mean','residual')
GROUP_COLUMNS = ('model','group','uf','size_band','initial_turnout_bin','initial_preference_bin','initial_other_bin',
    'units','sections','municipalities','target_slots','target_sections','movable','target_reachable','mean_section_delta')
MUNICIPAL_COLUMNS = ('model','uf','municipality','municipality_name','target','ns','units',*PAIRED_COUNTS,
    'delta_sum','delta_mean','residual_sum','residual_mean',*METRIC_FIELDS,'movable_units','movable_sections')
EDGE_COLUMNS = ('model','uf','left_municipality','right_municipality','left_name','right_name',
    'original_q1_left','original_q1_right','original_q1_gap_pp','left_sections','right_sections',
    'left_residual_mean','right_residual_mean','signed_contrast_pp','J_component','attains_max')
COVERAGE_COLUMNS = ('model','uf','cohort_sections','units','groups','municipalities','targets','target_sections',
    'movable_groups','movable_units','movable_sections','target_reachable_groups','target_movable_units',
    'target_movable_sections','reachable_targets','adjacent_pairs')
DISTRIBUTION_COLUMNS = ('universe','scope_type','scope','metric','units','defined_units','undefined_units',
    'min','q025','q25','median','q75','q975','max','mean','exact_unique')
REPETITION_COLUMNS = ('universe','scope_type','scope','metric','numerator','denominator','value','frequency','defined_units')
TEST_COLUMNS = ('model','statistic','tail','observed','simulation_mean','simulation_q025','simulation_q975',
    'exceedances','simulations','p_raw','p_holm','detected','status','applicability_reason')
PERMUTATION_COLUMNS = ('model','repetition',*STATISTICS)
SENSITIVITY_COLUMNS = ('scenario','model','bins','finalist_floor','unchanged_aptos','min_target','cohort_sections','units',
    'groups','movable_groups','movable_units','movable_sections','municipalities','targets','target_sections','adjacent_pairs',*STATISTICS)
_WORKER = None


def json_write(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


@contextmanager
def csv_writer(path,columns):
    path=Path(path)
    with path.open('wb') as raw:
        compressed=gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) if path.suffix=='.gz' else raw
        with io.TextIOWrapper(compressed,encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns,lineterminator='\n',extrasaction='raise')
            writer.writeheader();yield writer


def write_csv(path,columns,rows):
    with csv_writer(path,columns) as writer:
        writer.writerows(rows)


def scalar(value):
    if isinstance(value,(bool,np.bool_)):return bool(value)
    if isinstance(value,(int,np.integer)):return int(value)
    if value is None or not np.isfinite(value):return ''
    return float(value)


def scopes(ufs):
    """BR means domestic municipalities; overseas source units are separate."""
    ufs=np.asarray(ufs)
    unknown=set(ufs.tolist())-REGIONS.keys()
    if unknown:raise ValueError(f'Unknown UF: {unknown}')
    domestic=ufs!='ZZ'
    yield 'BR','BR',domestic
    for uf in sorted(set(ufs.tolist())):
        yield 'UF',str(uf),ufs==uf
    regions=np.asarray([REGIONS[str(uf)] for uf in ufs])
    for region in sorted(set(regions[domestic].tolist())):
        yield 'region',region,regions==region
    if np.any(~domestic):yield 'exterior','Exterior',~domestic


def pairing_rows(joined):
    first,second=joined['rounds'];pairs=joined['pairs']
    for uf in ['BR',*sorted(set(first['uf'].tolist())|set(second['uf'].tolist()))]:
        count=lambda values:len(values) if uf=='BR' else int(np.count_nonzero(values==uf))
        yield dict(uf=uf,round1_records=count(first['uf']),round2_records=count(second['uf']),
            matched_pairs=count(pairs['uf']),only_round1=count(first['uf'][joined['unmatched'][0][2]]),
            only_round2=count(second['uf'][joined['unmatched'][1][2]]))


def eligibility_rows(pairs):
    mask,reasons,basic=eligibility(pairs)
    for uf in ['BR',*sorted(set(pairs['uf'].tolist()))]:
        use=np.ones(len(mask),dtype=bool) if uf=='BR' else pairs['uf']==uf
        chosen=use&mask
        row=dict(uf=uf,matched_pairs=int(use.sum()),basic_eligible=int((use&basic).sum()),
            cohort_pairs=int(chosen.sum()),domestic_cohort_pairs=int((chosen&(pairs['uf']!='ZZ')).sum()))
        for reason in ('section_status','aptos_below_50','nonpositive_turnout','nominal_below_50',
                       'finalists_below_floor','missing_place','changed_place','aptos_ratio'):
            row[f'excluded_{reason}']=int((use&(reasons==reason)).sum())
        row['changed_aptos_cohort']=int((chosen&(pairs['aptos_1']!=pairs['aptos_2'])).sum())
        yield row


def round_municipal(rd,indices=None):
    indices=np.arange(len(rd['uf'])) if indices is None else np.asarray(indices,dtype=int)
    if not len(indices):return {}
    keys=np.empty(len(indices),dtype=[('uf','U2'),('municipality','i4')])
    keys['uf'],keys['municipality']=rd['uf'][indices],rd['municipality'][indices]
    unique,labels,sizes=np.unique(keys,return_inverse=True,return_counts=True)
    source={field:rd[field][indices].astype(np.int64) for field in BASE_COUNTS if field not in {'v13','v22','f'}}
    candidates={number:rd['candidate_votes'][indices,j].astype(np.int64) for j,number in enumerate(rd['candidate_numbers'])}
    source.update(v13=candidates[13],v22=candidates[22],f=candidates[13]+candidates[22])
    def totals(values):
        if np.any(values<0) or int(values.sum(dtype=np.int64))>2**53:
            raise ArithmeticError('Unsafe aggregate count bound')
        return np.bincount(labels,weights=values,minlength=len(unique)).astype(np.int64)
    sums={field:totals(value) for field,value in source.items()}
    cv={number:totals(value) for number,value in candidates.items()}
    result={}
    for i,key in enumerate(unique):
        result[str(key['uf']),int(key['municipality'])]=dict(sections=int(sizes[i]),
            **{field:int(value[i]) for field,value in sums.items()},
            candidates={number:int(value[i]) for number,value in cv.items()})
    return result


def metric_row(values,index):
    result={field:scalar(values[field][index]) for field in METRIC_FIELDS}
    for metric in ('count','nominal','relative','conditional'):
        if not bool(values[f'defined_{metric}'][index]):
            result[f'sign_{metric}']=''
            if metric=='count':
                for field in ('gain13','gain22','count_advantage'):result[field]=''
            else:
                result[f'{metric}_num']=result[f'{metric}_den']=''
    return result


def census(joined,names):
    pairs=joined['pairs'];mask,_,_=eligibility(pairs);ids=np.flatnonzero(mask)
    rounds=joined['rounds']
    raw={turn:round_municipal(rd) for turn,rd in zip((1,2),rounds)}
    cohort={turn:round_municipal(rd,index[ids]) for turn,rd,index in zip((1,2),rounds,joined['matched_indices'])}
    keys=sorted(set(raw[1])|set(raw[2]))
    rows=[];candidate_rows=[]
    zero=dict(sections=0,**{field:0 for field in BASE_COUNTS},candidates={})
    for universe,maps in (('raw',raw),('cohort',cohort)):
        counts={field:np.asarray([maps[turn].get(key,zero)[base] for key in keys],dtype=np.int64)
                for turn in (1,2) for base in BASE_COUNTS for field in (f'{base}_{turn}',)}
        counts.update({f'present_{turn}':np.asarray([key in maps[turn] for key in keys]) for turn in (1,2)})
        metrics=municipality_metrics(counts)
        for i,(uf,municipality) in enumerate(keys):
            row=dict(universe=universe,uf=uf,municipality=municipality,
                municipality_name=names.get(f'{uf}:{municipality}',''),region=REGIONS[uf],domestic=uf!='ZZ')
            for turn,rd in zip((1,2),rounds):
                selected=maps[turn].get((uf,municipality),zero)
                original=raw[turn].get((uf,municipality),zero)
                eligible=cohort[turn].get((uf,municipality),zero)
                row.update({f'present_{turn}':(uf,municipality) in maps[turn],f'sections_{turn}':selected['sections'],
                    **{f'{field}_{turn}':selected[field] for field in BASE_COUNTS},
                    f'other_nominal_{turn}':selected['nominal']-selected['f'],
                    f'raw_sections_{turn}':original['sections'],f'cohort_sections_{turn}':eligible['sections'],
                    f'cohort_section_coverage_{turn}':eligible['sections']/original['sections'] if original['sections'] else '',
                    f'cohort_nominal_coverage_{turn}':eligible['nominal']/original['nominal'] if original['nominal'] else '',
                    f'aptos_identity_residual_{turn}':selected['aptos']-selected['turnout']-selected['abstentions']})
                for number in rd['candidate_numbers']:
                    candidate_rows.append(dict(universe=universe,uf=uf,municipality=municipality,turno=turn,candidate=number,
                        candidate_name='',votes=selected['candidates'].get(number,0),present=row[f'present_{turn}']))
            row.update(metric_row(metrics,i))
            for field in ('nominal_shift_term_pp','nominal_exit_term_pp','nominal_identity_residual',
                          'count_shift_term','count_exposure_term','count_identity_residual'):
                row[field]=''
            if row['present_1'] and row['present_2'] and row['f_1']>0 and row['f_2']>0 and row['nominal_1']>0 and row['nominal_2']>0:
                q1=Fraction(row['v13_1'],row['f_1']);q2=Fraction(row['v13_2'],row['f_2'])
                nominal_shift=200*(q2-q1)
                nominal_exit=100*(1-Fraction(row['f_1'],row['nominal_1']))*(2*q1-1)
                nominal_adv=100*(Fraction(row['v13_2']-row['v22_2'],row['nominal_2'])-Fraction(row['v13_1']-row['v22_1'],row['nominal_1']))
                count_shift=2*row['f_2']*(q2-q1)
                count_exposure=(row['f_2']-row['f_1'])*(2*q1-1)
                if row['f_2']!=row['nominal_2'] or nominal_shift+nominal_exit!=nominal_adv or count_shift+count_exposure!=row['count_advantage']:
                    raise ArithmeticError('Municipal mechanical identities failed')
                row.update(nominal_shift_term_pp=float(nominal_shift),nominal_exit_term_pp=float(nominal_exit),nominal_identity_residual=0,
                    count_shift_term=float(count_shift),count_exposure_term=float(count_exposure),count_identity_residual=0)
            rows.append(row)
    return rows,candidate_rows


def direction_rows(census_rows):
    for universe in ('raw','cohort'):
        selected=[row for row in census_rows if row['universe']==universe]
        ufs=np.asarray([row['uf'] for row in selected])
        for scope_type,scope,use in scopes(ufs):
            rows=[row for row,take in zip(selected,use) if take]
            for metric in ('count','nominal','relative','conditional'):
                defined=[row for row in rows if row[f'defined_{metric}']]
                positive=[row for row in defined if row[f'sign_{metric}']>0]
                negative=[row for row in defined if row[f'sign_{metric}']<0]
                n=len(rows);d=len(defined);a=len(positive);b=len(negative)
                w=sum(row['nominal_2'] for row in defined);wa=sum(row['nominal_2'] for row in positive);wb=sum(row['nominal_2'] for row in negative)
                yield dict(universe=universe,scope_type=scope_type,scope=scope,metric=metric,units=n,defined_units=d,undefined_units=n-d,
                    advantage13=a,advantage22=b,ties=d-a-b,fraction13_all=a/n if n else '',fraction22_all=b/n if n else '',
                    fraction13_defined=a/d if d else '',fraction22_defined=b/d if d else '',
                    reaches99_13_all=100*a>=99*n if n else '',reaches99_22_all=100*b>=99*n if n else '',
                    reaches99_13_defined=100*a>=99*d if d else '',reaches99_22_defined=100*b>=99*d if d else '',
                    nominal2_weight_defined=w,nominal2_weight_13=wa,nominal2_weight_22=wb,
                    fraction13_vote_weighted_defined=wa/w if w else '',fraction22_vote_weighted_defined=wb/w if w else '')


def section_rows(pairs,ids,changes,names):
    for j,i in enumerate(ids):
        row={field:str(pairs[field][i]) if field=='uf' else int(pairs[field][i]) for field in ('uf','municipality','zone','section')}
        row.update(municipality_name=names.get(f'{row["uf"]}:{row["municipality"]}',''),place=int(pairs['place_1'][i]),
            source_line_1=int(pairs['source_line_1'][i]),source_line_2=int(pairs['source_line_2'][i]),domestic=row['uf']!='ZZ',
            **{field:int(pairs[field][i]) for field in PAIRED_COUNTS},q1=float(changes['q1'][j]),q2=float(changes['q2'][j]),
            delta=float(changes['delta'][j]),delta_numerator=int(changes['numerator'][j]),delta_denominator=int(changes['denominator'][j]))
        yield row


def unit_rows(prepared):
    units,group=prepared['units'],prepared['group'];labels=group['labels']
    for i,n in enumerate(units['ns']):
        g=int(labels[i])
        yield dict(model=prepared['model'],unit=i,uf=str(units['uf'][i]),municipality=int(units['municipality'][i]),
            zone=int(units['zone'][i]),place=int(units['place'][i]),section=int(units['section'][i]),ns=int(n),
            **{field:int(units[field][i]) for field in PAIRED_COUNTS},group=g,size_band=int(prepared['unit_size_band'][i]),
            initial_turnout_bin=int(prepared['unit_turnout_band'][i]),initial_preference_bin=int(prepared['unit_preference_band'][i]),
            initial_other_bin=int(prepared['unit_other_band'][i]),movable=bool(prepared['group_movable'][g]),
            target_destination=bool(prepared['targets'][prepared['unit_municipality'][i]]),delta_sum=float(units['delta_sum'][i]),
            delta_mean=float(units['delta_sum'][i]/n),group_mean=float(prepared['group_mean'][g]),residual=float(prepared['unit_residual'][i]))


def group_rows(prepared):
    units,group=prepared['units'],prepared['group'];labels=group['labels'];count=len(group['sizes'])
    target=prepared['targets'][prepared['unit_municipality']]
    target_slots=np.bincount(labels,weights=target,minlength=count).astype(int)
    target_sections=np.bincount(labels,weights=target*units['ns'],minlength=count).astype(np.int64)
    ns=np.bincount(labels,weights=units['ns'],minlength=count).astype(np.int64)
    for g,n in enumerate(group['sizes']):
        i=group['first'][g]
        yield dict(model=prepared['model'],group=g,uf=str(units['uf'][i]),size_band=int(prepared['unit_size_band'][i]),
            initial_turnout_bin=int(prepared['unit_turnout_band'][i]),initial_preference_bin=int(prepared['unit_preference_band'][i]),
            initial_other_bin=int(prepared['unit_other_band'][i]),units=int(n),sections=int(ns[g]),municipalities=int(prepared['group_municipalities'][g]),
            target_slots=int(target_slots[g]),target_sections=int(target_sections[g]),movable=bool(prepared['group_movable'][g]),
            target_reachable=bool(prepared['group_target_reachable'][g]),mean_section_delta=float(prepared['group_mean'][g]))


def municipal_rows(prepared,names):
    data=prepared['municipal'];count=prepared['mun_count'];units=prepared['units']
    movable=prepared['group_movable'][prepared['group']['labels']]
    moved_units=np.bincount(prepared['unit_municipality'],weights=movable,minlength=count).astype(int)
    moved_sections=np.bincount(prepared['unit_municipality'],weights=movable*units['ns'],minlength=count).astype(np.int64)
    for i in range(count):
        uf,code=str(data['uf'][i]),int(data['municipality'][i])
        yield dict(model=prepared['model'],uf=uf,municipality=code,municipality_name=names.get(f'{uf}:{code}',''),
            target=bool(prepared['targets'][i]),ns=int(data['ns'][i]),units=int(data['units'][i]),
            **{field:int(data[field][i]) for field in PAIRED_COUNTS},
            **{field:float(data[field][i]) for field in ('delta_sum','delta_mean','residual_sum','residual_mean')},
            **metric_row(data['metrics'],i),movable_units=int(moved_units[i]),movable_sections=int(moved_sections[i]))


def edge_rows(prepared,names):
    data=prepared['municipal'];edges=prepared['edges'];components=[]
    for left,right in edges:
        contrast=float(data['residual_mean'][left]-data['residual_mean'][right])
        components.append(abs(contrast)/np.sqrt(1/data['ns'][left]+1/data['ns'][right]))
    maximum=max(components,default=0.)
    for (left,right),value in zip(edges,components):
        uf=str(data['uf'][left]);lc,rc=int(data['municipality'][left]),int(data['municipality'][right])
        ql=Fraction(int(data['v13_1'][left]),int(data['f_1'][left]));qr=Fraction(int(data['v13_1'][right]),int(data['f_1'][right]))
        if data['uf'][right]!=uf or ql>qr:raise ArithmeticError('Fixed profile adjacency order is inconsistent')
        yield dict(model=prepared['model'],uf=uf,left_municipality=lc,right_municipality=rc,
            left_name=names.get(f'{uf}:{lc}',''),right_name=names.get(f'{uf}:{rc}',''),
            original_q1_left=float(100*ql),original_q1_right=float(100*qr),original_q1_gap_pp=float(100*(qr-ql)),
            left_sections=int(data['ns'][left]),right_sections=int(data['ns'][right]),
            left_residual_mean=float(data['residual_mean'][left]),right_residual_mean=float(data['residual_mean'][right]),
            signed_contrast_pp=float(data['residual_mean'][left]-data['residual_mean'][right]),J_component=float(value),
            attains_max=bool(abs(value-maximum)<=EPS))


def coverage_rows(prepared):
    units,group,data=prepared['units'],prepared['group'],prepared['municipal']
    gufs=units['uf'][group['first']]
    target=prepared['targets'];movable=prepared['group_movable'];unitmov=movable[group['labels']]
    unit_target=target[prepared['unit_municipality']]
    for uf in ['BR',*sorted(set(units['uf'].tolist()))]:
        use=np.ones(len(units['ns']),dtype=bool) if uf=='BR' else units['uf']==uf
        guse=np.ones(len(group['sizes']),dtype=bool) if uf=='BR' else gufs==uf
        muse=np.ones(prepared['mun_count'],dtype=bool) if uf=='BR' else data['uf']==uf
        target_movable=use&unitmov&unit_target
        reachable=np.unique(prepared['unit_municipality'][target_movable])
        edge_count=len(prepared['edges']) if uf=='BR' else int(np.count_nonzero(data['uf'][prepared['edges'][:,0]]==uf))
        yield dict(model=prepared['model'],uf=uf,cohort_sections=int(units['ns'][use].sum()),units=int(use.sum()),
            groups=int(guse.sum()),municipalities=int(muse.sum()),targets=int((muse&target).sum()),target_sections=int(data['ns'][muse&target].sum()),
            movable_groups=int((guse&movable).sum()),movable_units=int((use&unitmov).sum()),movable_sections=int(units['ns'][use&unitmov].sum()),
            target_reachable_groups=int((guse&movable&prepared['group_target_reachable']).sum()),target_movable_units=int(target_movable.sum()),
            target_movable_sections=int(units['ns'][target_movable].sum()),reachable_targets=len(reachable),adjacent_pairs=edge_count)


def exact_metric(row,metric):
    if metric=='count_advantage':
        return Fraction(int(row[metric]),1) if row['defined_count'] else None
    key={'nominal_advantage':'nominal','relative_advantage':'relative','delta':'conditional'}[metric]
    return 100*Fraction(int(row[f'{key}_num']),int(row[f'{key}_den'])) if row[f'defined_{key}'] else None


def distribution_rows(census_rows,pairs,ids,changes):
    metrics=('count_advantage','nominal_advantage','relative_advantage','delta')
    for universe in ('raw','cohort'):
        selected=[row for row in census_rows if row['universe']==universe]
        for scope_type,scope,use in scopes(np.asarray([row['uf'] for row in selected])):
            rows=[row for row,take in zip(selected,use) if take]
            for metric in metrics:
                exact=[value for row in rows if (value:=exact_metric(row,metric)) is not None]
                values=np.asarray([float(value) for value in exact]);n=len(values)
                quantile=np.quantile(values,[0,.025,.25,.5,.75,.975,1]) if n else ['']*7
                yield dict(universe=universe,scope_type=scope_type,scope=scope,metric=metric,units=len(rows),defined_units=n,
                    undefined_units=len(rows)-n,**dict(zip(('min','q025','q25','median','q75','q975','max'),quantile)),
                    mean=float(values.mean()) if n else '',exact_unique=len(set(exact)))
    for scope_type,scope,use in scopes(pairs['uf'][ids]):
        values=changes['delta'][use];n=len(values)
        exact=set(zip(changes['numerator'][use].tolist(),changes['denominator'][use].tolist()))
        quantile=np.quantile(values,[0,.025,.25,.5,.75,.975,1]) if n else ['']*7
        yield dict(universe='sections',scope_type=scope_type,scope=scope,metric='delta',units=n,defined_units=n,undefined_units=0,
            **dict(zip(('min','q025','q25','median','q75','q975','max'),quantile)),mean=float(values.mean()) if n else '',exact_unique=len(exact))


def repetition_rows(census_rows,changes,pairs,ids):
    for universe in ('raw','cohort','sections'):
        for scope_type,scope,domestic in (('BR','BR',True),('exterior','Exterior',False)):
            for metric in (('delta',) if universe=='sections' else ('count_advantage','nominal_advantage','relative_advantage','delta')):
                if universe=='sections':
                    use=(pairs['uf'][ids]!='ZZ') if domestic else (pairs['uf'][ids]=='ZZ')
                    values=[100*Fraction(int(n),int(d)) for n,d in zip(changes['numerator'][use],changes['denominator'][use])]
                else:
                    values=[value for row in census_rows if row['universe']==universe and row['domestic']==domestic
                            and (value:=exact_metric(row,metric)) is not None]
                frequency=Counter(values)
                for value,n in sorted(frequency.items(),key=lambda item:(-item[1],item[0].numerator,item[0].denominator)):
                    if n>=2:
                        yield dict(universe=universe,scope_type=scope_type,scope=scope,metric=metric,
                            numerator=value.numerator,denominator=value.denominator,value=float(value),frequency=n,defined_units=len(values))


def worker_init(state,directory):
    global _WORKER
    _WORKER=dict(state)
    _WORKER['scores']=np.load(Path(directory)/'scores.npy',mmap_mode='r+')


def simulate_chunk(bounds):
    state=_WORKER;prefix={}
    for rep in range(*bounds):
        assigned=assignment(state['prepared'],state['seed'],state['model_id'],rep)
        state['scores'][rep]=score(state['prepared'],assigned)
        if rep<2:prefix[str(rep)]=hashlib.sha256(assigned.astype('<i4').tobytes()).hexdigest()
    state['scores'].flush()
    return dict(done=bounds[1]-bounds[0],assignment_prefix=prefix)


def simulations(prepared,directory,b,seed,workers,fingerprint):
    directory=Path(directory)
    if directory.exists() and any(directory.iterdir()):
        meta_path=directory/'metadata.json'
        if not meta_path.is_file() or not (directory/'scores.npy').is_file():
            raise ValueError('Unknown simulation cache; choose a new directory')
        meta=json.loads(meta_path.read_text())
        if meta.get('status')!='completed' or meta.get('fingerprint')!=fingerprint or meta.get('scores_sha256')!=sha256(directory/'scores.npy'):
            raise ValueError('Incomplete, different or corrupted simulation cache; choose a new directory')
        expected=dict(model=prepared['model'],model_id=MODELS[prepared['model']],simulations=b,seed=seed,
                      statistics=list(STATISTICS),tails=list(TAILS))
        if any(meta.get(field)!=value for field,value in expected.items()):
            raise ValueError('Simulation cache parameters differ; choose a new directory')
        values=np.load(directory/'scores.npy',mmap_mode='r')
        if values.shape!=(b,5) or np.any(~np.isfinite(values)) or np.any(values<0) or np.any(values[:,:3]>1+EPS):
            raise ValueError('Invalid cached allocation scores')
        return meta
    directory.mkdir(parents=True,exist_ok=True)
    meta=dict(status='running',fingerprint=fingerprint,model=prepared['model'],model_id=MODELS[prepared['model']],
        simulations=b,seed=seed,statistics=list(STATISTICS),tails=list(TAILS),score_representation='natural nonnegative scores; Rlow uses lower tail',assignment_prefix={})
    json_write(directory/'metadata.json',meta)
    values=np.lib.format.open_memmap(directory/'scores.npy',mode='w+',dtype=np.float64,shape=(b,5));values.flush();del values
    state=dict(prepared=simulation_state(prepared),seed=seed,model_id=MODELS[prepared['model']])
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
    values=np.load(directory/'scores.npy',mmap_mode='r')
    if np.any(~np.isfinite(values)) or np.any(values<0) or np.any(values[:,:3]>1+EPS):
        raise ArithmeticError('Invalid simulated territorial-allocation scores')
    meta.update(status='completed',scores_sha256=sha256(directory/'scores.npy'))
    json_write(directory/'metadata.json',meta)
    return meta


def sensitivity_row(prepared,scenario):
    cov=next(coverage_rows(prepared));observed=score(prepared)
    return dict(scenario=scenario,model=prepared['model'],bins=prepared['bins'],finalist_floor=prepared['finalist_floor'],
        unchanged_aptos=prepared['unchanged_aptos'],min_target=prepared['min_target'],cohort_sections=len(prepared['ids']),
        units=len(prepared['units']['ns']),groups=len(prepared['group']['sizes']),movable_groups=cov['movable_groups'],
        movable_units=cov['movable_units'],movable_sections=cov['movable_sections'],municipalities=prepared['mun_count'],
        targets=cov['targets'],target_sections=cov['target_sections'],adjacent_pairs=cov['adjacent_pairs'],
        **{name:float(value) for name,value in zip(STATISTICS,observed)})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,default=HERE/'evidence/analysis')
    parser.add_argument('--cache',type=Path,default=HERE/'.work/data')
    parser.add_argument('--simulation-cache',type=Path,default=HERE/'.work/simulations')
    parser.add_argument('--simulations',type=int,default=4999)
    parser.add_argument('--seed',type=int,default=20261029)
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    if args.simulations<1 or not 1<=args.workers<=4:parser.error('Use positive simulations and 1–4 workers')
    if sha256(HERE/'METHOD.pt-BR.md')!=METHOD_SHA256:parser.error('Frozen H7 method hash differs; review/version the protocol')
    if args.output.exists() and any(args.output.iterdir()):parser.error('Refusing a nonempty output directory')
    args.output.mkdir(parents=True,exist_ok=True)
    core={name:sha256(HERE/'code'/name) for name in ('load_data.py','regularity_statistics.py','run_analysis.py')}
    manifest=dict(status='running',hypothesis='H7',started_at_utc=datetime.now(timezone.utc).isoformat(),method_sha256=METHOD_SHA256,
        implementation_sha256=core,git_base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.root,text=True).strip(),
        parameters=dict(simulations=args.simulations,seed=args.seed,workers=args.workers,models=MODELS,statistics=list(STATISTICS),tails=list(TAILS),
            family_size=10,epsilon=EPS,baseline_bins=20,min_target=5,domestic_formal=True,
            score_cache='Natural nonnegative scores; Rlow lower tail and all other scores upper tail',
            rng='PCG64; SeedSequence([seed,7,model_id],spawn_key=(repetition,))',
            target_policy='Original domestic municipalities with at least five cohort sections; target set fixed under assignments',
            census_BR='Domestic municipal source units only; overseas ZZ units kept separately'),simulation_caches=[])
    json_write(args.output/'manifest.json',manifest)
    loaded=load_data(args.root,args.cache);joined=pair_sections(loaded['rounds']);pairs=joined['pairs']
    mask,_,_=eligibility(pairs);ids=np.flatnonzero(mask);changes=section_changes(pairs,ids)
    print(f'Paired {len(pairs["uf"])} physical keys; cohort {len(ids)} including overseas',flush=True)
    manifest.update(source_inputs=loaded['source_inputs'],source_counts=loaded['source_counts'],data_fingerprint=loaded['cache_fingerprint'])
    pairing=list(pairing_rows(joined));eligible=list(eligibility_rows(pairs))
    write_csv(args.output/'pairing.csv',list(pairing[0]),pairing)
    write_csv(args.output/'eligibility.csv',list(eligible[0]),eligible)
    unmatched=[]
    for turn,rd,index in joined['unmatched']:
        for i in index:
            unmatched.append(dict(present_in_round=turn,uf=str(rd['uf'][i]),municipality=int(rd['municipality'][i]),
                zone=int(rd['zone'][i]),section=int(rd['section'][i]),source_line=int(rd['source_line'][i])))
    write_csv(args.output/'unmatched.csv',('present_in_round','uf','municipality','zone','section','source_line'),unmatched)
    census_rows,candidate_rows=census(joined,loaded['names'])
    for row in candidate_rows:
        row['candidate_name']=loaded['candidate_names'].get(f'{row["turno"]}:{row["candidate"]}','')
    write_csv(args.output/'municipal-census.csv',CENSUS_COLUMNS,census_rows)
    write_csv(args.output/'candidate-totals.csv.gz',CANDIDATE_COLUMNS,candidate_rows)
    directions=list(direction_rows(census_rows));write_csv(args.output/'gain-directions.csv',DIRECTION_COLUMNS,directions)
    write_csv(args.output/'cohort-sections.csv.gz',SECTION_COLUMNS,section_rows(pairs,ids,changes,loaded['names']))
    write_csv(args.output/'distribution.csv',DISTRIBUTION_COLUMNS,distribution_rows(census_rows,pairs,ids,changes))
    write_csv(args.output/'exact-repetitions.csv.gz',REPETITION_COLUMNS,repetition_rows(census_rows,changes,pairs,ids))
    tests=[];coverage=[];sens=[]
    with csv_writer(args.output/'allocation-units.csv.gz',UNIT_COLUMNS) as unit_writer, \
         csv_writer(args.output/'allocation-groups.csv.gz',GROUP_COLUMNS) as group_writer, \
         csv_writer(args.output/'municipality-results.csv',MUNICIPAL_COLUMNS) as municipal_writer, \
         csv_writer(args.output/'adjacent-profiles.csv',EDGE_COLUMNS) as edge_writer, \
         csv_writer(args.output/'permutation-scores.csv.gz',PERMUTATION_COLUMNS) as score_writer:
        for model in MODELS:
            prepared=prepare(pairs,model);observed=score(prepared)
            print(f'Observed {model}: {len(prepared["units"]["ns"])} units; {int(prepared["targets"].sum())} fixed targets',flush=True)
            unit_writer.writerows(unit_rows(prepared));group_writer.writerows(group_rows(prepared))
            municipal_writer.writerows(municipal_rows(prepared,loaded['names']));edge_writer.writerows(edge_rows(prepared,loaded['names']))
            coverage.extend(coverage_rows(prepared));sens.append(sensitivity_row(prepared,'primary'))
            fingerprint=hashlib.sha256(json.dumps(dict(core=core,method=METHOD_SHA256,data=loaded['cache_fingerprint'],model=model,
                simulations=args.simulations,seed=args.seed),sort_keys=True).encode()).hexdigest()
            directory=args.simulation_cache/model
            meta=simulations(prepared,directory,args.simulations,args.seed,args.workers,fingerprint)
            manifest['simulation_caches'].append(dict(path=str(directory.relative_to(args.root)) if directory.is_relative_to(args.root) else str(directory),
                metadata=meta,metadata_sha256=sha256(directory/'metadata.json')))
            draws=np.load(directory/'scores.npy',mmap_mode='r')
            for rep,values in enumerate(draws):
                score_writer.writerow(dict(model=model,repetition=rep,**{name:float(value) for name,value in zip(STATISTICS,values)}))
            possible,reasons=score_variability(prepared,draws,observed)
            quantiles=np.quantile(draws,[.025,.975],axis=0);means=draws.mean(axis=0)
            for k,(stat,tail) in enumerate(zip(STATISTICS,TAILS)):
                exceed=int(np.count_nonzero(draws[:,k]<=observed[k]+EPS if tail=='lower' else draws[:,k]>=observed[k]-EPS))
                tests.append(dict(model=model,statistic=stat,tail=tail,observed=float(observed[k]),simulation_mean=float(means[k]),
                    simulation_q025=float(quantiles[0,k]),simulation_q975=float(quantiles[1,k]),exceedances=exceed,simulations=args.simulations,
                    p_raw=(1+exceed)/(1+args.simulations) if possible[k] else '',p_holm='',detected='',
                    status='applicable' if possible[k] else 'not_applicable_unresolved' if reasons[k].startswith('unresolved') else 'not_applicable',
                    applicability_reason=reasons[k]))
    adjusted=holm([row['p_raw'] if row['status']=='applicable' else 1 for row in tests])
    for row,p in zip(tests,adjusted):
        if row['status']=='applicable':row.update(p_holm=float(p),detected=bool(p<=.05),status='detected' if p<=.05 else 'not_detected')
    write_csv(args.output/'tests.csv',TEST_COLUMNS,tests)
    write_csv(args.output/'coverage.csv',COVERAGE_COLUMNS,coverage)
    configs=[('baseline_2_5pp',40,50,False,5),('baseline_10pp',10,50,False,5),
        ('unchanged_aptos',20,50,True,5),('finalists_100',20,100,False,5),('targets_1',20,50,False,1),('targets_10',20,50,False,10)]
    for scenario,bins,floor,unchanged,target in configs:
        for model in MODELS:
            prepared=prepare(pairs,model,bins=bins,finalist_floor=floor,unchanged_aptos=unchanged,min_target=target)
            sens.append(sensitivity_row(prepared,scenario))
    write_csv(args.output/'sensitivity.csv',SENSITIVITY_COLUMNS,sens)
    summary=dict(matched_pairs=len(pairs['uf']),cohort_pairs=len(ids),domestic_cohort_pairs=int(np.count_nonzero(pairs['uf'][ids]!='ZZ')),
        paired_elections=[int(pairs['election_1']),int(pairs['election_2'])],family_size=10,
        primary_detected=sum(row['status']=='detected' for row in tests),primary_not_detected=sum(row['status']=='not_detected' for row in tests),
        primary_not_applicable=sum(row['status'].startswith('not_applicable') for row in tests),
        primary_unresolved=sum(row['status']=='not_applicable_unresolved' for row in tests),
        domestic_municipalities=sum(row['universe']=='raw' and row['domestic'] for row in census_rows),
        overseas_source_units=sum(row['universe']=='raw' and not row['domestic'] for row in census_rows),
        domestic_direction_census=[row for row in directions if row['scope_type']=='BR'],
        interpretation='Census definitions and territorial allocation references do not establish artificial cause, individual voter transitions or naturalness of preserved marginal trajectories')
    json_write(args.output/'summary.json',summary)
    for source in loaded['source_inputs'].values():
        if sha256(args.root/source['path'])!=source['sha256']:raise ValueError('Original input changed during H7 analysis')
    manifest.update(status='completed',completed_at_utc=datetime.now(timezone.utc).isoformat(),numpy_version=np.__version__,
        artifacts={path.name:dict(size_bytes=path.stat().st_size,sha256=sha256(path)) for path in sorted(args.output.iterdir()) if path.name!='manifest.json'})
    json_write(args.output/'manifest.json',manifest)
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
