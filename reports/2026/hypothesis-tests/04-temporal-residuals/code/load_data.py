#!/usr/bin/env python3
"""Prepare H4 arrays directly from the original CSVs; no replay DB dependency.

No observations are excluded here. H4's analysis selects its own eligible rows.
The pinned, completed H1 audit establishes vote-key uniqueness; this loader also
checks detail-key uniqueness and reconciles every section's category totals.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parents[1]
SOURCE_PATHS = {
    'votes': 'data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv',
    'details': 'data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv',
}
KEY_FIELDS = ('CD_ELEICAO', 'NR_TURNO', 'SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO', 'CD_CARGO')
METRICS = {
    'aptos': 'QT_APTOS', 'turnout': 'QT_COMPARECIMENTO', 'abstentions': 'QT_ABSTENCOES',
    'nominal': 'QT_VOTOS_NOMINAIS', 'blank': 'QT_VOTOS_BRANCOS', 'null_votes': 'QT_VOTOS_NULOS',
    'legend': 'QT_VOTOS_LEGENDA', 'separate': 'QT_VOTOS_ANULADOS_APU_SEP',
}
KEY_PACKER = struct.Struct('>7I')
H1_ESSENTIAL_CHECKS = {
    'unique_detail_key', 'unique_vote_key', 'detail_quantities_complete',
    'detail_quantities_nonnegative', 'vote_quantities_complete', 'vote_quantities_nonnegative',
    'vote_section_has_unique_detail', 'source_votes_equal_turnout',
    'reconcile_nominal', 'reconcile_blank', 'reconcile_null_votes', 'reconcile_separate',
    'presidential_legend_zero',
}
INT32_MAX = np.iinfo(np.int32).max
MISSING = {'', '#NULO', '#NE', '-1', '-3'}
TIME_FIELDS = {
    'first_time': 'DT_PRIM_TOT_PARCIAL_HOR_TSE',
    'bu_time': 'DT_RECEBIMENTO_BU_HOR_TSE',
}
EPOCH = datetime(1970, 1, 1)
TIME_CONVENTION = ('Hora TSE wall-clock seconds since a naive 1970-01-01 epoch; '
                   'not UTC or POSIX instants; no timezone conversion; missing=-1')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _json_write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temporary.replace(path)


def _csv_rows(path, required):
    with Path(path).open('rb') as stream:
        if stream.read(100).startswith(b'version https://git-lfs.github.com/spec/v1'):
            raise ValueError(f'{path}: Git LFS pointer, not original CSV data')
    with Path(path).open(encoding='latin1', newline='') as stream:
        reader = csv.reader(stream, delimiter=';')
        header = next(reader, [])
        if len(header) != len(set(header)):
            raise ValueError(f'{path}: duplicate header columns')
        missing = set(required) - set(header)
        if missing:
            raise ValueError(f'{path}: missing columns {sorted(missing)}')
        positions = {field: index for index, field in enumerate(header)}
        for line, row in enumerate(reader, 2):
            if len(row) != len(header):
                raise ValueError(f'{path}:{line}: malformed CSV row')
            yield line, row, positions


def _nonnegative(raw, field):
    raw = raw.strip()
    if not re.fullmatch('[0-9]+', raw):
        raise ValueError(f'{field}: missing, negative or invalid integer {raw!r}')
    number = int(raw)
    if number > INT32_MAX:
        raise ValueError(f'{field}: quantity outside int32 range')
    return number


def _flag(raw, field):
    value = raw.strip().casefold()
    if value in {'s', 'sim'}:
        return True
    if value in {'n', 'não', 'nao'}:
        return False
    raise ValueError(f'{field}: unknown flag {raw!r}')


def _timestamp(raw, field):
    """Parse exact local date/time strings without inventing a UTC offset.

    Seconds are stored as an int64 coordinate on the unconverted wall clock,
    not as an assertion that Hora TSE equals UTC. Missing values stay missing.
    Fractional seconds and timezone suffixes are rejected rather than rounded.
    """
    value = raw.strip()
    if value.upper() in MISSING:
        return -1
    if re.fullmatch(r'[0-9]{2}/[0-9]{2}/[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}', value):
        fmt = '%d/%m/%Y %H:%M:%S'
    elif re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}', value):
        fmt = '%Y-%m-%dT%H:%M:%S' if 'T' in value else '%Y-%m-%d %H:%M:%S'
    else:
        raise ValueError(f'{field}: invalid local timestamp {value!r}')
    try:
        parsed = datetime.strptime(value, fmt)
    except ValueError as error:
        raise ValueError(f'{field}: invalid local timestamp {value!r}') from error
    if parsed < EPOCH:
        raise ValueError(f'{field}: timestamp predates the wall-clock epoch')
    return int((parsed - EPOCH).total_seconds())


def _optional_identifier(raw, field):
    return -1 if raw.strip().upper() in MISSING else _nonnegative(raw, field)


def _timing_summary(values):
    valid = values[values >= 0]
    minimum = int(valid.min()) if len(valid) else None
    maximum = int(valid.max()) if len(valid) else None
    return dict(valid=int(len(valid)), missing=int(len(values) - len(valid)),
                min_seconds=minimum, max_seconds=maximum,
                min_local=(EPOCH + timedelta(seconds=minimum)).isoformat(sep=' ') if minimum is not None else None,
                max_local=(EPOCH + timedelta(seconds=maximum)).isoformat(sep=' ') if maximum is not None else None)


def _key(row, columns):
    values = []
    for field in KEY_FIELDS:
        raw = row[columns[field]].strip()
        if field == 'SG_UF':
            raw = raw.upper()
            if not re.fullmatch('[A-Z]{2}', raw):
                raise ValueError(f'Invalid UF {raw!r}')
            values.append(raw)
        else:
            values.append(_nonnegative(raw, field))
    if values[1] not in {1, 2} or values[-1] != 1:
        raise ValueError('Unsupported presidential section scope')
    packed = KEY_PACKER.pack(values[0], values[1], int.from_bytes(values[2].encode('ascii'), 'big'), *values[3:])
    return packed, tuple(values)


def _selected(row, columns):
    if int(row[columns['ANO_ELEICAO']]) != 2026 or int(row[columns['CD_CARGO']]) != 1:
        return False
    if row[columns['DS_CARGO']].strip().casefold() != 'presidente' or row[columns['SG_UE']].strip().upper() != 'BR':
        raise ValueError('Inconsistent presidential source scope')
    return True


def _validated_inputs(root):
    stage1_path = root / 'reports/2026/input-manifest.json'
    h1_path = root / 'reports/2026/hypothesis-tests/01-accounting-integrity/evidence/accounting/manifest.json'
    stage1 = json.loads(stage1_path.read_text())
    h1 = json.loads(h1_path.read_text())
    if stage1.get('status') != 'completed' or h1.get('status') != 'completed' or h1.get('hypothesis') != 'H1':
        raise ValueError('Completed stage 1 and H1 manifests are required')
    sources = {}
    for name, relative in SOURCE_PATHS.items():
        path = root / relative
        with path.open('rb') as stream:
            if stream.read(100).startswith(b'version https://git-lfs.github.com/spec/v1'):
                raise ValueError(f'{path}: Git LFS pointer, not original CSV data')
        actual = dict(path=relative, size_bytes=path.stat().st_size, sha256=sha256(path))
        for baseline in (stage1['inputs'][name], h1['inputs'][name]):
            if actual['sha256'] != baseline['sha256'] or actual['size_bytes'] != baseline['size_bytes']:
                raise ValueError(f'{name}: source does not match the completed stage 1/H1 snapshot')
        sources[name] = actual
    h1_files = {}
    for filename in ('checks.csv', 'totals.csv'):
        path = h1_path.parent / filename
        actual_hash = sha256(path)
        if actual_hash != h1['artifact_sha256'].get(filename):
            raise ValueError(f'H1 {filename}: artifact hash mismatch')
        h1_files[filename] = actual_hash
    with (h1_path.parent / 'checks.csv').open(newline='', encoding='utf-8') as stream:
        national = [row for row in csv.DictReader(stream) if row['uf'] == 'BR']
    by_scope = defaultdict(dict)
    for row in national:
        cid = row['check']
        scope = (int(row['election_code']), int(row['turno']))
        if cid in by_scope[scope]:
            raise ValueError('Repeated check in completed H1 evidence')
        by_scope[scope][cid] = row
    if not by_scope:
        raise ValueError('H1 check inventory is empty')
    for scope, checks in by_scope.items():
        if not H1_ESSENTIAL_CHECKS <= checks.keys():
            raise ValueError(f'H1 essential check missing for {scope}')
        for cid in H1_ESSENTIAL_CHECKS:
            row = checks[cid]
            if int(row['violations']) or int(row['not_comparable']):
                raise ValueError(f'H1 prerequisite not satisfied: {scope}/{cid}')
    with (h1_path.parent / 'totals.csv').open(newline='', encoding='utf-8') as stream:
        h1_totals = {(int(row['election_code']), int(row['turno'])): row
                     for row in csv.DictReader(stream) if row['uf'] == 'BR'}
    if h1_totals.keys() != by_scope.keys():
        raise ValueError('H1 scope inventory differs between checks and totals')
    fingerprint = dict(schema_version=2, hypothesis='H4', time_convention=TIME_CONVENTION,
                       loader_code_sha256=sha256(__file__), numpy_version=np.__version__,
                       stage1_manifest_sha256=sha256(stage1_path), h1_manifest_sha256=sha256(h1_path),
                       h1_artifacts=h1_files, source_inputs=sources)
    return sources, fingerprint, h1_totals, h1


def _assert_rounds(rounds, h1_totals):
    if {(r['election_code'], r['turno']) for r in rounds} != h1_totals.keys():
        raise ValueError('Loaded round inventory differs from H1')
    for data in rounds:
        scope = data['election_code'], data['turno']
        expected = h1_totals[scope]
        n = len(data['aptos'])
        if n != int(expected['section_records']):
            raise ValueError(f'{scope}: section count differs from H1')
        if data['candidate_votes'].shape != (n, len(data['candidate_numbers'])):
            raise ValueError('Candidate matrix shape mismatch')
        for field in TIME_FIELDS:
            if data[field].shape != (n,) or data[field].dtype != np.dtype('int64'):
                raise ValueError(f'{field}: timing array must be one-dimensional int64')
            if np.any(data[field] < -1):
                raise ValueError(f'{field}: timing array has an invalid missing sentinel')
        if data['model_urna'].shape != (n,) or data['model_urna'].dtype != np.dtype('int32'):
            raise ValueError('model_urna: identifier array must be one-dimensional int32')
        if np.any(data['model_urna'] < -1):
            raise ValueError('model_urna: invalid missing identifier')
        if np.any(data['candidate_votes'] < 0):
            raise ValueError('Negative candidate vote count')
        if not np.array_equal(data['candidate_votes'].sum(axis=1, dtype=np.int64), data['nominal']):
            raise ValueError(f'{scope}: candidate votes do not reconcile to nominal detail votes')
        if np.any(data['legend'] != 0):
            raise ValueError('Unexpected presidential party-list votes')
        categories = sum(data[f].astype(np.int64) for f in ('nominal', 'blank', 'null_votes', 'legend', 'separate'))
        if not np.array_equal(categories, data['turnout']):
            raise ValueError(f'{scope}: vote categories do not reconcile to turnout')
        for field in METRICS:
            if int(data[field].sum(dtype=np.int64)) != int(expected[field]):
                raise ValueError(f'{scope}/{field}: totals differ from completed H1 evidence')


def _build(root, sources, h1_totals, h1):
    records = {field: [] for field in ('election_code', 'turno', 'uf', 'municipality', 'zone', 'section',
                                      'place', 'source_line', *METRICS, 'installed', 'cancelled',
                                      *TIME_FIELDS, 'model_urna')}
    section_lookup, names, candidate_names = {}, {}, {}
    stats = {'details': Counter(), 'votes': Counter()}
    extraction = {'details': set(), 'votes': set()}
    print('H4 loader: reading original detail CSV', file=sys.stderr, flush=True)
    detail_required = [*KEY_FIELDS, 'ANO_ELEICAO', 'DS_CARGO', 'SG_UE', *METRICS.values(),
                       'ST_SECAO_INSTALADA', 'ST_SECAO_ANULADA', 'NR_LOCAL_VOTACAO', 'NM_MUNICIPIO',
                       *TIME_FIELDS.values()]
    for line, row, cols in _csv_rows(root / SOURCE_PATHS['details'], detail_required):
        stats['details']['rows_read'] += 1
        if not _selected(row, cols):
            stats['details']['excluded_scope_rows'] += 1
            continue
        packed, values = _key(row, cols)
        if packed in section_lookup:
            raise ValueError(f'Duplicate normalized detail key at source line {line}')
        section_lookup[packed] = len(records['aptos'])
        election, turn, uf, municipality, zone, section, _ = values
        for field, value in zip(('election_code', 'turno', 'uf', 'municipality', 'zone', 'section'), values[:6]):
            records[field].append(value)
        for field, source in METRICS.items():
            records[field].append(_nonnegative(row[cols[source]], source))
        place = row[cols['NR_LOCAL_VOTACAO']].strip()
        if place.upper() in {'', '-1', '-3', '#NULO', '#NE'}:
            records['place'].append(-1)
            stats['details']['missing_place_ids'] += 1
        else:
            records['place'].append(_nonnegative(place, 'NR_LOCAL_VOTACAO'))
        records['source_line'].append(line)
        records['installed'].append(_flag(row[cols['ST_SECAO_INSTALADA']], 'ST_SECAO_INSTALADA'))
        records['cancelled'].append(_flag(row[cols['ST_SECAO_ANULADA']], 'ST_SECAO_ANULADA'))
        for field, source in TIME_FIELDS.items():
            parsed = _timestamp(row[cols[source]], source)
            records[field].append(parsed)
            if parsed == -1:
                stats['details'][f'missing_{field}'] += 1
        model = _optional_identifier(row[cols['CD_MODELO_URNA']] if 'CD_MODELO_URNA' in cols else '', 'CD_MODELO_URNA')
        records['model_urna'].append(model)
        if model == -1:
            stats['details']['missing_model_urna'] += 1
        name_key = f'{uf}:{municipality}'
        name = row[cols['NM_MUNICIPIO']].strip()
        names[name_key] = min(names.get(name_key, name), name)
        stats['details']['selected_rows'] += 1
        extraction['details'].add(tuple(row[cols[f]] if f in cols else '' for f in ('DT_GERACAO', 'HH_GERACAO')))
    if not records['aptos']:
        raise ValueError('Detail source contains no selected presidential records')
    records = {field: np.asarray(values, dtype='U2' if field == 'uf' else np.bool_ if field in {'installed', 'cancelled'}
                                else np.int64 if field in TIME_FIELDS else np.int32)
               for field, values in records.items()}
    n = len(records['aptos'])
    candidate_columns, candidates_by_scope = {}, defaultdict(set)
    special = {95: np.zeros(n, dtype=np.int64), 96: np.zeros(n, dtype=np.int64), 97: np.zeros(n, dtype=np.int64)}
    has_votes = np.zeros(n, dtype=np.bool_)
    rows_by_scope = Counter()
    print('H4 loader: reading original voting CSV', file=sys.stderr, flush=True)
    vote_required = [*KEY_FIELDS, 'ANO_ELEICAO', 'DS_CARGO', 'SG_UE', 'NR_VOTAVEL', 'NM_VOTAVEL', 'QT_VOTOS']
    for line, row, cols in _csv_rows(root / SOURCE_PATHS['votes'], vote_required):
        stats['votes']['rows_read'] += 1
        if not _selected(row, cols):
            stats['votes']['excluded_scope_rows'] += 1
            continue
        packed, values = _key(row, cols)
        index = section_lookup.get(packed)
        if index is None:
            raise ValueError(f'Vote source line {line}: no matching detail section')
        number = _nonnegative(row[cols['NR_VOTAVEL']], 'NR_VOTAVEL')
        quantity = _nonnegative(row[cols['QT_VOTOS']], 'QT_VOTOS')
        if number == 0:
            raise ValueError('NR_VOTAVEL must be positive')
        has_votes[index] = True
        scope = values[0], values[1]
        rows_by_scope[scope] += 1
        if number in special:
            special[number][index] += quantity
        else:
            if number not in candidate_columns:
                candidate_columns[number] = np.zeros(n, dtype=np.int64)
            candidate_columns[number][index] += quantity
            candidates_by_scope[scope].add(number)
            name_key = f'{values[1]}:{number}'
            name = row[cols['NM_VOTAVEL']].strip()
            candidate_names[name_key] = min(candidate_names.get(name_key, name), name)
        stats['votes']['selected_rows'] += 1
        extraction['votes'].add(tuple(row[cols[f]] if f in cols else '' for f in ('DT_GERACAO', 'HH_GERACAO')))
        if stats['votes']['selected_rows'] % 1000000 == 0:
            print(f'H4 loader: {stats["votes"]["selected_rows"]:,} vote rows', file=sys.stderr, flush=True)
    if not stats['votes']['selected_rows']:
        raise ValueError('Voting source contains no selected presidential records')
    for number, field in ((95, 'blank'), (96, 'null_votes'), (97, 'separate')):
        if not np.array_equal(special[number], records[field]):
            raise ValueError(f'Original vote/detail category mismatch for {field}')
    rounds, round_counts = [], []
    for election, turn in sorted(set(zip(records['election_code'].tolist(), records['turno'].tolist()))):
        scope = int(election), int(turn)
        index = np.flatnonzero((records['election_code'] == election) & (records['turno'] == turn))
        order = np.lexsort((records['section'][index], records['zone'][index], records['municipality'][index], records['uf'][index]))
        index = index[order]
        data = {field: values[index] for field, values in records.items() if field not in {'election_code', 'turno'}}
        numbers = sorted(candidates_by_scope[scope])
        if not numbers:
            raise ValueError(f'No nominal candidate observed for {scope}')
        matrix = np.column_stack([candidate_columns[number][index] for number in numbers])
        if np.any(matrix > INT32_MAX):
            raise ValueError('Candidate section total outside int32 range')
        data.update(election_code=scope[0], turno=scope[1], candidate_numbers=numbers,
                    candidate_votes=matrix.astype(np.int32))
        rounds.append(data)
        round_counts.append(dict(election_code=scope[0], turno=scope[1], detail_rows=len(index),
                                 vote_rows=rows_by_scope[scope], vote_sections=int(has_votes[index].sum()),
                                 detail_only_sections=int((~has_votes[index]).sum()), candidate_numbers=numbers,
                                 timing={field: _timing_summary(data[field]) for field in TIME_FIELDS},
                                 missing_model_urna=int((data['model_urna'] == -1).sum()),
                                 totals={field: int(data[field].sum(dtype=np.int64)) for field in METRICS},
                                 candidate_vote_totals={str(number): int(matrix[:, i].sum(dtype=np.int64)) for i, number in enumerate(numbers)}))
    _assert_rounds(rounds, h1_totals)
    for kind in ('details', 'votes'):
        expected = h1.get('ingestion', {}).get(kind, {}).get('counts', {})
        for field in ('rows_read', 'selected_rows'):
            if field in expected and stats[kind][field] != expected[field]:
                raise ValueError(f'{kind}/{field}: row count differs from H1')
    source_counts = {kind: dict(stats[kind], extraction_values=sorted(extraction[kind])) for kind in ('details', 'votes')}
    source_counts.update(rounds=round_counts,
                         vote_key_uniqueness='Asserted from zero-violation completed H1 unique_vote_key checks for exactly these source hashes; not re-inferred from summed candidate vectors',
                         detail_key_uniqueness='Checked directly during this source scan',
                         missing_candidate_rows='Zero-filled only for existing detail keys; all section/category totals reconciled exactly',
                         missing_place_ids='Represented as -1, never replaced by an existing polling place',
                         missing_model_urna='Represented as -1; optional source column, never inferred from another field',
                         time_convention=TIME_CONVENTION)
    return dict(rounds=rounds, source_inputs=sources, source_counts=source_counts,
                names=names, candidate_names=candidate_names)


def load_data(root: Path, cache_dir: Path):
    root, cache_dir = Path(root).resolve(), Path(cache_dir).resolve()
    sources, fingerprint, h1_totals, h1 = _validated_inputs(root)
    metadata_path, arrays_path = cache_dir / 'metadata.json', cache_dir / 'arrays.npz'
    if cache_dir.exists() and any(cache_dir.iterdir()):
        if not metadata_path.is_file() or not arrays_path.is_file():
            raise ValueError('Refusing unknown/non-completed nonempty data cache; choose a new cache directory')
        metadata = json.loads(metadata_path.read_text())
        if metadata.get('status') != 'completed' or metadata.get('fingerprint') != fingerprint:
            raise ValueError('Data cache fingerprint differs or run is incomplete; choose a new cache directory')
        if metadata.get('arrays_sha256') != sha256(arrays_path):
            raise ValueError('Data cache array hash mismatch')
        rounds = []
        with np.load(arrays_path, allow_pickle=False) as archive:
            for i, description in enumerate(metadata['rounds']):
                data = {field: archive[f'r{i}_{field}'] for field in description['array_fields']}
                data.update(election_code=description['election_code'], turno=description['turno'],
                            candidate_numbers=description['candidate_numbers'])
                rounds.append(data)
        _assert_rounds(rounds, h1_totals)
        return dict(rounds=rounds, source_inputs=sources, source_counts=metadata['source_counts'],
                    names=metadata['names'], candidate_names=metadata['candidate_names'],
                    cache_reused=True, cache_fingerprint=fingerprint)
    cache_dir.mkdir(parents=True, exist_ok=True)
    metadata = dict(status='running', started_at_utc=datetime.now(timezone.utc).isoformat(), fingerprint=fingerprint)
    _json_write(metadata_path, metadata)
    try:
        data = _build(root, sources, h1_totals, h1)
        for name, source in sources.items():
            if sha256(root / source['path']) != source['sha256']:
                raise ValueError(f'{name}: source changed during data loading')
        arrays = {}
        descriptions = []
        for i, round_data in enumerate(data['rounds']):
            array_fields = sorted(field for field, value in round_data.items() if isinstance(value, np.ndarray))
            arrays.update({f'r{i}_{field}': round_data[field] for field in array_fields})
            descriptions.append(dict(election_code=round_data['election_code'], turno=round_data['turno'],
                                     candidate_numbers=round_data['candidate_numbers'], array_fields=array_fields))
        temporary = cache_dir / 'arrays.tmp.npz'
        np.savez_compressed(temporary, **arrays)
        temporary.replace(arrays_path)
        metadata.update(status='completed', completed_at_utc=datetime.now(timezone.utc).isoformat(),
                        arrays_sha256=sha256(arrays_path), arrays_size_bytes=arrays_path.stat().st_size,
                        rounds=descriptions, source_counts=data['source_counts'], names=data['names'],
                        candidate_names=data['candidate_names'])
        _json_write(metadata_path, metadata)
        data.update(cache_reused=False, cache_fingerprint=fingerprint)
        return data
    except Exception as error:
        metadata.update(status='failed', error=str(error))
        _json_write(metadata_path, metadata)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--cache', type=Path, default=HERE / '.work/data')
    args = parser.parse_args()
    data = load_data(args.root, args.cache)
    print(json.dumps(dict(cache_reused=data['cache_reused'], source_counts=data['source_counts']), ensure_ascii=False))


if __name__ == '__main__':
    main()
