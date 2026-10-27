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
    """Stream original section events, retaining independent regional/UF cutoffs.

    Candidate 22 is read directly; it is never inferred as the complement of 13.
    Each simultaneous timestamp group is completely applied before milestones.
    """
    results = {}
    elections = db.execute('SELECT DISTINCT election_code,turno FROM sections ORDER BY election_code,turno').fetchall()
    join13 = ' AND '.join(f's.{key}=v.{key}' for key in KEY)
    join22 = ' AND '.join(f's.{key}=f.{key}' for key in KEY)
    for election, turn in elections:
        totals = {uf: (n, v) for uf, n, v in db.execute(
            'SELECT uf,COUNT(*),SUM(nominal_votes) FROM sections WHERE election_code=? AND turno=? GROUP BY uf', (election, turn))}
        region_totals = defaultdict(lambda: [0, 0])
        for uf, (n, votes) in totals.items():
            region_totals[REGIONS[uf]][0] += n
            region_totals[REGIONS[uf]][1] += votes
        national_sections = sum(n for n, _ in totals.values())
        for source, column in SOURCE.items():
            sql = f"""SELECT d.{column},s.uf,COUNT(*),SUM(s.nominal_votes),
                    SUM(COALESCE(v.votes,0)),SUM(COALESCE(f.votes,0))
                FROM sections s JOIN details d USING ({','.join(KEY)})
                LEFT JOIN votes v ON {join13} AND v.nr_votavel=13
                LEFT JOIN votes f ON {join22} AND f.nr_votavel=22
                WHERE s.election_code=? AND s.turno=? AND d.{column} IS NOT NULL
                GROUP BY d.{column},s.uf ORDER BY d.{column},s.uf"""
            date = db.execute(f'SELECT MIN(substr({column},1,10)) FROM details WHERE election_code=? AND turno=?', (election, turn)).fetchone()[0]
            limits = iter(date + ' ' + clock + ':00.000000' for clock in CLOCKS)
            limit = next(limits, None)
            states = defaultdict(lambda: [0, 0, 0, 0])
            regions = defaultdict(lambda: [0, 0, 0, 0])
            national = [0, 0, 0, 0]
            quantiles, fixed, snapshots = defaultdict(dict), {}, {}
            uf_snapshots = {uf: {} for uf in totals}
            pending_national = list(STAGES)
            pending_states = {uf: list(STAGES) for uf in totals}

            def group_snapshot(counts, group_total, time):
                return {'time': time, 'sections': counts[0], 'nominal_votes': counts[1],
                        'lula_votes': counts[2], 'flavio_votes': counts[3],
                        'section_completion_pct': 100 * counts[0] / group_total[0],
                        'nominal_completion_pct': 100 * counts[1] / group_total[1] if group_total[1] else None,
                        'nominal_weight_pct': 100 * counts[1] / national[1] if national[1] else 0,
                        'lula_share_pct': 100 * counts[2] / counts[1] if counts[1] else None,
                        'flavio_share_pct': 100 * counts[3] / counts[1] if counts[1] else None}

            def snapshot(time):
                return {'time': time, 'national_completion_pct': 100 * national[0] / national_sections,
                        'national_sections': national[0], 'national_nominal_votes': national[1],
                        'lula_share_pct': 100 * national[2] / national[1] if national[1] else None,
                        'flavio_share_pct': 100 * national[3] / national[1] if national[1] else None,
                        'regions': {region: group_snapshot(counts,region_totals[region],time)
                                    for region,counts in regions.items()},
                        'uf': {uf: group_snapshot(counts,totals[uf],time) for uf,counts in states.items()}}

            rows = db.execute(sql, (election, turn))
            for time, group in groupby(rows, key=lambda row: row[0]):
                while limit is not None and time > limit:
                    fixed[limit] = snapshot(limit)
                    limit = next(limits, None)
                changed = set()
                for _, uf, count, nominal, lula, flavio in group:
                    changed.add(uf)
                    for target in (states[uf], regions[REGIONS[uf]], national):
                        target[0] += count
                        target[1] += nominal
                        target[2] += lula
                        target[3] += flavio
                for dimension, groups, group_totals in [('uf', states, totals), ('region', regions, region_totals)]:
                    for name, counts in groups.items():
                        for q in (10, 50, 90, 99):
                            if q not in quantiles[(dimension, name)] and counts[0] >= math.ceil(group_totals[name][0] * q / 100):
                                quantiles[(dimension, name)][q] = time
                while pending_national and national[0] >= math.ceil(national_sections * pending_national[0] / 100):
                    snapshots[pending_national.pop(0)] = snapshot(time)
                for uf in changed:
                    pending = pending_states[uf]
                    while pending and states[uf][0] >= math.ceil(totals[uf][0] * pending[0] / 100):
                        own = group_snapshot(states[uf],totals[uf],time)
                        own['actual_completion_pct'] = own['section_completion_pct']
                        uf_snapshots[uf][pending.pop(0)] = own
            while limit is not None:
                fixed[limit] = snapshot(limit)
                limit = next(limits, None)
            results[(source, election, turn)] = {'quantiles': quantiles, 'fixed': fixed,
                'snapshots': snapshots, 'sp_snapshots': uf_snapshots.get('SP',{}),
                'uf_snapshots': uf_snapshots, 'totals': totals}
    return results


