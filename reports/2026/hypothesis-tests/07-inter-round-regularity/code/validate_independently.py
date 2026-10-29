#!/usr/bin/env python3
"""Independent original-source reconstruction and validation for the H7 study.

The independent parser and physical join adapt H6 commit cb32076a0eea70a35782fbabba7777a5e49c94fc.
No primary H7 parser, group builder, statistic, or simulation helper is imported.
The source parser has its own content-addressed cache. Monte Carlo ranks and
quantiles are recomputed from retained, fingerprinted simulation arrays; that
is distinct from independently repeating every large random assignment.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
from itertools import permutations, product
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import inspect
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
SOURCE_PATHS = {
    'details': 'data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv',
    'votes': 'data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv',
}
KEY_FIELDS = ('CD_ELEICAO', 'NR_TURNO', 'SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO', 'CD_CARGO')
QUANTITIES = {
    'aptos': 'QT_APTOS', 'turnout': 'QT_COMPARECIMENTO', 'abstentions': 'QT_ABSTENCOES',
    'nominal': 'QT_VOTOS_NOMINAIS', 'blank': 'QT_VOTOS_BRANCOS', 'null_votes': 'QT_VOTOS_NULOS',
    'legend': 'QT_VOTOS_LEGENDA', 'separate': 'QT_VOTOS_ANULADOS_APU_SEP',
}
PACK = struct.Struct('>7I')
MISSING = {'', '#NULO', '#NE', '-1', '-3'}
MODELS = ('section', 'place_block')
STAT_NAMES = ('Ucount', 'Unominal', 'Uconditional', 'Rlow', 'Jhigh')
TAILS = ('upper', 'upper', 'upper', 'lower', 'upper')
COUNT_FIELDS = (*QUANTITIES, 'v13', 'v22', 'f')
METHOD_SHA256 = '7212a1f6941c2357b751bb3b44dae60e931e2cdba5801c7dc231bd86bcb44066'


def digest_file(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def integer(raw):
    text = raw.strip()
    if not text.isascii() or not text.isdecimal():
        raise ValueError(f'Missing, negative or invalid count: {text!r}')
    return int(text)


def yes_no(raw):
    text = raw.strip().casefold()
    if text in {'sim', 's'}:
        return True
    if text in {'não', 'nao', 'n'}:
        return False
    raise ValueError(f'Unknown source flag: {raw!r}')


def raw_rows(path):
    with Path(path).open('rb') as stream:
        if stream.read(100).startswith(b'version https://git-lfs.github.com/spec/v1'):
            raise ValueError(f'Git LFS pointer, not original CSV: {path}')
    with Path(path).open(encoding='latin1', newline='') as stream:
        reader = csv.reader(stream, delimiter=';')
        header = next(reader)
        if len(header) != len(set(header)):
            raise ValueError('Duplicate original-source header')
        columns = {name: i for i, name in enumerate(header)}
        for line, row in enumerate(reader, 2):
            if len(row) != len(header):
                raise ValueError(f'Malformed original CSV at {path}:{line}')
            yield line, row, columns


def source_key(row, columns):
    values = [row[columns[field]].strip() for field in KEY_FIELDS]
    uf = values[2].upper()
    if len(uf) != 2 or not uf.isascii() or not uf.isalpha():
        raise ValueError('Invalid source UF')
    numbers = [integer(values[i]) for i in (0, 1, 3, 4, 5, 6)]
    if numbers[1] not in (1, 2) or numbers[-1] != 1:
        raise ValueError('Unsupported presidential scope')
    packed = PACK.pack(numbers[0], numbers[1], int.from_bytes(uf.encode(), 'big'), *numbers[2:])
    return packed, (numbers[0], numbers[1], uf, *numbers[2:-1])


def source_snapshot(root):
    stage1 = json.loads((root / 'reports/2026/input-manifest.json').read_text())
    h1 = json.loads((root / 'reports/2026/hypothesis-tests/01-accounting-integrity/evidence/accounting/manifest.json').read_text())
    if stage1['status'] != 'completed' or h1['status'] != 'completed':
        raise ValueError('Stage 1/H1 provenance is required')
    result = {}
    for name, relative in SOURCE_PATHS.items():
        path = root / relative
        entry = dict(path=relative, size_bytes=path.stat().st_size, sha256=digest_file(path))
        for baseline in (stage1['inputs'][name], h1['inputs'][name]):
            if entry['sha256'] != baseline['sha256'] or entry['size_bytes'] != baseline['size_bytes']:
                raise ValueError(f'{name}: source differs from stage 1/H1 snapshot')
        result[name] = entry
    return result


def read_sources(root):
    """Separate CSV scan and exact section/category reconciliation."""
    records = {field: [] for field in ('election_code', 'turno', 'uf', 'municipality', 'zone', 'section',
                                     'place', 'source_line', 'installed', 'cancelled', *QUANTITIES,
                                     )}
    lookup = {}
    statistics = Counter()
    for line, row, columns in raw_rows(root / SOURCE_PATHS['details']):
        statistics['detail_rows_read'] += 1
        if integer(row[columns['ANO_ELEICAO']]) != 2026 or integer(row[columns['CD_CARGO']]) != 1:
            continue
        packed, key = source_key(row, columns)
        if packed in lookup:
            raise ValueError('Duplicate normalized detail section')
        if row[columns['SG_UE']].strip().upper() != 'BR' or row[columns['DS_CARGO']].strip().casefold() != 'presidente':
            raise ValueError('Unexpected source scope')
        lookup[packed] = len(records['aptos'])
        for field, value in zip(('election_code', 'turno', 'uf', 'municipality', 'zone', 'section'), key):
            records[field].append(value)
        place = row[columns['NR_LOCAL_VOTACAO']].strip()
        records['place'].append(-1 if place.upper() in MISSING else integer(place))
        for field, original in QUANTITIES.items():
            records[field].append(integer(row[columns[original]]))
        records['source_line'].append(line)
        records['installed'].append(yes_no(row[columns['ST_SECAO_INSTALADA']]))
        records['cancelled'].append(yes_no(row[columns['ST_SECAO_ANULADA']]))
        statistics['detail_rows_selected'] += 1
    if not records['aptos']:
        raise ValueError('No presidential details in original source')
    arrays = {field: np.asarray(values, dtype='U2' if field == 'uf' else np.bool_ if field in {'installed', 'cancelled'} else np.int64)
              for field, values in records.items()}
    del records
    n = len(arrays['aptos'])
    candidate_votes = {}
    scopes = defaultdict(set)
    special = {number: np.zeros(n, dtype=np.int64) for number in (95, 96, 97)}
    for line, row, columns in raw_rows(root / SOURCE_PATHS['votes']):
        statistics['vote_rows_read'] += 1
        if integer(row[columns['ANO_ELEICAO']]) != 2026 or integer(row[columns['CD_CARGO']]) != 1:
            continue
        packed, key = source_key(row, columns)
        if packed not in lookup:
            raise ValueError('Vote source section has no detail')
        index = lookup[packed]
        candidate = integer(row[columns['NR_VOTAVEL']])
        value = integer(row[columns['QT_VOTOS']])
        if candidate == 0:
            raise ValueError('Zero votable identifier')
        if candidate in special:
            special[candidate][index] += value
        else:
            if candidate not in candidate_votes:
                candidate_votes[candidate] = np.zeros(n, dtype=np.int64)
            candidate_votes[candidate][index] += value
            scopes[key[:2]].add(candidate)
        statistics['vote_rows_selected'] += 1
        if statistics['vote_rows_selected'] % 1000000 == 0:
            print(f'Independent H7 parser: {statistics["vote_rows_selected"]:,} vote rows', file=sys.stderr, flush=True)
    if not statistics['vote_rows_selected']:
        raise ValueError('No presidential voting rows')
    for code, field in ((95, 'blank'), (96, 'null_votes'), (97, 'separate')):
        if not np.array_equal(special[code], arrays[field]):
            raise ValueError(f'Independent source reconciliation failed: {field}')
    if np.any(arrays['legend']) or not np.array_equal(sum(arrays[field] for field in ('nominal', 'blank', 'null_votes', 'legend', 'separate')), arrays['turnout']):
        raise ValueError('Independent total/category reconciliation failed')
    if not np.array_equal(sum(candidate_votes.values()), arrays['nominal']):
        raise ValueError('Independent nominal reconciliation failed')
    if np.any(arrays['turnout'] > arrays['aptos']):
        raise ValueError('Independent turnout exceeds electorate')
    rounds = []
    for election, turn in sorted(scopes):
        ix = np.flatnonzero((arrays['election_code'] == election) & (arrays['turno'] == turn))
        # Lexical source-key ordering is explicitly reconstructed, independently of the primary cache.
        order = np.lexsort((arrays['section'][ix], arrays['zone'][ix], arrays['municipality'][ix], arrays['uf'][ix]))
        ix = ix[order]
        data = {field: values[ix] for field, values in arrays.items() if field not in {'election_code', 'turno'}}
        numbers = sorted(scopes[election, turn])
        data.update(election_code=int(election), turno=int(turn), candidate_numbers=numbers,
                    candidate_votes=np.column_stack([candidate_votes[number][ix] for number in numbers]))
        rounds.append(data)
    return rounds, dict(statistics)


def parser_fingerprint():
    names = (integer, yes_no, raw_rows, source_key, read_sources)
    body = '\n'.join(inspect.getsource(function) for function in names)
    return hashlib.sha256(body.encode()).hexdigest()


def independent_data(root, cache):
    sources = source_snapshot(root)
    cache = Path(cache)
    metadata_path = cache / 'metadata.json'
    arrays_path = cache / 'arrays.npz'
    fingerprint = hashlib.sha256(json.dumps(dict(sources=sources, parser=parser_fingerprint()), sort_keys=True).encode()).hexdigest()
    if cache.exists() and any(cache.iterdir()):
        if not metadata_path.is_file() or not arrays_path.is_file():
            raise ValueError('Unknown independent cache; choose a new path')
        metadata = json.loads(metadata_path.read_text())
        if metadata.get('status') != 'completed' or metadata.get('fingerprint') != fingerprint or metadata.get('arrays_sha256') != digest_file(arrays_path):
            raise ValueError('Independent cache fingerprint/integrity mismatch; choose a new path')
        with np.load(arrays_path, allow_pickle=False) as archive:
            rounds = []
            for index, description in enumerate(metadata['rounds']):
                round_data = {field: archive[f'r{index}_{field}'] for field in description['fields']}
                round_data.update({field: description[field] for field in ('election_code', 'turno', 'candidate_numbers')})
                rounds.append(round_data)
        return rounds, metadata
    cache.mkdir(parents=True, exist_ok=True)
    rounds, statistics = read_sources(root)
    for name, source in sources.items():
        if digest_file(root / source['path']) != source['sha256']:
            raise ValueError('Original source changed during independent scan')
    packed = {}
    descriptions = []
    for index, data in enumerate(rounds):
        fields = sorted(field for field, value in data.items() if isinstance(value, np.ndarray))
        for field in fields:
            packed[f'r{index}_{field}'] = data[field]
        descriptions.append(dict(election_code=data['election_code'], turno=data['turno'], candidate_numbers=data['candidate_numbers'], fields=fields))
    np.savez_compressed(arrays_path, **packed)
    metadata = dict(status='completed', completed_at_utc=datetime.now(timezone.utc).isoformat(), source_inputs=sources,
                    source_counts=statistics, fingerprint=fingerprint, parser_sha256=parser_fingerprint(),
                    arrays_sha256=digest_file(arrays_path), rounds=descriptions)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    return rounds, metadata


def physical_key(data, index):
    return tuple(str(data['uf'][index]) if field == 'uf' else int(data[field][index])
                 for field in ('uf', 'municipality', 'zone', 'section'))


def pair_reference(rounds, min_finalists=50, unchanged_electorate=False, domestic_only=False):
    """Own dictionary join and exclusive exclusions, independent of primary code."""
    by_turn = {int(data['turno']): data for data in rounds}
    if len(rounds) != 2 or set(by_turn) != {1, 2}:
        raise ValueError('H7 requires one presidential election per round')
    first, second = by_turn[1], by_turn[2]
    if set(second['candidate_numbers']) != {13, 22}:
        raise ValueError('Second-round nominal votes must exhaust the finalists')
    lookup = []
    for data in (first, second):
        current = {}
        for i in range(len(data['aptos'])):
            key = physical_key(data, i)
            if key in current:
                raise ValueError('Duplicate physical section key')
            current[key] = i
        lookup.append(current)
    keys = sorted(set(lookup[0]) & set(lookup[1]))
    indices = [np.array([mapping[key] for key in keys], dtype=np.int64) for mapping in lookup]
    result = dict(keys=keys, first=first, second=second, first_indices=indices[0], second_indices=indices[1],
                  only_first=sorted(set(lookup[0])-set(lookup[1])), only_second=sorted(set(lookup[1])-set(lookup[0])))
    for turn, data, ids in ((1, first, indices[0]), (2, second, indices[1])):
        if not {13, 22} <= set(data['candidate_numbers']):
            raise ValueError('Missing finalist in one round')
        for field in ('place', 'source_line', 'installed', 'cancelled', *QUANTITIES):
            result[f'{field}_{turn}'] = data[field][ids]
        for candidate in (13, 22):
            result[f'v{candidate}_{turn}'] = data['candidate_votes'][ids, data['candidate_numbers'].index(candidate)]
        result[f'f_{turn}'] = result[f'v13_{turn}'] + result[f'v22_{turn}']
        result[f'other_{turn}'] = result[f'nominal_{turn}'] - result[f'f_{turn}']
    reasons = np.full(len(keys), 'eligible', dtype='U32')
    tests = [
        ('section_status', ~result['installed_1'] | result['cancelled_1'] | ~result['installed_2'] | result['cancelled_2']),
        ('aptos_below_50', (result['aptos_1'] < 50) | (result['aptos_2'] < 50)),
        ('nonpositive_turnout', (result['turnout_1'] <= 0) | (result['turnout_2'] <= 0)),
        ('nominal_below_50', (result['nominal_1'] < 50) | (result['nominal_2'] < 50)),
        ('finalists_below_floor', result['f_1'] < min_finalists),
        ('missing_place', (result['place_1'] < 0) | (result['place_2'] < 0)),
        ('changed_place', result['place_1'] != result['place_2']),
        ('aptos_ratio', 4*np.maximum(result['aptos_1'], result['aptos_2']) > 5*np.minimum(result['aptos_1'], result['aptos_2'])),
    ]
    if unchanged_electorate:
        tests.append(('changed_aptos', result['aptos_1'] != result['aptos_2']))
    if domestic_only:
        tests.append(('exterior', np.array([key[0] == 'ZZ' for key in keys])))
    for name, excluded in tests:
        reasons[(reasons == 'eligible') & excluded] = name
    selected = np.flatnonzero(reasons == 'eligible')
    for turn in (1, 2):
        if np.any(result[f'aptos_{turn}'][selected] != result[f'turnout_{turn}'][selected] + result[f'abstentions_{turn}'][selected]):
            raise ValueError('Electorate identity fails in H7 cohort')
    result.update(reasons=reasons, selected=selected)
    return result


def sign(value):
    return (value > 0) - (value < 0)


def rate(numerator, denominator, scale=100):
    return scale * float(Fraction(int(numerator), int(denominator))) if denominator else None


def fraction_metrics(counts):
    """All municipal comparisons are derived using Python integers/Fraction."""
    v11, v12 = int(counts['v13_1']), int(counts['v13_2'])
    v21, v22 = int(counts['v22_1']), int(counts['v22_2'])
    n1, n2 = int(counts['nominal_1']), int(counts['nominal_2'])
    f1, f2 = v11 + v21, v12 + v22
    q1, q2 = Fraction(v11, f1) if f1 else None, Fraction(v12, f2) if f2 else None
    g13, g22 = v12-v11, v22-v21
    p13 = 100*(Fraction(v12,n2)-Fraction(v11,n1)) if n1 and n2 else None
    p22 = 100*(Fraction(v22,n2)-Fraction(v21,n1)) if n1 and n2 else None
    growth13 = 100*(Fraction(v12,v11)-1) if v11 else None
    growth22 = 100*(Fraction(v22,v21)-1) if v21 else None
    delta = 100*(q2-q1) if q1 is not None and q2 is not None else None
    result = dict(gain13_count=g13, gain22_count=g22, count_difference=g13-g22,
                  gain13_nominal_pp=p13, gain22_nominal_pp=p22,
                  nominal_difference_pp=p13-p22 if p13 is not None and p22 is not None else None,
                  growth13_pct=growth13,growth22_pct=growth22,
                  growth_difference_pct=growth13-growth22 if growth13 is not None and growth22 is not None else None,
                  q1=100*q1 if q1 is not None else None,q2=100*q2 if q2 is not None else None,
                  delta_q_pp=delta)
    result.update(count_sign=sign(result['count_difference']),
                  nominal_sign=sign(result['nominal_difference_pp']) if result['nominal_difference_pp'] is not None else None,
                  growth_sign=sign(result['growth_difference_pct']) if result['growth_difference_pct'] is not None else None,
                  conditional_sign=sign(delta) if delta is not None else None)
    if delta is not None and n1 and n2:
        if n2 != f2:
            raise ValueError('Round 2 finalists must exhaust nominal votes')
        if result['nominal_difference_pp'] != 100*(2*(q2-q1)+(1-Fraction(f1,n1))*(2*q1-1)):
            raise ArithmeticError('Nominal improvement identity fails')
        if result['count_difference'] != 2*f2*(q2-q1)+(f2-f1)*(2*q1-1):
            raise ArithmeticError('Count improvement identity fails')
    if result['growth_sign'] is not None and result['conditional_sign'] is not None and result['growth_sign'] != result['conditional_sign']:
        raise ArithmeticError('Growth/conditional directions disagree')
    return result


def section_delta(pair):
    """Compute each eligible section's conditional change independently."""
    if '_delta' not in pair:
        selected=pair['selected']
        pair['_delta']=np.array([100*float(Fraction(int(pair['v13_2'][i]),int(pair['f_2'][i]))-
                                          Fraction(int(pair['v13_1'][i]),int(pair['f_1'][i])))
                                 for i in selected],dtype=float)
    return pair['_delta']


