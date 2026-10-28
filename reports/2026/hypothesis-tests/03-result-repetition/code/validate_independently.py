#!/usr/bin/env python3
"""Independent H3 source parser, collision inventory and exact conditional moments."""
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

HERE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[5]
SOURCE_PATHS={
    'details':'data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv',
    'votes':'data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv',
}
KEY_FIELDS=('CD_ELEICAO','NR_TURNO','SG_UF','CD_MUNICIPIO','NR_ZONA','NR_SECAO','CD_CARGO')
DETAIL_FIELDS=('QT_APTOS','QT_COMPARECIMENTO','QT_ABSTENCOES','QT_VOTOS_NOMINAIS',
    'QT_VOTOS_BRANCOS','QT_VOTOS_NULOS','QT_VOTOS_LEGENDA','QT_VOTOS_ANULADOS_APU_SEP')
PACK=struct.Struct('>7I')
VIEWS=('all_details','eligible','small_positive','zero_activity','other_excluded_positive')
CONFIG=dict(min_aptos=50,min_nominal=50,band_ratio=1.25,exact_nominal=True,
    stratum_fields=['uf','municipality','zone','nominal','size_band'],family_size=2,
    reference='Cantelli upper bound for excess collision pairs under conditional block exchangeability')


def digest_file(path):
    sha=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            sha.update(block)
    return sha.hexdigest()


def raw_rows(path):
    with Path(path).open('rb') as stream:
        if stream.read(100).startswith(b'version https://git-lfs.github.com/spec/v1'):
            raise ValueError(f'Git LFS pointer, not original data: {path}')
    with Path(path).open(encoding='latin1',newline='') as stream:
        reader=csv.reader(stream,delimiter=';');header=next(reader)
        if len(header)!=len(set(header)):
            raise ValueError('Duplicate source header')
        columns={name:i for i,name in enumerate(header)}
        for line,row in enumerate(reader,2):
            if len(row)!=len(header):
                raise ValueError(f'Malformed CSV row {path}:{line}')
            yield line,row,columns


def count(raw):
    raw=raw.strip()
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError(f'Missing/negative/invalid count: {raw!r}')
    return int(raw)


def flag(raw):
    value=raw.strip().casefold()
    if value in {'sim','s'}:
        return True
    if value in {'não','nao','n'}:
        return False
    raise ValueError(f'Unknown yes/no flag: {raw!r}')


def section_key(row,columns):
    values=[row[columns[f]].strip() for f in KEY_FIELDS]
    uf=values[2].upper()
    if len(uf)!=2 or not uf.isascii() or not uf.isalpha():
        raise ValueError('Invalid UF')
    numbers=[count(values[i]) for i in (0,1,3,4,5,6)]
    if numbers[1] not in (1,2) or numbers[-1]!=1:
        raise ValueError('Unsupported presidential key')
    packed=PACK.pack(numbers[0],numbers[1],int.from_bytes(uf.encode(),'big'),*numbers[2:])
    return packed,(numbers[0],numbers[1],uf,*numbers[2:-1])


def source_snapshot(root):
    stage1=json.loads((root/'reports/2026/input-manifest.json').read_text())
    h1=json.loads((root/'reports/2026/hypothesis-tests/01-accounting-integrity/evidence/accounting/manifest.json').read_text())
    if stage1['status']!='completed' or h1['status']!='completed':
        raise ValueError('Completed stage 1/H1 evidence required')
    result={}
    for kind,relative in SOURCE_PATHS.items():
        path=root/relative
        value=dict(path=relative,size_bytes=path.stat().st_size,sha256=digest_file(path))
        for baseline in (stage1['inputs'][kind],h1['inputs'][kind]):
            if value['sha256']!=baseline['sha256'] or value['size_bytes']!=baseline['size_bytes']:
                raise ValueError(f'{kind}: original snapshot differs from completed stages')
        result[kind]=value
    return result


