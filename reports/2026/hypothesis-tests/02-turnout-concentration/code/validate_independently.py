#!/usr/bin/env python3
"""Independent H2 source parser and exact-ratio reference (no primary imports)."""
from __future__ import annotations

import argparse
from array import array
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import csv
import gzip
import hashlib
import inspect
import json
import math
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
SOURCE_PATHS = {
    'details': 'data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv',
    'votes': 'data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv',
}
KEY_FIELDS = ('CD_ELEICAO','NR_TURNO','SG_UF','CD_MUNICIPIO','NR_ZONA','NR_SECAO','CD_CARGO')
DETAIL_FIELDS = ('QT_APTOS','QT_COMPARECIMENTO','QT_ABSTENCOES','QT_VOTOS_NOMINAIS',
                 'QT_VOTOS_BRANCOS','QT_VOTOS_NULOS','QT_VOTOS_LEGENDA','QT_VOTOS_ANULADOS_APU_SEP')
PACK = struct.Struct('>7I')
CONFIG = dict(min_aptos=50,min_nominal=50,min_group=30,band_ratio=1.25,
              tail_numerator=1,tail_denominator=20,turnout_gap_numerator=1,
              turnout_gap_denominator=20,share_gap_numerator=1,share_gap_denominator=10,
              min_other_place_peers=4,place_size_ratio=1.25)


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def raw_rows(path):
    with Path(path).open('rb') as stream:
        if stream.read(100).startswith(b'version https://git-lfs.github.com/spec/v1'):
            raise ValueError(f'Git LFS pointer rather than CSV: {path}')
    with Path(path).open(encoding='latin1',newline='') as stream:
        reader=csv.reader(stream,delimiter=';')
        header=next(reader)
        if len(header)!=len(set(header)):
            raise ValueError(f'Duplicate columns: {path}')
        columns={name:i for i,name in enumerate(header)}
        for line,row in enumerate(reader,2):
            if len(row)!=len(header):
                raise ValueError(f'Malformed CSV row {path}:{line}')
            yield line,row,columns


def section_key(row,columns):
    values=[row[columns[field]].strip() for field in KEY_FIELDS]
    uf=values[2].upper()
    if len(uf)!=2 or not uf.isascii() or not uf.isalpha():
        raise ValueError(f'Invalid UF {uf!r}')
    numeric=[int(values[i]) for i in (0,1,3,4,5,6)]
    if any(v<0 for v in numeric) or numeric[1] not in (1,2):
        raise ValueError('Invalid section identification')
    return PACK.pack(numeric[0],numeric[1],int.from_bytes(uf.encode(),'big'),*numeric[2:]), \
           (numeric[0],numeric[1],uf,*numeric[2:-1])


def yes_no(raw):
    raw=raw.strip().casefold()
    if raw in {'sim','s'}:
        return True
    if raw in {'não','nao','n'}:
        return False
    raise ValueError(f'Unknown yes/no flag {raw!r}')


def complete_quantity(raw):
    raw=raw.strip()
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError(f'Missing, invalid or negative quantity {raw!r}')
    return int(raw)


def upper_tail(values,q=Fraction(1,20)):
    """Return high flags plus inclusive upper-rank counts, preserving every tie."""
    counts=Counter(values)
    upper={}
    cumulative=0
    for value in sorted(counts,reverse=True):
        cumulative+=counts[value]
        upper[value]=cumulative
    n=len(values)
    return [upper[v]*q.denominator<=n*q.numerator for v in values], [upper[v] for v in values]


