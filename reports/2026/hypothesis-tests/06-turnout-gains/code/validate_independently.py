#!/usr/bin/env python3
"""Independent original-source reconstruction and validation for the H6 study.

The original-source parser is adapted from H5 commit a3362b3ec72c0c567fcf80c5b6761b6cc1cc52c2.
No primary H6 parser, group builder, statistic, or simulation helper is imported.
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
MODELS = ('zone_baseline', 'place_baseline')
STAT_NAMES = ('linear', 'rank')


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
            print(f'Independent H6 parser: {statistics["vote_rows_selected"]:,} vote rows', file=sys.stderr, flush=True)
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
        raise ValueError('H6 requires one presidential election per round')
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
            raise ValueError('Electorate identity fails in H6 cohort')
    result.update(reasons=reasons, selected=selected)
    return result


def rational_difference(a2, b2, a1, b1):
    """Integer reduced pairs; Python integers avoid cross-product overflow."""
    result = [Fraction(int(c2), int(d2))-Fraction(int(c1), int(d1))
              for c2, d2, c1, d1 in zip(a2, b2, a1, b1)]
    return result


def measurements(pair, outcome='change'):
    chosen = pair['selected']
    get = lambda name: pair[name][chosen]
    exact_x = rational_difference(get('turnout_2'), get('aptos_2'), get('turnout_1'), get('aptos_1'))
    exact_delta = rational_difference(get('v13_2'), get('f_2'), get('v13_1'), get('f_1'))
    exact_y = exact_delta if outcome == 'change' else [Fraction(int(v), int(f)) for v, f in zip(get('v13_2'), get('f_2'))]
    if outcome not in ('change', 'q2', 'second_share'):
        raise ValueError('Unknown outcome')
    result = dict(x=np.array([100*float(value) for value in exact_x]),
                  y=np.array([100*float(value) for value in exact_y]),
                  exact_x=exact_x, exact_y=exact_y,
                  delta=np.array([100*float(value) for value in exact_delta]))
    for turn in (1, 2):
        result[f'q{turn}'] = 100*get(f'v13_{turn}')/get(f'f_{turn}')
        result[f't{turn}'] = 100*get(f'turnout_{turn}')/get(f'aptos_{turn}')
    for candidate in (13, 22):
        v1, v2 = get(f'v{candidate}_1'), get(f'v{candidate}_2')
        a1, a2 = get('aptos_1'), get('aptos_2')
        t1, t2 = get('turnout_1')/a1, get('turnout_2')/a2
        s1, s2 = v1/get('turnout_1'), v2/get('turnout_2')
        result[f'gain{candidate}'] = v2-v1
        result[f'delta_per_aptos{candidate}'] = 100*(v2/a2-v1/a1)
        result[f'component_turnout{candidate}'] = 50*(s1+s2)*(t2-t1)
        result[f'component_composition{candidate}'] = 50*(t1+t2)*(s2-s1)
        result[f'delta_nominal{candidate}'] = 100*(v2/get('nominal_2')-v1/get('nominal_1'))
    return result


def initial_band(numerator, denominator, bins=20):
    if bins <= 0 or denominator <= 0:
        raise ValueError('Positive bins and denominator required')
    return min(bins-1, bins*int(numerator)//int(denominator))


def average_ranks(values):
    """Exact Fraction sort and average positions, including exact rational ties."""
    order = sorted(range(len(values)), key=values.__getitem__)
    result = np.empty(len(values), dtype=float)
    start = 0
    while start < len(order):
        stop = start+1
        while stop < len(order) and values[order[stop]] == values[order[start]]:
            stop += 1
        middle = (start+1+stop)/2
        result[[order[j] for j in range(start, stop)]] = middle
        start = stop
    return result


def grouping_reference(pair, model, bins=20, outcome='change'):
    if model not in MODELS:
        raise ValueError('Unknown H6 reference')
    chosen = pair['selected']
    measure = measurements(pair, outcome)
    groups = defaultdict(list)
    for position, raw_index in enumerate(chosen):
        i = int(raw_index)
        key = pair['keys'][i][:3] + (
            math.floor(math.log(int(pair['aptos_1'][i]))/math.log(1.25)),
            initial_band(pair['turnout_1'][i], pair['aptos_1'][i], bins),
            initial_band(pair['v13_1'][i], pair['f_1'][i], bins),
            initial_band(pair['other_1'][i], pair['turnout_1'][i], bins))
        if model == 'place_baseline':
            key += (int(pair['place_1'][i]),)
        groups[key].append(position)
    groups = dict(sorted(groups.items()))
    n = len(chosen)
    arrays = {name: np.zeros(n) for name in ('rx', 'ry', 'rank_x', 'rank_y')}
    informative = np.zeros(n, dtype=bool)
    labels = np.empty(n, dtype=np.int64)
    rows = []
    for number, (key, members) in enumerate(groups.items()):
        labels[members] = number
        x, y = measure['x'][members], measure['y'][members]
        varying_x = len({measure['exact_x'][i] for i in members}) > 1
        varying_y = len({measure['exact_y'][i] for i in members}) > 1
        if len(members) < 2:
            status = 'singleton'
        elif not varying_x and not varying_y:
            status = 'constant_both'
        elif not varying_x:
            status = 'constant_x'
        elif not varying_y:
            status = 'constant_y'
        else:
            status = 'informative'
        mx, my = math.fsum(map(float, x))/len(members), math.fsum(map(float, y))/len(members)
        raw_x = x-mx if varying_x else np.zeros(len(members))
        raw_y = y-my if varying_y else np.zeros(len(members))
        if status == 'informative':
            informative[members] = True
            arrays['rx'][members], arrays['ry'][members] = raw_x, raw_y
            rank_x = average_ranks([measure['exact_x'][i] for i in members])
            rank_y = average_ranks([measure['exact_y'][i] for i in members])
            arrays['rank_x'][members] = rank_x-(len(members)+1)/2
            arrays['rank_y'][members] = rank_y-(len(members)+1)/2
        rows.append(dict(key=key, members=members, size=len(members), variable_x=varying_x,
                         variable_y=varying_y, status=status, mean_x=mx, mean_y=my,
                         sxx=math.fsum(float(v*v) for v in raw_x),
                         syy=math.fsum(float(v*v) for v in raw_y),
                         sxy=math.fsum(float(a*b) for a,b in zip(raw_x,raw_y))))
    return dict(pair=pair, model=model, bins=bins, outcome=outcome, selected=chosen, measure=measure,
                groups=groups, group_rows=rows, informative=informative, labels=labels, **arrays)


def association_scores(reference, assignment=None, mask=None):
    arrays = reference
    use = reference['informative'] if mask is None else reference['informative'] & np.asarray(mask)
    if assignment is None:
        assignment = np.arange(len(use))
    scores = []
    for xfield, yfield in (('rx', 'ry'), ('rank_x', 'rank_y')):
        x, y = arrays[xfield][use], arrays[yfield][np.asarray(assignment)[use]]
        xx = math.fsum(float(v*v) for v in x)
        yy = math.fsum(float(v*v) for v in y)
        xy = math.fsum(float(a*b) for a,b in zip(x,y))
        scores.append(xy/math.sqrt(xx*yy) if xx > 0 and yy > 0 else float('nan'))
    return np.array(scores)


def slope_reference(reference, mask=None):
    use = reference['informative'] if mask is None else reference['informative'] & np.asarray(mask)
    x, y = reference['rx'][use], reference['ry'][use]
    xx = math.fsum(float(value*value) for value in x)
    return math.fsum(float(a*b) for a,b in zip(x,y))/xx if xx else float('nan')


def independent_assignment(reference, seed, model_id, repetition):
    rng = np.random.default_rng(np.random.SeedSequence([seed,6,model_id], spawn_key=(repetition,)))
    eligible = [row['members'] for row in reference['group_rows'] if row['status'] == 'informative']
    result = np.arange(len(reference['selected']), dtype=np.int32)
    for size in sorted({len(members) for members in eligible}):
        bucket = np.array([members for members in eligible if len(members) == size], dtype=np.int32)
        result[bucket.ravel()] = rng.permuted(bucket, axis=1).ravel()
    return result


def exact_assignments(reference):
    groups = [row['members'] for row in reference['group_rows'] if row['status'] == 'informative']
    for choices in product(*(permutations(members) for members in groups)):
        assignment = np.arange(len(reference['selected']), dtype=np.int32)
        for slots, sources in zip(groups, choices):
            assignment[slots] = sources
        yield assignment


def exact_covariance_magnitudes(reference, assignment):
    """Exact numerator proof: denominators are fixed over a permutation orbit."""
    totals = [Fraction(0),Fraction(0)]
    x = reference['measure']['exact_x']; y = reference['measure']['exact_y']
    for row in reference['group_rows']:
        if row['status'] != 'informative':
            continue
        members = row['members']
        xs = [x[i] for i in members]
        ys = [y[int(assignment[i])] for i in members]
        totals[0] += sum((a*b for a,b in zip(xs,ys)),Fraction(0))-sum(xs,Fraction(0))*sum(ys,Fraction(0))/len(members)
        # Mid-ranks and their centered values are integers or half-integers.
        totals[1] += sum((Fraction(float(reference['rank_x'][i]))*
                          Fraction(float(reference['rank_y'][int(assignment[i])])) for i in members),Fraction(0))
    return tuple(abs(value) for value in totals)


def score_applicability(reference, sampled, observed, max_exact=40320):
    if not np.any(reference['informative']):
        return np.zeros(2,dtype=bool), ['no_informative_groups']*2
    combined = np.abs(np.vstack([observed, sampled]))
    varying = np.ptp(combined, axis=0) > 1e-12
    reasons = ['sampled_distinct_scores' if value else '' for value in varying]
    if np.all(varying):
        return varying, reasons
    orbit = 1
    for row in reference['group_rows']:
        if row['status'] == 'informative':
            orbit *= math.factorial(row['size'])
            if orbit > max_exact:
                raise ArithmeticError('Unresolved magnitude variability: orbit too large')
    distinct = [set(),set()]
    for assignment in exact_assignments(reference):
        for j,value in enumerate(exact_covariance_magnitudes(reference,assignment)):
            distinct[j].add(value)
    for j in np.flatnonzero(~varying):
        varying[j] = len(distinct[j]) > 1
        reasons[j] = 'exact_enumeration_variable' if varying[j] else 'exact_enumeration_constant'
    return varying, reasons


def holm_reference(values):
    order = sorted(values,key=lambda key:(values[key],key))
    result = {}; running = 0.
    for rank,key in enumerate(order):
        running = max(running,(len(order)-rank)*values[key])
        result[key] = min(1.,running)
    return result


def monte_carlo_p(observed, simulated, tolerance=1e-12):
    return (1+int(np.count_nonzero(np.asarray(simulated)>=observed-tolerance)))/(len(simulated)+1)


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


REGIONS = {
    **dict.fromkeys(('AC','AP','AM','PA','RO','RR','TO'),'Norte'),
    **dict.fromkeys(('AL','BA','CE','MA','PB','PE','PI','RN','SE'),'Nordeste'),
    **dict.fromkeys(('DF','GO','MT','MS'),'Centro-Oeste'),
    **dict.fromkeys(('ES','MG','RJ','SP'),'Sudeste'),
    **dict.fromkeys(('PR','RS','SC'),'Sul'), 'ZZ':'Exterior',
}


def scope_masks(ufs):
    values = np.asarray(ufs)
    regions = np.array([REGIONS[str(uf)] for uf in values])
    yield 'BR','BR',np.ones(len(values),dtype=bool)
    for uf in sorted(set(values.tolist())):
        yield 'UF',str(uf),values==uf
    for region in sorted(set(regions.tolist())):
        yield 'region',str(region),regions==region


def municipality_names(root):
    names = {}
    for _,row,columns in raw_rows(root/SOURCE_PATHS['details']):
        key = f"{row[columns['SG_UF']].strip().upper()}:{integer(row[columns['CD_MUNICIPIO']])}"
        name = row[columns['NM_MUNICIPIO']].strip() if 'NM_MUNICIPIO' in columns else ''
        names[key] = min(name,names.get(key,name))
    return names


def canonical_measurements(pair):
    m = measurements(pair)
    selected = pair['selected']
    result = dict(x=m['x'],y=m['y'],q1=m['q1'],q2=m['q2'],delta_q=m['delta'],
                  turnout_rate1=m['t1'],turnout_rate2=m['t2'],
                  abstention_rate1=100*pair['abstentions_1'][selected]/pair['aptos_1'][selected],
                  abstention_rate2=100*pair['abstentions_2'][selected]/pair['aptos_2'][selected],
                  other_1=pair['other_1'][selected],other_2=pair['other_2'][selected])
    for c in (13,22):
        result.update({f'gain{c}_count':m[f'gain{c}'],f'gain{c}_nominal_pp':m[f'delta_nominal{c}'],
                       f'gain{c}_aptos_pp':m[f'delta_per_aptos{c}'],
                       f'turnout{c}_component_pp':m[f'component_turnout{c}'],
                       f'composition{c}_component_pp':m[f'component_composition{c}']})
        for prefix,field in (('gain',f'delta_per_aptos{c}'),('turnout',f'component_turnout{c}'),('composition',f'component_composition{c}')):
            result[f'{prefix}{c}_equiv_votes'] = m[field]*pair['aptos_1'][selected]/100
    for prefix,values in (('x',m['exact_x']),('y',m['exact_y'])):
        result[f'{prefix}_numerator'] = np.array([v.numerator for v in values],dtype=np.int64)
        result[f'{prefix}_denominator'] = np.array([v.denominator for v in values],dtype=np.int64)
    return result


def pairing_rows(pair):
    first,second = pair['first'],pair['second']
    for uf in ['BR',*sorted(set(first['uf'].tolist())|set(second['uf'].tolist()))]:
        yield dict(uf=uf,
            round1_records=sum(uf=='BR' or str(value)==uf for value in first['uf']),
            round2_records=sum(uf=='BR' or str(value)==uf for value in second['uf']),
            matched_pairs=sum(uf=='BR' or key[0]==uf for key in pair['keys']),
            only_round1=sum(uf=='BR' or key[0]==uf for key in pair['only_first']),
            only_round2=sum(uf=='BR' or key[0]==uf for key in pair['only_second']))


def eligibility_rows(pair):
    reasons = pair['reasons']; selected = reasons=='eligible'
    labels = ('section_status','aptos_below_50','nonpositive_turnout','nominal_below_50',
              'finalists_below_floor','missing_place','changed_place','aptos_ratio')
    basic = np.isin(reasons,('eligible','finalists_below_floor','missing_place','changed_place','aptos_ratio'))
    for uf in ['BR',*sorted({key[0] for key in pair['keys']})]:
        use = np.array([uf=='BR' or key[0]==uf for key in pair['keys']])
        chosen = use&selected
        row = dict(uf=uf,matched_pairs=int(use.sum()),basic_eligible=int((use&basic).sum()),cohort_pairs=int(chosen.sum()))
        row.update({f'excluded_{label}':int((use&(reasons==label)).sum()) for label in labels})
        row['changed_aptos_cohort'] = int((chosen&(pair['aptos_1']!=pair['aptos_2'])).sum())
        yield row


def unmatched_rows(pair):
    for turn,data,keys in ((1,pair['first'],pair['only_first']),(2,pair['second'],pair['only_second'])):
        lookup = {physical_key(data,i):i for i in range(len(data['aptos']))}
        for key in keys:
            yield dict(present_in_round=turn,**dict(zip(('uf','municipality','zone','section'),key)),
                       source_line=int(data['source_line'][lookup[key]]))


def paired_rows(pair,names):
    fields = ('place','source_line','installed','cancelled','aptos','turnout','abstentions','nominal',
              'blank','null_votes','legend','separate','v13','v22','f')
    for i,key in enumerate(pair['keys']):
        row = dict(zip(('uf','municipality','zone','section'),key))
        row.update(municipality_name=names.get(f'{key[0]}:{key[1]}',''),
                   election_1=int(pair['first']['election_code']),election_2=int(pair['second']['election_code']))
        for turn in (1,2):
            for field in fields:
                raw = pair[f'{field}_{turn}'][i]
                row[f'{field}_{turn}'] = bool(raw) if field in ('installed','cancelled') else int(raw)
        row.update(eligible=bool(pair['reasons'][i]=='eligible'),exclusion_reason=str(pair['reasons'][i]))
        yield row


def measurement_rows(pair,measured,references):
    for position,i in enumerate(pair['selected']):
        row = dict(zip(('uf','municipality','zone','section'),pair['keys'][int(i)]))
        row['place'] = int(pair['place_1'][i])
        row.update({field:values[position] for field,values in measured.items()})
        row.update({f'support_{model}':bool(ref['informative'][position]) for model,ref in references.items()})
        yield row


def group_rows(reference):
    for source in reference['group_rows']:
        key = source['key']
        yield dict(model=reference['model'],uf=key[0],municipality=key[1],zone=key[2],
            place=key[7] if reference['model']=='place_baseline' else -1,size_band=key[3],
            initial_turnout_bin=key[4],initial_preference_bin=key[5],initial_other_bin=key[6],
            n=source['size'],status=source['status'],variable_x=source['variable_x'],variable_y=source['variable_y'],
            informative=source['status']=='informative',mean_x=source['mean_x'],mean_y=source['mean_y'],
            ss_x=source['sxx'],ss_y=source['syy'],covariance=source['sxy'])


def coverage_rows(reference):
    pair = reference['pair']
    ufs = np.array([pair['keys'][int(i)][0] for i in reference['selected']])
    aliases = dict(singleton='singleton',constant_both='constant_both',constant_x_only='constant_x',
                   constant_y_only='constant_y',informative='informative')
    for uf in ['BR',*sorted(set(ufs.tolist()))]:
        chosen = [row for row in reference['group_rows'] if uf=='BR' or row['key'][0]==uf]
        row = dict(model=reference['model'],uf=uf,cohort_pairs=int(np.count_nonzero(ufs==uf)) if uf!='BR' else len(ufs),groups=len(chosen))
        for label,status in aliases.items():
            rows = [group for group in chosen if group['status']==status]
            row[f'{label}_groups'],row[f'{label}_pairs'] = len(rows),sum(group['size'] for group in rows)
        yield row


def totals_rows(rounds):
    r1,r2 = sorted(rounds,key=lambda rd:int(rd['turno']))
    all_ufs = sorted(set(r1['uf'].tolist())|set(r2['uf'].tolist()))
    fields = ('aptos','turnout','abstentions','nominal','blank','null_votes','legend','separate','v13','v22','other_nominal')
    for scope_type,scope,_ in scope_masks(all_ufs):
        row = dict(scope_type=scope_type,scope=scope)
        for turn,data in ((1,r1),(2,r2)):
            use = np.array([scope_type=='BR' or (str(uf)==scope if scope_type=='UF' else REGIONS[str(uf)]==scope) for uf in data['uf']])
            row[f'sections_{turn}'] = int(use.sum())
            values = {key:data[key] for key in fields if key not in ('v13','v22','other_nominal')}
            for c in (13,22):
                values[f'v{c}'] = data['candidate_votes'][:,data['candidate_numbers'].index(c)]
            values['other_nominal'] = data['nominal']-values['v13']-values['v22']
            for field in fields:
                row[f'{field}_{turn}'] = int(values[field][use].sum(dtype=np.int64))
            row[f'aptos_identity_residual_{turn}'] = row[f'aptos_{turn}']-row[f'turnout_{turn}']-row[f'abstentions_{turn}']
            row[f'turnout_rate_{turn}'] = 100*row[f'turnout_{turn}']/row[f'aptos_{turn}'] if row[f'aptos_{turn}'] else None
        for field in fields:
            row[f'{field}_change'] = row[f'{field}_2']-row[f'{field}_1']
        row['finalist_gain'] = row['v13_change']+row['v22_change']
        row['other_and_special_change'] = sum(row[f'{field}_change'] for field in ('other_nominal','blank','null_votes','legend','separate'))
        row['identity_residual'] = row['finalist_gain']-row['turnout_change']+row['other_and_special_change']
        row['turnout_rate_change'] = row['turnout_rate_2']-row['turnout_rate_1'] if row['aptos_1'] and row['aptos_2'] else None
        yield row


def basic_correlation(x,y):
    if not len(x):
        return None,None
    rx,ry = x-math.fsum(map(float,x))/len(x),y-math.fsum(map(float,y))/len(y)
    xx,yy = math.fsum(float(v*v) for v in rx),math.fsum(float(v*v) for v in ry)
    xy = math.fsum(float(a*b) for a,b in zip(rx,ry))
    return xy/math.sqrt(xx*yy) if xx and yy else None,xy/xx if xx else None


def descriptive_rows(pair,measured,references):
    selected = pair['selected']
    ufs = [pair['keys'][int(i)][0] for i in selected]
    fields = [key for key in measured if key not in ('x_numerator','x_denominator','y_numerator','y_denominator')]
    for scope_type,scope,use in scope_masks(ufs):
        raw_rho,raw_beta = basic_correlation(measured['x'][use],measured['y'][use])
        exact_sign = measured['x_numerator'][use]
        row = dict(scope_type=scope_type,scope=scope,cohort_pairs=int(use.sum()),
            increased_turnout_pairs=int(np.count_nonzero(exact_sign>0)),unchanged_turnout_pairs=int(np.count_nonzero(exact_sign==0)),
            decreased_turnout_pairs=int(np.count_nonzero(exact_sign<0)),
            changed_aptos_pairs=int(np.count_nonzero(pair['aptos_1'][selected][use]!=pair['aptos_2'][selected][use])),
            raw_rho=raw_rho,raw_beta=raw_beta)
        for field in fields:
            row[f'mean_{field}'] = math.fsum(map(float,measured[field][use]))/int(use.sum())
        for c in (13,22):
            for field in (f'gain{c}_count',f'gain{c}_equiv_votes',f'turnout{c}_equiv_votes',f'composition{c}_equiv_votes'):
                row[f'sum_{field}'] = int(measured[field][use].sum()) if field.endswith('_count') else math.fsum(map(float,measured[field][use]))
        for model,reference in references.items():
            supported = use&reference['informative']
            correlations = association_scores(reference,mask=use)
            row.update({f'{model}_supported_pairs':int(supported.sum()),f'{model}_rho_linear':correlations[0],
                        f'{model}_rho_rank':correlations[1],f'{model}_beta':slope_reference(reference,mask=use)})
        yield row


EDGES = [-math.inf,*range(-10,11,2),math.inf]


def boundary(value):
    return '-inf' if value==-math.inf else 'inf' if value==math.inf else int(value)


def bin_indices(values):
    from bisect import bisect_right
    return np.array([bisect_right(EDGES[1:-1],float(value)) for value in values])


def xbin_rows(pair,measured):
    bins = bin_indices(measured['x'])
    ufs = [pair['keys'][int(i)][0] for i in pair['selected']]
    fields = ('x','y','gain13_count','gain22_count','gain13_aptos_pp','gain22_aptos_pp',
              'turnout13_component_pp','turnout22_component_pp','composition13_component_pp','composition22_component_pp')
    for scope_type,scope,use in scope_masks(ufs):
        for b in range(len(EDGES)-1):
            chosen = use&(bins==b)
            row = dict(scope_type=scope_type,scope=scope,bin=b,left_pp=boundary(EDGES[b]),right_pp=boundary(EDGES[b+1]),sections=int(chosen.sum()))
            for field in fields:
                row[f'mean_{field}'] = math.fsum(map(float,measured[field][chosen]))/int(chosen.sum()) if np.any(chosen) else None
            yield row


def heatmap_rows(measured):
    from collections import Counter
    counts = Counter(zip(bin_indices(measured['x']),bin_indices(measured['y'])))
    for x in range(len(EDGES)-1):
        for y in range(len(EDGES)-1):
            yield dict(x_bin=x,x_left_pp=boundary(EDGES[x]),x_right_pp=boundary(EDGES[x+1]),
                y_bin=y,y_left_pp=boundary(EDGES[y]),y_right_pp=boundary(EDGES[y+1]),sections=counts[x,y])


def sensitivity_rows(rounds,primary):
    configs = [('primary',20,50,False,False,'change'),('baseline_2_5pp',40,50,False,False,'change'),
               ('baseline_10pp',10,50,False,False,'change'),('unchanged_aptos',20,50,True,False,'change'),
               ('finalists_100',20,100,False,False,'change'),('domestic_only',20,50,False,True,'change'),
               ('final_preference',20,50,False,False,'second_share')]
    for scenario,bins,floor,unchanged,domestic,outcome in configs:
        pair = primary if floor==50 and not unchanged and not domestic else pair_reference(rounds,floor,unchanged,domestic)
        for model in MODELS:
            ref = grouping_reference(pair,model,bins,outcome)
            scores = association_scores(ref)
            yield dict(scenario=scenario,model=model,bins=bins,finalist_floor=floor,
                unchanged_aptos=unchanged,domestic_only=domestic,outcome=outcome,
                cohort_pairs=len(pair['selected']),groups=len(ref['groups']),
                informative_groups=sum(row['status']=='informative' for row in ref['group_rows']),
                informative_pairs=int(ref['informative'].sum()),rho_linear=scores[0],rho_rank=scores[1],beta=slope_reference(ref))


def audit_provenance(root,analysis,manifest,source_metadata,audit):
    audit.same(manifest.get('status'),'completed','provenance','primary completion')
    audit.same(manifest.get('hypothesis'),'H6','provenance','hypothesis identifier')
    audit.same(manifest.get('method_sha256'),digest_file(HERE/'METHOD.pt-BR.md'),'provenance','frozen method hash')
    for name,expected in manifest.get('implementation_sha256',{}).items():
        audit.same(digest_file(HERE/'code'/name),expected,'provenance',f'implementation {name}')
    for name,expected in source_metadata['source_inputs'].items():
        audit.require(manifest['source_inputs'].get(name)==expected,'provenance',f'original-source snapshot {name}')
    primary_counts = manifest['source_counts']
    for independent_name,source_name,field in (
            ('detail_rows_read','details','rows_read'),('detail_rows_selected','details','selected_rows'),
            ('vote_rows_read','votes','rows_read'),('vote_rows_selected','votes','selected_rows')):
        audit.same(primary_counts[source_name][field],source_metadata['source_counts'][independent_name],
                   'provenance',f'raw source count {independent_name}')
    audit.same(manifest['parameters']['family_size'],4,'provenance','fixed Holm family')
    audit.same(manifest['parameters']['baseline_bins'],20,'provenance','primary baseline bins')
    audit.same(manifest['parameters']['seed'],20261029,'provenance','seed')
    audit.same(manifest['parameters']['statistics'],list(STAT_NAMES),'provenance','statistics')
    for name,entry in manifest['artifacts'].items():
        path = analysis/name
        audit.require(path.is_file(),'artifact_integrity',f'missing {name}')
        if path.is_file():
            audit.same(path.stat().st_size,entry['size_bytes'],'artifact_integrity',f'{name} size')
            audit.same(digest_file(path),entry['sha256'],'artifact_integrity',f'{name} SHA256')


def audit_simulations(root,analysis,manifest,references,audit):
    b = int(manifest['parameters']['simulations']); seed = int(manifest['parameters']['seed'])
    expected_tests = []; simulation_arrays = {}; repetitions = []
    caches = {entry['metadata']['model']:entry for entry in manifest['simulation_caches']}
    audit.require(set(caches)==set(MODELS),'simulation_integrity','two simulation references')
    for model_id,model in enumerate(MODELS):
        reference = references[model]
        entry = caches[model]; directory = Path(entry['path'])
        if not directory.is_absolute():
            directory = root/directory
        metadata_path = directory/'metadata.json'
        audit.same(digest_file(metadata_path),entry['metadata_sha256'],'simulation_integrity',f'{model} metadata hash')
        metadata = json.loads(metadata_path.read_text())
        audit.require(metadata==entry['metadata'],'simulation_integrity',f'{model} embedded metadata')
        audit.same(metadata['status'],'completed','simulation_integrity',f'{model} cache status')
        audit.same(metadata['model_id'],model_id,'simulation_integrity',f'{model} ID')
        audit.same(metadata['simulations'],b,'simulation_integrity',f'{model} draw count')
        score_path = directory/'scores.npy'
        audit.same(digest_file(score_path),metadata['scores_sha256'],'simulation_integrity',f'{model} retained scores hash')
        simulated = np.load(score_path,allow_pickle=False)
        audit.require(simulated.shape==(b,2) and simulated.dtype==np.dtype('float64') and np.all(np.isfinite(simulated))
                      and np.all(np.abs(simulated)<=1+1e-12),'simulation_integrity',f'{model} signed score array shape/range')
        simulation_arrays[model] = simulated
        observed = association_scores(reference)
        flags,reasons = score_applicability(reference,simulated,observed)
        for rep in (0,1):
            if rep >= b:
                continue
            assignment = independent_assignment(reference,seed,model_id,rep)
            assignment_hash = hashlib.sha256(assignment.astype('<i4').tobytes()).hexdigest()
            audit.same(assignment_hash,metadata['assignment_prefix'][str(rep)],'repeated_assignments',f'{model}/{rep} full assignment hash')
            repeated_scores = association_scores(reference,assignment)
            for k,stat in enumerate(STAT_NAMES):
                audit.same(float(simulated[rep,k]),float(repeated_scores[k]),'repeated_assignments',f'{model}/{rep}/{stat} signed score',1e-10)
            repetitions.append(dict(model=model,repetition=rep,assignment_sha256=assignment_hash,
                                    independently_recomputed_signed_scores=[float(value) for value in repeated_scores]))
        absolute = np.abs(simulated)
        for k,stat in enumerate(STAT_NAMES):
            exceedances = int(np.count_nonzero(absolute[:,k]>=abs(observed[k])-1e-12))
            expected_tests.append(dict(model=model,statistic=stat,observed_signed=float(observed[k]),observed_abs=float(abs(observed[k])),
                beta=slope_reference(reference) if stat=='linear' else None,
                simulation_mean_abs=math.fsum(map(float,absolute[:,k]))/b,
                simulation_q025_abs=float(np.quantile(absolute[:,k],.025)),simulation_q975_abs=float(np.quantile(absolute[:,k],.975)),
                exceedances=exceedances,simulations=b,p_raw=(1+exceedances)/(1+b) if flags[k] else None,
                p_holm=None,detected=None,status='applicable' if flags[k] else 'not_applicable',applicability_reason=reasons[k]))
    adjusted = holm_reference({(row['model'],row['statistic']):row['p_raw'] if row['status']=='applicable' else 1. for row in expected_tests})
    for row in expected_tests:
        if row['status']=='applicable':
            p = adjusted[row['model'],row['statistic']]
            row.update(p_holm=p,detected=bool(p<=.05),status='detected' if p<=.05 else 'not_detected')
    compare_ordered_table(analysis/'tests.csv',iter(expected_tests),audit,'formal_tests')
    def published_scores():
        for model in MODELS:
            for rep,score in enumerate(simulation_arrays[model]):
                yield dict(model=model,repetition=rep,rho_linear=float(score[0]),rho_rank=float(score[1]))
    compare_ordered_table(analysis/'permutation-scores.csv.gz',published_scores(),audit,'published_simulation_scores')
    return expected_tests,repetitions,sum(len(array) for array in simulation_arrays.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--analysis',type=Path,default=HERE/'evidence/analysis')
    parser.add_argument('--cache',type=Path,default=HERE/'.work/independent-source')
    parser.add_argument('--output',type=Path,default=HERE/'evidence/independent-validation.json')
    args = parser.parse_args()
    root,analysis,cache,output = (path.resolve() for path in (args.root,args.analysis,args.cache,args.output))
    if output.exists():
        parser.error('Refusing to overwrite an existing independent-validation output; choose a new path')
    manifest = json.loads((analysis/'manifest.json').read_text())
    if manifest.get('status')!='completed':
        parser.error('Primary analysis must be completed before validation')
    audit = Comparisons()
    started = datetime.now(timezone.utc).isoformat()
    rounds,source_metadata = independent_data(root,cache)
    audit_provenance(root,analysis,manifest,source_metadata,audit)
    print('Independent H6: reconstructing physical pairs and exact changes',flush=True)
    pair = pair_reference(rounds)
    measured = canonical_measurements(pair)
    references = {model:grouping_reference(pair,model) for model in MODELS}
    names = municipality_names(root)
    checks = [
        ('pairing.csv',pairing_rows(pair),'pairing'),
        ('eligibility.csv',eligibility_rows(pair),'eligibility'),
        ('unmatched.csv',unmatched_rows(pair),'unmatched'),
        ('paired-sections.csv.gz',paired_rows(pair,names),'all_paired_sections'),
        ('section-measures.csv.gz',measurement_rows(pair,measured,references),'all_section_measures'),
        ('totals.csv',totals_rows(rounds),'raw_totals'),
        ('descriptive.csv',descriptive_rows(pair,measured,references),'cohort_descriptive'),
        ('x-bins.csv',xbin_rows(pair,measured),'turnout_bins'),
        ('heatmap.csv',heatmap_rows(measured),'heatmap'),
        ('association-groups.csv.gz',(row for ref in references.values() for row in group_rows(ref)),'all_association_groups'),
        ('coverage.csv',(row for ref in references.values() for row in coverage_rows(ref)),'coverage'),
    ]
    for filename,rows,category in checks:
        print(f'Independent H6: {filename}',flush=True)
        compare_ordered_table(analysis/filename,rows,audit,category)
    tests,repeated_assignments,retained_score_rows = audit_simulations(root,analysis,manifest,references,audit)
    print('Independent H6: all fourteen fixed sensitivity rows',flush=True)
    compare_ordered_table(analysis/'sensitivity.csv',sensitivity_rows(rounds,pair),audit,'sensitivity')
    summary = json.loads((analysis/'summary.json').read_text())
    expected_summary = dict(matched_pairs=len(pair['keys']),cohort_pairs=len(pair['selected']),
        paired_elections=[int(pair['first']['election_code']),int(pair['second']['election_code'])],family_size=4,
        primary_detected=sum(row['status']=='detected' for row in tests),primary_not_detected=sum(row['status']=='not_detected' for row in tests),
        primary_not_applicable=sum(row['status']=='not_applicable' for row in tests))
    for field,value in expected_summary.items():
        audit.same(summary.get(field),value,'summary',field)
    for field,expected in (('national_raw_counts',next(totals_rows(rounds))),
                           ('national_cohort_descriptive',next(descriptive_rows(pair,measured,references)))):
        audit.require(set(summary[field])==set(expected),'summary',f'{field} schema')
        for key,value in expected.items():
            tolerance = 2e-7 if key.startswith('sum_') and 'equiv_votes' in key else 1e-9
            audit.same(summary[field].get(key),value,'summary',f'{field}/{key}',tolerance)
    for name,entry in source_metadata['source_inputs'].items():
        audit.same(digest_file(root/entry['path']),entry['sha256'],'provenance',f'{name} unchanged after independent validation')
    result = dict(status='passed' if not audit.counts['mismatches'] else 'failed',hypothesis='H6',
        started_at_utc=started,completed_at_utc=datetime.now(timezone.utc).isoformat(),
        script_sha256=digest_file(Path(__file__)),method_sha256=digest_file(HERE/'METHOD.pt-BR.md'),
        primary_manifest_sha256=digest_file(analysis/'manifest.json'),source_inputs=source_metadata['source_inputs'],
        independent_parser_sha256=source_metadata['parser_sha256'],source_counts=source_metadata['source_counts'],
        independent_source_cache=dict(path=str(cache.relative_to(root)) if cache.is_relative_to(root) else str(cache),
                                      arrays_sha256=source_metadata['arrays_sha256'],fingerprint=source_metadata['fingerprint']),
        comparisons=sum(value for key,value in audit.counts.items() if key!='mismatches'),
        mismatches=int(audit.counts['mismatches']),checks_by_category=dict(audit.counts),
        maximum_absolute_numerical_difference=audit.maximum_error,failures=audit.failures,
        numerical_csv_files_checked=14,sensitivity_rows_recomputed=14,
        independently_regenerated_full_assignments=repeated_assignments,
        retained_signed_score_rows_audited=retained_score_rows,
        limits='All original-source numerical CSVs are reconstructed. Realizations 0 and 1 per model are independently regenerated; all remaining retained Monte Carlo scores are audited for publication, ranks, moments and multiplicity, not independently regenerated. Check counts are integrity comparisons, not independent statistical observations.')
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary = output.with_suffix(output.suffix+'.tmp')
    if temporary.exists():
        parser.error('Temporary validation output already exists; choose a new output path')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temporary.replace(output)
    print(json.dumps({key:result[key] for key in ('status','comparisons','mismatches','maximum_absolute_numerical_difference')},ensure_ascii=False),flush=True)
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