def read_sources(root):
    records=[];index={};vectors={};special={};scopes=Counter();statistics=Counter()
    for line,row,columns in raw_rows(root/SOURCE_PATHS['details']):
        statistics['detail_rows_read']+=1
        if count(row[columns['ANO_ELEICAO']])!=2026 or count(row[columns['CD_CARGO']])!=1:
            continue
        key,scope=section_key(row,columns)
        if key in index:
            raise ValueError('Duplicate detail key')
        if row[columns['SG_UE']].strip().upper()!='BR' or row[columns['DS_CARGO']].strip().casefold()!='presidente':
            raise ValueError('Unexpected presidential scope')
        quantities=tuple(count(row[columns[f]]) for f in DETAIL_FIELDS)
        index[key]=len(records)
        records.append((scope,count(row[columns['NR_LOCAL_VOTACAO']]),quantities,
            flag(row[columns['ST_SECAO_INSTALADA']]),flag(row[columns['ST_SECAO_ANULADA']]),line))
        scopes[scope[:2]]+=1;statistics['detail_rows_selected']+=1
    if not records:
        raise ValueError('No selected details')
    n=len(records)
    for scope in scopes:
        special[scope]=[array('q',[0])*n for _ in range(3)]
    for line,row,columns in raw_rows(root/SOURCE_PATHS['votes']):
        statistics['vote_rows_read']+=1
        if count(row[columns['ANO_ELEICAO']])!=2026 or count(row[columns['CD_CARGO']])!=1:
            continue
        key,scope=section_key(row,columns)
        if key not in index:
            raise ValueError('Vote key without detail')
        candidate=count(row[columns['NR_VOTAVEL']]);value=count(row[columns['QT_VOTOS']]);i=index[key]
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
        raise ValueError('No selected votes')
    candidates={scope:sorted(k[2] for k in vectors if k[:2]==scope) for scope in scopes}
    totals={}
    for i,(scope,place,q,installed,cancelled,line) in enumerate(records):
        election,turn,uf,municipality,zone,section=scope
        aptos,turnout,abstentions,nominal,blank,null,legend,separate=q
        if sum(vectors[(election,turn,c)][i] for c in candidates[(election,turn)])!=nominal:
            raise ValueError(f'Nominal reconciliation failed at {scope}')
        if tuple(v[i] for v in special[(election,turn)])!=(blank,null,separate):
            raise ValueError(f'Special-vote reconciliation failed at {scope}')
        if legend!=0 or nominal+blank+null+legend+separate!=turnout or turnout>aptos:
            raise ValueError(f'Invalid section accounting at {scope}')
        total=totals.setdefault((election,turn,uf),Counter())
        total.update(dict(records=1,aptos=aptos,turnout=turnout,abstentions=abstentions,
            nominal=nominal,blank=blank,null_votes=null,legend=legend,separate=separate))
    return records,vectors,candidates,statistics,totals


def choose2(n):
    return n*(n-1)//2


def falling(n,k):
    result=1
    for j in range(k):
        result*=n-j
    return result


def exact_moments(a_counts,b_counts,joint_counts):
    """Independent U-statistic derivation; every operation uses exact fractions."""
    n=sum(a_counts)
    if n!=sum(b_counts) or n!=sum(joint_counts):
        raise ValueError('Incompatible block margins')
    x=sum(choose2(v) for v in joint_counts)
    a2=sum(choose2(v) for v in a_counts)
    b2=sum(choose2(v) for v in b_counts)
    if n<2:
        return x,Fraction(0),Fraction(0)
    q2=Fraction(b2,choose2(n))
    e=a2*q2
    h=sum(3*math.comb(v,3) for v in a_counts if v>=3)
    d=choose2(a2)-h
    q3=Fraction(sum(falling(v,3) for v in b_counts),falling(n,3)) if h else Fraction(0)
    q22=Fraction((2*b2)**2-sum(falling(v,2)**2 for v in b_counts)
        +sum(falling(v,4) for v in b_counts),falling(n,4)) if d else Fraction(0)
    variance=a2*(q2-q2*q2)+2*h*(q3-q2*q2)+2*d*(q22-q2*q2)
    if variance<0:
        raise ValueError('Negative exact conditional variance')
    return x,e,variance


def view_members(q,installed,cancelled):
    aptos,turnout,_,nominal,*_=q
    eligible=installed and not cancelled and aptos>=50 and nominal>=50 and turnout>0
    small=installed and not cancelled and turnout>0 and (aptos<50 or nominal<50)
    return dict(all_details=True,eligible=eligible,small_positive=small,
        zero_activity=turnout==0,other_excluded_positive=turnout>0 and not eligible and not small)


def signature_id(signature):
    text=json.dumps(list(signature),separators=(',',':'))
    return hashlib.sha256(text.encode()).hexdigest()


def summarize_vectors(signatures):
    counts=Counter(signatures)
    repeated=[v for v in counts.values() if v>1]
    return dict(sections=sum(counts.values()),unique_vectors=len(counts),repeated_clusters=len(repeated),
        repeated_sections=sum(repeated),collision_pairs=sum(choose2(v) for v in repeated),
        max_multiplicity=max(counts.values(),default=0))


