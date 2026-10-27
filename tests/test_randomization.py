"""Permutation inference on tiny synthetic data, never published election output."""

import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import numpy as np

from election_replay.geography_randomization import curve_test, holm_adjust, run_randomization


FIELDS = [
    'election_code', 'turno', 'uf', 'municipality', 'municipality_name', 'zone',
    'section', 'region', 'is_capital', 'size_band', 'municipality_electorate', 'aptos',
    'nominal_votes', 'lula_votes', 'flavio_votes', 'first_time', 'bu_time',
]
PRIMARY = 'first_partial_totalization'
RECEIPT = 'bu_received'


def section(number, uf='SP', time='2026-10-04 17:00:00.000000', nominal=100,
            lula=20, flavio=30, capital=1, band='>1m', election='100', turn='1', bu=None):
    """Candidate shares intentionally need not sum to 100% in round one."""
    region = {'SP': 'Sudeste', 'BA': 'Nordeste', 'DF': 'Centro-Oeste', 'ZZ': 'Exterior'}[uf]
    return dict(zip(FIELDS, [election, turn, uf, '1' if capital else '2',
        'Município Sintético', '1', str(number), region, capital, band,
        2000000 if capital else 9000, nominal + 10, nominal, lula, flavio,
        time, time if bu is None else bu]))


class CurveInferenceTests(unittest.TestCase):
    def test_symmetric_pooled_center_and_plus_one_rank(self):
        observed = np.array([0.0, 0.0])
        draws = np.array([[10.0, 10.0], [11.0, 10.0], [9.0, 11.0]])
        result = curve_test(observed, draws)
        self.assertEqual(result['status'], 'tested')
        np.testing.assert_allclose(result['reference_mean'], [7.5, 7.75])
        self.assertAlmostEqual(result['observed_statistic_pp'], 7.75)
        np.testing.assert_allclose(result['statistics'], [7.75, 2.5, 3.5, 3.25])
        self.assertEqual(result['p_value'], 1 / 4)
        self.assertGreater(result['p_value'], 0)

    def test_equal_statistics_do_not_make_varying_curves_invariant(self):
        result = curve_test(np.array([0.0, 1.0]), np.array([[1.0, 0.0]]))
        self.assertEqual(result['status'], 'tested')
        self.assertEqual(result['p_value'], 1.0)

    def test_invariant_or_undefined_curve_is_not_evidence_of_randomness(self):
        constant = curve_test(np.array([10.0, 20.0]), np.array([[10.0, 20.0]] * 3))
        self.assertEqual(constant['status'], 'not_applicable')
        self.assertIsNone(constant['p_value'])
        invalid = curve_test(np.array([float('nan'), 20.0]), np.array([[10.0, 20.0]] * 3))
        self.assertEqual(invalid['status'], 'not_applicable')
        self.assertIsNone(invalid['p_value'])

    def test_holm_adjustment_known_values_original_order_and_na(self):
        values = [0.01, None, 0.04, 0.03, 0.002]
        adjusted = holm_adjust(values)
        expected = [0.03, None, 0.06, 0.06, 0.008]
        for actual, target in zip(adjusted, expected):
            if target is None:
                self.assertIsNone(actual)
            else:
                self.assertAlmostEqual(actual, target)
        self.assertEqual(holm_adjust([]), [])
        self.assertEqual(holm_adjust([None, None]), [None, None])


class RandomizationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / 'events.sqlite'
        self.output = self.root / 'analysis'

    def prepare(self, events):
        text_fields = {'election_code', 'turno', 'uf', 'municipality', 'municipality_name',
                       'zone', 'section', 'region', 'size_band', 'first_time', 'bu_time'}
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE section_events (' + ','.join(
                name + (' TEXT' if name in text_fields else ' INTEGER') for name in FIELDS) + ')')
            db.executemany('INSERT INTO section_events VALUES (' + ','.join('?' for _ in FIELDS) + ')',
                           [tuple(row[name] for name in FIELDS) for row in events])

    def execute(self, events, permutations=19, seed=12345, output=None):
        self.prepare(events)
        before = hashlib.sha256(self.database.read_bytes()).hexdigest()
        result = run_randomization(self.database, output or self.output,
                                   permutations=permutations, seed=seed)
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), before)
        return result

    def rows(self, filename, output=None, **matches):
        with ((output or self.output) / filename).open(encoding='utf8', newline='') as stream:
            return [row for row in csv.DictReader(stream)
                    if all(row[name] == str(value) for name, value in matches.items())]

    @staticmethod
    def tied_fixture():
        return [
            section(1, nominal=100, lula=20, flavio=30),
            section(2, nominal=50, lula=10, flavio=15),
            section(3, nominal=100, lula=70, flavio=20, capital=0, band='<=10k',
                    time='2026-10-04 18:00:00.000000'),
            section(4, nominal=50, lula=35, flavio=10, capital=0, band='<=10k',
                    time='2026-10-04 18:00:00.000000'),
            section(5, uf='BA', nominal=100, lula=80, flavio=10,
                    time='2026-10-04 19:00:00.000000'),
            section(6, uf='BA', nominal=50, lula=40, flavio=5,
                    time='2026-10-04 19:00:00.000000'),
            section(7, uf='BA', nominal=100, lula=30, flavio=40, capital=0, band='<=10k',
                    time='2026-10-04 20:00:00.000000'),
            section(8, uf='BA', nominal=50, lula=15, flavio=20, capital=0, band='<=10k',
                    time='2026-10-04 20:00:00.000000'),
        ]

    def test_seed_reproduces_outputs_and_source_database_is_read_only(self):
        self.execute(self.tied_fixture(), permutations=19)
        other = self.root / 'repeated'
        run_randomization(self.database, other, permutations=19, seed=12345)
        for name in ['randomization-results.csv', 'randomization-bands.csv']:
            self.assertEqual((self.output / name).read_bytes(), (other / name).read_bytes(), name)

    def test_ties_weighted_candidate_payload_and_noncomplement_first_round(self):
        self.execute(self.tied_fixture(), permutations=19)
        first = self.rows('randomization-bands.csv', source_timestamp=PRIMARY,
                          null_model='global', requested_sections_percentage='10')
        self.assertTrue(first)
        self.assertTrue(all(float(row['actual_sections_percentage']) == 25 for row in first))
        final = self.rows('randomization-bands.csv', source_timestamp=PRIMARY,
                          null_model='global', dimension='candidate', group='BR',
                          metric='candidate_percentage', requested_sections_percentage='99')
        observed = {row['candidate']: float(row['observed']) for row in final}
        self.assertEqual(observed, {'13': 50.0, '22': 25.0})
        # Nominal weights also preserve each section's unequal vote total.
        [sp] = self.rows('randomization-bands.csv', source_timestamp=PRIMARY,
                         null_model='global', dimension='uf', group='SP',
                         metric='nominal_weight_percentage', requested_sections_percentage='10')
        self.assertEqual(float(sp['observed']), 100.0)

    def test_candidate_curves_weight_votes_and_keep_draw_payloads_joint(self):
        events = [section(1, nominal=100, lula=90, flavio=5),
                  section(2, nominal=10, lula=0, flavio=5, capital=0, band='<=10k'),
                  section(3, nominal=90, lula=0, flavio=80, capital=0, band='<=10k',
                          time='2026-10-04 18:00:00.000000')]
        self.execute(events, permutations=49)
        [lula] = self.rows('randomization-bands.csv', source_timestamp=PRIMARY,
                           null_model='global', dimension='candidate', group='BR', candidate='13',
                           requested_sections_percentage='10')
        self.assertAlmostEqual(float(lula['observed']), 100 * 90 / 110)
        self.assertNotEqual(float(lula['observed']), 45.0)  # Mean of the two section percentages.
        candidates = self.rows('randomization-bands.csv', dimension='candidate')
        for row in candidates:
            for field in ['observed', 'reference_mean', 'lower_2_5', 'upper_97_5']:
                if row[field]:
                    self.assertGreaterEqual(float(row[field]), 0)
                    self.assertLessEqual(float(row[field]), 100)

    def test_common_permutations_across_identical_sources_and_primary_family_only(self):
        self.execute(self.tied_fixture(), permutations=19)
        rows = self.rows('randomization-bands.csv')
        identifiers = ['election_code', 'turno', 'null_model', 'dimension', 'group',
                       'candidate', 'metric', 'requested_sections_percentage']
        primary = {tuple(row[k] for k in identifiers): row for row in rows if row['source_timestamp'] == PRIMARY}
        receipt = {tuple(row[k] for k in identifiers): row for row in rows if row['source_timestamp'] == RECEIPT}
        self.assertEqual(set(primary), set(receipt))
        for key, row in primary.items():
            for field in ['observed', 'reference_mean', 'lower_2_5', 'upper_97_5']:
                self.assertEqual(row[field], receipt[key][field], (key, field))
        results = self.rows('randomization-results.csv')
        for row in results:
            if row['source_timestamp'] == RECEIPT:
                self.assertEqual(row['primary_test'], '0')
                self.assertEqual(row['p_adjusted'], '')
                self.assertNotEqual(row['status'], 'detected')
            elif row['primary_test'] == '1' and row['p_value']:
                self.assertGreaterEqual(float(row['p_value']), 1 / 20)

    def test_holm_family_pools_both_rounds_and_excludes_sensitivity(self):
        first = self.tied_fixture()
        second = []
        for row in first:
            item = dict(row, election_code='101', turno='2')
            item['first_time'] = row['first_time'].replace('10-04', '10-25')
            item['bu_time'] = row['bu_time'].replace('10-04', '10-25')
            item['flavio_votes'] = item['nominal_votes'] - item['lula_votes']
            second.append(item)
        self.execute(first + second, permutations=49)
        primary = [row for row in self.rows('randomization-results.csv') if row['primary_test'] == '1']
        self.assertEqual({row['turno'] for row in primary}, {'1', '2'})
        self.assertTrue(all(row['source_timestamp'] == PRIMARY for row in primary))
        expected = holm_adjust([float(row['p_value']) if row['p_value'] else None for row in primary])
        for row, adjusted in zip(primary, expected):
            if adjusted is None:
                self.assertEqual(row['p_adjusted'], '')
            else:
                self.assertAlmostEqual(float(row['p_adjusted']), adjusted)

    def test_conditional_reference_preserves_uf_order_and_uses_own_center(self):
        self.execute(self.tied_fixture(), permutations=49)
        within = self.rows('randomization-results.csv', null_model='within_uf')
        self.assertFalse(any(row['dimension'] in {'region', 'uf'} and row['primary_test'] == '1'
                             for row in within))
        # With SP fully counted and BA not yet started, shuffling only inside UF
        # leaves the national 50% endpoint at the exact final SP share (45%),
        # distinct from the national final share (50%).
        [row] = self.rows('randomization-bands.csv', source_timestamp=PRIMARY,
                         null_model='within_uf', dimension='candidate', group='BR', candidate='13',
                         requested_sections_percentage='50')
        self.assertAlmostEqual(float(row['observed']), 45.0)
        self.assertAlmostEqual(float(row['reference_mean']), 45.0)
        self.assertNotEqual(float(row['reference_mean']), 50.0)
        self.assertAlmostEqual(float(row['lower_2_5']), 45.0)
        self.assertAlmostEqual(float(row['upper_97_5']), 45.0)

    def test_constant_payload_and_single_uf_have_no_applicable_order_test(self):
        events = [section(i, uf='DF', nominal=100, lula=30, flavio=40,
                          time=f'2026-10-04 {17+i:02d}:00:00.000000') for i in range(4)]
        self.execute(events, permutations=9)
        primary = [row for row in self.rows('randomization-results.csv') if row['primary_test'] == '1']
        self.assertTrue(primary)
        self.assertTrue(all(row['status'] == 'not_applicable' for row in primary))
        self.assertTrue(all(row['p_value'] == '' and row['p_adjusted'] == '' for row in primary))

    def test_clear_territorial_order_departs_from_global_exchangeability(self):
        events = [section(i, uf='SP' if i < 10 else 'BA', nominal=10, lula=4, flavio=3,
                          capital=i % 2, band='>1m' if i % 2 else '<=10k',
                          time=f'2026-10-04 17:{i:02d}:00.000000') for i in range(20)]
        self.execute(events, permutations=99, seed=41)
        [row] = self.rows('randomization-results.csv', source_timestamp=PRIMARY,
                         null_model='global', dimension='uf', group='SP',
                         metric='section_completion_percentage')
        self.assertLessEqual(float(row['p_value']), 0.03)

    def test_missing_timestamp_fails_instead_of_creating_false_complete_coverage(self):
        events = self.tied_fixture()
        events[0]['first_time'] = None
        self.prepare(events)
        with self.assertRaises(ValueError):
            run_randomization(self.database, self.output, permutations=9, seed=1)

    def test_zero_nominal_denominator_is_undefined_not_zero_share(self):
        events = [section(1, nominal=0, lula=0, flavio=0),
                  section(2, nominal=100, lula=20, flavio=30,
                          time='2026-10-04 18:00:00.000000')]
        self.execute(events, permutations=9)
        rows = self.rows('randomization-bands.csv', source_timestamp=PRIMARY,
                         null_model='global', dimension='candidate', group='BR',
                         requested_sections_percentage='10')
        self.assertTrue(rows)
        self.assertTrue(all(row['observed'] == '' for row in rows))
        candidates = self.rows('randomization-results.csv', source_timestamp=PRIMARY,
                               null_model='global', dimension='candidate', group='BR')
        self.assertTrue(all(row['status'] == 'not_applicable' for row in candidates))


if __name__ == '__main__':
    unittest.main()
