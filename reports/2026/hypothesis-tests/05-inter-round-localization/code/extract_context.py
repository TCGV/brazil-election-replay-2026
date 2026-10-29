#!/usr/bin/env python3
"""Extract original detail fields for descriptive H5 selections, without new tests.

Selection is the union of every strict screening priority and every cohort
section in each target attaining the published MAX under either reference.
The original source and selection tables are hash checked before use. Names,
addresses, equipment, and origin are context, never causal classifications.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
KEY_FIELDS = ('uf', 'municipality', 'zone', 'section')
PLACE_FIELDS = ('uf', 'municipality', 'zone', 'place')
INPUT_NAMES = ('tests.csv', 'place-results.csv.gz', 'section-screening.csv.gz',
               'paired-sections.csv.gz')
SOURCE_FIELDS = (
    'DT_GERACAO', 'HH_GERACAO', 'ANO_ELEICAO', 'CD_ELEICAO', 'NR_TURNO',
    'SG_UF', 'SG_UE', 'CD_MUNICIPIO', 'NM_MUNICIPIO', 'NR_ZONA', 'NR_SECAO',
    'CD_CARGO', 'DS_CARGO', 'NR_LOCAL_VOTACAO', 'NM_LOCAL_VOTACAO',
    'DS_LOCAL_VOTACAO_ENDERECO', 'DS_ORIGEM_VOTO', 'CD_MODELO_URNA',
    'DS_MODELO_URNA', 'ST_SECAO_INSTALADA', 'ST_SECAO_ANULADA', 'QT_APTOS',
    'QT_COMPARECIMENTO', 'QT_ABSTENCOES', 'QT_VOTOS_NOMINAIS', 'QT_VOTOS_BRANCOS',
    'QT_VOTOS_NULOS', 'QT_VOTOS_LEGENDA', 'QT_VOTOS_ANULADOS_APU_SEP',
    'DT_RECEBIMENTO_BU_HOR_TSE', 'DT_PRIM_TOT_PARCIAL_HOR_TSE',
)
OUTPUT_COLUMNS = ('selected_because', 'source_line', *SOURCE_FIELDS)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def snapshot(path, root):
    path = Path(path).resolve()
    return dict(path=str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
                size_bytes=path.stat().st_size, sha256=digest(path))


def table_rows(path):
    opener = gzip.open if Path(path).suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f'{path}: missing or duplicate table headers')
        yield from reader


def identity(row, fields=KEY_FIELDS):
    return tuple(row[field].strip().upper() if field == 'uf' else int(row[field]) for field in fields)


def truth(value):
    if value not in {'True', 'False'}:
        raise ValueError(f'Unknown published boolean: {value!r}')
    return value == 'True'


def select_sections(analysis, manifest):
    tolerance = float(manifest['parameters']['epsilon_pp'])
    models = set(manifest['parameters']['models'])
    maxima = {}
    for row in table_rows(analysis/'tests.csv'):
        if row['statistic'] == 'MAX':
            if row['model'] in maxima:
                raise ValueError('Duplicate published MAX test')
            maxima[row['model']] = float(row['observed'])
    if set(maxima) != models:
        raise ValueError('Missing published MAX for a predeclared reference')

    max_places = {}
    place_descriptions = []
    for row in table_rows(analysis/'place-results.csv.gz'):
        model = row['model']
        if model not in models:
            raise ValueError('Unknown published reference')
        if truth(row['target']) and abs(float(row['max_component'])-maxima[model]) <= tolerance:
            key = identity(row, PLACE_FIELDS)
            max_places.setdefault(key, set()).add(f'MAX_target:{model}')
            place_descriptions.append(dict(model=model, uf=key[0], municipality=key[1],
                zone=key[2], place=key[3], cohort_sections=int(row['n']),
                observed_MAX=maxima[model], max_component=float(row['max_component'])))
    if {row['model'] for row in place_descriptions} != models:
        raise ValueError('No target attains a published MAX')

    selected, expected_places, members = {}, {}, {key: 0 for key in max_places}
    strict_priority_count = 0
    seen = set()
    for row in table_rows(analysis/'section-screening.csv.gz'):
        key = identity(row)
        if key in seen:
            raise ValueError('Duplicate published cohort section')
        seen.add(key)
        place = identity(row, PLACE_FIELDS)
        reasons = set()
        if truth(row['strict_priority']):
            reasons.add('strict_priority')
            strict_priority_count += 1
        if place in max_places:
            reasons.update(max_places[place]);members[place] += 1
        if reasons:
            selected[key] = reasons
            expected_places[key] = place[3]
    for row in place_descriptions:
        key = identity(row, PLACE_FIELDS)
        if members[key] != row['cohort_sections']:
            raise ValueError('Selected MAX target membership does not match published n')
    return selected, expected_places, dict(strict_priority_sections=strict_priority_count,
        MAX_target_selections=place_descriptions, distinct_selected_sections=len(selected))


def extract(root, analysis, output, context_manifest):
    root, analysis = Path(root).resolve(), Path(analysis).resolve()
    output, context_manifest = Path(output).resolve(), Path(context_manifest).resolve()
    if output == context_manifest or output.exists() or context_manifest.exists():
        raise ValueError('Refusing to replace an existing context table or manifest; choose new paths')
    primary_path = analysis/'manifest.json'
    primary = json.loads(primary_path.read_text(encoding='utf-8'))
    if primary.get('status') != 'completed':
        raise ValueError('Context extraction requires a completed primary analysis')
    inputs = dict(analysis_manifest=snapshot(primary_path, root))
    for name in INPUT_NAMES:
        path = analysis/name
        actual = snapshot(path, root)
        pinned = primary['artifacts'][name]
        if actual['sha256'] != pinned['sha256'] or actual['size_bytes'] != pinned['size_bytes']:
            raise ValueError(f'{name}: published selection-table hash mismatch')
        inputs[name] = actual

    h1_path = root/'reports/2026/hypothesis-tests/01-accounting-integrity/evidence/accounting/manifest.json'
    h1 = json.loads(h1_path.read_text(encoding='utf-8'))
    if h1.get('status') != 'completed':
        raise ValueError('Accounting-source provenance is required')
    inputs['accounting_manifest'] = snapshot(h1_path, root)
    source = primary['source_inputs']['details']
    detail = root/source['path']
    actual_source = snapshot(detail, root)
    for pinned in (source, h1['inputs']['details']):
        if actual_source['sha256'] != pinned['sha256'] or actual_source['size_bytes'] != pinned['size_bytes']:
            raise ValueError('Original detail CSV differs from pinned H5/accounting snapshot')

    selected, expected_places, selection_summary = select_sections(analysis, primary)
    expected = {}
    for row in table_rows(analysis/'paired-sections.csv.gz'):
        key = identity(row)
        if key not in selected:
            continue
        if not truth(row['eligible']):
            raise ValueError('Selected section is outside the published cohort')
        for turn in (1, 2):
            key_turn = (*key, turn)
            if key_turn in expected:
                raise ValueError('Duplicate selected source pointer')
            expected[key_turn] = dict(source_line=int(row[f'source_line_{turn}']),
                aptos=int(row[f'aptos_{turn}']), turnout=int(row[f'turnout_{turn}']),
                nominal=int(row[f'nominal_{turn}']))
    if len(expected) != 2*len(selected):
        raise ValueError('Not every selected cohort section has both original-source pointers')

    found, rows_scanned = {}, 0
    with detail.open(encoding='latin1', newline='') as stream:
        reader = csv.DictReader(stream, delimiter=';')
        header = reader.fieldnames or []
        if len(header) != len(set(header)) or set(SOURCE_FIELDS)-set(header):
            raise ValueError('Original detail header is incomplete or ambiguous')
        for source_line, row in enumerate(reader, 2):
            rows_scanned += 1
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Malformed original detail row at line {source_line}')
            if int(row['ANO_ELEICAO']) != 2026 or int(row['CD_CARGO']) != 1:
                continue
            key = (row['SG_UF'].strip().upper(), int(row['CD_MUNICIPIO']), int(row['NR_ZONA']), int(row['NR_SECAO']))
            key_turn = (*key, int(row['NR_TURNO']))
            if key_turn not in expected:
                continue
            if key_turn in found:
                raise ValueError('Duplicate selected original detail key')
            pointer = expected[key_turn]
            if source_line != pointer['source_line'] or int(row['NR_LOCAL_VOTACAO']) != expected_places[key]:
                raise ValueError('Original source key/place/line differs from published selection')
            for field, source_name in [('aptos','QT_APTOS'), ('turnout','QT_COMPARECIMENTO'), ('nominal','QT_VOTOS_NOMINAIS')]:
                if int(row[source_name]) != pointer[field]:
                    raise ValueError('Selected original counts differ from published pair')
            found[key_turn] = dict(selected_because=json.dumps(sorted(selected[key]), ensure_ascii=False, separators=(',',':')),
                source_line=source_line, **{field:row[field] for field in SOURCE_FIELDS})
    if set(found) != set(expected):
        raise ValueError('Missing selected original detail rows')
    if digest(detail) != actual_source['sha256'] or detail.stat().st_size != actual_source['size_bytes']:
        raise ValueError('Original detail CSV changed during extraction')
    # Recheck selection inputs after the scan, before publishing context.
    for entry in inputs.values():
        if digest(root/entry['path']) != entry['sha256']:
            raise ValueError('A selection/provenance input changed during extraction')

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS, lineterminator='\n')
        writer.writeheader();writer.writerows(found[key] for key in sorted(found))
    result = dict(status='completed', created_at_utc=datetime.now(timezone.utc).isoformat(),
        extractor_sha256=digest(Path(__file__)), inputs=inputs, source_input=actual_source,
        selection=dict(rule='All strict priorities, plus every cohort section in every target attaining the published MAX for either reference',
            MAX_matching_tolerance=float(primary['parameters']['epsilon_pp']), **selection_summary),
        original_rows_scanned=rows_scanned, selected_original_rows=len(found), source_unchanged=True,
        output=snapshot(output, root),
        interpretation='Descriptive original-source context only; no additional statistical test, causal inference, or classification of manipulation')
    context_manifest.parent.mkdir(parents=True, exist_ok=True)
    with context_manifest.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2);stream.write('\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--analysis-dir', type=Path, default=HERE/'evidence/analysis')
    parser.add_argument('--output', type=Path, default=HERE/'evidence/selected-source-context.csv')
    parser.add_argument('--manifest', type=Path, default=HERE/'evidence/context-manifest.json')
    args = parser.parse_args()
    result = extract(args.root, args.analysis_dir, args.output, args.manifest)
    print(json.dumps(dict(status=result['status'], selected_sections=result['selection']['distinct_selected_sections'],
                          selected_original_rows=result['selected_original_rows'], source_unchanged=result['source_unchanged'])))


if __name__ == '__main__':
    main()