def reference_from_records(records,vectors,candidates,statistics,totals):
    signatures={};round_members=defaultdict(list);group_members=defaultdict(list)
    for i,(scope,place,q,installed,cancelled,line) in enumerate(records):
        election,turn,uf,municipality,zone,section=scope
        aptos,turnout,abstentions,nominal,blank,null,legend,separate=q
        signature=tuple(vectors[(election,turn,c)][i] for c in candidates[(election,turn)])+(blank,null,legend,separate,turnout)
        signatures[i]=signature;round_members[(election,turn)].append(i)
        if view_members(q,installed,cancelled)['eligible']:
            band=math.floor(math.log(aptos)/math.log(1.25))
            group_members[(election,turn,uf,municipality,zone,nominal,band)].append(i)
    inventory=[];clusters=[];cluster_members=[];turnout_distribution=[]
    for identity,all_ids in sorted(round_members.items()):
        election,turn=identity
        views={name:[] for name in VIEWS}
        for i in all_ids:
            for name,include in view_members(records[i][2],records[i][3],records[i][4]).items():
                if include:
                    views[name].append(i)
        for view,ids in views.items():
            for kind in ('full','extended'):
                def vector(i):
                    return signatures[i]+(records[i][2][0],records[i][2][2]) if kind=='extended' else signatures[i]
                counts=Counter(vector(i) for i in ids)
                inventory.append(dict(election_code=election,turno=turn,view=view,signature_type=kind,
                    **summarize_vectors(vector(i) for i in ids)))
                by_turnout=defaultdict(Counter)
                for key,n in counts.items():
                    turnout=key[-3] if kind=='extended' else key[-1]
                    by_turnout[turnout].update(dict(sections=n,unique_vectors=1,
                        repeated_clusters=int(n>1),repeated_sections=n if n>1 else 0,
                        collision_pairs=choose2(n)))
                for turnout,tally in sorted(by_turnout.items()):
                    turnout_distribution.append(dict(election_code=election,turno=turn,view=view,
                        signature_type=kind,turnout=turnout,**dict(tally)))
                repeated={key:value for key,value in counts.items() if value>1}
                locations={key:[] for key in repeated}
                for i in ids:
                    key=vector(i)
                    if key in locations:
                        locations[key].append(i)
                for key,n in sorted(repeated.items()):
                    cluster_id=signature_id(key)
                    clusters.append(dict(election_code=election,turno=turn,view=view,signature_type=kind,
                        cluster_id=cluster_id,signature=list(key),multiplicity=n,collision_pairs=choose2(n)))
                    for i in locations[key]:
                        scope,place,q,installed,cancelled,line=records[i]
                        cluster_members.append(dict(election_code=election,turno=turn,view=view,signature_type=kind,
                            cluster_id=cluster_id,signature=list(key),uf=scope[2],municipality=scope[3],zone=scope[4],
                            section=scope[5],place=place,source_line=line,aptos=q[0],turnout=q[1],abstentions=q[2],
                            nominal=q[3],installed=installed,cancelled=cancelled))
    strata=[];rounds={identity:dict(x=0,e=Fraction(0),v=Fraction(0),groups=0,sections=0,
        nonsingleton_groups=0,nonsingleton_sections=0,informative_groups=0,informative_sections=0)
        for identity in round_members}
    for key,ids in sorted(group_members.items()):
        election,turn,uf,municipality,zone,nominal,band=key
        a=Counter(tuple(vectors[(election,turn,c)][i] for c in candidates[(election,turn)]) for i in ids)
        b=Counter(signatures[i][-5:] for i in ids)
        joint=Counter(signatures[i] for i in ids)
        x,e,v=exact_moments(list(a.values()),list(b.values()),list(joint.values()))
        row=dict(election_code=election,turno=turn,uf=uf,municipality=municipality,zone=zone,
            nominal=nominal,size_band=band,n=len(ids),min_aptos=min(records[i][2][0] for i in ids),
            max_aptos=max(records[i][2][0] for i in ids),a_unique=len(a),b_unique=len(b),
            a_pairs=sum(choose2(n) for n in a.values()),b_pairs=sum(choose2(n) for n in b.values()),
            observed_pairs=x,expected_pairs=float(e),variance=float(v),
            expected_numerator=str(e.numerator),expected_denominator=str(e.denominator),
            variance_numerator=str(v.numerator),variance_denominator=str(v.denominator))
        strata.append(row)
        total=rounds[(election,turn)]
        total['x']+=x;total['e']+=e;total['v']+=v;total['groups']+=1;total['sections']+=len(ids)
        total['nonsingleton_groups']+=len(ids)>1
        total['nonsingleton_sections']+=len(ids) if len(ids)>1 else 0
        total['informative_groups']+=v>0
        total['informative_sections']+=len(ids) if v>0 else 0
    round_rows=[]
    for (election,turn),r in sorted(rounds.items()):
        x,e,v=r.pop('x'),r.pop('e'),r.pop('v')
        if v==0 and Fraction(x)!=e:
            raise ValueError('Observed value incompatible with a degenerate reference')
        bound=v/(v+(x-e)**2) if v>0 and x>e else Fraction(1)
        round_rows.append(dict(election_code=election,turno=turn,observed_pairs=x,expected_pairs=float(e),variance=float(v),
            expected_numerator=str(e.numerator),expected_denominator=str(e.denominator),
            variance_numerator=str(v.numerator),variance_denominator=str(v.denominator),
            p_bound=float(bound) if v>0 else None,p_numerator=str(bound.numerator),p_denominator=str(bound.denominator),**r))
    return dict(config=CONFIG,source_statistics=dict(statistics),
        candidates=[dict(election_code=e,turno=t,numbers=ns) for (e,t),ns in sorted(candidates.items())],
        totals=[dict(election_code=s[0],turno=s[1],uf=s[2],**dict(v)) for s,v in sorted(totals.items())],
        inventory=inventory,clusters=clusters,cluster_members=cluster_members,
        turnout_distribution=turnout_distribution,strata=strata,rounds=round_rows)