def initial_band(numerator, denominator, bins=20):
    if bins < 1 or denominator <= 0 or numerator < 0 or numerator > denominator:
        raise ValueError('Valid proportion required')
    return min(bins-1,bins*int(numerator)//int(denominator))


def reference_prepare(pair, model, bins=20, min_target=5):
    """Independent dictionary construction of units, groups, fixed targets and edges."""
    if model not in MODELS or min_target < 1:
        raise ValueError('Unknown reference or target floor')
    selected=pair['selected']
    if not len(selected) or any(pair['keys'][int(i)][0]=='ZZ' for i in selected):
        raise ValueError('Formal reference requires a nonempty domestic cohort')
    member_lists=defaultdict(list)
    for position,i in enumerate(selected):
        physical=pair['keys'][int(i)]
        key=physical if model=='section' else physical[:3]+(int(pair['place_1'][i]),)
        member_lists[key].append(position)
    unit_keys=sorted(member_lists)
    delta=section_delta(pair)
    fields=[f'{field}_{turn}' for turn in (1,2) for field in COUNT_FIELDS]
    unit={field:np.empty(len(unit_keys),dtype=np.int64) for field in fields}
    unit.update(ns=np.empty(len(unit_keys),dtype=np.int64),delta_sum=np.empty(len(unit_keys)))
    unit_members=[]
    for u,key in enumerate(unit_keys):
        local=member_lists[key]; raw=selected[local]
        unit_members.append(local)
        unit['ns'][u]=len(local)
        unit['delta_sum'][u]=math.fsum(float(delta[j]) for j in local)
        for field in fields:
            unit[field][u]=sum(int(pair[field][i]) for i in raw)
    municipality_keys=sorted({key[:2] for key in unit_keys})
    mun_index={key:i for i,key in enumerate(municipality_keys)}
    unit['municipality_label']=np.array([mun_index[key[:2]] for key in unit_keys],dtype=np.int64)
    municipal_original={field:np.zeros(len(municipality_keys),dtype=np.int64) for field in fields+['ns']}
    for u,m in enumerate(unit['municipality_label']):
        for field in fields+['ns']:
            municipal_original[field][m]+=unit[field][u]
    targets=municipal_original['ns']>=min_target
    target_order=[];edges=[]
    for uf in sorted({key[0] for key in municipality_keys}):
        order=sorted((i for i,key in enumerate(municipality_keys) if key[0]==uf and targets[i]),
                     key=lambda i:(Fraction(int(municipal_original['v13_1'][i]),int(municipal_original['f_1'][i])),municipality_keys[i][1]))
        target_order.extend(order);edges.extend(zip(order[:-1],order[1:]))
    groups=defaultdict(list)
    for u,key in enumerate(unit_keys):
        a=int(unit['aptos_1'][u]);t=int(unit['turnout_1'][u]);f=int(unit['f_1'][u])
        gkey=(key[0],math.floor(math.log(a)/math.log(1.25)),
              initial_band(int(unit['turnout_1'][u]),a,bins),
              initial_band(int(unit['v13_1'][u]),f,bins),
              initial_band(int(unit['nominal_1'][u]-unit['f_1'][u]),t,bins))
        groups[gkey].append(u)
    groups=dict(sorted(groups.items()));labels=np.empty(len(unit_keys),dtype=np.int64)
    residual=np.empty(len(unit_keys));rows=[]
    for g,(key,members) in enumerate(groups.items()):
        labels[members]=g
        ns=sum(int(unit['ns'][u]) for u in members)
        mean=math.fsum(float(unit['delta_sum'][u]) for u in members)/ns
        residual[members]=unit['delta_sum'][members]-mean*unit['ns'][members]
        municipalities={int(unit['municipality_label'][u]) for u in members}
        movable=len(municipalities)>=2
        rows.append(dict(key=key,members=members,n_units=len(members),n_sections=ns,
                         municipalities=len(municipalities),movable=movable,mean_delta=mean,
                         target_units=sum(bool(targets[unit['municipality_label'][u]]) for u in members),
                         target_sections=sum(int(unit['ns'][u]) for u in members if targets[unit['municipality_label'][u]])))
    movable_groups=[row for row in rows if row['movable']]
    buckets=[np.array([row['members'] for row in movable_groups if row['n_units']==size],dtype=np.int32)
             for size in sorted({row['n_units'] for row in movable_groups})]
    return dict(pair=pair,model=model,bins=bins,min_target=min_target,unit=unit,unit_keys=unit_keys,
                unit_members=unit_members,municipality_keys=municipality_keys,municipal_original=municipal_original,
                targets=targets,target_order=target_order,edges=np.asarray(edges,dtype=np.int64).reshape(-1,2),
                groups=groups,group_rows=rows,labels=labels,residual=residual,buckets=buckets)


def independent_assignment(reference,seed,model_id,repetition):
    if model_id != MODELS.index(reference['model']):
        raise ValueError('Model ID disagrees')
    rng=np.random.default_rng(np.random.SeedSequence([seed,7,model_id],spawn_key=(repetition,)))
    result=np.arange(len(reference['unit_keys']),dtype=np.int32)
    for bucket in reference['buckets']:
        result[bucket.ravel()]=rng.permuted(bucket,axis=1).ravel()
    return result


def reference_aggregate(reference,assignment=None):
    unit=reference['unit'];n=len(unit['ns']);m=len(reference['municipality_keys'])
    if assignment is None:
        assignment=np.arange(n)
    fields=[f'{field}_{turn}' for turn in (1,2) for field in COUNT_FIELDS]
    labels=unit['municipality_label']
    # np.add.at preserves integer arithmetic for every municipal count.
    result={field:np.zeros(m,dtype=np.int64) for field in fields+['ns']}
    for field in result:
        np.add.at(result[field],labels,unit[field][assignment])
    residual_sum=[[] for _ in range(m)];delta_sum=[[] for _ in range(m)]
    for u,target in enumerate(labels):
        residual_sum[int(target)].append(float(reference['residual'][assignment[u]]))
        delta_sum[int(target)].append(float(unit['delta_sum'][assignment[u]]))
    result['residual_sum']=np.array([math.fsum(values) for values in residual_sum])
    result['delta_sum']=np.array([math.fsum(values) for values in delta_sum])
    result['residual_mean']=result['residual_sum']/result['ns']
    result['mean_section_delta']=result['delta_sum']/result['ns']
    return result


def reference_scores(reference,assignment=None,aggregated=None):
    aggregated=reference_aggregate(reference,assignment) if aggregated is None else aggregated
    targets=np.flatnonzero(reference['targets']);m=len(targets)
    if not m:
        return np.zeros(5)
    signs=[[],[],[]]
    for i in targets:
        row={field:int(values[i]) for field,values in aggregated.items() if field in {
            'v13_1','v13_2','v22_1','v22_2','nominal_1','nominal_2'}}
        metrics=fraction_metrics(row)
        for collection,key in zip(signs,('count_sign','nominal_sign','conditional_sign')):
            collection.append(metrics[key])
    prevalence=[max(values.count(1),values.count(-1))/m for values in signs]
    ns=aggregated['ns'];r=aggregated['residual_mean']
    rms=math.sqrt(math.fsum(float(ns[i])*float(r[i])**2 for i in targets)/sum(int(ns[i]) for i in targets))
    jump=max((abs(float(r[a])-float(r[b]))/math.sqrt(1/int(ns[a])+1/int(ns[b])) for a,b in reference['edges']),default=0.)
    return np.array([*prevalence,rms,jump])


def finite_assignments(reference):
    groups=[row['members'] for row in reference['group_rows'] if row['movable']]
    for draw in product(*(permutations(members) for members in groups)):
        result=np.arange(len(reference['unit_keys']),dtype=np.int32)
        for members,source in zip(groups,draw):
            result[members]=source
        yield result


def exact_score_squares(reference,assignment):
    """Exact prevalence, RMS squared and jump squared for small finite fixtures."""
    pair=reference['pair'];selected=pair['selected']
    exact_section=[100*(Fraction(int(pair['v13_2'][i]),int(pair['f_2'][i]))-
                        Fraction(int(pair['v13_1'][i]),int(pair['f_1'][i]))) for i in selected]
    sums=[sum((exact_section[j] for j in members),Fraction(0)) for members in reference['unit_members']]
    residual=[Fraction(0)]*len(sums)
    for row in reference['group_rows']:
        mean=sum((sums[u] for u in row['members']),Fraction(0))/row['n_sections']
        for u in row['members']:
            residual[u]=sums[u]-mean*int(reference['unit']['ns'][u])
    m=len(reference['municipality_keys']);count=[0]*m;rsum=[Fraction(0) for _ in range(m)]
    aggregates={field:[0]*m for field in ('v13_1','v13_2','v22_1','v22_2','nominal_1','nominal_2')}
    for target,donor in enumerate(assignment):
        municipal=int(reference['unit']['municipality_label'][target]);donor=int(donor)
        count[municipal]+=int(reference['unit']['ns'][donor]);rsum[municipal]+=residual[donor]
        for field in aggregates:
            aggregates[field][municipal]+=int(reference['unit'][field][donor])
    chosen=np.flatnonzero(reference['targets']);length=len(chosen)
    if not length:
        return (Fraction(0),)*5
    directions=[[],[],[]]
    for i in chosen:
        metrics=fraction_metrics({field:values[i] for field,values in aggregates.items()})
        for values,key in zip(directions,('count_sign','nominal_sign','conditional_sign')):
            values.append(metrics[key])
    prevalence=[Fraction(max(values.count(1),values.count(-1)),length) for values in directions]
    rms=sum((rsum[i]**2/count[i] for i in chosen),Fraction(0))/sum(count[i] for i in chosen)
    jumps=[(rsum[a]/count[a]-rsum[b]/count[b])**2/(Fraction(1,count[a])+Fraction(1,count[b]))
           for a,b in reference['edges']]
    return (*prevalence,rms,max(jumps,default=Fraction(0)))


def score_applicability(reference,simulated,observed,max_exact=40320):
    draws=np.asarray(simulated);observed=np.asarray(observed)
    varying=np.ptp(np.vstack([observed,draws]),axis=0)>1e-12
    reasons=['sampled_distinct_scores' if flag else '' for flag in varying]
    if not np.any(reference['targets']):
        return np.zeros(5,dtype=bool),['no_target_municipalities']*5
    if not len(reference['edges']):
        varying[4]=False;reasons[4]='no_adjacent_target_municipality_pairs'
    active=[]
    for row in reference['group_rows']:
        if row['movable'] and any(reference['targets'][reference['unit']['municipality_label'][u]] for u in row['members']):
            active.append(row['members'])
    unresolved=[i for i,flag in enumerate(varying) if not flag and not reasons[i]]
    if not unresolved:
        return varying,reasons
    if not active:
        for i in unresolved:reasons[i]='no_cross_target_municipality_mobility'
        return varying,reasons
    orbit=1
    for members in active:
        for factor in range(2,len(members)+1):
            orbit*=factor
            if orbit>max_exact:
                for i in unresolved:reasons[i]='unresolved_large_orbit'
                return varying,reasons
    if len(reference['pair']['selected'])>5000:
        for i in unresolved:reasons[i]='unresolved_exact_backdrop_too_large'
        return varying,reasons
    distinct=[set() for _ in range(5)]
    for draw in product(*(permutations(members) for members in active)):
        assigned=np.arange(len(reference['unit_keys']),dtype=np.int32)
        for members,sources in zip(active,draw):assigned[members]=sources
        exact=exact_score_squares(reference,assigned)
        for i in unresolved:distinct[i].add(exact[i])
        if all(len(distinct[i])>1 for i in unresolved):break
    for i in unresolved:
        varying[i]=len(distinct[i])>1
        reasons[i]='exact_enumeration_variable' if varying[i] else 'exact_enumeration_constant'
    return varying,reasons


def holm_reference(values):
    order=sorted(values,key=lambda key:(values[key],key));result={};running=0.
    for rank,key in enumerate(order):
        running=max(running,(len(order)-rank)*values[key]);result[key]=min(1.,running)
    return result


class Comparisons:
    def __init__(self):
        self.counts=Counter();self.failures=[];self.maximum_error=0.

    def require(self, condition, category, description):
        self.counts[category]+=1
        if not condition:
            self.counts['mismatches']+=1
            if len(self.failures)<100:
                self.failures.append(dict(category=category,description=description))

    def same(self, actual, expected, category, description, tolerance=1e-9):
        if expected is None or isinstance(expected,(float,np.floating)) and not math.isfinite(expected):
            okay=actual in ('',None)
        elif isinstance(expected,(bool,np.bool_)):
            okay=str(actual)==str(bool(expected))
        elif isinstance(expected,(int,np.integer)):
            okay=str(actual)==str(int(expected))
        elif isinstance(expected,(float,np.floating)):
            try:
                error=abs(float(actual)-float(expected))
                self.maximum_error=max(self.maximum_error,error)
                okay=math.isfinite(float(actual)) and error<=tolerance
            except (TypeError,ValueError):
                okay=False
        else:
            okay=actual==expected
        self.require(okay,category,f'{description}: actual={actual!r}, expected={expected!r}')


def read_table(path):
    opener=gzip.open if Path(path).suffix=='.gz' else open
    with opener(path,'rt',encoding='utf-8',newline='') as stream:
        reader=csv.DictReader(stream)
        if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)):
            raise ValueError('Invalid publication header')
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('Malformed published CSV row')
            yield row