def validate(replay_db: Path, analysis_dir: Path):
    db = sqlite3.connect(replay_db.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        baseline = independent_baseline(db)
    finally:
        db.close()
    counts = {'core': 0, 'fixed_clock': 0, 'ols_coefficients': 0, 'candidate_22': 0, 'uf_milestones': 0}
    max_difference = 0.0
    tolerance = 1e-9

    def numeric(actual, expected, category):
        nonlocal max_difference
        difference = abs(float(actual) - expected)
        max_difference = max(max_difference, difference)
        if not math.isfinite(difference) or difference > tolerance:
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
            if 'flavio_percentage' in row:
                numeric(row['flavio_percentage'],expected['flavio_share_pct'],'candidate_22')
        elif row['scope'] == 'SP':
            expected = data['sp_snapshots'][stage]
            assert row['cutoff_timestamp'] == expected['time']
            numeric(row['lula_percentage'], expected['lula_share_pct'], 'core')
            numeric(row['actual_sections_percentage'], expected['actual_completion_pct'], 'core')
            if 'flavio_percentage' in row:
                numeric(row['flavio_percentage'],expected['flavio_share_pct'],'candidate_22')
    if (analysis_dir/'uf-milestones.csv').exists():
        seen=set()
        for row in read('uf-milestones.csv'):
            stage=int(float(row['requested_sections_percentage']))
            data=base(row)
            expected=data['uf_snapshots'][row['scope']][stage]
            assert row['cutoff_timestamp']==expected['time']
            assert row['target_reached']=='1'
            identity=(row['source_timestamp'],row['election_code'],row['turno'],row['scope'],stage)
            if identity in seen:raise AssertionError('Duplicate UF milestone')
            seen.add(identity)
            final=data['uf_snapshots'][row['scope']][100]
            for field,value in [('actual_sections_percentage',expected['section_completion_pct']),
                ('cumulative_sections',expected['sections']),('total_sections',data['totals'][row['scope']][0]),
                ('cumulative_nominal_votes',expected['nominal_votes']),('total_nominal_votes',final['nominal_votes']),
                ('nominal_completion_percentage',expected['nominal_completion_pct']),
                ('lula_percentage',expected['lula_share_pct']),('flavio_percentage',expected['flavio_share_pct']),
                ('lula_final_percentage',final['lula_share_pct']),('flavio_final_percentage',final['flavio_share_pct'])]:
                numeric(row[field],value,'uf_milestones')
        expected_count=sum(len(data['totals'])*len(STAGES) for data in baseline.values())
        assert len(seen)==expected_count,(len(seen),expected_count)
    for row in read('milestone-composition.csv'):
        if row['dimension'] not in {'region','uf'} or 'flavio_percentage' not in row:continue
        data=base(row);stage=int(float(row['requested_sections_percentage']))
        expected=data['snapshots'][stage]['regions' if row['dimension']=='region' else 'uf'].get(row['group'])
        if expected is None or expected['nominal_votes']==0:
            assert row['flavio_percentage']=='',row
        else:
            numeric(row['flavio_percentage'],expected['flavio_share_pct'],'candidate_22')
        final=data['snapshots'][100]['regions' if row['dimension']=='region' else 'uf'][row['group']]
        numeric(row['flavio_final_percentage'],final['flavio_share_pct'],'candidate_22')
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
        if 'flavio_percentage' in row:
            if expected.get('flavio_share_pct') is None:assert row['flavio_percentage']==''
            else:numeric(row['flavio_percentage'],expected['flavio_share_pct'],'candidate_22')
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
        'interpretation': 'Descriptive accounting and conditional associations, not causal effects or individual demographic inference; municipal size is registered electorate, not population. This validator does not assess randomization-test results.'}
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