def exact_median(values):
    ordered=sorted(values)
    n=len(ordered)
    if not n:
        raise ValueError('Median of empty sample')
    if n%2:
        return ordered[n//2]
    return (ordered[n//2-1]+ordered[n//2])/2


def source_snapshot(root):
    baseline=json.loads((root/'reports/2026/input-manifest.json').read_text())
    h1=json.loads((root/'reports/2026/hypothesis-tests/01-accounting-integrity/evidence/accounting/manifest.json').read_text())
    if baseline['status']!='completed' or h1['status']!='completed':
        raise ValueError('Completed stage 1 and H1 provenance required')
    result={}
    for name,relative in SOURCE_PATHS.items():
        path=root/relative
        sha=digest_file(path)
        size=path.stat().st_size
        if sha!=baseline['inputs'][name]['sha256'] or sha!=h1['inputs'][name]['sha256']:
            raise ValueError(f'Source differs from stage 1/H1: {name}')
        if size!=baseline['inputs'][name]['size_bytes'] or size!=h1['inputs'][name]['size_bytes']:
            raise ValueError(f'Source size differs from stage 1/H1: {name}')
        result[name]=dict(path=relative,sha256=sha,size_bytes=size)
    return result


def read_sources(root):
    """Independently assemble complete candidate vectors from the original files."""
    records=[]
    index={}
    vectors={}
    special={}
    scopes=Counter()
    statistics=Counter()
    for line,row,columns in raw_rows(root/SOURCE_PATHS['details']):
        statistics['detail_rows_read']+=1
        if int(row[columns['ANO_ELEICAO']])!=2026 or int(row[columns['CD_CARGO']])!=1:
            continue
        key,scope=section_key(row,columns)
        if key in index:
            raise ValueError('Duplicate detail key; H2 requires unambiguous sections')
        if row[columns['SG_UE']].strip().upper()!='BR':
            raise ValueError('Unexpected electoral unit')
        quantities=tuple(complete_quantity(row[columns[f]]) for f in DETAIL_FIELDS)
        place=complete_quantity(row[columns['NR_LOCAL_VOTACAO']])
        installed=yes_no(row[columns['ST_SECAO_INSTALADA']])
        cancelled=yes_no(row[columns['ST_SECAO_ANULADA']])
        index[key]=len(records)
        records.append((scope,place,quantities,installed,cancelled,line))
        statistics['detail_rows_selected']+=1
        scopes[scope[:2]]+=1
    if not records:
        raise ValueError('No presidential details selected')
    n=len(records)
    for scope in scopes:
        special[scope]=[array('q',[0])*n for _ in range(3)]
    for line,row,columns in raw_rows(root/SOURCE_PATHS['votes']):
        statistics['vote_rows_read']+=1
        if int(row[columns['ANO_ELEICAO']])!=2026 or int(row[columns['CD_CARGO']])!=1:
            continue
        key,scope=section_key(row,columns)
        if key not in index:
            raise ValueError('Vote section without corresponding detail')
        i=index[key]
        candidate=complete_quantity(row[columns['NR_VOTAVEL']])
        value=complete_quantity(row[columns['QT_VOTOS']])
        if candidate<=0:
            raise ValueError('Invalid votable number')
        if candidate in (95,96,97):
            special[scope[:2]][{95:0,96:1,97:2}[candidate]][i]+=value
        else:
            identity=(*scope[:2],candidate)
            if identity not in vectors:
                vectors[identity]=array('q',[0])*n
            vectors[identity][i]+=value
        statistics['vote_rows_selected']+=1
    if not statistics['vote_rows_selected']:
        raise ValueError('No presidential vote rows selected')
    candidates={scope:sorted(k[2] for k in vectors if k[:2]==scope) for scope in scopes}
    totals={}
    for i,(scope,place,quantities,installed,cancelled,line) in enumerate(records):
        election,turn,uf,municipality,zone,section=scope
        aptos,turnout,abstentions,nominal,blank,null,legend,separate=quantities
        nominal_from_votes=sum(vectors[(election,turn,c)][i] for c in candidates[(election,turn)])
        special_from_votes=tuple(v[i] for v in special[(election,turn)])
        if nominal_from_votes!=nominal or special_from_votes!=(blank,null,separate):
            raise ValueError(f'Independent category reconciliation failed at {scope}')
        if legend!=0 or nominal+blank+null+legend+separate!=turnout or turnout>aptos:
            raise ValueError(f'Unsupported section quantities at {scope}')
        total=totals.setdefault((election,turn,uf),Counter())
        total.update(dict(records=1,aptos=aptos,turnout=turnout,nominal=nominal,
                          blank=blank,null_votes=null,legend=legend,separate=separate))
    return records,vectors,candidates,statistics,totals


def reference_from_records(records,vectors,candidates,statistics,totals):
    groups=defaultdict(list)
    places=defaultdict(list)
    coverage={scope:Counter(raw_details=t['records']) for scope,t in totals.items()}
    eligible=[]
    for i,(scope,place,quantities,installed,cancelled,line) in enumerate(records):
        election,turn,uf,municipality,zone,section=scope
        aptos,turnout,abstentions,nominal,*_=quantities
        tally=coverage[(election,turn,uf)]
        if not installed or cancelled:
            tally['excluded_status']+=1
        elif aptos<50:
            tally['excluded_electorate']+=1
        elif turnout<=0:
            tally['excluded_turnout']+=1
        elif nominal<50:
            tally['excluded_nominal']+=1
        else:
            tally['eligible']+=1
            eligible.append(i)
            band=math.floor(math.log(aptos)/math.log(1.25))
            groups[(election,turn,uf,municipality,zone,band)].append(i)
            places[(election,turn,uf,municipality,zone,place)].append(i)
    strata=[]
    cases=[]
    for group,members in sorted(groups.items()):
        election,turn,uf,municipality,zone,band=group
        coverage[(election,turn,uf)]['n_strata_all']+=1
        if len(members)<30:
            coverage[(election,turn,uf)]['no_peer_support']+=len(members)
            continue
        n=len(members)
        coverage[(election,turn,uf)]['covered']+=n
        coverage[(election,turn,uf)]['n_strata_supported']+=1
        turnout_values=[Fraction(records[i][2][1],records[i][2][0]) for i in members]
        turnout_high,turnout_upper=upper_tail(turnout_values)
        turnout_median=exact_median(turnout_values)
        a=sum(turnout_high)
        for candidate in candidates[(election,turn)]:
            share_values=[Fraction(vectors[(election,turn,candidate)][i],records[i][2][3]) for i in members]
            share_high,share_upper=upper_tail(share_values)
            share_median=exact_median(share_values)
            b=sum(share_high)
            joint=[j for j in range(n) if turnout_high[j] and share_high[j]]
            priority=[j for j in joint if turnout_values[j]-turnout_median>=Fraction(1,20)
                      and share_values[j]-share_median>=Fraction(1,10)]
            strata.append(dict(election_code=election,turno=turn,uf=uf,municipality=municipality,
                zone=zone,size_band=band,candidate=candidate,n=n,turnout_tail=a,candidate_tail=b,
                joint_count=len(joint),priority_count=len(priority),
                min_aptos=min(records[i][2][0] for i in members),
                max_aptos=max(records[i][2][0] for i in members),
                expected_joint=a*b/n,
                variance=a*b*(n-a)*(n-b)/(n*n*(n-1)),
                turnout_median=float(turnout_median),candidate_median=float(share_median)))
            for j in joint:
                i=members[j]
                scope,place,quantities,installed,cancelled,line=records[i]
                aptos,turnout,abstentions,nominal,*_=quantities
                row=dict(election_code=election,turno=turn,uf=uf,municipality=municipality,
                    zone=zone,section=scope[-1],place=place,candidate=candidate,size_band=band,
                    n=n,aptos=aptos,turnout=turnout,nominal=nominal,candidate_votes=vectors[(election,turn,candidate)][i],
                    turnout_rate=float(turnout_values[j]),candidate_share=float(share_values[j]),
                    turnout_upper_count=turnout_upper[j],candidate_upper_count=share_upper[j],
                    turnout_gap_pp=float((turnout_values[j]-turnout_median)*100),
                    candidate_gap_pp=float((share_values[j]-share_median)*100),priority=j in priority,
                    source_line=line)
                row['local_status']='not_priority_not_assessed'
                if row['priority']:
                    peers=[p for p in places[(election,turn,uf,municipality,zone,place)] if p!=i
                           and 4*max(aptos,records[p][2][0])<=5*min(aptos,records[p][2][0])]
                    row['place_peers']=len(peers)
                    if len(peers)>=4:
                        peer_turnout=exact_median([Fraction(records[p][2][1],records[p][2][0]) for p in peers])
                        peer_share=exact_median([Fraction(vectors[(election,turn,candidate)][p],records[p][2][3]) for p in peers])
                        row['place_turnout_gap_pp']=float((turnout_values[j]-peer_turnout)*100)
                        row['place_candidate_gap_pp']=float((share_values[j]-peer_share)*100)
                        row['local_median_turnout']=float(peer_turnout)
                        row['local_median_share']=float(peer_share)
                        row['place_persistent']=(turnout_values[j]-peer_turnout>=Fraction(1,20)
                                                 and share_values[j]-peer_share>=Fraction(1,10))
                        row['local_status']='persists_both' if row['place_persistent'] else 'attenuated_one_or_both'
                    else:
                        row['place_persistent']=None
                        row['local_status']='insufficient_peers'
                cases.append(row)
    return dict(config=CONFIG,source_statistics=dict(statistics),
                candidates=[dict(election_code=e,turno=t,numbers=n) for (e,t),n in sorted(candidates.items())],
                totals=[dict(election_code=s[0],turno=s[1],uf=s[2],**dict(v)) for s,v in sorted(totals.items())],
                coverage=[dict(election_code=s[0],turno=s[1],uf=s[2],**dict(v)) for s,v in sorted(coverage.items())],
                strata=strata,cases=cases)


def implementation_fingerprint():
    functions=[raw_rows,section_key,yes_no,complete_quantity,upper_tail,exact_median,
               source_snapshot,read_sources,reference_from_records]
    text=json.dumps(CONFIG,sort_keys=True)+'\n'.join(inspect.getsource(f) for f in functions)
    return hashlib.sha256(text.encode()).hexdigest()


def prepare(root,cache_dir):
    sources=source_snapshot(root)
    fingerprint=implementation_fingerprint()
    cache_dir.mkdir(parents=True,exist_ok=True)
    metadata_path=cache_dir/'reference-metadata.json'
    data_path=cache_dir/'reference.json.gz'
    if metadata_path.exists() and data_path.exists():
        metadata=json.loads(metadata_path.read_text())
        if metadata.get('source_inputs')!=sources or metadata.get('implementation_fingerprint')!=fingerprint:
            raise ValueError('Independent cache fingerprints changed; choose a new cache directory')
        if digest_file(data_path)!=metadata['reference_sha256']:
            raise ValueError('Independent reference cache hash mismatch')
        with gzip.open(data_path,'rt',encoding='utf-8') as stream:
            return json.load(stream),metadata
    if any(cache_dir.iterdir()):
        raise ValueError('Incomplete/nonempty independent cache; choose a new directory')
    print('Independent H2: reading original sources',flush=True)
    raw=read_sources(root)
    print('Independent H2: exact Fraction reference',flush=True)
    reference=reference_from_records(*raw)
    # Recheck source immutability after both complete scans.
    if sources!=source_snapshot(root):
        raise ValueError('Source changed during independent scan')
    with gzip.open(data_path,'wt',encoding='utf-8') as stream:
        json.dump(reference,stream,ensure_ascii=False,separators=(',',':'))
    metadata=dict(status='completed',created_at_utc=datetime.now(timezone.utc).isoformat(),
                  source_inputs=sources,implementation_fingerprint=fingerprint,
                  reference_sha256=digest_file(data_path))
    metadata_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return reference,metadata


def csv_rows(path):
    with Path(path).open(encoding='utf-8',newline='') as stream:
        return list(csv.DictReader(stream))


def row_key(row,fields):
    return tuple(row[field] if field=='uf' else int(row[field]) for field in fields)


def linear_quantile(values,q):
    """Independent linear empirical quantile; q is an exact rational."""
    ordered=sorted(map(int,values))
    position=(len(ordered)-1)*q
    low=position.numerator//position.denominator
    high=min(low+1,len(ordered)-1)
    return float(ordered[low]+(ordered[high]-ordered[low])*(position-low))


def holm_reference(values):
    order=sorted(values,key=lambda key:values[key])
    adjusted={}
    preceding=0.0
    for rank,key in enumerate(order):
        preceding=max(preceding,min(1.0,(len(order)-rank)*values[key]))
        adjusted[key]=preceding
    return adjusted


def validate_analysis(root,analysis,reference_cache,reference,metadata):
    """Check every primary observation and regenerate every conditional stream."""
    import numpy as np
    manifest=json.loads((analysis/'manifest.json').read_text())
    if manifest.get('status')!='completed':
        raise ValueError('Completed primary H2 analysis is required')
    counts=Counter()
    failures=[]
    maximum_error=0.0

    def same(category,label,actual,expected,tolerance=None):
        nonlocal maximum_error
        counts[category]+=1
        if tolerance is None:
            passed=actual==expected
        else:
            error=abs(float(actual)-float(expected))
            maximum_error=max(maximum_error,error)
            passed=math.isfinite(float(actual)) and math.isfinite(float(expected)) and error<=tolerance
        if not passed and len(failures)<100:
            def compact(value):
                return dict(length=len(value),first_items=value[:10]) if isinstance(value,list) and len(value)>20 else value
            failures.append(dict(category=category,comparison=label,primary=compact(actual),independent=compact(expected)))
        counts['all_mismatches']+=not passed

    def indexed(rows,fields,category):
        indexed_rows={row_key(row,fields):row for row in rows}
        same('inventory',category+' keys unique',len(indexed_rows),len(rows))
        return indexed_rows

    for name,source in metadata['source_inputs'].items():
        for field in ('sha256','size_bytes'):
            same('source_provenance',name+':'+field,manifest['source_inputs'][name][field],source[field])
    same('source_provenance','frozen method',manifest['method_sha256'],digest_file(HERE/'METHOD.pt-BR.md'))
    for name,sha in manifest['implementation_sha256'].items():
        same('code_provenance',name,sha,digest_file(HERE/'code'/name))
    for name,sha in manifest['artifact_sha256'].items():
        same('artifact_integrity',name,sha,digest_file(analysis/name))
    same('configuration','B',manifest['simulations'],19999)
    same('configuration','seed',manifest['seed'],20261028)
    same('configuration','family size',manifest['primary_family_size'],15)
    same('configuration','NumPy version',manifest['numpy_version'],np.__version__)
    for kind in ('details','votes'):
        prefix='detail' if kind=='details' else 'vote'
        for primary_field,independent_field in [('rows_read',f'{prefix}_rows_read'),('selected_rows',f'{prefix}_rows_selected')]:
            same('source_counts',kind+':'+primary_field,manifest['source_counts'][kind][primary_field],reference['source_statistics'][independent_field])

    group_fields=('election_code','turno','candidate','uf','municipality','zone','size_band')
    actual_groups=indexed(csv_rows(analysis/'strata.csv'),group_fields,'strata')
    expected_groups=indexed(reference['strata'],group_fields,'independent strata')
    same('inventory','complete stratum/candidate inventory',sorted(actual_groups),sorted(expected_groups))
    for key in sorted(set(actual_groups)&set(expected_groups)):
        actual,expected=actual_groups[key],expected_groups[key]
        for p,s in [('n','n'),('min_aptos','min_aptos'),('max_aptos','max_aptos'),
                    ('turnout_tail_count','turnout_tail'),('candidate_tail_count','candidate_tail'),
                    ('joint_count','joint_count'),('priority_count','priority_count')]:
            same('stratum_integer',f'{key}:{p}',int(actual[p]),expected[s])
        for p,s in [('expected_joint','expected_joint'),('variance','variance'),
                    ('median_turnout','turnout_median'),('median_candidate_share','candidate_median')]:
            same('stratum_numeric',f'{key}:{p}',float(actual[p]),expected[s],1e-12)

    case_fields=('election_code','turno','candidate','uf','municipality','zone','section')
    actual_cases=indexed(csv_rows(analysis/'cases.csv'),case_fields,'cases')
    expected_cases=indexed(reference['cases'],case_fields,'independent cases')
    same('inventory','all joint-tail case keys',sorted(actual_cases),sorted(expected_cases))
    for key in sorted(set(actual_cases)&set(expected_cases)):
        actual,expected=actual_cases[key],expected_cases[key]
        group_key=row_key(expected,group_fields)
        group=expected_groups[group_key]
        for p,s in [('place','place'),('source_line','source_line'),('aptos','aptos'),('turnout','turnout'),
                    ('nominal','nominal'),('candidate_votes','candidate_votes'),('size_band','size_band'),
                    ('stratum_n','n'),('turnout_upper_count','turnout_upper_count'),
                    ('candidate_upper_count','candidate_upper_count')]:
            same('case_integer',f'{key}:{p}',int(actual[p]),expected[s])
        same('case_integer',f'{key}:priority',int(actual['priority']),int(expected['priority']))
        for p,s in [('turnout_rate','turnout_rate'),('candidate_share','candidate_share'),
                    ('turnout_delta_pp','turnout_gap_pp'),('share_delta_pp','candidate_gap_pp')]:
            same('case_numeric',f'{key}:{p}',float(actual[p]),expected[s],1e-10)
        same('case_numeric',f'{key}:median_turnout',float(actual['median_turnout']),group['turnout_median'],1e-12)
        same('case_numeric',f'{key}:median_candidate_share',float(actual['median_candidate_share']),group['candidate_median'],1e-12)
        same('case_numeric',f'{key}:turnout_tail_fraction',float(actual['turnout_tail_fraction']),expected['turnout_upper_count']/expected['n'],1e-12)
        same('case_numeric',f'{key}:candidate_tail_fraction',float(actual['candidate_tail_fraction']),expected['candidate_upper_count']/expected['n'],1e-12)
        same('local_context',f'{key}:status',actual['local_status'],expected['local_status'])
        if expected['priority']:
            same('local_context',f'{key}:other peers',int(actual['local_peer_count']),expected['place_peers'])
            if expected['place_peers']>=4:
                for p,s in [('local_median_turnout','local_median_turnout'),('local_median_share','local_median_share'),
                            ('local_turnout_delta_pp','place_turnout_gap_pp'),('local_share_delta_pp','place_candidate_gap_pp')]:
                    same('local_context',f'{key}:{p}',float(actual[p]),expected[s],1e-10)

    coverage_fields=('election_code','turno','uf')
    expected_coverage={row_key(row,coverage_fields):row.copy() for row in reference['coverage']}
    coverage_numbers=('raw_details','eligible','excluded_status','excluded_electorate','excluded_turnout',
                      'excluded_nominal','no_peer_support','covered','n_strata_all','n_strata_supported')
    rounds={(r['election_code'],r['turno']) for r in reference['coverage']}
    for election,turn in rounds:
        rows=[r for r in reference['coverage'] if (r['election_code'],r['turno'])==(election,turn)]
        expected_coverage[(election,turn,'BR')]=dict(election_code=election,turno=turn,uf='BR',
                                                   **{f:sum(r.get(f,0) for r in rows) for f in coverage_numbers})
    actual_coverage=indexed(csv_rows(analysis/'coverage.csv'),coverage_fields,'coverage')
    same('inventory','coverage inventory',sorted(actual_coverage),sorted(expected_coverage))
    for key in sorted(set(actual_coverage)&set(expected_coverage)):
        for field in coverage_numbers:
            same('coverage',f'{key}:{field}',int(actual_coverage[key][field]),expected_coverage[key].get(field,0))

    # Every simulation is regenerated from independently reconstructed sufficient statistics.
    tests=indexed(csv_rows(analysis/'association-tests.csv'),('election_code','turno','candidate'),'association tests')
    expected_tests={(r['election_code'],r['turno'],c) for r in reference['candidates'] for c in r['numbers']}
    same('inventory','fixed candidate-round family',sorted(tests),sorted(expected_tests))
    same('inventory','exactly fifteen candidate-round tests',len(tests),15)
    raw_p={}
    applicable={}
    for identity in sorted(set(tests)&expected_tests):
        election,turn,candidate=identity
        actual=tests[identity]
        selected=[row for row in reference['strata'] if (row['election_code'],row['turno'],row['candidate'])==identity]
        selected.sort(key=lambda row:(row['uf'],row['municipality'],row['zone'],row['size_band']))
        n=np.array([row['n'] for row in selected],dtype=np.int64)
        a=np.array([row['turnout_tail'] for row in selected],dtype=np.int64)
        b=np.array([row['candidate_tail'] for row in selected],dtype=np.int64)
        observed=sum(row['joint_count'] for row in selected)
        expected=math.fsum(row['expected_joint'] for row in selected)
        variance=math.fsum(row['variance'] for row in selected)
        for field,value in [('n_strata',len(selected)),('n_sections',int(n.sum())),('observed_joint',observed),
                            ('priority_count',sum(row['priority_count'] for row in selected)),
                            ('simulations',19999),('seed',20261028)]:
            same('association_integer',f'{identity}:{field}',int(actual[field]),value)
        for field,value in [('expected_joint',expected),('variance',variance),('excess_joint',observed-expected)]:
            same('association_numeric',f'{identity}:{field}',float(actual[field]),value,1e-9)
        if expected:
            same('association_numeric',f'{identity}:ratio',float(actual['observed_expected_ratio']),observed/expected,1e-9)
        else:
            same('association_numeric',f'{identity}:undefined ratio',actual['observed_expected_ratio'],'')
        path=reference_cache/f'turn-{turn}-candidate-{candidate}.npy'
        saved=json.loads(path.with_suffix('.json').read_text())
        cached=np.load(path,allow_pickle=False)
        same('simulation_integrity',f'{identity}:sha256',saved['sha256'],digest_file(path))
        same('simulation_integrity',f'{identity}:shape',list(cached.shape),[19999])
        same('simulation_integrity',f'{identity}:dtype',str(cached.dtype),'int64')
        for field,value in [('simulations',19999),('seed',20261028),('turno',turn),('candidate',candidate)]:
            same('simulation_integrity',f'{identity}:{field}',saved[field],value)
        task=dict(n=n.tolist(),a=a.tolist(),b=b.tolist(),observed=observed,turno=turn,candidate=candidate,
                  seed=20261028,simulations=19999,code_sha256=manifest['implementation_sha256']['run_analysis.py'],
                  numpy=manifest['numpy_version'])
        signature=hashlib.sha256(json.dumps(task,sort_keys=True).encode()).hexdigest()
        same('simulation_integrity',f'{identity}:independent signature',saved['signature'],signature)
        valid=(a>0)&(b>0)
        rng=np.random.default_rng(np.random.SeedSequence([20261028,turn,candidate]))
        reproduced=np.zeros(19999,dtype=np.int64)
        for start in range(0,19999,500):
            stop=min(start+500,19999)
            if valid.any():
                reproduced[start:stop]=rng.hypergeometric(b[valid],n[valid]-b[valid],a[valid],
                                                          size=(stop-start,int(valid.sum()))).sum(axis=1)
        same('simulation_regeneration',f'{identity}:all 19999 counts',bool(np.array_equal(cached,reproduced)),True)
        counts['simulation_count_values_regenerated']+=len(reproduced)
        exceedances=sum(int(value)>=observed for value in cached)
        same('association_integer',f'{identity}:exceedances',int(actual['exceedances']),exceedances)
        for field,q in [('reference_low_2_5',Fraction(1,40)),('reference_high_97_5',Fraction(39,40))]:
            same('association_numeric',f'{identity}:{field}',float(actual[field]),linear_quantile(cached,q),1e-9)
        applicable[identity]=variance>0
        raw_p[identity]=(1+exceedances)/20000 if variance>0 else 1.0
        if variance>0:
            same('p_value',f'{identity}:plus-one p',float(actual['p_raw']),raw_p[identity],1e-15)
        else:
            same('p_value',f'{identity}:not applicable p',actual['p_raw'],'')
        print(f'Independent H2: verified full reference stream turn {turn}, candidate {candidate}',flush=True)
    adjusted=holm_reference(raw_p)
    for identity,p in adjusted.items():
        actual=tests[identity]
        if applicable[identity]:
            same('p_value',f'{identity}:Holm',float(actual['p_holm']),p,1e-15)
            status='excess_detected' if p<=.05 else 'not_detected'
        else:
            same('p_value',f'{identity}:not applicable Holm',actual['p_holm'],'')
            status='not_applicable'
        same('decision',str(identity),actual['status'],status)
    mismatch_count=counts.pop('all_mismatches')
    return dict(status='passed' if mismatch_count==0 else 'failed',
        completed_at_utc=datetime.now(timezone.utc).isoformat(),
        script_sha256=digest_file(Path(__file__)),reference_implementation_fingerprint=metadata['implementation_fingerprint'],
        source_inputs=metadata['source_inputs'],independent_source_counts=reference['source_statistics'],
        comparisons=dict(counts),mismatches=mismatch_count,maximum_numeric_error=maximum_error,
        numeric_tolerances=dict(ratios_and_stratum_moments=1e-12,case_percentage_points=1e-10,aggregate_moments=1e-9),
        failures=failures,failure_examples_limit=100,
        scope=dict(source_data='Original nationwide CSVs re-read independently; no primary parser/model imports',
            primary_reference='Every primary stratum/candidate, every joint-tail case, magnitudes, local peers and exclusive coverage',
            ratios='Fraction-based exact ties, medians and practical-effect thresholds',
            simulations='All 19999 draws regenerated for each of the 15 independent seeded streams; every cached count audited',
            p_values='Exceedance counts, plus-one raw p-values, linear quantiles, 15-member Holm family and decisions',
            sensitivities='Alternative descriptive scenarios are not independently recomputed here',
            interpretation='Conditional independence benchmark is not a null of natural elections; consistency does not authenticate the sources'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--cache-dir',type=Path,default=HERE/'.work/independent')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--analysis-dir',type=Path,default=HERE/'evidence/analysis')
    parser.add_argument('--reference-cache',type=Path,default=HERE/'.work/reference')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not args.prepare_only and args.output is None:
        parser.error('--output is required unless --prepare-only is selected')
    if args.output and args.output.exists():
        parser.error('Output already exists; choose a new path')
    reference,metadata=prepare(args.root.resolve(),args.cache_dir.resolve())
    if args.prepare_only:
        print(json.dumps(dict(status='completed',strata=len(reference['strata']),
                             joint_cases=len(reference['cases']),metadata=metadata),ensure_ascii=False))
        return
    result=validate_analysis(args.root.resolve(),args.analysis_dir.resolve(),args.reference_cache.resolve(),reference,metadata)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(0 if result['status']=='passed' else 1)


if __name__=='__main__':
    main()