def compare_table(path, rows, identity_fields, audit, category, allow_extra=False):
    expected={}
    for row in rows:
        key=tuple(str(row[field]) for field in identity_fields)
        if key in expected:
            raise ValueError(f'Duplicate independently reconstructed row {key}')
        expected[key]=row
    found=set()
    for actual in read_table(path):
        key=tuple(actual[field] for field in identity_fields)
        audit.require(key in expected and key not in found,category,f'Unexpected/duplicate identity {key}')
        if key not in expected or key in found:
            continue
        found.add(key);target=expected[key]
        if not allow_extra:
            audit.require(set(actual)==set(target),category,f'Columns differ for {key}')
        for field,value in target.items():
            audit.same(actual.get(field),value,category,f'{key}/{field}')
    audit.require(found==set(expected),category,f'Missing {len(set(expected)-found)} reconstructed rows')


def compare_ordered_table(path, rows, audit, category):
    """Streaming large-table check: exact order, schema and every cell."""
    from itertools import zip_longest
    absent = object()
    for number, (actual, expected) in enumerate(zip_longest(read_table(path),rows,fillvalue=absent),1):
        if actual is absent or expected is absent:
            audit.require(False,category,f'Row-count mismatch at row {number}')
            continue
        audit.require(set(actual)==set(expected),category,f'Columns differ at row {number}')
        for field,value in expected.items():
            tolerance = 2e-7 if field.startswith('sum_') and 'equiv_votes' in field else 1e-9
            audit.same(actual.get(field),value,category,f'row {number}/{field}',tolerance)


