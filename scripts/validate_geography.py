"""Independent geographic-result checks against the original replay database.

Uses only the standard library, read-only SQL, and no analysis implementation
imports. Event ties enter together. Quantiles are first timestamps reaching the
specified fraction of polling sections, not averages of adjacent observations.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from itertools import groupby
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import statistics

KEY = ('election_code', 'turno', 'uf', 'municipality', 'zone', 'section', 'cargo')
SOURCE = {'first_partial_totalization': 'first_time', 'bu_received': 'bu_time'}
REGIONS = {uf: region for region, ufs in {
    'Nordeste': 'AL BA CE MA PB PE PI RN SE', 'Norte': 'AC AP AM PA RO RR TO',
    'Sudeste': 'ES MG RJ SP', 'Sul': 'PR RS SC', 'Centro-Oeste': 'DF GO MT MS',
    'Exterior': 'ZZ',
}.items() for uf in ufs.split()}
STAGES = (5, 10, 25, 50, 75, 90, 99, 100)
CLOCKS = ('17:30', '18:00', '18:30', '19:00', '20:00', '21:00')


def independent_baseline(db):
    """Stream original section events, retaining aggregates and selected cutoffs."""
    results = {}
    elections = db.execute('SELECT DISTINCT election_code,turno FROM sections ORDER BY election_code,turno').fetchall()
    join = ' AND '.join(f's.{key}=v.{key}' for key in KEY)
    for election, turn in elections:
        totals = {uf: (n, v) for uf, n, v in db.execute(
            'SELECT uf,COUNT(*),SUM(nominal_votes) FROM sections WHERE election_code=? AND turno=? GROUP BY uf', (election, turn))}
        region_totals = defaultdict(lambda: [0, 0])
        for uf, (n, votes) in totals.items():
            region_totals[REGIONS[uf]][0] += n
            region_totals[REGIONS[uf]][1] += votes
        national_sections = sum(n for n, _ in totals.values())
        for source, column in SOURCE.items():
            sql = f'''SELECT d.{column},s.uf,COUNT(*),SUM(s.nominal_votes),SUM(COALESCE(v.votes,0))
                FROM sections s JOIN details d USING ({','.join(KEY)})
                LEFT JOIN votes v ON {join} AND v.nr_votavel=13
                WHERE s.election_code=? AND s.turno=? AND d.{column} IS NOT NULL
                GROUP BY d.{column},s.uf ORDER BY d.{column},s.uf'''
            date = db.execute(f'SELECT MIN(substr({column},1,10)) FROM details WHERE election_code=? AND turno=?', (election, turn)).fetchone()[0]
            limits = iter(date + ' ' + clock + ':00.000000' for clock in CLOCKS)
            limit = next(limits, None)
            states = defaultdict(lambda: [0, 0, 0])
            regions = defaultdict(lambda: [0, 0, 0])
            national = [0, 0, 0]
            quantiles, fixed, snapshots, sp_snapshots = defaultdict(dict), {}, {}, {}
            pending_national, pending_sp = list(STAGES), list(STAGES)

            def snapshot(time):
                return {'time': time, 'national_completion_pct': 100 * national[0] / national_sections,
                        'lula_share_pct': 100 * national[2] / national[1] if national[1] else None,
                        'regions': {region: {'section_completion_pct': 100 * counts[0] / region_totals[region][0],
                            'nominal_completion_pct': 100 * counts[1] / region_totals[region][1],
                            'nominal_weight_pct': 100 * counts[1] / national[1] if national[1] else 0,
                            'lula_share_pct': 100 * counts[2] / counts[1] if counts[1] else None}
                            for region, counts in regions.items()},
                        'uf': {uf: {'section_completion_pct': 100 * counts[0] / totals[uf][0],
                            'nominal_completion_pct': 100 * counts[1] / totals[uf][1]}
                            for uf, counts in states.items()}}

            rows = db.execute(sql, (election, turn))
            for time, group in groupby(rows, key=lambda row: row[0]):
                while limit is not None and time > limit:
                    fixed[limit] = snapshot(limit)
                    limit = next(limits, None)
                for _, uf, count, nominal, lula in group:
                    for target in (states[uf], regions[REGIONS[uf]], national):
                        target[0] += count
                        target[1] += nominal
                        target[2] += lula
                for dimension, groups, group_totals in [('uf', states, totals), ('region', regions, region_totals)]:
                    for name, counts in groups.items():
                        for q in (10, 50, 90, 99):
                            if q not in quantiles[(dimension, name)] and counts[0] >= math.ceil(group_totals[name][0] * q / 100):
                                quantiles[(dimension, name)][q] = time
                while pending_national and national[0] >= math.ceil(national_sections * pending_national[0] / 100):
                    snapshots[pending_national.pop(0)] = snapshot(time)
                while pending_sp and states['SP'][0] >= math.ceil(totals['SP'][0] * pending_sp[0] / 100):
                    sp = states['SP']
                    sp_snapshots[pending_sp.pop(0)] = {'time': time,
                        'actual_completion_pct': 100 * sp[0] / totals['SP'][0],
                        'lula_share_pct': 100 * sp[2] / sp[1]}
            while limit is not None:
                fixed[limit] = snapshot(limit)
                limit = next(limits, None)
            results[(source, election, turn)] = {'quantiles': quantiles, 'fixed': fixed,
                'snapshots': snapshots, 'sp_snapshots': sp_snapshots}
    return results


def validate(replay_db: Path, analysis_dir: Path):
    db = sqlite3.connect(replay_db.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        baseline = independent_baseline(db)
    finally:
        db.close()
    counts = {'core': 0, 'fixed_clock': 0, 'ols_coefficients': 0}
    max_difference = 0.0
    tolerance = 1e-9

    def numeric(actual, expected, category):
        nonlocal max_difference
        difference = abs(float(actual) - expected)
        max_difference = max(max_difference, difference)
        if difference > tolerance:
            raise AssertionError(f'{category}: {actual} != {expected}')
        counts[category] += 1

    def read(name):
        with (analysis_dir / name).open(encoding='utf8', newline='') as stream:
            yield from csv.DictReader(stream)

    def base(row):
        return baseline[row['source_timestamp'], row['election_code'], row['turno']]

    for row in read('national-milestones.csv'):
        data = base(row)
        stage = int(float(row['requested_sections_percentage']))
        if stage not in STAGES:
            continue
        if row['scope'] == 'BR':
            expected = data['snapshots'][stage]
            assert row['cutoff_timestamp'] == expected['time']
            for field, value in [('lula_percentage', expected['lula_share_pct']),
                ('actual_sections_percentage', expected['national_completion_pct']),
                ('ne_weight_percentage', expected['regions']['Nordeste']['nominal_weight_pct']),
                ('ne_sections_completion_percentage', expected['regions']['Nordeste']['section_completion_pct'])]:
                numeric(row[field], value, 'core')
        elif row['scope'] == 'SP':
            expected = data['sp_snapshots'][stage]
            assert row['cutoff_timestamp'] == expected['time']
            numeric(row['lula_percentage'], expected['lula_share_pct'], 'core')
            numeric(row['actual_sections_percentage'], expected['actual_completion_pct'], 'core')
    for row in read('timing-summary.csv'):
        if row['dimension'] in {'uf', 'region'}:
            expected = base(row)['quantiles'][row['dimension'], row['group']]
            for q in (10, 50, 90, 99):
                assert row['t' + str(q)] == expected[q]
                counts['core'] += 1
    for row in read('composition-decomposition.csv'):
        if row['scope'] != 'BR' or row['dimension'] != 'region':
            continue
        snapshots = base(row)['snapshots']
        stage = int(float(row['requested_sections_percentage']))
        if stage not in snapshots:
            continue
        current, final = snapshots[stage], snapshots[100]
        predicted = sum(group['nominal_weight_pct'] / 100 * final['regions'][name]['lula_share_pct']
                        for name, group in current['regions'].items())
        for field, value in [('counterfactual_lula_percentage', predicted),
            ('composition_effect_pp', predicted - final['lula_share_pct']),
            ('within_group_effect_pp', current['lula_share_pct'] - predicted),
            ('total_gap_pp', current['lula_share_pct'] - final['lula_share_pct'])]:
            numeric(row[field], value, 'core')
    for row in read('clock-completion.csv'):
        if row['dimension'] not in {'uf', 'region'}:
            continue
        snap = base(row)['fixed'].get(row['cutoff_timestamp'])
        if snap is None:
            continue
        expected = snap['uf' if row['dimension'] == 'uf' else 'regions'].get(row['group'], {})
        numeric(row['section_completion_percentage'], expected.get('section_completion_pct', 0), 'fixed_clock')
        numeric(row['nominal_completion_percentage'], expected.get('nominal_completion_pct', 0), 'fixed_clock')
    municipalities = list(read('municipality-timing.csv'))
    coefficient_checks = []
    for model in json.loads((analysis_dir / 'municipality-controls.json').read_text()):
        groups = defaultdict(list)
        for row in municipalities:
            if (row['source'], row['election_code'], row['turno']) == (model['source'], model['election_code'], model['turno']) and float(row['electorate']) > 0:
                groups[row['uf']].append((math.log10(float(row['electorate'])), float(row['is_capital']), float(row['t50_minutes'])))
        xx = cc = xc = xy = cy = 0.0
        for group in groups.values():
            mx, mc, my = [statistics.mean(row[i] for row in group) for i in range(3)]
            for x, capital, y in group:
                x, capital, y = x - mx, capital - mc, y - my
                xx += x*x; cc += capital*capital; xc += x*capital; xy += x*y; cy += capital*y
        determinant = xx*cc - xc*xc
        size = (xy*cc - cy*xc) / determinant
        capital = (cy*xx - xy*xc) / determinant
        numeric(model['ols_minutes_per_10x_electorate'], size, 'ols_coefficients')
        numeric(model['ols_capital_minutes_vs_noncapital'], capital, 'ols_coefficients')
        coefficient_checks.append({'source': model['source'], 'election_code': model['election_code'], 'turno': model['turno'],
            'independent_size_minutes_per_10x_electorate': size, 'independent_capital_minutes': capital,
            'size_absolute_difference': abs(model['ols_minutes_per_10x_electorate'] - size),
            'capital_absolute_difference': abs(model['ols_capital_minutes_vs_noncapital'] - capital)})
    result = {'status': 'passed', 'replay_database': str(replay_db), 'analysis_directory': str(analysis_dir),
        'validation_script': 'scripts/validate_geography.py',
        'validation_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'checks': counts, 'mismatches': 0, 'absolute_numeric_tolerance': tolerance,
        'maximum_absolute_numeric_difference': max_difference, 'coefficient_checks': coefficient_checks,
        'method': 'Independent read-only aggregation from the original replay database; exact timestamp ties included; OLS rechecked via within-UF demeaning and standard-library 2x2 normal equations.',
        'interpretation': 'Descriptive accounting and conditional associations, not causal effects or individual demographic inference; municipal size is registered electorate, not population. No inference p-values are claimed.'}
    (analysis_dir / 'independent-validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay-db', type=Path, default=Path('output/replay/replay.sqlite'))
    parser.add_argument('--analysis-dir', type=Path, default=Path('output/geography'))
    args = parser.parse_args()
    print(json.dumps(validate(args.replay_db, args.analysis_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
