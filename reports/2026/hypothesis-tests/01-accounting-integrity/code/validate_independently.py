#!/usr/bin/env python3
"""Independent H1 checks, reading the two original CSVs using only stdlib.

No imports from the replay or primary H1 implementation. All comparisons use
integer arithmetic; there are no tolerances or statistical significance tests.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


KEY_FIELDS = (
    'CD_ELEICAO', 'NR_TURNO', 'SG_UF', 'CD_MUNICIPIO',
    'NR_ZONA', 'NR_SECAO', 'CD_CARGO',
)
DETAIL_FIELDS = (
    'QT_APTOS', 'QT_COMPARECIMENTO', 'QT_ABSTENCOES',
    'QT_VOTOS_NOMINAIS', 'QT_VOTOS_BRANCOS', 'QT_VOTOS_NULOS',
    'QT_VOTOS_LEGENDA', 'QT_VOTOS_ANULADOS_APU_SEP',
)
MISSING = {'', '#NULO', '#NE', '-1', '-3'}
PACK = struct.Struct('>7I')


def digest_file(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(2**20), b''):
            sha.update(block)
    return sha.hexdigest()


def open_rows(path):
    with path.open(encoding='latin1', newline='') as stream:
        reader = csv.reader(stream, delimiter=';')
        header = next(reader)
        if len(header) != len(set(header)):
            raise ValueError(f'Duplicate header column: {path}')
        positions = {name: index for index, name in enumerate(header)}
        for line, row in enumerate(reader, 2):
            if len(row) != len(header):
                raise ValueError(f'Malformed CSV record at {path}:{line}')
            yield line, row, positions


def section_key(row, columns):
    values = [row[columns[field]].strip() for field in KEY_FIELDS]
    uf = values[2].upper()
    if not re.fullmatch('[A-Z]{2}', uf):
        raise ValueError(f'Invalid state code: {uf!r}')
    numbers = [int(values[i]) for i in (0, 1, 3, 4, 5, 6)]
    if any(value < 0 for value in numbers):
        raise ValueError('Negative section key component')
    return PACK.pack(numbers[0], numbers[1], int.from_bytes(uf.encode('ascii'), 'big'),
                     *numbers[2:]), (numbers[0], numbers[1], uf)


def unpack_key(key):
    election, turn, uf, municipality, zone, section, office = PACK.unpack(key)
    return dict(election_code=election, turno=turn,
                uf=uf.to_bytes(2, 'big').decode('ascii'),
                municipality=municipality, zone=zone, section=section, cargo=office)


def raw_digest(row):
    # Preserve all source columns, including names and extraction metadata.
    return hashlib.sha256(repr(tuple(row)).encode('utf-8')).digest()


def number(raw):
    raw = raw.strip()
    if raw.upper() in MISSING:
        return None, 'missing'
    if not re.fullmatch(r'[+-]?\d+', raw):
        return None, 'invalid'
    value = int(raw)
    return value, 'negative' if value < 0 else 'valid'


def installation_status(raw):
    normalized = raw.strip().upper()
    if normalized in {'S', 'SIM'}:
        return 'installed'
    if normalized in {'N', 'NAO', 'NÃO'}:
        return 'not_installed'
    return 'unknown_installation'


def validate(root):
    votes_path = root / 'data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv'
    details_path = root / 'data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv'
    groups = {}
    checks = {}
    flag_counts = Counter()
    invalid_fields = Counter()
    examples = {}
    details = {}
    votes = {}
    seen_votes = {}
    duplicate_vote_keys = set()
    duplicate_details = set()
    input_stats = {'details_rows_read': 0, 'votes_rows_read': 0,
                   'details_rows_selected': 0, 'votes_rows_selected': 0}

    def targets(scope):
        election, turn, uf = scope
        return (scope, (election, turn, 'BR'))

    def add(scope, field, value=1):
        for target in targets(scope):
            groups.setdefault(target, Counter())[field] += value

    def check(scope, name, comparable, passed=None):
        for target in targets(scope):
            counts = checks.setdefault((*target, name), Counter())
            counts['opportunities'] += 1
            counts['evaluated' if comparable else 'non_comparable'] += 1
            if comparable:
                counts['passed' if passed else 'mismatches'] += 1

    def sample(name, value):
        examples.setdefault(name, [])
        if len(examples[name]) < 100:
            examples[name].append(value)

    def select(row, columns):
        return (row[columns['ANO_ELEICAO']].strip() == '2026'
                and int(row[columns['CD_CARGO']]) == 1)

    print('Independent validator: reading detail CSV', flush=True)
    for line, row, columns in open_rows(details_path):
        input_stats['details_rows_read'] += 1
        if not select(row, columns):
            continue
        input_stats['details_rows_selected'] += 1
        key, scope = section_key(row, columns)
        values = []
        statuses = []
        for field in DETAIL_FIELDS:
            value, status = number(row[columns[field]])
            values.append(value)
            statuses.append(status)
            if status != 'valid':
                invalid_fields[('details', scope[0], scope[1], field, status)] += 1
        installed = row[columns['ST_SECAO_INSTALADA']].strip()
        cancelled = row[columns['ST_SECAO_ANULADA']].strip()
        origin = row[columns['DS_ORIGEM_VOTO']].strip()
        flag_counts[(*scope, installed, cancelled, origin)] += 1
        row_signature = raw_digest(row)
        if key in details:
            prior = details[key]
            prior[0] += 1
            if key not in duplicate_details:
                duplicate_details.add(key)
                add(scope, 'duplicate_detail_key_groups')
            add(scope, 'duplicate_detail_excess_rows')
            add(scope, 'detail_duplicate_rows_exact_to_first' if prior[3] == row_signature
                else 'detail_duplicate_rows_conflicting_with_first')
        else:
            details[key] = [1, tuple(values), (installed, cancelled, origin), row_signature]
        add(scope, 'detail_rows')
        for field, value in zip(DETAIL_FIELDS, values):
            if value is not None:
                add(scope, field, value)
        complete = all(status == 'valid' for status in statuses)
        check(scope, 'detail_numeric_complete_nonnegative', True, complete)
        aptos, turnout, abstentions, nominal, blank, null, legend, separate = values
        check(scope, 'turnout_not_above_electorate', aptos is not None and turnout is not None,
              aptos is not None and turnout is not None and turnout <= aptos)
        check(scope, 'abstentions_not_above_electorate', aptos is not None and abstentions is not None,
              aptos is not None and abstentions is not None and abstentions <= aptos)
        comparable = all(value is not None for value in (aptos, turnout, abstentions))
        identity = comparable and aptos == turnout + abstentions
        check(scope, 'electorate_equals_turnout_plus_abstentions', comparable, identity)
        installation = installation_status(installed)
        check(scope, 'installation_status_known', True, installation != 'unknown_installation')
        check(scope, f'electorate_equals_turnout_plus_abstentions_{installation}',
              comparable, identity)
        if comparable and not identity:
            sample('electorate_identity_mismatches',
                   dict(**unpack_key(key), input_line=line, aptos=aptos,
                        turnout=turnout, abstentions=abstentions, installed=installed,
                        cancelled=cancelled, origin=origin,
                        difference=aptos-turnout-abstentions))
        comparable = all(value is not None for value in values[1:2] + values[3:])
        detail_total = sum(values[3:]) if comparable else None
        check(scope, 'detail_all_categories_equal_turnout', comparable,
              comparable and detail_total == turnout)
        check(scope, 'presidential_legend_votes_zero', legend is not None,
              legend == 0)
        if comparable and detail_total != turnout:
            sample('detail_vote_total_mismatches',
                   dict(**unpack_key(key), turnout=turnout, category_sum=detail_total))
        if complete and all(value == 0 for value in values[1:]):
            add(scope, 'details_with_zero_turnout_abstentions_and_all_categories')
            add(scope, 'electorate_in_zero_activity_details', aptos)

    if not input_stats['details_rows_selected']:
        raise ValueError('Detail CSV has no selected 2026 presidential rows')
    print('Independent validator: reading vote CSV', flush=True)
    for line, row, columns in open_rows(votes_path):
        input_stats['votes_rows_read'] += 1
        if not select(row, columns):
            continue
        input_stats['votes_rows_selected'] += 1
        key, scope = section_key(row, columns)
        value, status = number(row[columns['QT_VOTOS']])
        candidate, candidate_status = number(row[columns['NR_VOTAVEL']])
        check(scope, 'vote_count_complete_nonnegative', True, status == 'valid')
        check(scope, 'vote_number_complete_positive', True,
              candidate_status == 'valid' and candidate > 0)
        if status != 'valid':
            invalid_fields[('votes', scope[0], scope[1], 'QT_VOTOS', status)] += 1
        if candidate_status != 'valid' or candidate == 0:
            invalid_fields[('votes', scope[0], scope[1], 'NR_VOTAVEL',
                            candidate_status if candidate != 0 else 'zero')] += 1
        add(scope, 'vote_rows')
        accum = votes.setdefault(key, [0, 0, 0, 0, 0, 0, False])
        accum[5] += 1
        if status != 'valid':
            # Keep source numeric totals when available, but never treat a
            # section with missing, malformed, or negative votes as comparable.
            accum[6] = True
        if candidate_status != 'valid' or candidate == 0:
            accum[6] = True
            continue
        vote_key = key + struct.pack('>I', candidate)
        signature = raw_digest(row)
        if vote_key in seen_votes:
            if vote_key not in duplicate_vote_keys:
                duplicate_vote_keys.add(vote_key)
                add(scope, 'duplicate_vote_key_groups')
            add(scope, 'duplicate_vote_excess_rows')
            add(scope, 'vote_duplicate_rows_exact_to_first' if seen_votes[vote_key] == signature
                else 'vote_duplicate_rows_conflicting_with_first')
        else:
            seen_votes[vote_key] = signature
        if value is None:
            continue
        category = {95: 1, 96: 2, 97: 3}.get(candidate, 0)
        accum[category] += value
        accum[4] += value
        add(scope, ('votes_nominal', 'votes_blank', 'votes_null', 'votes_separate')[category], value)
        add(scope, 'votes_total', value)

    if not input_stats['votes_rows_selected']:
        raise ValueError('Vote CSV has no selected 2026 presidential rows')
    print('Independent validator: comparing section dictionaries', flush=True)
    for key, info in details.items():
        scope = tuple(unpack_key(key)[field] for field in ('election_code', 'turno', 'uf'))
        add(scope, 'detail_unique_keys')
        vote = votes.get(key)
        if info[0] == 1:
            for index, name, detail_index in ((0, 'nominal', 3), (1, 'blank', 4),
                                              (2, 'null', 5), (3, 'separate', 7)):
                comparable = info[1][detail_index] is not None and (vote is None or not vote[6])
                value = 0 if vote is None else vote[index]
                check(scope, f'vote_detail_all_unique_{name}_equality', comparable,
                      comparable and value == info[1][detail_index])
            comparable = info[1][1] is not None and (vote is None or not vote[6])
            total = 0 if vote is None else vote[4]
            check(scope, 'vote_file_all_unique_categories_equal_turnout', comparable,
                  comparable and total == info[1][1])
        if vote is None:
            add(scope, 'detail_only_keys')
            if info[0] == 1:
                if all(value is not None for value in info[1]):
                    add(scope, 'detail_only_electorate', info[1][0])
                    add(scope, 'detail_only_turnout', info[1][1])
                    add(scope, 'detail_only_abstentions', info[1][2])
                    add(scope, 'detail_only_category_total', sum(info[1][3:]))
                else:
                    add(scope, 'detail_only_missing_numeric_keys')
                sample('detail_only_sections', dict(**unpack_key(key),
                       values=dict(zip(DETAIL_FIELDS, info[1])),
                       installed=info[2][0], cancelled=info[2][1], origin=info[2][2]))
            continue
        if info[0] != 1:
            add(scope, 'matched_ambiguous_detail_keys')
            continue
        add(scope, 'matched_unique_keys')
        values = info[1]
        for index, name, detail_index in ((0, 'nominal', 3), (1, 'blank', 4),
                                          (2, 'null', 5), (3, 'separate', 7)):
            comparable = values[detail_index] is not None and not vote[6]
            check(scope, f'vote_detail_{name}_equality', comparable,
                  comparable and vote[index] == values[detail_index])
        comparable = values[1] is not None and not vote[6]
        check(scope, 'vote_file_all_categories_equal_turnout', comparable,
              comparable and vote[4] == values[1])
        if comparable and vote[4] != values[1]:
            sample('vote_file_turnout_mismatches',
                   dict(**unpack_key(key), turnout=values[1], vote_total=vote[4]))
    for key in votes:
        scope = tuple(unpack_key(key)[field] for field in ('election_code', 'turno', 'uf'))
        add(scope, 'vote_unique_section_keys')
        if key not in details:
            add(scope, 'vote_only_keys')
            sample('vote_only_sections', unpack_key(key))

    return {
        'status': 'completed',
        'method': 'Independent original-CSV streaming parser and binary-key dictionaries; integer arithmetic; no imports from primary H1/replay analysis',
        'scope': '2026, CD_CARGO=1; all provided rounds and UFs including ZZ; original nationwide files only',
        'source_files': {name: {'path': str(path.relative_to(root)),
                               'bytes': path.stat().st_size, 'sha256': digest_file(path)}
                         for name, path in [('votes', votes_path), ('details', details_path)]},
        'script_sha256': digest_file(Path(__file__)),
        'input_statistics': input_stats,
        'group_totals': [dict(election_code=scope[0], turno=scope[1], uf=scope[2], **dict(sorted(values.items())))
                         for scope, values in sorted(groups.items())],
        'checks': [dict(election_code=key[0], turno=key[1], uf=key[2], check=key[3],
                        **{field: counts.get(field, 0) for field in
                           ('opportunities', 'evaluated', 'passed', 'mismatches', 'non_comparable')})
                   for key, counts in sorted(checks.items())],
        'flags': [dict(election_code=key[0], turno=key[1], uf=key[2], installed=key[3],
                       cancelled=key[4], origin=key[5], rows=count)
                  for key, count in sorted(flag_counts.items())],
        'invalid_or_missing_fields': [dict(file=key[0], election_code=key[1], turno=key[2],
                                           field=key[3], status=key[4], rows=count)
                                      for key, count in sorted(invalid_fields.items())],
        'examples_limit_per_kind': 100,
        'examples': examples,
        'interpretation': {
            'exact_duplicate': 'All original parsed CSV column values identical to the first row with that normalized key',
            'conflicting_duplicate': 'At least one original CSV column value differs from the first row with that normalized key',
            'detail_total': 'QT_VOTOS_NOMINAIS + QT_VOTOS_BRANCOS + QT_VOTOS_NULOS + QT_VOTOS_LEGENDA + QT_VOTOS_ANULADOS_APU_SEP',
            'vote_classification': '95=blank; 96=null; 97=separate; all other positive NR_VOTAVEL=nominal for presidential scope; legend separately checked zero',
            'missing_numeric': 'Empty, #NULO, #NE, -1, -3 are non-comparable; other invalid strings counted separately; never silently converted to zero in checks',
            'raw_totals': 'Detail/vote totals include every selected raw row; duplicate keys are reported and ambiguous details excluded from section reconciliation',
            'reconciliation_denominators': 'vote_detail_* and vote_file_all_categories checks use matched unique sections only; *_all_unique_* checks additionally treat absence of vote records as zero for a unique detail key and accompany this with explicit detail-only diagnostics; missing numeric values are never zero-filled',
            'identity_exceptions': 'Unconditional electorate identity mismatches retained; installed/not-installed strata reported separately; flags do not establish explanation',
            'non_certification': 'Internal consistency of the provided snapshots, not independent verification against signed BUs, external electorate inventory, or official publication history',
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[5])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a new path')
    started = datetime.now(timezone.utc).isoformat()
    result = validate(args.root.resolve())
    result['started_at_utc'] = started
    result['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                           encoding='utf-8')
    national = [row for row in result['group_totals'] if row['uf'] == 'BR']
    failures = [row for row in result['checks'] if row['uf'] == 'BR' and row['mismatches']]
    print(json.dumps({'output': str(args.output), 'national': national,
                      'national_failed_checks': failures}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