REGIONS={
    **dict.fromkeys(('AC','AP','AM','PA','RO','RR','TO'),'Norte'),
    **dict.fromkeys(('AL','BA','CE','MA','PB','PE','PI','RN','SE'),'Nordeste'),
    **dict.fromkeys(('DF','GO','MT','MS'),'Centro-Oeste'),
    **dict.fromkeys(('ES','MG','RJ','SP'),'Sudeste'),
    **dict.fromkeys(('PR','RS','SC'),'Sul'),'ZZ':'Exterior',
}


def scopes(ufs):
    values=np.asarray(ufs);domestic=values!='ZZ'
    yield 'BR','BR',domestic
    for uf in sorted(set(values.tolist())):yield 'UF',str(uf),values==uf
    regions=np.array([REGIONS[str(uf)] for uf in values])
    for region in sorted(set(regions[domestic].tolist())):
        yield 'region',region,regions==region
    if np.any(~domestic):yield 'exterior','Exterior',~domestic


def source_names(root,cache,source_inputs):
    signature=hashlib.sha256(json.dumps(dict(sources=source_inputs,
        code=inspect.getsource(source_names)),sort_keys=True).encode()).hexdigest()
    path=Path(cache)/'names.json'
    if path.exists():
        data=json.loads(path.read_text())
        if data['fingerprint']!=signature:
            raise ValueError('Independent names cache differs; choose new cache')
        payload=json.dumps(data['names'],ensure_ascii=False,sort_keys=True).encode()
        if hashlib.sha256(payload).hexdigest()!=data['names_sha256']:
            raise ValueError('Independent source-name cache corrupted')
        return data['names']['municipalities'],data['names']['candidates']
    municipalities={};candidates={}
    for _,row,c in raw_rows(root/SOURCE_PATHS['details']):
        if integer(row[c['ANO_ELEICAO']])!=2026 or integer(row[c['CD_CARGO']])!=1:continue
        key=f"{row[c['SG_UF']].strip().upper()}:{integer(row[c['CD_MUNICIPIO']])}"
        value=row[c['NM_MUNICIPIO']].strip() if 'NM_MUNICIPIO' in c else ''
        municipalities[key]=min(value,municipalities.get(key,value))
    for _,row,c in raw_rows(root/SOURCE_PATHS['votes']):
        if integer(row[c['ANO_ELEICAO']])!=2026 or integer(row[c['CD_CARGO']])!=1:continue
        candidate=integer(row[c['NR_VOTAVEL']])
        if candidate in (95,96,97):continue
        key=f"{integer(row[c['NR_TURNO']])}:{candidate}"
        value=row[c['NM_VOTAVEL']].strip() if 'NM_VOTAVEL' in c else ''
        candidates[key]=min(value,candidates.get(key,value))
    names=dict(municipalities=municipalities,candidates=candidates)
    payload=json.dumps(names,ensure_ascii=False,sort_keys=True).encode()
    path.write_text(json.dumps(dict(fingerprint=signature,names_sha256=hashlib.sha256(payload).hexdigest(),names=names),
                              ensure_ascii=False,indent=2)+'\n')
    return municipalities,candidates