def implementation_fingerprint():
    functions=[raw_rows,count,flag,section_key,source_snapshot,read_sources,choose2,falling,exact_moments,
        view_members,signature_id,summarize_vectors,reference_from_records]
    text=json.dumps(CONFIG,sort_keys=True)+'\n'.join(inspect.getsource(f) for f in functions)
    return hashlib.sha256(text.encode()).hexdigest()


def prepare(root,cache_dir):
    if not (HERE/'METHOD.pt-BR.md').is_file():
        raise ValueError('Freeze the H3 method before computing observed collisions')
    sources=source_snapshot(root);fingerprint=implementation_fingerprint()
    cache_dir.mkdir(parents=True,exist_ok=True)
    metadata_path=cache_dir/'reference-metadata.json';data_path=cache_dir/'reference.json.gz'
    if metadata_path.exists() and data_path.exists():
        metadata=json.loads(metadata_path.read_text())
        if metadata.get('source_inputs')!=sources or metadata.get('implementation_fingerprint')!=fingerprint:
            raise ValueError('Independent cache fingerprint mismatch; choose a new directory')
        if metadata.get('reference_sha256')!=digest_file(data_path):
            raise ValueError('Independent reference cache hash mismatch')
        with gzip.open(data_path,'rt',encoding='utf-8') as stream:
            return json.load(stream),metadata
    if any(cache_dir.iterdir()):
        raise ValueError('Incomplete/nonempty independent cache; choose a new directory')
    print('Independent H3: reading original sources',flush=True)
    reference=reference_from_records(*read_sources(root))
    if sources!=source_snapshot(root):
        raise ValueError('Original source changed during independent scan')
    with gzip.open(data_path,'wt',encoding='utf-8') as stream:
        json.dump(reference,stream,ensure_ascii=False,separators=(',',':'))
    metadata=dict(status='completed',created_at_utc=datetime.now(timezone.utc).isoformat(),
        source_inputs=sources,implementation_fingerprint=fingerprint,reference_sha256=digest_file(data_path))
    metadata_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return reference,metadata


def holm_reference(values):
    order=sorted(values,key=lambda identity:values[identity])
    running=Fraction(0);adjusted={}
    for rank,identity in enumerate(order):
        running=max(running,min(Fraction(1),(len(order)-rank)*values[identity]))
        adjusted[identity]=running
    return adjusted


def csv_rows(path):
    opener=gzip.open if Path(path).suffix=='.gz' else open
    with opener(path,'rt',encoding='utf-8',newline='') as stream:
        return list(csv.DictReader(stream))


def field(row,*names):
    for name in names:
        if name in row:
            return row[name]
    raise ValueError(f'Missing required primary column: {"/".join(names)}')


def vector_key(row):
    if 'signature' in row and isinstance(row['signature'],list):
        return tuple(row['signature'])
    return tuple(json.loads(field(row,'vector_json','signature_json','signature')))


