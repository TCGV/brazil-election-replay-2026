#!/usr/bin/env python3
"""Independent original-source reconstruction and validation for the H5 study.

No primary H5 parser, group builder, statistic, or simulation helper is imported.
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
MODELS = ('zone_size', 'zone_size_baseline')
STAT_NAMES = ('RMS', 'MAX')


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
            print(f'Independent H5 parser: {statistics["vote_rows_selected"]:,} vote rows', file=sys.stderr, flush=True)
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
    return (str(data['uf'][index]), int(data['municipality'][index]),
            int(data['zone'][index]), int(data['section'][index]))


def pair_reference(rounds, min_finalists=50, unchanged_electorate=False):
    """Match physical keys independently; never infer individual voter identity."""
    by_turn = {int(data['turno']): data for data in rounds}
    if set(by_turn) != {1, 2} or len(rounds) != 2:
        raise ValueError('H5 requires exactly one presidential election in each round')
    first, second = by_turn[1], by_turn[2]
    if set(second['candidate_numbers'])!={13,22}:
        raise ValueError('Round 2 nominal votes must be exhausted by the two finalists')
    lookups = []
    for data in (first, second):
        lookup = {}
        for i in range(len(data['aptos'])):
            key = physical_key(data, i)
            if key in lookup:
                raise ValueError('Duplicate physical key within round')
            lookup[key] = i
        lookups.append(lookup)
    keys = sorted(set(lookups[0]) & set(lookups[1]))
    i1 = np.array([lookups[0][key] for key in keys], dtype=np.int64)
    i2 = np.array([lookups[1][key] for key in keys], dtype=np.int64)
    if not len(keys):
        raise ValueError('No shared physical section keys')
    result = dict(keys=keys, first=first, second=second, first_indices=i1, second_indices=i2,
                  only_first=sorted(set(lookups[0])-set(lookups[1])),
                  only_second=sorted(set(lookups[1])-set(lookups[0])))
    for suffix, data, ids in (('1',first,i1),('2',second,i2)):
        if not {13,22} <= set(data['candidate_numbers']):
            raise ValueError('Both finalists are required in both rounds')
        for field in ('aptos','turnout','nominal','abstentions','place','source_line','installed','cancelled'):
            result[field+suffix] = data[field][ids]
        for number in (13,22):
            result[f'votes{number}_{suffix}'] = data['candidate_votes'][ids,data['candidate_numbers'].index(number)]
        result['finalists'+suffix] = result[f'votes13_{suffix}'] + result[f'votes22_{suffix}']
    reasons = np.full(len(keys),'eligible',dtype='U32')
    tests = [
        ('section_status',~result['installed1']|result['cancelled1']|~result['installed2']|result['cancelled2']),
        ('aptos_below_50',(result['aptos1']<50)|(result['aptos2']<50)),
        ('nonpositive_turnout',(result['turnout1']<=0)|(result['turnout2']<=0)),
        ('nominal_below_50',(result['nominal1']<50)|(result['nominal2']<50)),
        ('finalists_below_floor',result['finalists1']<min_finalists),
        ('missing_place',(result['place1']<0)|(result['place2']<0)),
        ('changed_place',result['place1']!=result['place2']),
        ('electorate_ratio',np.maximum(result['aptos1'],result['aptos2'])*4 > np.minimum(result['aptos1'],result['aptos2'])*5),
    ]
    if unchanged_electorate:
        tests.append(('changed_electorate',result['aptos1']!=result['aptos2']))
    for label, mask in tests:
        reasons[(reasons=='eligible') & mask] = label
    result.update(reasons=reasons,selected=np.flatnonzero(reasons=='eligible'))
    for suffix in ('1','2'):
        denominator=result['finalists'+suffix]
        result['q'+suffix]=np.divide(result['votes13_'+suffix],denominator,
            out=np.full(len(keys),np.nan),where=denominator>0)
    result['delta_numerator']=result['votes13_2']*result['finalists1']-result['votes13_1']*result['finalists2']
    result['delta_denominator']=result['finalists1']*result['finalists2']
    result['delta']=np.divide(100.*result['delta_numerator'],result['delta_denominator'],
        out=np.full(len(keys),np.nan),where=result['delta_denominator']>0)
    for candidate in (13,22):
        for suffix in ('1','2'):
            denominator=result['nominal'+suffix]
            result[f'p{candidate}_{suffix}']=np.divide(result[f'votes{candidate}_{suffix}'],denominator,
                out=np.full(len(keys),np.nan),where=denominator>0)
        result[f'delta_p{candidate}']=100*(result[f'p{candidate}_2']-result[f'p{candidate}_1'])
    return result


def initial_band(votes, finalists, bins=20):
    """Exact rational bin, including q=1 in the final closed endpoint."""
    return min(bins-1,bins*int(votes)//int(finalists))


def peer_reference(pair, baseline_bins=20, min_other=4):
    """Leave-one-out medians in two explicitly distinct descriptive contexts."""
    selected=pair['selected']
    strict=defaultdict(list); broad=defaultdict(list)
    for i in selected:
        key=pair['keys'][i][:3]+(int(pair['place1'][i]),math.floor(math.log(int(pair['aptos1'][i]))/math.log(1.25)))
        broad[key].append(int(i))
        strict[key+(initial_band(pair['votes13_1'][i],pair['finalists1'][i],baseline_bins),)].append(int(i))
    rows={}
    for label, groups in (('strict',strict),('broad',broad)):
        for members in groups.values():
            values=[float(pair['delta'][i]) for i in members]
            for offset,i in enumerate(members):
                others=values[:offset]+values[offset+1:]
                median=float(np.median(others)) if len(others)>=min_other else None
                difference=values[offset]-median if median is not None else None
                rows.setdefault(i,{})[label]=dict(other_count=len(others),median=median,
                    difference=difference,priority=None if difference is None else abs(difference)>=10-1e-12)
    return rows


def localization_reference(pair, model, baseline_bins=20, min_place=5):
    """Own Python key grouping; fixed place slots and whole paired changes."""
    if model not in MODELS:
        raise ValueError('Unknown H5 grouping reference')
    selected=pair['selected']; groups=defaultdict(list); places=defaultdict(list)
    for position, raw_index in enumerate(selected):
        i=int(raw_index); physical=pair['keys'][i]
        place=physical[:3]+(int(pair['place1'][i]),)
        places[place].append(position)
        key=physical[:3]+(math.floor(math.log(int(pair['aptos1'][i]))/math.log(1.25)),)
        if model=='zone_size_baseline':
            key+=(initial_band(pair['votes13_1'][i],pair['finalists1'][i],baseline_bins),)
        groups[key].append(position)
    groups=dict(sorted(groups.items()));places=dict(sorted(places.items()))
    delta=pair['delta'][selected]
    residual=np.zeros(len(selected))
    group_rows=[]
    for key,members in groups.items():
        mean=math.fsum(float(delta[i]) for i in members)/len(members)
        fractions={(Fraction(int(pair['votes13_2'][selected[i]]),int(pair['finalists2'][selected[i]]))-
                    Fraction(int(pair['votes13_1'][selected[i]]),int(pair['finalists1'][selected[i]]))) for i in members}
        residual[members]=delta[members]-mean if len(fractions)>1 else 0.
        place_keys={pair['keys'][int(selected[i])][:3]+(int(pair['place1'][selected[i]]),) for i in members}
        group_rows.append(dict(key=key,n=len(members),mean=mean,variable=len(fractions)>1,place_count=len(place_keys)))
    labels=np.empty(len(selected),dtype=np.int64)
    sizes=np.empty(len(places),dtype=np.int64)
    for number,members in enumerate(places.values()):
        labels[members]=number;sizes[number]=len(members)
    target=sizes>=min_place
    return dict(pair=pair,model=model,selected=selected,groups=groups,places=places,
                labels=labels,sizes=sizes,target=target,residual=residual,group_rows=group_rows,
                baseline_bins=baseline_bins,min_place=min_place)


def localization_scores(reference, residual=None):
    values=reference['residual'] if residual is None else np.asarray(residual)
    sums=np.bincount(reference['labels'],weights=values,minlength=len(reference['sizes']))
    target=reference['target']; sizes=reference['sizes']
    if not np.any(target):
        return np.zeros(2),sums
    rms=math.sqrt(math.fsum(float(x*x/n) for x,n in zip(sums[target],sizes[target]))/int(sizes[target].sum()))
    maximum=max(float(abs(x)/math.sqrt(int(n))) for x,n in zip(sums[target],sizes[target]))
    return np.array([rms,maximum]),sums


def independent_assignment(reference, seed, model_id, repetition):
    rng=np.random.default_rng(np.random.SeedSequence([seed,model_id],spawn_key=(repetition,)))
    groups=list(reference['groups'].values())
    result=np.arange(len(reference['selected']),dtype=np.int32)
    for size in sorted({len(members) for members in groups if len(members)>1}):
        bucket=np.asarray([members for members in groups if len(members)==size],dtype=np.int32)
        result[bucket.ravel()]=rng.permuted(bucket,axis=1).ravel()
    return result


def exact_localization(reference):
    """Exhaustive finite reference for small artificial examples only."""
    groups=list(reference['groups'].values())
    result=[]
    for draw in product(*(permutations(members) for members in groups)):
        assignment=np.arange(len(reference['selected']),dtype=np.int64)
        for destinations,sources in zip(groups,draw):
            assignment[destinations]=sources
        result.append(localization_scores(reference,reference['residual'][assignment])[0])
    return np.asarray(result)


def holm_reference(values):
    order=sorted(values,key=lambda key:(values[key],key))
    result={};running=0.
    for rank,key in enumerate(order):
        running=max(running,(len(order)-rank)*values[key])
        result[key]=min(1.,running)
    return result


def monte_carlo_p(observed, simulated, tolerance=1e-12):
    return (1+int(np.count_nonzero(np.asarray(simulated)>=observed-tolerance)))/(len(simulated)+1)


def score_applicability(reference, sampled, observed, max_exact=40320):
    """Independent proof of varying magnitudes; a constant sample is not proof."""
    if not np.any(reference['target']):
        return np.zeros(2,dtype=bool),['no_targets']*2
    potential=[]
    target=reference['target']; labels=reference['labels']
    for group,members in zip(reference['group_rows'],reference['groups'].values()):
        if group['variable'] and group['place_count']>=2 and np.any(target[labels[members]]):
            potential.append(members)
    if not potential:
        return np.zeros(2,dtype=bool),['no_movable_variable_groups']*2
    values=np.vstack([np.asarray(observed),np.asarray(sampled)])
    varying=np.ptp(values,axis=0)>1e-12
    reasons=['sampled_distinct_scores' if value else '' for value in varying]
    if np.all(varying):
        return varying,reasons
    orbit=1
    for members in potential:
        orbit*=math.factorial(len(members))
        if orbit>max_exact:
            raise ArithmeticError('Unresolved concentration variability without an exact manageable orbit')
    minimum=np.full(2,np.inf);maximum=np.full(2,-np.inf)
    for draw in product(*(permutations(members) for members in potential)):
        moved=reference['residual'].copy()
        for slots,sources in zip(potential,draw):
            moved[slots]=reference['residual'][list(sources)]
        scores,_=localization_scores(reference,moved)
        minimum=np.minimum(minimum,scores);maximum=np.maximum(maximum,scores)
        if np.all(varying|(maximum-minimum>1e-12)):
            break
    for j in np.flatnonzero(~varying):
        varying[j]=maximum[j]-minimum[j]>1e-12
        reasons[j]='exact_enumeration_variable' if varying[j] else 'exact_enumeration_constant'
    return varying,reasons


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
            if field.endswith('_json'):
                try:
                    audit.require(json.loads(actual.get(field,'null'))==json.loads(value),category,f'{key}/{field}')
                except (ValueError,TypeError):
                    audit.require(False,category,f'{key}/{field} malformed JSON')
            else:
                audit.same(actual.get(field),value,category,f'{key}/{field}')
    audit.require(found==set(expected),category,f'Missing {len(set(expected)-found)} reconstructed rows')


def municipality_names(root):
    names={}
    for _,row,columns in raw_rows(root/SOURCE_PATHS['details']):
        key=f"{row[columns['SG_UF']].strip().upper()}:{integer(row[columns['CD_MUNICIPIO']])}"
        name=row[columns['NM_MUNICIPIO']].strip() if 'NM_MUNICIPIO' in columns else ''
        names[key]=min(name,names.get(key,name))
    return names


def published_reason(reason):
    return {'electorate_ratio':'aptos_ratio','changed_electorate':'changed_aptos'}.get(str(reason),str(reason))


def pairing_rows(pair):
    first,second=pair['first'],pair['second']
    for uf in ['BR',*sorted(set(first['uf'].tolist())|set(second['uf'].tolist()))]:
        count=lambda data:len(data) if uf=='BR' else sum(str(value)==uf for value in data)
        yield dict(uf=uf,round1_records=count(first['uf']),round2_records=count(second['uf']),
            matched_pairs=sum(uf=='BR' or key[0]==uf for key in pair['keys']),
            only_round1=sum(uf=='BR' or key[0]==uf for key in pair['only_first']),
            only_round2=sum(uf=='BR' or key[0]==uf for key in pair['only_second']))


def eligibility_rows(pair):
    reasons=pair['reasons'];eligible=reasons=='eligible'
    labels=('section_status','aptos_below_50','nonpositive_turnout','nominal_below_50',
            'finalists_below_floor','missing_place','changed_place','electorate_ratio')
    basic=np.isin(reasons,['eligible','finalists_below_floor','missing_place','changed_place','electorate_ratio'])
    for uf in ['BR',*sorted({key[0] for key in pair['keys']})]:
        use=np.array([uf=='BR' or key[0]==uf for key in pair['keys']])
        chosen=use&eligible
        row=dict(uf=uf,matched_pairs=int(use.sum()),basic_eligible=int((use&basic).sum()),cohort_pairs=int(chosen.sum()))
        row.update({f'excluded_{published_reason(label)}':int((use&(reasons==label)).sum()) for label in labels})
        row.update(changed_aptos_cohort=int((chosen&(pair['aptos1']!=pair['aptos2'])).sum()),
            nominal_1=int(pair['nominal1'][chosen].sum()),nominal_2=int(pair['nominal2'][chosen].sum()))
        yield row


def raw_pair_rows(pair,names):
    fields={f'{field}_{suffix}':field+suffix for field in ('source_line','place','aptos','turnout','nominal') for suffix in ('1','2')}
    fields.update({f'v{candidate}_{suffix}':f'votes{candidate}_{suffix}' for candidate in (13,22) for suffix in ('1','2')})
    fields.update(f_1='finalists1',f_2='finalists2')
    for i,key in enumerate(pair['keys']):
        row=dict(zip(('uf','municipality','zone','section'),key))
        row.update({target:int(pair[source][i]) for target,source in fields.items()})
        row.update(municipality_name=names.get(f'{key[0]}:{key[1]}',''),other_nominal_1=int(pair['nominal1'][i]-pair['finalists1'][i]),
            q1=100*float(pair['q1'][i]),q2=100*float(pair['q2'][i]),delta_pp=float(pair['delta'][i]),
            dp13_pp=float(pair['delta_p13'][i]),dp22_pp=float(pair['delta_p22'][i]),
            gain_v13=int(pair['votes13_2'][i]-pair['votes13_1'][i]),gain_v22=int(pair['votes22_2'][i]-pair['votes22_1'][i]),
            eligible=bool(pair['reasons'][i]=='eligible'),exclusion_reason=published_reason(pair['reasons'][i]))
        yield row


def section_rows(pair,peers):
    for i in pair['selected']:
        key=pair['keys'][int(i)]
        row=dict(zip(('uf','municipality','zone','section'),key))
        row.update(place=int(pair['place1'][i]),q1=100*float(pair['q1'][i]),q2=100*float(pair['q2'][i]),
            delta_pp=float(pair['delta'][i]),dp13_pp=float(pair['delta_p13'][i]),dp22_pp=float(pair['delta_p22'][i]))
        for label in ('strict','broad'):
            context=peers[int(i)][label]
            row.update({f'{label}_peer_count':context['other_count'],f'{label}_median':context['median'],
                f'{label}_contrast':context['difference'],f'{label}_priority':bool(context['priority'])})
        strict=peers[int(i)]['strict']
        row['priority_candidate']=13 if strict['priority'] and strict['difference']>0 else 22 if strict['priority'] else ''
        yield row


def case_summary_rows(pair,peers):
    for uf in ['BR',*sorted({pair['keys'][int(i)][0] for i in pair['selected']})]:
        selected=[int(i) for i in pair['selected'] if uf=='BR' or pair['keys'][int(i)][0]==uf]
        row=dict(uf=uf,cohort_pairs=len(selected))
        for label in ('strict','broad'):
            contexts=[peers[i][label] for i in selected]
            row.update({f'{label}_supported':sum(c['median'] is not None for c in contexts),
                f'{label}_priorities':sum(bool(c['priority']) for c in contexts),
                f'{label}_priorities_13':sum(bool(c['priority']) and c['difference']>0 for c in contexts),
                f'{label}_priorities_22':sum(bool(c['priority']) and c['difference']<0 for c in contexts)})
        yield row


def metric_values(pair,peers):
    selected=pair['selected']
    return {'delta_pp':pair['delta'][selected],'dp13_pp':pair['delta_p13'][selected],
        'dp22_pp':pair['delta_p22'][selected],
        **{f'{label}_contrast':np.array([np.nan if peers[int(i)][label]['difference'] is None else peers[int(i)][label]['difference'] for i in selected])
           for label in ('strict','broad')}}


def distribution_rows(pair,peers):
    fields=metric_values(pair,peers)
    ufs=np.array([pair['keys'][int(i)][0] for i in pair['selected']])
    for uf in ['BR',*sorted(set(ufs.tolist()))]:
        use=np.ones(len(ufs),dtype=bool) if uf=='BR' else ufs==uf
        for metric,values in fields.items():
            chosen=values[use&np.isfinite(values)]
            quantiles=np.quantile(chosen,[0,.025,.25,.5,.75,.975,1]) if len(chosen) else [None]*7
            yield dict(uf=uf,metric=metric,n=len(chosen),
                **dict(zip(('min','q025','q25','median','q75','q975','max'),quantiles)),mean=float(chosen.mean()) if len(chosen) else None)


def histogram_rows(pair,peers):
    for metric,values in metric_values(pair,peers).items():
        values=values[np.isfinite(values)];limit=200 if 'contrast' in metric else 100
        counts,edges=np.histogram(values,bins=np.arange(-limit,limit+1))
        for left,right,count in zip(edges[:-1],edges[1:],counts):
            yield dict(metric=metric,left_pp=int(left),right_pp=int(right),sections=int(count),denominator=len(values))


def transition_rows(pair):
    counts=Counter()
    for i in pair['selected']:
        x=min(99,100*int(pair['votes13_1'][i])//int(pair['finalists1'][i]))
        y=min(99,100*int(pair['votes13_2'][i])//int(pair['finalists2'][i]))
        counts[x,y]+=1
    for x in range(100):
        for y in range(100):
            yield dict(q1_low_pp=x,q1_high_pp=x+1,q2_low_pp=y,q2_high_pp=y+1,sections=counts[x,y])


def group_rows(reference):
    for row,members in zip(reference['group_rows'],reference['groups'].values()):
        key=row['key']; slots=reference['labels'][members]
        target_slots=int(reference['target'][slots].sum())
        yield dict(model=reference['model'],uf=key[0],municipality=key[1],zone=key[2],size_band=key[3],
            baseline_bin=key[4] if reference['model']=='zone_size_baseline' else -1,n=row['n'],places=row['place_count'],
            target_slots=target_slots,delta_mean=row['mean'],
            delta_min=float(reference['pair']['delta'][reference['selected'][members]].min()),
            delta_max=float(reference['pair']['delta'][reference['selected'][members]].max()),variable_delta=row['variable'],
            potential=row['variable'] and row['place_count']>=2 and target_slots>0)


def place_rows(reference,peers):
    pair=reference['pair'];_,sums=localization_scores(reference)
    for number,(key,members) in enumerate(reference['places'].items()):
        ids=reference['selected'][members];n=len(members);s=float(sums[number])
        total=math.fsum(float(pair['delta'][i]) for i in ids)
        contexts=[peers[int(i)]['strict'] for i in ids]
        yield dict(model=reference['model'],uf=key[0],municipality=key[1],zone=key[2],place=key[3],n=n,
            target=bool(reference['target'][number]),delta_mean=total/n,expected_delta_mean=(total-s)/n,
            residual_sum=s,residual_mean=s/n,rms_component=s*s/n,max_component=abs(s)/math.sqrt(n),
            strict_supported=sum(c['median'] is not None for c in contexts),strict_priorities=sum(bool(c['priority']) for c in contexts),
            aptos_1_total=int(pair['aptos1'][ids].sum()),nominal_1_total=int(pair['nominal1'][ids].sum()),nominal_2_total=int(pair['nominal2'][ids].sum()))


def coverage_rows(reference):
    pair=reference['pair'];groups=list(group_rows(reference));places=list(reference['places'].items())
    selected=reference['selected']
    for uf in ['BR',*sorted({pair['keys'][int(i)][0] for i in selected})]:
        chosen_groups=[(row,members) for row,members in zip(groups,reference['groups'].values()) if uf=='BR' or row['uf']==uf]
        chosen_places=[(number,key,members) for number,(key,members) in enumerate(places) if uf=='BR' or key[0]==uf]
        potential=[(row,members) for row,members in chosen_groups if row['potential']]
        reachable=set()
        for _,members in potential:
            for label in reference['labels'][members]:
                if reference['target'][label]:reachable.add(int(label))
        yield dict(model=reference['model'],uf=uf,
            cohort_pairs=sum(uf=='BR' or pair['keys'][int(i)][0]==uf for i in selected),places=len(chosen_places),
            targets=sum(bool(reference['target'][number]) for number,_,_ in chosen_places),
            target_pairs=sum(len(members) for number,_,members in chosen_places if reference['target'][number]),
            groups=len(chosen_groups),groups_with_peers=sum(row['n']>1 for row,_ in chosen_groups),
            peer_pairs=sum(row['n'] for row,_ in chosen_groups if row['n']>1),
            multi_place_groups=sum(row['places']>1 for row,_ in chosen_groups),
            multi_place_pairs=sum(row['n'] for row,_ in chosen_groups if row['places']>1),
            potential_groups=len(potential),potential_pairs=sum(row['n'] for row,_ in potential),
            target_pairs_in_potential_groups=sum(row['target_slots'] for row,_ in potential),reachable_targets=len(reachable))


def sensitivity_row(reference,peers,scenario,finalist_floor=50,unchanged=False):
    score,_=localization_scores(reference)
    coverage=next(row for row in coverage_rows(reference) if row['uf']=='BR')
    case=next(row for row in case_summary_rows(reference['pair'],peers) if row['uf']=='BR')
    return dict(scenario=scenario,model=reference['model'],bins=reference['baseline_bins'],finalist_floor=finalist_floor,
        unchanged_aptos=unchanged,min_target=reference['min_place'],cohort_pairs=len(reference['selected']),
        targets=coverage['targets'],target_pairs=coverage['target_pairs'],RMS=float(score[0]),MAX=float(score[1]),
        strict_supported=case['strict_supported'],strict_priorities=case['strict_priorities'],
        broad_supported=case['broad_supported'],broad_priorities=case['broad_priorities'],
        potential_pairs=coverage['potential_pairs'],target_pairs_in_potential_groups=coverage['target_pairs_in_potential_groups'])


def monte_carlo_reference(folder,reference,seed,model_id,metadata,audit,repetitions=(0,1)):
    folder=Path(folder)
    scores=np.load(folder/'scores.npy',allow_pickle=False,mmap_mode='r')
    audit.require(scores.shape==(int(metadata['simulations']),2),'simulation_cache',f'{reference["model"]}: score shape')
    audit.require(bool(np.all(np.isfinite(scores))) and bool(np.all(scores>=0)),'simulation_cache','Finite nonnegative scores')
    repeated=[]
    for repetition in repetitions:
        if repetition>=len(scores):continue
        assignment=independent_assignment(reference,seed,model_id,repetition)
        signature=hashlib.sha256(assignment.astype('<i4').tobytes()).hexdigest()
        audit.same(metadata['assignment_prefix'].get(str(repetition)),signature,'simulation_assignment',
            f'{reference["model"]}/rep{repetition}: complete pair assignment SHA-256')
        expected,_=localization_scores(reference,reference['residual'][assignment])
        for j,name in enumerate(STAT_NAMES):
            audit.same(float(scores[repetition,j]),float(expected[j]),'simulation_assignment',
                f'{reference["model"]}/rep{repetition}/{name}',tolerance=1e-9)
        repeated.append(repetition)
    return scores,repeated


def unmatched_rows(pair):
    for turn,data,keys in ((1,pair['first'],pair['only_first']),(2,pair['second'],pair['only_second'])):
        lookup={physical_key(data,i):i for i in range(len(data['aptos']))}
        for key in keys:
            yield dict(present_in_round=turn,**dict(zip(('uf','municipality','zone','section'),key)),
                source_line=int(data['source_line'][lookup[key]]))


def validate_analysis(root,analysis,cache,simulation_cache,output):
    root,analysis,cache,simulation_cache,output=map(Path,(root,analysis,cache,simulation_cache,output))
    if output.exists():
        raise ValueError('Refusing to overwrite a validation artifact')
    audit=Comparisons()
    rounds,source_metadata=independent_data(root,cache)
    manifest=json.loads((analysis/'manifest.json').read_text())
    audit.require(manifest.get('status')=='completed','provenance','Completed primary execution')
    audit.require(manifest.get('source_inputs')==source_metadata['source_inputs'],'provenance','Independent original snapshots')
    audit.same(manifest.get('method_sha256'),digest_file(HERE/'METHOD.pt-BR.md'),'provenance','Frozen method hash')
    for name,expected in manifest.get('implementation_sha256',{}).items():
        audit.same(digest_file(HERE/'code'/name),expected,'provenance',f'Primary implementation {name}')
    artifacts=manifest.get('artifacts',{})
    audit.require(bool(artifacts),'publication_integrity','Nonempty artifact inventory')
    audit.require({p.name for p in analysis.iterdir() if p.is_file() and p.name!='manifest.json'}==set(artifacts),
        'publication_integrity','Complete artifact set')
    for name,entry in artifacts.items():
        audit.same(digest_file(analysis/name),entry['sha256'],'publication_integrity',name)
        audit.same((analysis/name).stat().st_size,int(entry['size_bytes']),'publication_integrity',f'{name}/size')
    parameters=manifest['parameters']
    audit.require(parameters.get('models')=={'zone_size':0,'zone_size_baseline':1},'configuration','Fixed reference models')
    audit.require(parameters.get('statistics')==list(STAT_NAMES),'configuration','Fixed statistics')
    for field,expected in [('family_size',4),('epsilon_pp',1e-12),('priority_pp',10.),('min_other_peers',4),('baseline_bins',20),('min_target',5)]:
        audit.same(parameters.get(field),expected,'configuration',field,tolerance=0.)
    for kind in ('details','votes'):
        for name in ('rows_read','selected_rows'):
            flat=('detail' if kind=='details' else 'vote')+'_'+name.replace('selected_rows','rows_selected')
            audit.same(manifest['source_counts'][kind][name],source_metadata['source_counts'][flat],'source_counts',f'{kind}/{name}')
    pair=pair_reference(rounds)
    peers=peer_reference(pair)
    names=municipality_names(root)
    tables={
        'pairing.csv':(list(pairing_rows(pair)),('uf',)),
        'eligibility.csv':(list(eligibility_rows(pair)),('uf',)),
        'unmatched.csv':(list(unmatched_rows(pair)),('present_in_round','uf','municipality','zone','section')),
        'case-summary.csv':(list(case_summary_rows(pair,peers)),('uf',)),
        'distribution.csv':(list(distribution_rows(pair,peers)),('uf','metric')),
        'histograms.csv':(list(histogram_rows(pair,peers)),('metric','left_pp')),
        'transition-grid.csv':(list(transition_rows(pair)),('q1_low_pp','q2_low_pp')),
    }
    row_counts={}
    print('Independent H5 compare: paired-sections.csv.gz',file=sys.stderr,flush=True)
    compare_table(analysis/'paired-sections.csv.gz',raw_pair_rows(pair,names),('uf','municipality','zone','section'),audit,'paired-sections.csv.gz')
    row_counts['paired-sections.csv.gz']=len(pair['keys'])
    print('Independent H5 compare: section-screening.csv.gz',file=sys.stderr,flush=True)
    compare_table(analysis/'section-screening.csv.gz',section_rows(pair,peers),('uf','municipality','zone','section'),audit,'section-screening.csv.gz')
    row_counts['section-screening.csv.gz']=len(pair['selected'])
    group_tables=[];place_tables=[];coverages=[];tests=[];sensitivities=[];independent_runs=[]
    seed=int(parameters['seed'])
    for model_id,model in enumerate(MODELS):
        print(f'Independent H5 reference: {model}',file=sys.stderr,flush=True)
        reference=localization_reference(pair,model)
        observed,_=localization_scores(reference)
        group_tables.extend(group_rows(reference));place_tables.extend(place_rows(reference,peers));coverages.extend(coverage_rows(reference))
        sensitivities.append(sensitivity_row(reference,peers,'primary'))
        folder=simulation_cache/model
        metadata=json.loads((folder/'metadata.json').read_text())
        audit.require(metadata.get('status')=='completed','simulation_cache',f'{model}: completed')
        for field,expected in [('model',model),('model_id',model_id),('simulations',int(parameters['simulations'])),('seed',seed)]:
            audit.same(metadata.get(field),expected,'simulation_cache',f'{model}/{field}')
        audit.require(metadata.get('statistics')==list(STAT_NAMES),'simulation_cache',f'{model}: score order')
        audit.same(digest_file(folder/'scores.npy'),metadata.get('scores_sha256'),'simulation_cache',f'{model}: scores hash')
        registered=[entry for entry in manifest.get('simulation_caches',[]) if entry.get('metadata',{}).get('model')==model]
        audit.require(len(registered)==1,'simulation_cache',f'{model}: uniquely registered cache')
        if len(registered)==1:
            audit.require(registered[0]['metadata']==metadata,'simulation_cache',f'{model}: registered metadata')
            audit.same(digest_file(folder/'metadata.json'),registered[0]['metadata_sha256'],'simulation_cache',f'{model}: metadata hash')
        draws,repeated=monte_carlo_reference(folder,reference,seed,model_id,metadata,audit)
        possible,reasons=score_applicability(reference,draws,observed)
        quantiles=np.quantile(draws,[.025,.975],axis=0);means=draws.mean(axis=0)
        independent_runs.append(dict(model=model,repetitions=repeated,
            all_scores_differ_between_independently_repeated_assignments=bool(len(draws)>1 and np.all(draws[0]!=draws[1]))))
        for j,statistic in enumerate(STAT_NAMES):
            exceed=int(np.count_nonzero(draws[:,j]>=observed[j]-1e-12))
            tests.append(dict(model=model,statistic=statistic,observed=float(observed[j]),simulation_mean=float(means[j]),
                simulation_q025=float(quantiles[0,j]),simulation_q975=float(quantiles[1,j]),exceedances=exceed,simulations=len(draws),
                p_raw=(1+exceed)/(len(draws)+1) if possible[j] else '',p_holm='',detected='',
                status='applicable' if possible[j] else 'not_applicable',applicability_reason=reasons[j]))
    adjusted=holm_reference({(row['model'],row['statistic']):row['p_raw'] if row['status']=='applicable' else 1. for row in tests})
    for row in tests:
        if row['status']=='applicable':
            p=adjusted[row['model'],row['statistic']]
            row.update(p_holm=float(p),detected=bool(p<=.05),status='detected' if p<=.05 else 'not_detected')
    alternatives=[('baseline_2_5pp','zone_size_baseline',40,50,False,5),('baseline_10pp','zone_size_baseline',10,50,False,5)]
    alternatives += [(scenario,model,20,floor,unchanged,target) for scenario,floor,unchanged,target in
        [('unchanged_aptos',50,True,5),('finalists_100',100,False,5),('targets_10',50,False,10)] for model in MODELS]
    cached_pairs={(50,False):pair};cached_peers={(20,50,False):peers}
    for scenario,model,bins,floor,unchanged,target in alternatives:
        key=floor,unchanged
        if key not in cached_pairs:cached_pairs[key]=pair_reference(rounds,min_finalists=floor,unchanged_electorate=unchanged)
        alternative=cached_pairs[key]
        screen_key=bins,floor,unchanged
        if screen_key not in cached_peers:cached_peers[screen_key]=peer_reference(alternative,baseline_bins=bins)
        contexts=cached_peers[screen_key]
        reference=localization_reference(alternative,model,baseline_bins=bins,min_place=target)
        sensitivities.append(sensitivity_row(reference,contexts,scenario,floor,unchanged))
    tables.update({
        'concentration-groups.csv.gz':(group_tables,('model','uf','municipality','zone','size_band','baseline_bin')),
        'place-results.csv.gz':(place_tables,('model','uf','municipality','zone','place')),
        'coverage.csv':(coverages,('model','uf')),
        'tests.csv':(tests,('model','statistic')),
        'sensitivity.csv':(sensitivities,('scenario','model')),
    })
    for name,(rows,keys) in tables.items():
        print(f'Independent H5 compare: {name} ({len(rows):,} rows)',file=sys.stderr,flush=True)
        compare_table(analysis/name,rows,keys,audit,name);row_counts[name]=len(rows)
    summary=json.loads((analysis/'summary.json').read_text())
    for field,expected in [('matched_pairs',len(pair['keys'])),('cohort_pairs',len(pair['selected'])),('family_size',4),
        ('primary_detected',sum(row['status']=='detected' for row in tests)),
        ('primary_not_detected',sum(row['status']=='not_detected' for row in tests)),
        ('primary_not_applicable',sum(row['status']=='not_applicable' for row in tests))]:
        audit.same(summary.get(field),expected,'summary',field)
    audit.require(summary.get('case_summary')==next(row for row in tables['case-summary.csv'][0] if row['uf']=='BR'),
        'summary','Whole case summary')
    audit.require(summary.get('paired_elections')==[int(pair['first']['election_code']),int(pair['second']['election_code'])],
        'summary','Paired election codes')
    for name,source in source_metadata['source_inputs'].items():
        audit.same(digest_file(root/source['path']),source['sha256'],'source_immutability',name)
    result=dict(status='passed' if not audit.counts['mismatches'] else 'failed',
        completed_at_utc=datetime.now(timezone.utc).isoformat(),script_sha256=digest_file(Path(__file__)),
        independent_parser_fingerprint=parser_fingerprint(),source_inputs=source_metadata['source_inputs'],
        independent_source_counts=source_metadata['source_counts'],
        parameters=dict(simulations=int(parameters['simulations']),seed=seed,primary_family_size=4,p_resolution=1/(int(parameters['simulations'])+1)),
        comparisons=dict(audit.counts),mismatches=int(audit.counts['mismatches']),maximum_absolute_numeric_difference=audit.maximum_error,
        numeric_tolerances=dict(shares_residuals_scores_and_summaries=1e-9,p_value_comparisons=1e-9),
        rows_validated=row_counts,failures=audit.failures,
        simulation_scope=dict(all_retained_scores='SHA-256 checked; every rank, mean, quantile and Holm adjustment recomputed',
            assignment_generation='Realizations 0 and 1 independently repeated per reference, with full paired-payload assignment hashes',
            repeated_assignments=independent_runs,full_simulation_repeated=False),
        sensitivity_scope='All predeclared descriptive alternatives independently reconstructed',
        interpretation='Section screens and conditional place allocation; no external authenticity, individual vote transfers, or causal attribution')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--analysis-dir',type=Path,default=HERE/'evidence/analysis')
    parser.add_argument('--cache',type=Path,default=HERE/'.work/independent-data')
    parser.add_argument('--simulation-cache',type=Path,default=HERE/'.work/simulations')
    parser.add_argument('--output',type=Path,default=HERE/'evidence/independent-validation.json')
    args=parser.parse_args()
    result=validate_analysis(args.root,args.analysis_dir,args.cache,args.simulation_cache,args.output)
    print(json.dumps({field:result[field] for field in ('status','mismatches','maximum_absolute_numeric_difference')}))
    raise SystemExit(0 if result['status']=='passed' else 1)


if __name__=='__main__':
    main()