def metric_values(counts,present=True,present1=None,present2=None):
    m=fraction_metrics(counts)
    result=dict(gain13=m['gain13_count'],gain22=m['gain22_count'],count_advantage=m['count_difference'],
                nominal_gain13=m['gain13_nominal_pp'],nominal_gain22=m['gain22_nominal_pp'],nominal_advantage=m['nominal_difference_pp'],
                relative_gain13=m['growth13_pct'],relative_gain22=m['growth22_pct'],relative_advantage=m['growth_difference_pct'],
                q1=m['q1'],q2=m['q2'],delta=m['delta_q_pp'])
    for metric,key,value in [('count','count_sign',m['count_difference']),('nominal','nominal_sign',m['nominal_difference_pp']),
                             ('relative','growth_sign',m['growth_difference_pct']),('conditional','conditional_sign',m['delta_q_pp'])]:
        defined=present and value is not None
        result[f'defined_{metric}']=defined
        result[f'sign_{metric}']=m[key] if defined else None
        if metric!='count':
            unscaled=value/100 if defined else None
            result[f'{metric}_num']=unscaled.numerator if unscaled is not None else None
            result[f'{metric}_den']=unscaled.denominator if unscaled is not None else None
    if not present:
        for field in ('gain13','gain22','count_advantage','nominal_gain13','nominal_gain22','nominal_advantage',
                      'relative_gain13','relative_gain22','relative_advantage','delta'):
            result[field]=None
        result['q1']=m['q1'] if present1 else None
        result['q2']=m['q2'] if present2 else None
    for field,value in list(result.items()):
        if isinstance(value,Fraction):result[field]=float(value)
    return result


def census_reference(rounds,pair,names):
    """Build raw and same-cohort municipal counts independently using dictionaries."""
    keys=sorted({(str(rd['uf'][i]),int(rd['municipality'][i])) for rd in rounds for i in range(len(rd['uf']))})
    raw={key:{f'{field}_{turn}':0 for turn in (1,2) for field in COUNT_FIELDS} for key in keys}
    cohort={key:{f'{field}_{turn}':0 for turn in (1,2) for field in COUNT_FIELDS} for key in keys}
    for record in (raw,cohort):
        for row in record.values():row.update(sections_1=0,sections_2=0)
    for rd in rounds:
        turn=int(rd['turno']);votes={c:rd['candidate_votes'][:,rd['candidate_numbers'].index(c)] for c in (13,22)}
        for i in range(len(rd['uf'])):
            row=raw[str(rd['uf'][i]),int(rd['municipality'][i])];row[f'sections_{turn}']+=1
            for field in COUNT_FIELDS:
                row[f'{field}_{turn}']+=int(votes[int(field[1:])][i]) if field in ('v13','v22') else \
                    int(votes[13][i])+int(votes[22][i]) if field=='f' else int(rd[field][i])
    for i in pair['selected']:
        key=pair['keys'][int(i)][:2];row=cohort[key]
        for turn in (1,2):
            row[f'sections_{turn}']+=1
            for field in COUNT_FIELDS:row[f'{field}_{turn}']+=int(pair[f'{field}_{turn}'][i])
    result={}
    for universe,source in (('raw',raw),('cohort',cohort)):
        rows=[]
        for key in keys:
            counts=source[key];present=counts['sections_1']>0 and counts['sections_2']>0
            row=dict(universe=universe,uf=key[0],municipality=key[1],municipality_name=names.get(f'{key[0]}:{key[1]}',''),
                     region=REGIONS[key[0]],domestic=key[0]!='ZZ',present_1=counts['sections_1']>0,present_2=counts['sections_2']>0,
                     **counts,other_nominal_1=counts['nominal_1']-counts['f_1'],other_nominal_2=counts['nominal_2']-counts['f_2'])
            for turn in (1,2):
                row[f'raw_sections_{turn}']=raw[key][f'sections_{turn}'];row[f'cohort_sections_{turn}']=cohort[key][f'sections_{turn}']
                row[f'cohort_section_coverage_{turn}']=rate(cohort[key][f'sections_{turn}'],raw[key][f'sections_{turn}'],1)
                row[f'cohort_nominal_coverage_{turn}']=rate(cohort[key][f'nominal_{turn}'],raw[key][f'nominal_{turn}'],1)
                row[f'aptos_identity_residual_{turn}']=counts[f'aptos_{turn}']-counts[f'turnout_{turn}']-counts[f'abstentions_{turn}']
            row.update(metric_values(counts,present,counts['sections_1']>0,counts['sections_2']>0))
            if present and counts['nominal_1'] and counts['nominal_2'] and counts['f_1'] and counts['f_2']:
                q1=Fraction(counts['v13_1'],counts['f_1']);q2=Fraction(counts['v13_2'],counts['f_2'])
                row.update(nominal_shift_term_pp=float(200*(q2-q1)),
                           nominal_exit_term_pp=float(100*(1-Fraction(counts['f_1'],counts['nominal_1']))*(2*q1-1)),
                           nominal_identity_residual=0.,count_shift_term=float(2*counts['f_2']*(q2-q1)),
                           count_exposure_term=float((counts['f_2']-counts['f_1'])*(2*q1-1)),count_identity_residual=0.)
            else:
                row.update({field:None for field in ('nominal_shift_term_pp','nominal_exit_term_pp','nominal_identity_residual',
                                                     'count_shift_term','count_exposure_term','count_identity_residual')})
            rows.append(row)
        result[universe]=rows
    return result


def pairing_rows(pair):
    first,second=pair['first'],pair['second']
    for uf in ['BR',*sorted(set(first['uf'].tolist())|set(second['uf'].tolist()))]:
        count=lambda keys:len(keys) if uf=='BR' else sum(key[0]==uf for key in keys)
        yield dict(uf=uf,round1_records=len(first['uf']) if uf=='BR' else int(np.count_nonzero(first['uf']==uf)),
                   round2_records=len(second['uf']) if uf=='BR' else int(np.count_nonzero(second['uf']==uf)),
                   matched_pairs=count(pair['keys']),only_round1=count(pair['only_first']),only_round2=count(pair['only_second']))


def eligibility_rows(pair):
    reasons=pair['reasons'];ufs=np.array([key[0] for key in pair['keys']]);eligible=reasons=='eligible'
    ordered=('section_status','aptos_below_50','nonpositive_turnout','nominal_below_50','finalists_below_floor',
             'missing_place','changed_place','aptos_ratio')
    basic=~np.isin(reasons,ordered[:4])
    for uf in ['BR',*sorted(set(ufs.tolist()))]:
        use=np.ones(len(ufs),dtype=bool) if uf=='BR' else ufs==uf
        row=dict(uf=uf,matched_pairs=int(use.sum()),basic_eligible=int((use&basic).sum()),cohort_pairs=int((use&eligible).sum()),
                 domestic_cohort_pairs=int((use&eligible&(ufs!='ZZ')).sum()))
        row.update({f'excluded_{reason}':int((use&(reasons==reason)).sum()) for reason in ordered})
        row['changed_aptos_cohort']=int((use&eligible&(pair['aptos_1']!=pair['aptos_2'])).sum())
        yield row


def unmatched_rows(pair):
    for turn,rd,keys in ((1,pair['first'],pair['only_first']),(2,pair['second'],pair['only_second'])):
        line={physical_key(rd,i):int(rd['source_line'][i]) for i in range(len(rd['uf']))}
        for key in keys:
            yield dict(present_in_round=turn,uf=key[0],municipality=key[1],zone=key[2],section=key[3],source_line=line[key])