def validate_analysis(analysis,reference,metadata):
    """Compare every primary inventory/member/stratum and exact Cantelli bounds."""
    manifest=json.loads((analysis/'manifest.json').read_text())
    if manifest.get('status')!='completed':
        raise ValueError('Completed H3 analysis required')
    counts=Counter();failures=[];maximum_error=0.0

    def same(category,label,actual,expected,tolerance=None):
        nonlocal maximum_error
        counts[category]+=1
        if tolerance is None:
            passed=actual==expected
        else:
            error=abs(float(actual)-float(expected));maximum_error=max(maximum_error,error)
            passed=math.isfinite(float(actual)) and math.isfinite(float(expected)) and error<=tolerance
        counts['all_mismatches']+=not passed
        if not passed and len(failures)<100:
            def compact(value):
                if isinstance(value,(list,tuple)) and len(value)>12:
                    return dict(length=len(value),first_items=value[:8])
                return value
            failures.append(dict(category=category,comparison=label,primary=compact(actual),independent=compact(expected)))

    def index(rows,key_function,label):
        result={key_function(row):row for row in rows}
        same('inventory',label+' unique keys',len(result),len(rows))
        return result

    def located(*names):
        for name in names:
            path=analysis/name
            if path.exists():
                return path
            path=analysis/(name+'.gz')
            if path.exists():
                return path
        raise ValueError(f'Missing required primary table: {names}')

    def scope(row):
        return int(row['election_code']),int(row['turno'])

    def inventory_key(row):
        view=field(row,'view','population')
        view={'all':'all_details','other_positive':'other_excluded_positive'}.get(view,view)
        return (*scope(row),view,field(row,'signature_type','signature_kind'))

    def cluster_key(row):
        return (*inventory_key(row),vector_key(row))

    def member_key(row):
        return (*cluster_key(row),row['uf'],int(row['municipality']),int(row['zone']),int(row['section']))

    def group_key(row):
        return (*scope(row),row['uf'],int(row['municipality']),int(row['zone']),
            int(field(row,'nominal','nominal_total')),int(field(row,'size_band','band')))

    for kind,source in metadata['source_inputs'].items():
        for name in ('sha256','size_bytes'):
            same('source_provenance',kind+':'+name,manifest['source_inputs'][kind][name],source[name])
    same('method_provenance','frozen method',manifest['method_sha256'],digest_file(HERE/'METHOD.pt-BR.md'))
    for name,sha in manifest['implementation_sha256'].items():
        same('code_provenance',name,sha,digest_file(HERE/'code'/name))
    for name,sha in manifest['artifact_sha256'].items():
        same('artifact_integrity',name,sha,digest_file(analysis/name))
    required_artifacts={'inventory.csv','clusters.csv.gz','cluster-members.csv.gz','turnout-distribution.csv',
        'strata.csv.gz','conditional-tests.csv','sensitivity.csv','coverage.csv','summary.json'}
    same('inventory','all required artifact hashes declared',sorted(required_artifacts&manifest['artifact_sha256'].keys()),sorted(required_artifacts))
    same('configuration','two-member primary family',manifest.get('primary_family_size'),2)
    for kind,prefix in [('details','detail'),('votes','vote')]:
        if 'source_counts' in manifest:
            for primary_name,source_name in [('rows_read',prefix+'_rows_read'),('selected_rows',prefix+'_rows_selected')]:
                same('source_counts',kind+':'+primary_name,manifest['source_counts'][kind][primary_name],reference['source_statistics'][source_name])

    inventory_path=located('inventory.csv','inventory-summary.csv')
    actual_inventory=index(csv_rows(inventory_path),inventory_key,'inventory summary')
    expected_inventory=index(reference['inventory'],inventory_key,'independent inventory summary')
    same('inventory','all populations/signatures/rounds',sorted(actual_inventory),sorted(expected_inventory))
    aliases=dict(sections=('sections','n_sections','rows'),unique_vectors=('unique_vectors','unique_signatures','distinct_signatures'),
        repeated_clusters=('repeated_clusters','repeated_groups'),repeated_sections=('repeated_sections',),
        collision_pairs=('collision_pairs','pairs'),max_multiplicity=('max_multiplicity','maximum_multiplicity'))
    for key in sorted(actual_inventory.keys()&expected_inventory.keys()):
        actual,expected=actual_inventory[key],expected_inventory[key]
        for name,names in aliases.items():
            same('collision_inventory',f'{key}:{name}',int(field(actual,*names)),expected[name])

    clusters=index(csv_rows(located('clusters.csv','repeated-clusters.csv')),cluster_key,'clusters')
    expected_clusters=index(reference['clusters'],cluster_key,'independent clusters')
    same('inventory','complete repeated-vector cluster inventory',sorted(clusters),sorted(expected_clusters))
    for key in sorted(clusters.keys()&expected_clusters.keys()):
        for name,names in [('multiplicity',('multiplicity','n')),('collision_pairs',('collision_pairs','pairs'))]:
            same('cluster_counts',f'{key}:{name}',int(field(clusters[key],*names)),expected_clusters[key][name])
        if 'cluster_id' in clusters[key]:
            same('cluster_identifiers',str(key),clusters[key]['cluster_id'],expected_clusters[key]['cluster_id'])

    members=index(csv_rows(located('cluster-members.csv','members.csv')),member_key,'cluster members')
    expected_members=index(reference['cluster_members'],member_key,'independent cluster members')
    same('inventory','all repeated-vector section memberships',sorted(members),sorted(expected_members))
    for key in sorted(members.keys()&expected_members.keys()):
        if 'cluster_id' in members[key]:
            same('cluster_identifiers',str(key),members[key]['cluster_id'],expected_members[key]['cluster_id'])
        for name,names in [('place',('place','voting_place')),('source_line',('source_line','input_line')),
            ('aptos',('aptos',)),('turnout',('turnout',)),('abstentions',('abstentions',)),('nominal',('nominal',))]:
            same('member_values',f'{key}:{name}',int(field(members[key],*names)),expected_members[key][name])
        for name in ('installed','cancelled'):
            if name in members[key]:
                raw=members[key][name].strip().casefold()
                if raw in {'true','1','s','sim'}:
                    actual_flag=True
                elif raw in {'false','0','n','não','nao'}:
                    actual_flag=False
                else:
                    raise ValueError(f'Invalid published boolean: {name}={raw!r}')
                same('member_values',f'{key}:{name}',actual_flag,expected_members[key][name])
    geography=defaultdict(list)
    for row in reference['cluster_members']:
        geography[cluster_key(row)].append((row['uf'],row['municipality'],row['zone'],row['place']))
    for key in sorted(clusters.keys()&expected_clusters.keys()):
        places=geography[key]
        for name,value in [('uf_count',len({p[0] for p in places})),
            ('municipality_count',len({p[:2] for p in places})),('zone_count',len({p[:3] for p in places})),
            ('place_count',len(set(places)))]:
            if name in clusters[key]:
                same('cluster_geography',f'{key}:{name}',int(clusters[key][name]),value)

    distribution=index(csv_rows(located('turnout-distribution.csv')),lambda r:(*inventory_key(r),int(r['turnout'])),'turnout distribution')
    expected_distribution=index(reference['turnout_distribution'],lambda r:(*inventory_key(r),int(r['turnout'])),'independent turnout distribution')
    same('inventory','all exact turnout bins',sorted(distribution),sorted(expected_distribution))
    for key in sorted(distribution.keys()&expected_distribution.keys()):
        for name in ('sections','unique_vectors','repeated_clusters','repeated_sections','collision_pairs'):
            same('turnout_distribution',f'{key}:{name}',int(distribution[key][name]),expected_distribution[key][name])
        if 'same_turnout_pairs' in distribution[key]:
            possible=choose2(expected_distribution[key]['sections'])
            same('turnout_distribution',f'{key}:same_turnout_pairs',int(distribution[key]['same_turnout_pairs']),possible)
            actual_rate=distribution[key]['collision_rate_same_turnout']
            if possible:
                same('turnout_distribution',f'{key}:collision_rate_same_turnout',float(actual_rate),
                    expected_distribution[key]['collision_pairs']/possible,1e-15)
            else:
                same('turnout_distribution',f'{key}:undefined_collision_rate',actual_rate,'')

    groups=index(csv_rows(located('strata.csv')),group_key,'primary strata')
    expected_groups=index(reference['strata'],group_key,'independent primary strata')
    same('inventory','all primary strata, including singletons',sorted(groups),sorted(expected_groups))
    group_aliases=dict(n=('n','sections'),min_aptos=('min_aptos',),max_aptos=('max_aptos',),
        a_unique=('a_unique','unique_a'),b_unique=('b_unique','unique_b'),
        a_pairs=('a_pairs','pairs_a'),b_pairs=('b_pairs','pairs_b'),observed_pairs=('observed_pairs','collision_pairs','x'))
    for key in sorted(groups.keys()&expected_groups.keys()):
        actual,expected=groups[key],expected_groups[key]
        for name,names in group_aliases.items():
            same('stratum_integer',f'{key}:{name}',int(field(actual,*names)),expected[name])
        for name,names in [('expected_pairs',('expected_pairs','expectation')),('variance',('variance',))]:
            same('stratum_moments',f'{key}:{name}',float(field(actual,*names)),expected[name],1e-12)
        for name in ('expected_numerator','expected_denominator','variance_numerator','variance_denominator'):
            if name in actual:
                same('stratum_rational',f'{key}:{name}',int(actual[name]),int(expected[name]))

    # UF coverage can be derived without rereading votes: eligible members are
    # exactly the primary groups, zero-activity rows have the unique zero vector,
    # and the two remaining populations partition the other raw detail records.
    coverage_numbers=('raw_details','eligible','small_positive','zero_activity','other_excluded_positive',
        'groups','sections','nonsingleton_groups','nonsingleton_sections','informative_groups','informative_sections')
    totals={(*scope(r),r['uf']):r for r in reference['totals']}
    derived_coverage={key:Counter(raw_details=r['records']) for key,r in totals.items()}
    for row in reference['strata']:
        key=(*scope(row),row['uf']);n=row['n'];tally=derived_coverage[key]
        tally.update(dict(eligible=n,groups=1,sections=n,nonsingleton_groups=int(n>1),
            nonsingleton_sections=n if n>1 else 0,informative_groups=int(int(row['variance_numerator'])>0),
            informative_sections=n if int(row['variance_numerator'])>0 else 0))
    zero_rows=[r for r in reference['cluster_members'] if r['view']=='zero_activity' and r['signature_type']=='full']
    for identity in sorted({scope(r) for r in reference['inventory']}):
        zero_summary=expected_inventory[(*identity,'zero_activity','full')]
        same('coverage_derivation',f'{identity}:zero-vector members exhaustive',
            sum(scope(r)==identity for r in zero_rows),zero_summary['sections'])
        other_summary=expected_inventory[(*identity,'other_excluded_positive','full')]
        same('coverage_derivation',f'{identity}:no excluded positive source records',other_summary['sections'],0)
    for row in zero_rows:
        derived_coverage[(*scope(row),row['uf'])]['zero_activity']+=1
    for key,tally in derived_coverage.items():
        tally['small_positive']=tally['raw_details']-tally['eligible']-tally['zero_activity']
    for identity in sorted({key[:2] for key in derived_coverage}):
        selected=[r for key,r in derived_coverage.items() if key[:2]==identity]
        derived_coverage[(*identity,'BR')]=Counter({f:sum(r[f] for r in selected) for f in coverage_numbers})
    coverage_path=located('coverage.csv')
    coverage_rows=csv_rows(coverage_path)
    actual_coverage=index(coverage_rows,lambda r:(*scope(r),r['uf']),'coverage')
    same('inventory','all coverage UF and national keys',sorted(actual_coverage),sorted(derived_coverage))
    for key in sorted(actual_coverage.keys()&derived_coverage.keys()):
        for name in coverage_numbers:
            same('coverage',f'{key}:{name}',int(actual_coverage[key][name]),derived_coverage[key][name])

    tests=index(csv_rows(located('conditional-tests.csv','collision-tests.csv')),scope,'primary test family')
    expected_tests=index(reference['rounds'],scope,'independent test family')
    same('inventory','exactly two primary tests',len(tests),2)
    same('inventory','fixed two-round family',sorted(tests),sorted(expected_tests))
    raw={};applicable={}
    for identity in sorted(tests.keys()&expected_tests.keys()):
        actual,expected=tests[identity],expected_tests[identity]
        for name,names in [('observed_pairs',('observed_pairs','collision_pairs','x')),('groups',('groups','n_strata')),
            ('sections',('sections','n_sections')),('nonsingleton_groups',('nonsingleton_groups','pair_strata')),
            ('nonsingleton_sections',('nonsingleton_sections','pair_sections')),
            ('informative_groups',('informative_groups','informative_strata')),
            ('informative_sections',('informative_sections',))]:
            same('test_integer',f'{identity}:{name}',int(field(actual,*names)),expected[name])
        for name,names in [('expected_pairs',('expected_pairs','expectation')),('variance',('variance',))]:
            same('test_moments',f'{identity}:{name}',float(field(actual,*names)),expected[name],1e-10)
        for name in ('expected_numerator','expected_denominator','variance_numerator','variance_denominator'):
            if name in actual:
                same('test_rational',f'{identity}:{name}',int(actual[name]),int(expected[name]))
        exact_v=Fraction(int(expected['variance_numerator']),int(expected['variance_denominator']))
        applicable[identity]=exact_v>0
        raw[identity]=Fraction(int(expected['p_numerator']),int(expected['p_denominator'])) if exact_v else Fraction(1)
        if exact_v:
            same('cantelli_bound',str(identity),float(field(actual,'p_bound','p_upper_bound','cantelli_bound')),float(raw[identity]),1e-12)
            for name in ('p_numerator','p_denominator'):
                if name in actual:
                    same('cantelli_rational',f'{identity}:{name}',int(actual[name]),int(expected[name]))
        else:
            same('cantelli_bound',str(identity),field(actual,'p_bound','p_upper_bound','cantelli_bound'),'')
    adjusted=holm_reference(raw)
    for identity,p in adjusted.items():
        if applicable[identity]:
            same('holm',str(identity),float(field(tests[identity],'p_holm','bound_holm')),float(p),1e-12)
            for name,value in [('holm_numerator',p.numerator),('holm_denominator',p.denominator)]:
                if name in tests[identity]:
                    same('holm_rational',f'{identity}:{name}',int(tests[identity][name]),value)
            status='excess_detected' if p<=Fraction(1,20) else 'not_detected'
        else:
            same('holm',str(identity),field(tests[identity],'p_holm','bound_holm'),'')
            status='not_applicable'
        same('decision',str(identity),tests[identity]['status'],status)

    # These are publication links from tables independently checked above;
    # sensitivity model outcomes remain explicitly outside this independent run.
    summary=json.loads((analysis/'summary.json').read_text())
    for label,key_function,actual_rows,csv_expected in [
        ('inventory',inventory_key,summary['inventory'],list(actual_inventory.values())),
        ('conditional_tests',scope,summary['conditional_tests'],list(tests.values())),
        ('coverage',lambda r:(*scope(r),r['uf']),summary['coverage'],[r for r in coverage_rows if r['uf']=='BR'])]:
        lhs=index(actual_rows,key_function,'summary '+label)
        rhs=index(csv_expected,key_function,'CSV '+label)
        same('summary_link',label+' complete keys',sorted(lhs),sorted(rhs))
        for key in sorted(lhs.keys()&rhs.keys()):
            for name,value in rhs[key].items():
                same('summary_link',f'{label}:{key}:{name}',str(lhs[key].get(name)),value)
    candidate_map={scope(r):r['numbers'] for r in reference['candidates']}
    primary_candidates={scope(r):r['numbers'] for r in summary['candidates']}
    same('summary_link','all nominal candidates retained',primary_candidates,candidate_map)
    sensitivity_csv=csv_rows(located('sensitivity.csv'))
    sensitivity_key=lambda r:(*scope(r),r['scenario'])
    lhs=index(summary['sensitivity'],sensitivity_key,'summary sensitivities')
    rhs=index(sensitivity_csv,sensitivity_key,'CSV sensitivities')
    same('summary_link','sensitivity publication keys',sorted(lhs),sorted(rhs))
    for key in sorted(lhs.keys()&rhs.keys()):
        for name,value in rhs[key].items():
            same('summary_link',f'sensitivity:{key}:{name}',str(lhs[key].get(name)),value)
    mismatch_count=counts.pop('all_mismatches')
    return dict(status='passed' if mismatch_count==0 else 'failed',
        completed_at_utc=datetime.now(timezone.utc).isoformat(),script_sha256=digest_file(Path(__file__)),
        reference_implementation_fingerprint=metadata['implementation_fingerprint'],source_inputs=metadata['source_inputs'],
        independent_source_counts=reference['source_statistics'],comparisons=dict(counts),mismatches=mismatch_count,
        maximum_numeric_error=maximum_error,numeric_tolerances=dict(stratum_moments=1e-12,aggregate_moments=1e-10,bounds=1e-12),
        failures=failures,failure_examples_limit=100,
        scope=dict(source_data='Original national CSVs re-read independently; no imports of primary analysis helpers',
            inventory='Full and extended signatures in every declared population, all repeated vectors and member keys',
            reference='Every primary stratum, exact rational moments summed by round, Cantelli upper bounds and fixed two-member Holm family',
            sensitivities='Alternative descriptive scenarios are not independently recomputed here',
            interpretation='Conditional block-exchangeability reference, not a test of naturalness or external authenticity'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--cache-dir',type=Path,default=HERE/'.work/independent')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--analysis-dir',type=Path,default=HERE/'evidence/analysis')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output and args.output.exists():
        parser.error('Output already exists; choose a new path')
    reference,metadata=prepare(args.root.resolve(),args.cache_dir.resolve())
    if args.prepare_only:
        print(json.dumps(dict(status='completed',inventory_rows=len(reference['inventory']),
            clusters=len(reference['clusters']),strata=len(reference['strata']),metadata=metadata),ensure_ascii=False))
        return
    if args.output is None:
        parser.error('--output is required unless --prepare-only is selected')
    result=validate_analysis(args.analysis_dir.resolve(),reference,metadata)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(0 if result['status']=='passed' else 1)


if __name__=='__main__':
    main()
