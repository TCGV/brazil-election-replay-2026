#!/usr/bin/env python3
"""Independent original-source reconstruction and validation for the H4 study.

No primary H4 parser, group builder, statistic, or simulation helper is imported.
The source parser has its own content-addressed cache. Monte Carlo ranks and
pointwise bands are recomputed from retained, fingerprinted simulation arrays;
that is distinct from independently repeating every large random assignment.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import inspect
import json
import math
from pathlib import Path
import re
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
TIME_FIELDS = {'first_time': 'DT_PRIM_TOT_PARCIAL_HOR_TSE', 'bu_time': 'DT_RECEBIMENTO_BU_HOR_TSE'}
MODELS = ('zone_size', 'place_size')
SOURCE_NAMES = ('first_time', 'bu_time')
STAT_NAMES = ('gradual', 'cumulative', 'minute')
EPOCH = datetime(1970, 1, 1)


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


def wall_clock(raw):
    """Parse local wall clock independently; never use timestamp()/UTC conversion."""
    text = raw.strip()
    if text.upper() in MISSING:
        return -1
    if re.fullmatch(r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}', text):
        day, month, year, hour, minute, second = map(int, re.findall(r'\d+', text))
    elif re.fullmatch(r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}', text):
        year, month, day, hour, minute, second = map(int, re.findall(r'\d+', text))
    else:
        raise ValueError(f'Invalid local wall clock: {text!r}')
    value = datetime(year, month, day, hour, minute, second)
    delta = value - EPOCH
    if delta.days < 0:
        raise ValueError('Pre-epoch local wall clock is unsupported')
    return delta.days * 86400 + delta.seconds


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
                                     *TIME_FIELDS)}
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
        for field, original in TIME_FIELDS.items():
            records[field].append(wall_clock(row[columns[original]]))
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
            print(f'Independent H4 parser: {statistics["vote_rows_selected"]:,} vote rows', file=sys.stderr, flush=True)
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
    names = (integer, yes_no, wall_clock, raw_rows, source_key, read_sources)
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


def eligibility(data, min_nominal=50):
    """Exclusive exclusions in the declared order; all arrays remain in raw data."""
    n = len(data['aptos'])
    reason = np.full(n, 'eligible', dtype='U28')
    tests = (
        ('section_status', ~data['installed'] | data['cancelled']),
        ('aptos_below_50', data['aptos'] < 50),
        ('nonpositive_turnout', data['turnout'] <= 0),
        ('nominal_below_floor', data['nominal'] < min_nominal),
        ('missing_place', data['place'] < 0),
        ('missing_time', (data['first_time'] < 0) | (data['bu_time'] < 0)),
    )
    for label, condition in tests:
        reason[(reason == 'eligible') & condition] = label
    return reason == 'eligible', reason


def group_members(data, model, min_nominal=50):
    """Use Python key dictionaries instead of primary NumPy grouping."""
    if model not in {'zone_size', 'place_size', 'place_no_size'}:
        raise ValueError(f'Unknown independent group model: {model}')
    mask, reasons = eligibility(data, min_nominal)
    selected = np.flatnonzero(mask)
    groups = defaultdict(list)
    for index in selected:
        i = int(index)
        key = (str(data['uf'][i]), int(data['municipality'][i]), int(data['zone'][i]))
        if model != 'zone_size':
            key += (int(data['place'][i]),)
        if model != 'place_no_size':
            key += (math.floor(math.log(int(data['aptos'][i])) / math.log(1.25)),)
        groups[key].append(i)
    return dict(sorted(groups.items())), mask, reasons


def model_reference(data, model, min_nominal=50):
    """Group integer sums, section residuals and supports computed afresh."""
    groups, mask, reasons = group_members(data, model, min_nominal)
    selected = np.flatnonzero(mask)
    positions = np.full(len(mask), -1, dtype=np.int64)
    positions[selected] = np.arange(len(selected))
    residual = np.zeros((len(selected), len(data['candidate_numbers'])), dtype=np.float64)
    rows = []
    for key, members in groups.items():
        ix = np.asarray(members)
        nominal = int(data['nominal'][ix].sum(dtype=np.int64))
        votes = data['candidate_votes'][ix].sum(axis=0, dtype=np.int64)
        numerators = data['candidate_votes'][ix] * nominal - data['nominal'][ix, None] * votes
        values = numerators / nominal
        residual[positions[ix]] = values
        place = int(data['place'][ix[0]]) if model != 'zone_size' else -1
        size_band = key[-1] if model != 'place_no_size' else -1
        first = data['first_time'][ix]
        bu = data['bu_time'][ix]
        rows.append(dict(election_code=data['election_code'], turno=data['turno'], model=model,
            uf=key[0], municipality=key[1], zone=key[2], place=place, size_band=int(size_band), n=len(ix),
            nominal_total=nominal,
            min_aptos=int(data['aptos'][ix].min()), max_aptos=int(data['aptos'][ix].max()),
            candidate_votes_json=json.dumps(votes.tolist(), separators=(',', ':')),
            first_minute_min=int(first.min()//60), first_minute_max=int(first.max()//60),
            bu_minute_min=int(bu.min()//60), bu_minute_max=int(bu.max()//60),
            first_distinct_minutes=len(set((first // 60).tolist())), bu_distinct_minutes=len(set((bu // 60).tolist()))))
    return dict(data=data, model=model, groups=groups, selected=selected, reasons=reasons,
                residual=residual, group_rows=rows)


def minute_reference(reference, source):
    data = reference['data']
    ix = reference['selected']
    times = data[source][ix] // 60
    if not len(times):
        raise ValueError('No independently eligible sections')
    start, end = int(times.min()), int(times.max())
    bins = times - start
    length = end - start + 1
    sections = np.bincount(bins, minlength=length).astype(np.int64)
    nominal = np.bincount(bins, weights=data['nominal'][ix], minlength=length).astype(np.int64)
    votes = np.column_stack([np.bincount(bins, weights=data['candidate_votes'][ix, j], minlength=length)
                             for j in range(len(data['candidate_numbers']))]).astype(np.int64)
    residual = np.column_stack([np.bincount(bins, weights=reference['residual'][:, j], minlength=length)
                                for j in range(len(data['candidate_numbers']))])
    cumulative_sections = sections.cumsum()
    cumulative_nominal = nominal.cumsum()
    cumulative_votes = votes.cumsum(axis=0)
    cumulative_residual = residual.cumsum(axis=0)
    midrank = (cumulative_sections - sections / 2) / len(ix) - .5
    nominal_final = int(nominal.sum())
    signed_gradual = (midrank[:, None] * residual).sum(axis=0) * (100 / nominal_final)
    statistics = np.column_stack([abs(signed_gradual), np.max(abs(cumulative_residual), axis=0) * (100 / nominal_final),
                                  np.max(abs(residual), axis=0) * (100 / nominal_final)])
    checkpoints = np.empty(101, dtype=np.int64)
    checkpoints[0] = -1
    for percent in range(1, 101):
        checkpoints[percent] = np.searchsorted(cumulative_sections, math.ceil(percent * len(ix) / 100), side='left')
    return dict(start=start, end=end, bins=bins, sections=sections, nominal=nominal, votes=votes,
        residual=residual, cumulative_sections=cumulative_sections, cumulative_nominal=cumulative_nominal,
        cumulative_votes=cumulative_votes, cumulative_residual=cumulative_residual, midrank=midrank,
        signed_gradual=signed_gradual, statistics=statistics, checkpoints=checkpoints,
        nominal_final=nominal_final)


def holm_reference(p_values):
    """Fixed-family Holm adjustment, including any non-applicable members as one."""
    ordered = sorted(p_values, key=lambda key: (p_values[key], key))
    result = {}
    running = 0.
    n = len(ordered)
    for rank, key in enumerate(ordered):
        running = max(running, (n - rank) * p_values[key])
        result[key] = min(1., running)
    return result


def monte_carlo_p(observed, simulated, tolerance=1e-12):
    values = np.asarray(simulated, dtype=float)
    return (1 + int(np.count_nonzero(values >= observed - tolerance))) / (len(values) + 1)


def exact_permutation_statistics(nominal, votes, times, groups):
    """Small, independent exhaustive oracle for synthetic tests only."""
    import itertools
    nominal = list(map(int, nominal))
    votes = list(map(int, votes))
    times = list(map(int, times))
    n = len(nominal)
    residual = [0.] * n
    for members in groups:
        p = sum(votes[i] for i in members) / sum(nominal[i] for i in members)
        for i in members:
            residual[i] = votes[i] - p * nominal[i]
    minutes = sorted(set(times))
    counts = Counter(times)
    before = 0
    weights = {}
    for minute in minutes:
        weights[minute] = (before + counts[minute] / 2) / n - .5
        before += counts[minute]
    results = []
    permutations = [list(itertools.permutations(members)) for members in groups]
    for assignment in itertools.product(*permutations):
        moved = [0.] * n
        for slots, payload in zip(groups, assignment):
            for destination, source in zip(slots, payload):
                moved[destination] = residual[source]
        increments = [math.fsum(moved[i] for i, t in enumerate(times) if t == minute) for minute in minutes]
        running = 0.
        excursion = 0.
        for value in increments:
            running += value
            excursion = max(excursion, abs(running))
        gradual = abs(math.fsum(weights[times[i]] * moved[i] for i in range(n)))
        results.append((100 * gradual / sum(nominal), 100 * excursion / sum(nominal),
                        100 * max(map(abs, increments)) / sum(nominal)))
    return results


# The publication comparator is defined below once the primary artifact schema is fixed.


def minute_text(epoch_minute):
    from datetime import timedelta
    return (EPOCH + timedelta(minutes=int(epoch_minute))).strftime('%Y-%m-%d %H:%M:00')


def curve_rows(reference, source, minute):
    data = reference['data']
    scale = 100 / minute['nominal_final']
    for j, candidate in enumerate(data['candidate_numbers']):
        for i in range(len(minute['sections'])):
            denominator = int(minute['cumulative_nominal'][i])
            residual = float(minute['cumulative_residual'][i, j])
            actual = int(minute['cumulative_votes'][i, j])
            expected = actual - residual
            yield dict(model=reference['model'], election_code=data['election_code'], turno=data['turno'],
                source=source, candidate=candidate, minute=minute_text(minute['start'] + i),
                sections_cumulative=int(minute['cumulative_sections'][i]), nominal_cumulative=denominator,
                votes_cumulative=actual, expected_cumulative=expected, residual_cumulative=residual,
                share=100*actual/denominator, composition_share=100*expected/denominator,
                residual_current_pp=100*residual/denominator, residual_final_pp=scale*residual,
                minute_residual_pp_final=scale*float(minute['residual'][i, j]))


def coverage_rows(reference, source):
    data = reference['data']
    selected = reference['selected']
    original_to_selected = np.full(len(data['aptos']), -1, dtype=np.int64)
    original_to_selected[selected] = np.arange(len(selected))
    basic = data['installed'] & ~data['cancelled'] & (data['aptos'] >= 50) & (data['turnout'] > 0) & (data['nominal'] >= 50)
    per_uf = {}
    for uf in [*sorted(set(data['uf'].tolist())), 'BR']:
        raw = np.ones(len(data['aptos']), dtype=bool) if uf == 'BR' else data['uf'] == uf
        cohort = raw[selected]
        per_uf[uf] = dict(detail_sections=int(raw.sum()), eligible_basic=int((basic & raw).sum()),
            cohort_sections=int(cohort.sum()), groups=0, sections_with_peers=0, sections_time_varied=0,
            nominal_total=int(data['nominal'][selected][cohort].sum(dtype=np.int64)),
            informative_groups=np.zeros(len(data['candidate_numbers']), dtype=np.int64),
            informative_sections=np.zeros(len(data['candidate_numbers']), dtype=np.int64))
    for key, members in reference['groups'].items():
        ix = np.asarray(members)
        n = len(ix)
        varied = np.ptp(data[source][ix] // 60) > 0
        informative = np.any(reference['residual'][original_to_selected[ix]] != 0, axis=0) & varied
        for uf in (key[0], 'BR'):
            row = per_uf[uf]
            row['groups'] += 1
            row['sections_with_peers'] += n if n >= 2 else 0
            row['sections_time_varied'] += n if varied else 0
            row['informative_groups'] += informative
            row['informative_sections'] += n * informative
    for uf, info in per_uf.items():
        for j, candidate in enumerate(data['candidate_numbers']):
            row = {field: int(value[j]) if isinstance(value, np.ndarray) else value for field, value in info.items()}
            yield dict(model=reference['model'], election_code=data['election_code'], turno=data['turno'],
                       source=source, candidate=candidate, uf=uf, **row)


def diagnostic_observed(reference, source, minute):
    data = reference['data']
    result = []
    for j, candidate in enumerate(data['candidate_numbers']):
        c_index = int(np.argmax(abs(minute['cumulative_residual'][:, j])))
        m_index = int(np.argmax(abs(minute['residual'][:, j])))
        for index, name in enumerate(('G', 'C', 'M')):
            if name == 'G':
                signed = float(minute['signed_gradual'][j])
                peak = ''
            elif name == 'C':
                signed = float(minute['cumulative_residual'][c_index, j] * 100 / minute['nominal_final'])
                peak = minute_text(minute['start'] + c_index)
            else:
                signed = float(minute['residual'][m_index, j] * 100 / minute['nominal_final'])
                peak = minute_text(minute['start'] + m_index)
            result.append(dict(model=reference['model'], election_code=data['election_code'], turno=data['turno'],
                candidate=candidate, statistic=name, observed=float(minute['statistics'][j, index]),
                signed_observed=signed, peak_minute=peak))
    return result


class Comparisons:
    def __init__(self):
        self.counts = Counter()
        self.failures = []
        self.maximum_error = 0.

    def require(self, value, category, description):
        self.counts[category] += 1
        if not value:
            if len(self.failures) < 100:
                self.failures.append(dict(category=category, description=description))
            self.counts['mismatches'] += 1

    def same(self, actual, expected, category, description, tolerance=0.):
        if isinstance(expected, (int, np.integer)):
            try:
                matches = str(actual).strip() == str(int(expected))
            except (ValueError, TypeError):
                matches = False
        elif isinstance(expected, (float, np.floating)):
            try:
                error = abs(float(actual) - float(expected))
                self.maximum_error = max(self.maximum_error, error)
                matches = math.isfinite(float(actual)) and error <= tolerance
            except (ValueError, TypeError):
                matches = False
        else:
            matches = actual == expected
        self.require(matches, category, f'{description}: actual={actual!r}, expected={expected!r}')


def read_table(path):
    opener = gzip.open if Path(path).suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f'Invalid published CSV header: {path}')
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Malformed published CSV row: {path}')
            yield row


def compare_table(path, expected_rows, key_fields, comparisons, category, allow_extra=False):
    """Compare every reconstructed row, detecting duplicate or missing identities."""
    expected = {}
    for row in expected_rows:
        key = tuple(str(row[field]) for field in key_fields)
        if key in expected:
            raise ValueError(f'Duplicate independent expected identity {key}')
        expected[key] = row
    found = set()
    for row in read_table(path):
        key = tuple(row[field] for field in key_fields)
        comparisons.require(key in expected and key not in found, category, f'{path.name}: unknown/duplicate key {key}')
        if key not in expected or key in found:
            continue
        found.add(key)
        target = expected[key]
        if not allow_extra:
            comparisons.require(set(row) == set(target), category, f'{path.name}: column set differs for {key}')
        for field, value in target.items():
            if field.endswith('_json'):
                try:
                    comparisons.require(json.loads(row.get(field, 'null')) == json.loads(value), category, f'{path.name}/{key}/{field}')
                except (TypeError, json.JSONDecodeError):
                    comparisons.require(False, category, f'{path.name}: malformed JSON {key}/{field}')
            else:
                # Cumulative vote-scale expectations can sum millions of floating values.
                tolerance = 1e-7 if field in {'expected_cumulative', 'residual_cumulative'} else 1e-9
                comparisons.same(row.get(field), value, category, f'{path.name}/{key}/{field}', tolerance=tolerance)
    comparisons.require(found == set(expected), category, f'{path.name}: missing {len(set(expected)-found)} reconstructed rows')


def simulation_buckets(reference):
    """Reconstruct exact lexical group ordering and equal-size shuffle buckets."""
    selected = reference['selected']
    location = np.full(len(reference['data']['aptos']), -1, dtype=np.int64)
    location[selected] = np.arange(len(selected))
    by_size = defaultdict(list)
    for members in reference['groups'].values():
        if len(members) >= 2:
            by_size[len(members)].append(location[np.asarray(members)])
    return [np.asarray(by_size[size], dtype=np.int32) for size in sorted(by_size)]


def independent_assignment(reference, seed, model_id, repetition):
    data = reference['data']
    generator = np.random.default_rng(np.random.SeedSequence([int(seed), int(data['turno']), int(model_id)], spawn_key=(int(repetition),)))
    assignment = np.arange(len(reference['selected']), dtype=np.int32)
    for bucket in simulation_buckets(reference):
        assignment[bucket.ravel()] = generator.permuted(bucket, axis=1).ravel()
    return assignment


def moved_statistics(reference, minute, assignment):
    moved = reference['residual'][assignment]
    increments = np.column_stack([np.bincount(minute['bins'], weights=moved[:, j], minlength=len(minute['sections']))
                                   for j in range(moved.shape[1])])
    cumulative = increments.cumsum(axis=0)
    scale = 100 / minute['nominal_final']
    signed_gradual = (minute['midrank'][:, None] * increments).sum(axis=0) * scale
    scores = np.column_stack([abs(signed_gradual), np.max(abs(cumulative), axis=0)*scale,
                              np.max(abs(increments), axis=0)*scale])
    grid = np.zeros((101, moved.shape[1]))
    grid[1:] = cumulative[minute['checkpoints'][1:]] * scale
    return scores, grid


def monte_carlo_reference(cache_path, reference, minutes, seed, comparisons, sample_repetitions=(0,1)):
    """Audit retained arrays and repeat selected full assignments independently."""
    data = reference['data']
    folder = Path(cache_path) / f'{reference["model"]}-{data["turno"]}'
    scores_path, grid_path = folder / 'scores.npy', folder / 'grid-curves.npy'
    scores = np.load(scores_path, mmap_mode='r', allow_pickle=False)
    grid = np.load(grid_path, mmap_mode='r', allow_pickle=False)
    b = scores.shape[0]
    k = len(data['candidate_numbers'])
    comparisons.require(scores.shape == (b,2,k,3), 'simulation_cache', f'{folder.name}: score shape')
    comparisons.require(grid.shape == (b,2,101,k), 'simulation_cache', f'{folder.name}: curve shape')
    comparisons.require(bool(np.all(np.isfinite(scores))) and bool(np.all(scores>=0)), 'simulation_cache', f'{folder.name}: finite nonnegative scores')
    comparisons.require(bool(np.all(np.isfinite(grid))), 'simulation_cache', f'{folder.name}: finite curves')
    for repetition in sample_repetitions:
        if repetition >= b:
            continue
        assignment = independent_assignment(reference, seed, MODELS.index(reference['model']), repetition)
        for source_index, source in enumerate(SOURCE_NAMES):
            expected_scores, expected_grid = moved_statistics(reference, minutes[source], assignment)
            score_error = float(np.max(abs(scores[repetition, source_index] - expected_scores)))
            curve_error = float(np.max(abs(grid[repetition, source_index] - expected_grid)))
            comparisons.maximum_error = max(comparisons.maximum_error, score_error, curve_error)
            comparisons.require(score_error <= 1e-9, 'simulation_assignment', f'{folder.name}/{source}/{repetition}: score error {score_error}')
            comparisons.require(curve_error <= 1e-9, 'simulation_assignment', f'{folder.name}/{source}/{repetition}: curve error {curve_error}')
    return scores, grid


def milestone_rows(reference, source, minute):
    data = reference['data']
    for j, candidate in enumerate(data['candidate_numbers']):
        for stage in (1,5,10,25,50,75,90,95,99,100):
            i = int(minute['checkpoints'][stage])
            denominator = int(minute['cumulative_nominal'][i])
            residual = float(minute['cumulative_residual'][i,j])
            votes = int(minute['cumulative_votes'][i,j])
            yield dict(model=reference['model'], election_code=data['election_code'], turno=data['turno'],
                source=source, candidate=candidate, stage=stage, cutoff_minute=minute_text(minute['start']+i),
                progress_actual=100*int(minute['cumulative_sections'][i])/len(reference['selected']),
                sections_cumulative=int(minute['cumulative_sections'][i]), nominal_cumulative=denominator,
                share=100*votes/denominator, composition_share=100*(votes-residual)/denominator,
                residual_current_pp=100*residual/denominator, residual_final_pp=100*residual/minute['nominal_final'])


def sensitivity_rows(reference, source, minute, scenario):
    data = reference['data']
    supports = {row['candidate']: row['informative_sections'] for row in coverage_rows(reference,source) if row['uf']=='BR'}
    for j, candidate in enumerate(data['candidate_numbers']):
        ci = int(np.argmax(abs(minute['cumulative_residual'][:,j])))
        mi = int(np.argmax(abs(minute['residual'][:,j])))
        yield dict(scenario=scenario, model=reference['model'], election_code=data['election_code'], turno=data['turno'],
            source=source, candidate=candidate, G_signed=float(minute['signed_gradual'][j]),
            G=float(minute['statistics'][j,0]), C=float(minute['statistics'][j,1]), M=float(minute['statistics'][j,2]),
            C_minute=minute_text(minute['start']+ci), M_minute=minute_text(minute['start']+mi),
            cohort_sections=len(reference['selected']), nominal_total=minute['nominal_final'],
            informative_sections=int(supports[candidate]))


def state_rows(reference, source):
    data = reference['data']
    ix = reference['selected']
    for uf in sorted(set(data['uf'][ix].tolist())):
        keep = data['uf'][ix] == uf
        subset = dict(data=data, selected=ix[keep], residual=reference['residual'][keep])
        minute = minute_reference(subset,source)
        for j, candidate in enumerate(data['candidate_numbers']):
            ci = int(np.argmax(abs(minute['cumulative_residual'][:,j])))
            mi = int(np.argmax(abs(minute['residual'][:,j])))
            yield dict(model=reference['model'], election_code=data['election_code'], turno=data['turno'],
                source=source, candidate=candidate, uf=uf, sections=int(keep.sum()), nominal_total=minute['nominal_final'],
                final_share=100*int(data['candidate_votes'][ix[keep],j].sum())/minute['nominal_final'],
                G_signed=float(minute['signed_gradual'][j]), C=float(minute['statistics'][j,1]), M=float(minute['statistics'][j,2]),
                C_minute=minute_text(minute['start']+ci), M_minute=minute_text(minute['start']+mi))


def span_rows(reference, source):
    data=reference['data']
    spans=[]
    sizes=[]
    for members in reference['groups'].values():
        if len(members)>=2:
            minutes=data[source][np.asarray(members)]//60
            spans.append(int(minutes.max()-minutes.min()))
            sizes.append(len(members))
    spans=np.asarray(spans,dtype=np.int64)
    sizes=np.asarray(sizes,dtype=np.int64)
    common=dict(model=reference['model'],election_code=data['election_code'],turno=data['turno'],source=source)
    rows=[]
    for threshold in (0,1,5,15,30,60):
        use=spans>=threshold
        rows.append(dict(common,threshold_minutes=threshold,groups=int(use.sum()),sections=int(sizes[use].sum())))
    quantiles=np.quantile(spans,[0,.25,.5,.75,.95,1])
    summary=dict(common,nonsingleton_groups=len(spans),span_min=float(quantiles[0]),span_q25=float(quantiles[1]),
        span_median=float(quantiles[2]),span_q75=float(quantiles[3]),span_q95=float(quantiles[4]),span_max=float(quantiles[5]))
    return rows,summary


def eligibility_rows(data):
    eligible,reasons=eligibility(data)
    basic=data['installed'] & ~data['cancelled'] & (data['aptos']>=50) & (data['turnout']>0) & (data['nominal']>=50)
    labels=('section_status','aptos_below_50','nonpositive_turnout','nominal_below_floor','missing_place','missing_time')
    for uf in ['BR',*sorted(set(data['uf'].tolist()))]:
        use=np.ones(len(eligible),dtype=bool) if uf=='BR' else data['uf']==uf
        yield dict(election_code=data['election_code'],turno=data['turno'],uf=uf,detail_sections=int(use.sum()),
            eligible_basic=int((use&basic).sum()),cohort_sections=int((use&eligible).sum()),
            **{f'excluded_{label}':int((use&(reasons==label)).sum()) for label in labels})


def band_rows(reference, source, minute, scores, grid):
    data=reference['data']
    s=SOURCE_NAMES.index(source)
    mean=np.mean(grid[:,s],axis=0)
    limits=np.quantile(grid[:,s],[.025,.975],axis=0)
    for j,candidate in enumerate(data['candidate_numbers']):
        for stage in range(101):
            i=int(minute['checkpoints'][stage])
            yield dict(model=reference['model'],election_code=data['election_code'],turno=data['turno'],source=source,
                candidate=candidate,stage=stage,cutoff_minute='' if stage==0 else minute_text(minute['start']+i),
                progress_actual=0. if stage==0 else 100*int(minute['cumulative_sections'][i])/len(reference['selected']),
                observed=0. if stage==0 else 100*float(minute['cumulative_residual'][i,j])/minute['nominal_final'],
                simulation_mean=float(mean[stage,j]),simulation_q025=float(limits[0,stage,j]),simulation_q975=float(limits[1,stage,j]))



def score_applicability(reference, source, minute, candidate_index, statistic_index, observed, simulated, support):
    """Certify nondegeneracy by witnesses, or independently enumerate small cases."""
    tolerance=1e-12
    if not support:
        return False,'no_informative_groups'
    values=np.asarray(simulated)
    if max(float(values.max()),observed)-min(float(values.min()),observed)>tolerance:
        return True,'sampled_distinct_scores'
    import itertools
    locations={int(original):i for i,original in enumerate(reference['selected'])}
    active=[]
    product=1
    for members in reference['groups'].values():
        local=np.asarray([locations[i] for i in members])
        if np.ptp(reference['data'][source][np.asarray(members)]//60)==0 or not np.any(reference['residual'][local,candidate_index]):
            continue
        if len(local)>8:
            raise ValueError('Cannot independently certify constant-score applicability without an excessive enumeration')
        product*=math.factorial(len(local))
        if product>40320:
            raise ValueError('Cannot independently certify constant-score applicability within enumeration limit')
        active.append(local)
    base=minute['residual'][:,candidate_index].copy()
    for local in active:
        np.add.at(base,minute['bins'][local],-reference['residual'][local,candidate_index])
    minimum=maximum=None
    assignments=[list(itertools.permutations(local.tolist())) for local in active]
    for chosen in itertools.product(*assignments):
        arrivals=base.copy()
        for slots,payload in zip(active,chosen):
            np.add.at(arrivals,minute['bins'][slots],reference['residual'][np.asarray(payload),candidate_index])
        if statistic_index==0:
            value=abs(float(np.dot(minute['midrank'],arrivals)))*100/minute['nominal_final']
        elif statistic_index==1:
            value=float(np.max(abs(arrivals.cumsum())))*100/minute['nominal_final']
        else:
            value=float(np.max(abs(arrivals)))*100/minute['nominal_final']
        minimum=value if minimum is None else min(minimum,value)
        maximum=value if maximum is None else max(maximum,value)
        if maximum-minimum>tolerance:
            return True,'exact_enumeration_variable'
    return False,'exact_enumeration_constant'


def simulation_rows(reference, source, minute, scores):
    data=reference['data']
    s=SOURCE_NAMES.index(source)
    quantiles=np.quantile(scores[:,s],[.025,.975],axis=0)
    means=np.mean(scores[:,s],axis=0)
    supports={row['candidate']:row['informative_sections'] for row in coverage_rows(reference,source) if row['uf']=='BR'}
    results=[]
    for row in diagnostic_observed(reference,source,minute):
        j=data['candidate_numbers'].index(row['candidate'])
        statistic=('G','C','M').index(row['statistic'])
        row.update(source=source,simulation_mean=float(means[j,statistic]),
            simulation_q025=float(quantiles[0,j,statistic]),simulation_q975=float(quantiles[1,j,statistic]),
            informative_sections=int(supports[row['candidate']]))
        results.append(row)
    return results


def validate_analysis(root, analysis, cache, simulation_cache, output):
    root,analysis,cache,simulation_cache,output=map(Path,(root,analysis,cache,simulation_cache,output))
    if output.exists():
        raise ValueError('Refusing to overwrite an existing validation result')
    comparisons=Comparisons()
    rounds,metadata=independent_data(root,cache)
    manifest=json.loads((analysis/'manifest.json').read_text())
    comparisons.require(manifest.get('status')=='completed','provenance','Completed primary manifest')
    comparisons.require(manifest.get('source_inputs')==metadata['source_inputs'],'provenance','Original snapshots match independent source scan')
    comparisons.same(manifest.get('method_sha256'),digest_file(HERE/'METHOD.pt-BR.md'),'provenance','Frozen protocol hash')
    for name,value in manifest.get('implementation_sha256',{}).items():
        comparisons.same(value,digest_file(HERE/'code'/name),'provenance',f'Primary code fingerprint {name}')
    artifacts=manifest.get('artifacts',{})
    comparisons.require(bool(artifacts),'publication_integrity','Primary artifact set is nonempty')
    actual_names={path.name for path in analysis.iterdir() if path.is_file() and path.name!='manifest.json'}
    comparisons.require(actual_names==set(artifacts),'publication_integrity','Primary artifact file set')
    for name,entry in artifacts.items():
        path=analysis/name
        comparisons.same(digest_file(path),entry['sha256'],'publication_integrity',name)
        comparisons.same(path.stat().st_size,int(entry['size_bytes']),'publication_integrity',name)
    parameters=manifest['parameters']
    comparisons.require(parameters.get('models')=={'zone_size':0,'place_size':1},'configuration','Fixed two reference models')
    comparisons.require(parameters.get('statistics')==['G','C','M'],'configuration','Fixed three statistics')
    comparisons.require(parameters.get('sources')==list(SOURCE_NAMES),'configuration','Paired timestamp sources')
    comparisons.same(parameters.get('family_size'),90,'configuration','Fixed 90-member family')
    comparisons.same(parameters.get('p_tolerance'),1e-12,'configuration','P-value tolerance',tolerance=0.)
    seed=int(parameters['seed'])
    tables=defaultdict(list)
    all_tests=[]
    independently_repeated=[]
    summaries=[]
    for data in rounds:
        tables['eligibility.csv'].extend(eligibility_rows(data))
        for model in MODELS:
            print(f'Independent H4 reference: {model}/turn {data["turno"]}',file=sys.stderr,flush=True)
            reference=model_reference(data,model)
            minutes={source:minute_reference(reference,source) for source in SOURCE_NAMES}
            tables['group-totals.csv.gz'].extend(reference['group_rows'])
            for source in SOURCE_NAMES:
                minute=minutes[source]
                tables['curves.csv.gz'].extend(curve_rows(reference,source,minute))
                tables['coverage.csv'].extend(coverage_rows(reference,source))
                tables['milestones.csv'].extend(milestone_rows(reference,source,minute))
                tables['uf-summary.csv'].extend(state_rows(reference,source))
                tables['sensitivity.csv'].extend(sensitivity_rows(reference,source,minute,'primary'))
                spans,span_summary=span_rows(reference,source)
                tables['group-spans.csv'].extend(spans)
                tables['span-summary.csv'].append(span_summary)
            folder=simulation_cache/f'{model}-{data["turno"]}'
            simulation_metadata=json.loads((folder/'metadata.json').read_text())
            comparisons.require(simulation_metadata.get('status')=='completed','simulation_cache',f'{folder.name}: completed cache')
            comparisons.require(simulation_metadata.get('seed')==seed and simulation_metadata.get('model')==model
                and simulation_metadata.get('turno')==data['turno'],'simulation_cache',f'{folder.name}: configuration')
            comparisons.require(simulation_metadata.get('candidate_numbers')==data['candidate_numbers'],'simulation_cache',f'{folder.name}: candidate order')
            comparisons.require(simulation_metadata.get('sources')==list(SOURCE_NAMES) and simulation_metadata.get('statistics')==['G','C','M'],
                'simulation_cache',f'{folder.name}: source/statistic order')
            for name in ('scores.npy','grid-curves.npy'):
                comparisons.same(digest_file(folder/name),simulation_metadata['sha256'][name],'simulation_cache',f'{folder.name}/{name}')
            registered=[entry for entry in manifest.get('simulation_caches',[]) if entry.get('metadata',{}).get('model')==model
                and entry.get('metadata',{}).get('turno')==data['turno']]
            comparisons.require(len(registered)==1,'simulation_cache',f'{folder.name}: uniquely registered cache')
            if len(registered)==1:
                comparisons.require(registered[0]['metadata']==simulation_metadata,'simulation_cache',f'{folder.name}: metadata identical')
                comparisons.same(digest_file(folder/'metadata.json'),registered[0]['metadata_sha256'],'simulation_cache',f'{folder.name}: metadata hash')
            scores,grid=monte_carlo_reference(simulation_cache,reference,minutes,seed,comparisons)
            comparisons.same(len(scores),int(parameters['simulations']),'simulation_cache',f'{folder.name}: simulation count')
            independently_repeated.append(dict(model=model,turno=data['turno'],repetitions=[0,1],
                all_primary_scores_differ_between_independently_repeated_assignments=bool(len(scores)>1 and np.all(scores[0,0] != scores[1,0]))))
            for source in SOURCE_NAMES:
                rows=simulation_rows(reference,source,minutes[source],scores)
                tables['mc-quantiles.csv'].extend(rows)
                tables['bands.csv'].extend(band_rows(reference,source,minutes[source],scores,grid))
                if source=='first_time':
                    for row in rows:
                        row=dict(row)
                        row.pop('source')
                        j=data['candidate_numbers'].index(row['candidate'])
                        k=('G','C','M').index(row['statistic'])
                        exceeded=int(np.count_nonzero(scores[:,0,j,k]>=row['observed']-1e-12))
                        applicable,reason=score_applicability(reference,source,minutes[source],j,k,row['observed'],scores[:,0,j,k],row['informative_sections'])
                        row.update(simulations=len(scores),exceedances=exceeded,
                            p_raw=(exceeded+1)/(len(scores)+1) if applicable else '',
                            p_holm='',detected='',status='applicable' if applicable else 'not_applicable',applicability_reason=reason)
                        all_tests.append(row)
            summaries.append(dict(model=model,turno=data['turno'],cohort_sections=len(reference['selected']),
                groups=len(reference['groups']),candidate_numbers=data['candidate_numbers']))
        # Every predeclared descriptive alternative is reconstructed, not merely linked.
        for model,floor,scenario in [('place_no_size',50,'place_no_size'),('zone_size',100,'nominal_100'),('place_size',100,'nominal_100')]:
            reference=model_reference(data,model,min_nominal=floor)
            for source in SOURCE_NAMES:
                tables['sensitivity.csv'].extend(sensitivity_rows(reference,source,minute_reference(reference,source),scenario))
    comparisons.same(len(all_tests),90,'family','Number of reconstructed primary tests')
    pvalues={tuple(row[field] for field in ('model','election_code','turno','candidate','statistic')):
        row['p_raw'] if row['status']=='applicable' else 1. for row in all_tests}
    adjusted=holm_reference(pvalues)
    for row in all_tests:
        if row['status']=='applicable':
            key=tuple(row[field] for field in ('model','election_code','turno','candidate','statistic'))
            row['p_holm']=adjusted[key]
            row['detected']=str(adjusted[key]<=.05)
            row['status']='detected' if adjusted[key]<=.05 else 'not_detected'
    tables['tests.csv']=all_tests
    schemas={
        'group-totals.csv.gz':('model','election_code','turno','uf','municipality','zone','place','size_band'),
        'curves.csv.gz':('model','election_code','turno','source','candidate','minute'),
        'coverage.csv':('model','election_code','turno','source','candidate','uf'),
        'tests.csv':('model','election_code','turno','candidate','statistic'),
        'bands.csv':('model','election_code','turno','source','candidate','stage'),
        'sensitivity.csv':('scenario','model','election_code','turno','source','candidate'),
        'milestones.csv':('model','election_code','turno','source','candidate','stage'),
        'uf-summary.csv':('model','election_code','turno','source','candidate','uf'),
        'group-spans.csv':('model','election_code','turno','source','threshold_minutes'),
        'span-summary.csv':('model','election_code','turno','source'),
        'eligibility.csv':('election_code','turno','uf'),
        'mc-quantiles.csv':('model','election_code','turno','source','candidate','statistic'),
    }
    row_counts={}
    for name,keys in schemas.items():
        print(f'Independent H4 compare: {name} ({len(tables[name]):,} rows)',file=sys.stderr,flush=True)
        compare_table(analysis/name,tables[name],keys,comparisons,name)
        row_counts[name]=len(tables[name])
    summary=json.loads((analysis/'summary.json').read_text())
    for field,expected in [('family_size',90),('primary_detected',sum(row['status']=='detected' for row in all_tests)),
        ('primary_not_detected',sum(row['status']=='not_detected' for row in all_tests)),
        ('primary_not_applicable',sum(row['status']=='not_applicable' for row in all_tests))]:
        comparisons.same(summary.get(field),expected,'summary',field)
    comparisons.require(summary.get('candidate_numbers')=={str(data['turno']):data['candidate_numbers'] for data in rounds},'summary','Candidate inventory')
    # Verify source immutability at completion; original parser cache remains snapshot-specific.
    for kind,source in metadata['source_inputs'].items():
        comparisons.same(digest_file(root/source['path']),source['sha256'],'source_immutability',kind)
    result=dict(status='passed' if not comparisons.counts['mismatches'] else 'failed',
        completed_at_utc=datetime.now(timezone.utc).isoformat(),script_sha256=digest_file(Path(__file__)),
        independent_parser_fingerprint=parser_fingerprint(),source_inputs=metadata['source_inputs'],
        independent_source_counts=metadata['source_counts'],
        parameters=dict(simulations=int(parameters['simulations']),seed=seed,primary_family_size=90,
                        p_resolution=1/(int(parameters['simulations'])+1)),comparisons=dict(comparisons.counts),
        mismatches=int(comparisons.counts['mismatches']),maximum_absolute_numeric_difference=comparisons.maximum_error,
        numeric_tolerances=dict(cumulative_vote_scale=1e-7,shares_scores_and_quantiles=1e-9,p_value_comparisons=1e-9),
        rows_validated=row_counts,independent_models=summaries,failures=comparisons.failures,
        simulation_scope=dict(all_retained_scores_and_grid_curves='SHA-256 verified; all published ranks, Holm adjustments, means and quantiles recomputed',
            assignment_generation='Two full assignments per round/reference repeated independently, for both timestamp sources and every candidate',
            repeated_assignments=independently_repeated,full_simulation_repeated=False),
        sensitivity_scope='All declared descriptive alternatives independently reconstructed from original sources',
        interpretation='Internal conditional-order validation; neither causal attribution nor independent authentication of source records')
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
    print(json.dumps({key:result[key] for key in ('status','mismatches','maximum_absolute_numeric_difference')}))
    raise SystemExit(0 if result['status']=='passed' else 1)


if __name__=='__main__':
    main()