def candidate_rows(rounds,pair,census,names):
    keys=[(row['uf'],row['municipality']) for row in census['raw']]
    for universe in ('raw','cohort'):
        accumulated=Counter()
        for rd in rounds:
            turn=int(rd['turno'])
            indices=range(len(rd['uf'])) if universe=='raw' else pair['first_indices' if turn==1 else 'second_indices'][pair['selected']]
            for i in indices:
                key=str(rd['uf'][i]),int(rd['municipality'][i])
                for col,candidate in enumerate(rd['candidate_numbers']):
                    accumulated[key,turn,candidate]+=int(rd['candidate_votes'][i,col])
        by_key={(row['uf'],row['municipality']):row for row in census[universe]}
        for key in keys:
            for rd in rounds:
                turn=int(rd['turno'])
                for candidate in rd['candidate_numbers']:
                    yield dict(universe=universe,uf=key[0],municipality=key[1],turno=turn,candidate=candidate,
                               candidate_name=names.get(f'{turn}:{candidate}',''),votes=accumulated[key,turn,candidate],
                               present=by_key[key][f'present_{turn}'])


def direction_rows(census):
    for universe in ('raw','cohort'):
        all_rows=census[universe];ufs=[row['uf'] for row in all_rows]
        for scope_type,scope,use in scopes(ufs):
            rows=[row for row,take in zip(all_rows,use) if take]
            for metric in ('count','nominal','relative','conditional'):
                valid=[row for row in rows if row[f'defined_{metric}']]
                positive=[row for row in valid if row[f'sign_{metric}']==1];negative=[row for row in valid if row[f'sign_{metric}']==-1]
                m=len(rows);n=len(valid);a=len(positive);b=len(negative)
                weight=sum(row['nominal_2'] for row in valid);wa=sum(row['nominal_2'] for row in positive);wb=sum(row['nominal_2'] for row in negative)
                yield dict(universe=universe,scope_type=scope_type,scope=scope,metric=metric,units=m,defined_units=n,undefined_units=m-n,
                           advantage13=a,advantage22=b,ties=n-a-b,fraction13_all=a/m if m else None,fraction22_all=b/m if m else None,
                           fraction13_defined=a/n if n else None,fraction22_defined=b/n if n else None,
                           reaches99_13_all=(100*a>=99*m) if m else None,reaches99_22_all=(100*b>=99*m) if m else None,
                           reaches99_13_defined=(100*a>=99*n) if n else None,reaches99_22_defined=(100*b>=99*n) if n else None,
                           nominal2_weight_defined=weight,nominal2_weight_13=wa,nominal2_weight_22=wb,
                           fraction13_vote_weighted_defined=wa/weight if weight else None,fraction22_vote_weighted_defined=wb/weight if weight else None)


def section_rows(pair,names):
    for i in pair['selected']:
        uf,mun,zone,section=pair['keys'][int(i)]
        exact=Fraction(int(pair['v13_2'][i]),int(pair['f_2'][i]))-Fraction(int(pair['v13_1'][i]),int(pair['f_1'][i]))
        yield dict(uf=uf,municipality=mun,municipality_name=names.get(f'{uf}:{mun}',''),zone=zone,section=section,
                   place=int(pair['place_1'][i]),source_line_1=int(pair['source_line_1'][i]),source_line_2=int(pair['source_line_2'][i]),domestic=uf!='ZZ',
                   **{f'{field}_{turn}':int(pair[f'{field}_{turn}'][i]) for turn in (1,2) for field in COUNT_FIELDS},
                   q1=100*float(Fraction(int(pair['v13_1'][i]),int(pair['f_1'][i]))),
                   q2=100*float(Fraction(int(pair['v13_2'][i]),int(pair['f_2'][i]))),delta=100*float(exact),
                   delta_numerator=exact.numerator,delta_denominator=exact.denominator)


def unit_rows(ref):
    for u,key in enumerate(ref['unit_keys']):
        g=int(ref['labels'][u]);group=ref['group_rows'][g];gkey=group['key'];unit=ref['unit']
        first=ref['pair']['selected'][ref['unit_members'][u][0]]
        yield dict(model=ref['model'],unit=u,uf=key[0],municipality=key[1],zone=key[2],
                   place=int(ref['pair']['place_1'][first]) if ref['model']=='section' else key[3],
                   section=key[3] if ref['model']=='section' else -1,ns=int(unit['ns'][u]),
                   **{f'{field}_{turn}':int(unit[f'{field}_{turn}'][u]) for turn in (1,2) for field in COUNT_FIELDS},
                   group=g,size_band=gkey[1],initial_turnout_bin=gkey[2],initial_preference_bin=gkey[3],initial_other_bin=gkey[4],
                   movable=group['movable'],target_destination=bool(ref['targets'][unit['municipality_label'][u]]),
                   delta_sum=float(unit['delta_sum'][u]),delta_mean=float(unit['delta_sum'][u]/unit['ns'][u]),
                   group_mean=group['mean_delta'],residual=float(ref['residual'][u]))


def group_rows(ref):
    for g,group in enumerate(ref['group_rows']):
        key=group['key']
        yield dict(model=ref['model'],group=g,uf=key[0],size_band=key[1],initial_turnout_bin=key[2],initial_preference_bin=key[3],initial_other_bin=key[4],
                   units=group['n_units'],sections=group['n_sections'],municipalities=group['municipalities'],
                   target_slots=group['target_units'],target_sections=group['target_sections'],movable=group['movable'],
                   target_reachable=bool(group['target_units']>0),mean_section_delta=group['mean_delta'])


def municipal_rows(ref,names):
    ag=reference_aggregate(ref);labels=ref['unit']['municipality_label'];moved_units=Counter();moved_sections=Counter();unit_count=Counter(labels)
    for group in ref['group_rows']:
        if group['movable']:
            for u in group['members']:
                m=int(labels[u]);moved_units[m]+=1;moved_sections[m]+=int(ref['unit']['ns'][u])
    for i,(uf,code) in enumerate(ref['municipality_keys']):
        counts={f'{field}_{turn}':int(ag[f'{field}_{turn}'][i]) for turn in (1,2) for field in COUNT_FIELDS}
        yield dict(model=ref['model'],uf=uf,municipality=code,municipality_name=names.get(f'{uf}:{code}',''),target=bool(ref['targets'][i]),
                   ns=int(ag['ns'][i]),units=unit_count[i],**counts,delta_sum=float(ag['delta_sum'][i]),delta_mean=float(ag['mean_section_delta'][i]),
                   residual_sum=float(ag['residual_sum'][i]),residual_mean=float(ag['residual_mean'][i]),**metric_values(counts),
                   movable_units=moved_units[i],movable_sections=moved_sections[i])


def edge_rows(ref,names):
    ag=reference_aggregate(ref);components=[]
    for a,b in ref['edges']:
        components.append(abs(float(ag['residual_mean'][a]-ag['residual_mean'][b]))/math.sqrt(1/int(ag['ns'][a])+1/int(ag['ns'][b])))
    maximum=max(components,default=0.)
    for (a,b),value in zip(ref['edges'],components):
        uf,lc=ref['municipality_keys'][a];_,rc=ref['municipality_keys'][b]
        ql=Fraction(int(ag['v13_1'][a]),int(ag['f_1'][a]));qr=Fraction(int(ag['v13_1'][b]),int(ag['f_1'][b]))
        yield dict(model=ref['model'],uf=uf,left_municipality=lc,right_municipality=rc,left_name=names.get(f'{uf}:{lc}',''),right_name=names.get(f'{uf}:{rc}',''),
                   original_q1_left=float(100*ql),original_q1_right=float(100*qr),original_q1_gap_pp=float(100*(qr-ql)),
                   left_sections=int(ag['ns'][a]),right_sections=int(ag['ns'][b]),left_residual_mean=float(ag['residual_mean'][a]),right_residual_mean=float(ag['residual_mean'][b]),
                   signed_contrast_pp=float(ag['residual_mean'][a]-ag['residual_mean'][b]),J_component=value,attains_max=abs(value-maximum)<=1e-12)


def coverage_rows(ref):
    units=ref['unit'];labels=units['municipality_label'];unit_ufs=[key[0] for key in ref['unit_keys']]
    for uf in ['BR',*sorted(set(unit_ufs))]:
        members=[u for u,key in enumerate(ref['unit_keys']) if uf=='BR' or key[0]==uf]
        groups=[row for row in ref['group_rows'] if uf=='BR' or row['key'][0]==uf]
        muns=[i for i,key in enumerate(ref['municipality_keys']) if uf=='BR' or key[0]==uf]
        movable={u for row in groups if row['movable'] for u in row['members']}
        target_movable={u for u in movable if ref['targets'][labels[u]]}
        yield dict(model=ref['model'],uf=uf,cohort_sections=sum(int(units['ns'][u]) for u in members),units=len(members),groups=len(groups),
                   municipalities=len(muns),targets=sum(bool(ref['targets'][i]) for i in muns),
                   target_sections=sum(int(ref['municipal_original']['ns'][i]) for i in muns if ref['targets'][i]),
                   movable_groups=sum(row['movable'] for row in groups),movable_units=len(movable),movable_sections=sum(int(units['ns'][u]) for u in movable),
                   target_reachable_groups=sum(row['movable'] and row['target_units']>0 for row in groups),
                   target_movable_units=len(target_movable),target_movable_sections=sum(int(units['ns'][u]) for u in target_movable),
                   reachable_targets=len({int(labels[u]) for u in target_movable}),
                   adjacent_pairs=sum(uf=='BR' or ref['municipality_keys'][a][0]==uf for a,b in ref['edges']))


def exact_metric(row,metric):
    if metric=='count_advantage':return Fraction(int(row[metric])) if row['defined_count'] else None
    kind={'nominal_advantage':'nominal','relative_advantage':'relative','delta':'conditional'}[metric]
    return 100*Fraction(row[f'{kind}_num'],row[f'{kind}_den']) if row[f'defined_{kind}'] else None


def distribution_rows(census,pair):
    quantile_fields=('min','q025','q25','median','q75','q975','max')
    for universe in ('raw','cohort'):
        all_rows=census[universe]
        for scope_type,scope,use in scopes([row['uf'] for row in all_rows]):
            rows=[row for row,take in zip(all_rows,use) if take]
            for metric in ('count_advantage','nominal_advantage','relative_advantage','delta'):
                exact=[value for row in rows if (value:=exact_metric(row,metric)) is not None]
                values=[float(value) for value in exact];n=len(values)
                quantiles=np.quantile(values,[0,.025,.25,.5,.75,.975,1]) if n else [None]*7
                yield dict(universe=universe,scope_type=scope_type,scope=scope,metric=metric,units=len(rows),defined_units=n,undefined_units=len(rows)-n,
                           **dict(zip(quantile_fields,quantiles)),mean=math.fsum(values)/n if n else None,exact_unique=len(set(exact)))
    selected=pair['selected'];delta=section_delta(pair);ufs=[pair['keys'][int(i)][0] for i in selected]
    exact=[Fraction(int(pair['v13_2'][i]),int(pair['f_2'][i]))-Fraction(int(pair['v13_1'][i]),int(pair['f_1'][i])) for i in selected]
    for scope_type,scope,use in scopes(ufs):
        chosen=np.flatnonzero(use);values=delta[chosen];n=len(chosen)
        quantiles=np.quantile(values,[0,.025,.25,.5,.75,.975,1]) if n else [None]*7
        yield dict(universe='sections',scope_type=scope_type,scope=scope,metric='delta',units=n,defined_units=n,undefined_units=0,
                   **dict(zip(quantile_fields,quantiles)),mean=math.fsum(map(float,values))/n if n else None,
                   exact_unique=len({exact[i] for i in chosen}))


def repetition_rows(census,pair):
    for universe in ('raw','cohort','sections'):
        for scope_type,scope,domestic in (('BR','BR',True),('exterior','Exterior',False)):
            for metric in (('delta',) if universe=='sections' else ('count_advantage','nominal_advantage','relative_advantage','delta')):
                if universe=='sections':
                    chosen=[i for i in pair['selected'] if (pair['keys'][int(i)][0]!='ZZ')==domestic]
                    values=[100*(Fraction(int(pair['v13_2'][i]),int(pair['f_2'][i]))-Fraction(int(pair['v13_1'][i]),int(pair['f_1'][i]))) for i in chosen]
                else:
                    values=[value for row in census[universe] if row['domestic']==domestic and (value:=exact_metric(row,metric)) is not None]
                frequency=Counter(values)
                for value,n in sorted(frequency.items(),key=lambda item:(-item[1],item[0].numerator,item[0].denominator)):
                    if n>=2:
                        yield dict(universe=universe,scope_type=scope_type,scope=scope,metric=metric,numerator=value.numerator,denominator=value.denominator,
                                   value=float(value),frequency=n,defined_units=len(values))


def sensitivity_rows(rounds,primary_pair):
    configs=[('primary',20,50,False,5),('baseline_2_5pp',40,50,False,5),('baseline_10pp',10,50,False,5),
             ('unchanged_aptos',20,50,True,5),('finalists_100',20,100,False,5),('targets_1',20,50,False,1),('targets_10',20,50,False,10)]
    for scenario,bins,floor,unchanged,target in configs:
        pair=primary_pair if floor==50 and not unchanged else pair_reference(rounds,floor,unchanged,domestic_only=True)
        for model in MODELS:
            ref=reference_prepare(pair,model,bins,target);values=reference_scores(ref)
            movable=[row for row in ref['group_rows'] if row['movable']]
            yield dict(scenario=scenario,model=model,bins=bins,finalist_floor=floor,unchanged_aptos=unchanged,min_target=target,
                       cohort_sections=len(pair['selected']),units=len(ref['unit_keys']),groups=len(ref['groups']),
                       movable_groups=len(movable),movable_units=sum(row['n_units'] for row in movable),
                       movable_sections=sum(row['n_sections'] for row in movable),municipalities=len(ref['municipality_keys']),
                       targets=int(ref['targets'].sum()),target_sections=int(ref['municipal_original']['ns'][ref['targets']].sum()),
                       adjacent_pairs=len(ref['edges']),**dict(zip(STAT_NAMES,map(float,values))))


def audit_provenance(root,analysis,manifest,metadata,audit):
    audit.same(manifest.get('status'),'completed','provenance','primary complete')
    audit.same(manifest.get('hypothesis'),'H7','provenance','hypothesis ID')
    audit.same(manifest.get('method_sha256'),METHOD_SHA256,'provenance','primary frozen method')
    audit.same(digest_file(HERE/'METHOD.pt-BR.md'),METHOD_SHA256,'provenance','current frozen method')
    for name,value in manifest.get('implementation_sha256',{}).items():
        audit.same(digest_file(HERE/'code'/name),value,'provenance',f'primary code {name}')
    for name,expected in metadata['source_inputs'].items():
        audit.require(manifest['source_inputs'].get(name)==expected,'provenance',f'original snapshot {name}')
    for independent_name,source_name,field in [('detail_rows_read','details','rows_read'),('detail_rows_selected','details','selected_rows'),
                                             ('vote_rows_read','votes','rows_read'),('vote_rows_selected','votes','selected_rows')]:
        audit.same(manifest['source_counts'][source_name][field],metadata['source_counts'][independent_name],
                   'provenance',f'source count {independent_name}')
    audit.same(manifest['parameters']['family_size'],10,'provenance','Holm family')
    for filename,entry in manifest['artifacts'].items():
        path=analysis/filename
        audit.same(path.stat().st_size,entry['size_bytes'],'artifact_integrity',f'{filename} bytes')
        audit.same(digest_file(path),entry['sha256'],'artifact_integrity',f'{filename} sha')


def audit_simulations(root,analysis,manifest,references,audit):
    tests=[];repetitions=[];arrays={};seed=manifest['parameters']['seed'];b=manifest['parameters']['simulations']
    paths={item['metadata']['model']:item for item in manifest['simulation_caches']}
    for model_id,model in enumerate(MODELS):
        ref=references[model];entry=paths[model];directory=Path(entry['path'])
        if not directory.is_absolute():directory=root/directory
        meta=json.loads((directory/'metadata.json').read_text())
        audit.same(digest_file(directory/'metadata.json'),entry['metadata_sha256'],'simulation_integrity',f'{model} metadata sha')
        audit.require(meta==entry['metadata'],'simulation_integrity',f'{model} metadata snapshot')
        audit.same(meta['status'],'completed','simulation_integrity',f'{model} completion')
        audit.same(meta['model_id'],model_id,'simulation_integrity',f'{model} ID')
        audit.same(meta['simulations'],b,'simulation_integrity',f'{model} count')
        audit.same(digest_file(directory/'scores.npy'),meta['scores_sha256'],'simulation_integrity',f'{model} score sha')
        simulated=np.load(directory/'scores.npy',allow_pickle=False)
        audit.require(simulated.shape==(b,5) and simulated.dtype==np.dtype('float64') and np.all(np.isfinite(simulated)) and np.all(simulated>=0),
                      'simulation_integrity',f'{model} shape/type/range')
        arrays[model]=simulated
        observed=reference_scores(ref);flags,reasons=score_applicability(ref,simulated,observed)
        for rep in (0,1):
            if rep>=b:continue
            assigned=independent_assignment(ref,seed,model_id,rep)
            assignment_hash=hashlib.sha256(assigned.astype('<i4').tobytes()).hexdigest()
            audit.same(assignment_hash,meta['assignment_prefix'][str(rep)],'repeated_assignments',f'{model}/{rep} assignment hash')
            regenerated=reference_scores(ref,assigned)
            for k,name in enumerate(STAT_NAMES):
                audit.same(float(simulated[rep,k]),float(regenerated[k]),'repeated_assignments',f'{model}/{rep}/{name}',1e-8)
            repetitions.append(dict(model=model,repetition=rep,assignment_sha256=assignment_hash,
                                    independently_recomputed_scores=[float(value) for value in regenerated]))
        for k,(name,tail) in enumerate(zip(STAT_NAMES,TAILS)):
            exceeded=int(np.count_nonzero(simulated[:,k]<=observed[k]+1e-12 if tail=='lower' else simulated[:,k]>=observed[k]-1e-12))
            tests.append(dict(model=model,statistic=name,tail=tail,observed=float(observed[k]),simulation_mean=math.fsum(map(float,simulated[:,k]))/b,
                              simulation_q025=float(np.quantile(simulated[:,k],.025)),simulation_q975=float(np.quantile(simulated[:,k],.975)),
                              exceedances=exceeded,simulations=b,p_raw=(1+exceeded)/(1+b) if flags[k] else None,
                              p_holm=None,detected=None,status='applicable' if flags[k] else 'not_applicable_unresolved' if reasons[k].startswith('unresolved') else 'not_applicable',
                              applicability_reason=reasons[k]))
    adjusted=holm_reference({(row['model'],row['statistic']):row['p_raw'] if row['status']=='applicable' else 1. for row in tests})
    for row in tests:
        if row['status']=='applicable':
            p=adjusted[row['model'],row['statistic']]
            row.update(p_holm=p,detected=bool(p<=.05),status='detected' if p<=.05 else 'not_detected')
    compare_ordered_table(analysis/'tests.csv',iter(tests),audit,'formal_tests')
    def public_scores():
        for model in MODELS:
            for rep,values in enumerate(arrays[model]):
                yield dict(model=model,repetition=rep,**dict(zip(STAT_NAMES,map(float,values))))
    compare_ordered_table(analysis/'permutation-scores.csv.gz',public_scores(),audit,'published_score_rows')
    # Decimal CSV produced by Python float repr must round-trip exactly.
    for row in read_table(analysis/'permutation-scores.csv.gz'):
        expected=arrays[row['model']][int(row['repetition'])]
        actual=np.array([float(row[name]) for name in STAT_NAMES],dtype=np.float64)
        audit.require(np.array_equal(actual.view(np.uint64),expected.view(np.uint64)),
                      'published_score_bitwise',f"{row['model']}/{row['repetition']} exact float64 round-trip")
    return tests,repetitions,sum(len(values) for values in arrays.values())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--analysis',type=Path,default=HERE/'evidence/analysis')
    parser.add_argument('--cache',type=Path,default=HERE/'.work/independent-source')
    parser.add_argument('--output',type=Path,default=HERE/'evidence/independent-validation.json')
    args=parser.parse_args()
    root,analysis,cache,output=(path.resolve() for path in (args.root,args.analysis,args.cache,args.output))
    if output.exists():parser.error('Refusing to overwrite independent-validation output; choose a new path')
    manifest=json.loads((analysis/'manifest.json').read_text())
    if manifest.get('status')!='completed':parser.error('Primary analysis must be completed before audit')
    started=datetime.now(timezone.utc).isoformat();script_sha=digest_file(Path(__file__))
    rounds,metadata=independent_data(root,cache);audit=Comparisons()
    audit_provenance(root,analysis,manifest,metadata,audit)
    print('Independent H7: reconstructing physical pairs and unit references',flush=True)
    pair=pair_reference(rounds)
    domestic=pair_reference(rounds,domestic_only=True)
    refs={model:reference_prepare(domestic,model) for model in MODELS}
    print('Independent H7: original municipality/candidate names',flush=True)
    names,candidate_names=source_names(root,cache,metadata['source_inputs'])
    census=census_reference(rounds,pair,names)
    table_specs=[
        ('pairing.csv',pairing_rows(pair),'pairing'),
        ('eligibility.csv',eligibility_rows(pair),'eligibility'),
        ('unmatched.csv',unmatched_rows(pair),'unmatched'),
        ('municipal-census.csv',(row for universe in ('raw','cohort') for row in census[universe]),'municipal_census'),
        ('candidate-totals.csv.gz',candidate_rows(rounds,pair,census,candidate_names),'all_candidate_totals'),
        ('gain-directions.csv',direction_rows(census),'gain_directions'),
        ('cohort-sections.csv.gz',section_rows(pair,names),'all_cohort_sections'),
        ('allocation-units.csv.gz',(row for ref in refs.values() for row in unit_rows(ref)),'all_allocation_units'),
        ('allocation-groups.csv.gz',(row for ref in refs.values() for row in group_rows(ref)),'all_allocation_groups'),
        ('municipality-results.csv',(row for ref in refs.values() for row in municipal_rows(ref,names)),'all_municipal_results'),
        ('adjacent-profiles.csv',(row for ref in refs.values() for row in edge_rows(ref,names)),'all_profile_pairs'),
        ('coverage.csv',(row for ref in refs.values() for row in coverage_rows(ref)),'coverage'),
        ('distribution.csv',distribution_rows(census,pair),'all_distributions'),
        ('exact-repetitions.csv.gz',repetition_rows(census,pair),'exact_repetition_inventories'),
    ]
    for filename,rows,category in table_specs:
        print(f'Independent H7: {filename}',flush=True)
        compare_ordered_table(analysis/filename,rows,audit,category)
    print('Independent H7: retained scores and four complete assignment repetitions',flush=True)
    tests,repetitions,score_rows=audit_simulations(root,analysis,manifest,refs,audit)
    print('Independent H7: all fourteen fixed sensitivity rows',flush=True)
    compare_ordered_table(analysis/'sensitivity.csv',sensitivity_rows(rounds,domestic),audit,'sensitivity')
    summary=json.loads((analysis/'summary.json').read_text())
    expected=dict(matched_pairs=len(pair['keys']),cohort_pairs=len(pair['selected']),domestic_cohort_pairs=len(domestic['selected']),
                  paired_elections=[int(pair['first']['election_code']),int(pair['second']['election_code'])],family_size=10,
                  primary_detected=sum(row['status']=='detected' for row in tests),primary_not_detected=sum(row['status']=='not_detected' for row in tests),
                  primary_not_applicable=sum(row['status'].startswith('not_applicable') for row in tests),
                  primary_unresolved=sum(row['status']=='not_applicable_unresolved' for row in tests),
                  domestic_municipalities=sum(row['domestic'] for row in census['raw']),overseas_source_units=sum(not row['domestic'] for row in census['raw']))
    for field,value in expected.items():audit.same(summary.get(field),value,'summary',field)
    expected_directions=[row for row in direction_rows(census) if row['scope_type']=='BR']
    audit.require(len(summary['domestic_direction_census'])==len(expected_directions),'summary','domestic direction row count')
    for actual,expected_row in zip(summary['domestic_direction_census'],expected_directions):
        audit.require(set(actual)==set(expected_row),'summary','domestic direction schema')
        for field,value in expected_row.items():audit.same(actual.get(field),value,'summary',field)
    for name,entry in metadata['source_inputs'].items():
        audit.same(digest_file(root/entry['path']),entry['sha256'],'provenance',f'{name} unchanged after independent validation')
    audit.same(digest_file(Path(__file__)),script_sha,'provenance','independent script unchanged during audit')
    result=dict(status='passed' if not audit.counts['mismatches'] else 'failed',hypothesis='H7',
                started_at_utc=started,completed_at_utc=datetime.now(timezone.utc).isoformat(),script_sha256=script_sha,
                method_sha256=digest_file(HERE/'METHOD.pt-BR.md'),primary_manifest_sha256=digest_file(analysis/'manifest.json'),
                source_inputs=metadata['source_inputs'],independent_parser_sha256=metadata['parser_sha256'],source_counts=metadata['source_counts'],
                independent_source_cache=dict(path=str(cache.relative_to(root)) if cache.is_relative_to(root) else str(cache),
                                              arrays_sha256=metadata['arrays_sha256'],fingerprint=metadata['fingerprint']),
                comparisons=sum(value for key,value in audit.counts.items() if key!='mismatches'),mismatches=int(audit.counts['mismatches']),
                checks_by_category=dict(audit.counts),maximum_absolute_numerical_difference=audit.maximum_error,failures=audit.failures,
                numerical_csv_files_checked=17,sensitivity_rows_recomputed=14,independently_regenerated_full_assignments=repetitions,
                retained_score_rows_audited=score_rows,
                limits='All original-source numerical CSVs are reconstructed. Realizations 0 and 1 per model are independently regenerated; remaining retained Monte Carlo scores are audited for bitwise publication, ranks, moments and multiplicity, not independently regenerated. Check counts are integrity comparisons, not independent statistical observations.')
    output.parent.mkdir(parents=True,exist_ok=True);temporary=output.with_suffix(output.suffix+'.tmp')
    if temporary.exists():parser.error('Temporary validation output exists; choose new output path')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temporary.replace(output)
    print(json.dumps({key:result[key] for key in ('status','comparisons','mismatches','maximum_absolute_numerical_difference')},ensure_ascii=False),flush=True)
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
