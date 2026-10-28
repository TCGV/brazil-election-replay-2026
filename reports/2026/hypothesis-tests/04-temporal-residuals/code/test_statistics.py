"""Independent finite examples for temporal statistics; no election data read."""
from __future__ import annotations

from fractions import Fraction
from itertools import permutations, product
import unittest

import numpy as np

from temporal_statistics import (
    assignment, cohort, gradual_variance, holm, minute_values, prepare,
    score_variability, scores_from_minutes, timing,
)


EPOCH = 1_700_000_000 // 60 * 60


def fixture(votes, minutes=None, places=None, zones=None, bu_minutes=None,
            aptos=250):
    votes = np.asarray(votes, dtype=np.int64)
    count = len(votes)
    minutes = np.arange(count) if minutes is None else np.asarray(minutes)
    bu_minutes = minutes if bu_minutes is None else np.asarray(bu_minutes)
    nominal = votes.sum(axis=1)
    return dict(
        aptos=np.full(count, aptos, dtype=np.int64),
        turnout=nominal + 5, nominal=nominal,
        candidate_votes=votes,
        installed=np.ones(count, dtype=bool),
        cancelled=np.zeros(count, dtype=bool),
        uf=np.asarray(['SP'] * count),
        municipality=np.ones(count, dtype=np.int64),
        zone=np.asarray(zones if zones is not None else [1] * count),
        place=np.asarray(places if places is not None else [1] * count),
        first_time=EPOCH + minutes * 60,
        bu_time=EPOCH + bu_minutes * 60,
        blank=np.full(count, 2, dtype=np.int64),
        null=np.full(count, 3, dtype=np.int64),
    )


def small_fixture():
    return fixture(
        [[40, 30, 10], [60, 30, 10], [80, 25, 15], [20, 60, 10],
         [30, 70, 10], [45, 40, 10]],
        minutes=[0, 0, 2, 4, 1, 4], places=[1, 1, 1, 1, 2, 2],
        zones=[1, 1, 1, 1, 2, 2], bu_minutes=[0, 1, 1, 3, 0, 3],
    )


def fraction_residuals(votes, groups):
    """Pure-Python oracle; group membership is supplied by the example."""
    nominal = [sum(row) for row in votes]
    result = [[Fraction(0) for _ in votes[0]] for _ in votes]
    for group in groups:
        total = sum(nominal[index] for index in group)
        for candidate in range(len(votes[0])):
            rate = Fraction(sum(votes[index][candidate] for index in group), total)
            for index in group:
                result[index][candidate] = votes[index][candidate] - rate * nominal[index]
    return result


def fraction_scores(residuals, minutes, final_nominal, assign=None):
    """Rational G/C/M oracle, including every empty intervening minute."""
    assign = list(range(len(residuals))) if assign is None else assign
    first, last = min(minutes), max(minutes)
    by_minute = [[Fraction(0) for _ in residuals[0]]
                 for _ in range(first, last + 1)]
    counts = [0] * len(by_minute)
    for slot, source in enumerate(assign):
        minute = minutes[slot] - first
        counts[minute] += 1
        for candidate, residual in enumerate(residuals[source]):
            by_minute[minute][candidate] += residual
    weights = []
    before = 0
    for count in counts:
        weights.append(Fraction(2 * before + count, 2 * len(minutes)) - Fraction(1, 2))
        before += count
    signed, indices = [], []
    scale = Fraction(100, final_nominal)
    for candidate in range(len(residuals[0])):
        arrivals = [row[candidate] for row in by_minute]
        running = Fraction(0)
        cumulative = []
        for value in arrivals:
            running += value
            cumulative.append(running)
        ci = max(range(len(cumulative)), key=lambda index: abs(cumulative[index]))
        mi = max(range(len(arrivals)), key=lambda index: abs(arrivals[index]))
        signed.append((sum(w * value for w, value in zip(weights, arrivals)) * scale,
                       cumulative[ci] * scale, arrivals[mi] * scale))
        indices.append((ci, mi))
    return signed, indices


class TemporalStatisticsTests(unittest.TestCase):
    def evaluate(self, prepared, source='first_time', assign=None):
        residual = prepared['residual']
        if assign is not None:
            residual = residual[assign]
        time = prepared['sources'][source]
        arrivals = minute_values(residual, time)
        return scores_from_minutes(arrivals, time, prepared['final_nominal'])

    def test_exact_residuals_and_local_closure(self):
        data = small_fixture()
        prepared = prepare(data, 'place_size')
        expected = fraction_residuals(data['candidate_votes'].tolist(),
                                      [(0, 1, 2, 3), (4, 5)])
        np.testing.assert_allclose(prepared['residual'],
                                   [[float(value) for value in row] for row in expected],
                                   rtol=1e-13, atol=1e-13)
        for indices in [(0, 1, 2, 3), (4, 5)]:
            np.testing.assert_allclose(prepared['residual'][list(indices)].sum(axis=0),
                                       0, atol=1e-12)

    def test_all_48_permutations_against_rational_oracle_both_clocks(self):
        data = small_fixture()
        prepared = prepare(data, 'place_size')
        residuals = fraction_residuals(data['candidate_votes'].tolist(),
                                      [(0, 1, 2, 3), (4, 5)])
        checked = 0
        for left, right in product(permutations(range(4)), permutations((4, 5))):
            assign = list(left + right)
            for source in ('first_time', 'bu_time'):
                minutes = ((data[source] - EPOCH) // 60).tolist()
                expected, indices = fraction_scores(residuals, minutes,
                                                     int(data['nominal'].sum()), assign)
                actual, signed, ci, mi, cumulative = self.evaluate(prepared, source, assign)
                expected_float = np.asarray([[float(value) for value in row]
                                             for row in expected])
                np.testing.assert_allclose(signed, expected_float, rtol=1e-12, atol=1e-12)
                np.testing.assert_allclose(actual, np.abs(expected_float),
                                           rtol=1e-12, atol=1e-12)
                # Earliest maximizing index is part of the deterministic oracle;
                # exact ties can differ only by roundoff in the rational inputs.
                for candidate, (expected_ci, expected_mi) in enumerate(indices):
                    self.assertAlmostEqual(abs(cumulative[ci[candidate], candidate]),
                                           abs(cumulative[expected_ci, candidate]), places=11)
                    arrivals = minute_values(prepared['residual'][assign], prepared['sources'][source])
                    self.assertAlmostEqual(abs(arrivals[mi[candidate], candidate]),
                                           abs(arrivals[expected_mi, candidate]), places=11)
                np.testing.assert_allclose(cumulative[-1], 0, atol=1e-12)
                checked += 1
        self.assertEqual(checked, 96)

    def test_gradual_variance_matches_exhaustive_rational_second_moment(self):
        data = small_fixture()
        prepared = prepare(data, 'place_size')
        residuals = fraction_residuals(data['candidate_votes'].tolist(),
                                      [(0, 1, 2, 3), (4, 5)])
        for source in ('first_time', 'bu_time'):
            values = []
            minutes = ((data[source] - EPOCH) // 60).tolist()
            for left, right in product(permutations(range(4)), permutations((4, 5))):
                scores, _ = fraction_scores(residuals, minutes, int(data['nominal'].sum()),
                                            list(left + right))
                values.append([row[0] for row in scores])
            means = [sum(row[candidate] for row in values) / len(values)
                     for candidate in range(3)]
            self.assertEqual(means, [0, 0, 0])
            variances = [sum(row[candidate] ** 2 for row in values) / len(values)
                         for candidate in range(3)]
            np.testing.assert_allclose(gradual_variance(prepared, source),
                                       [float(value) for value in variances],
                                       rtol=1e-12, atol=1e-12)

    def test_exhaustive_absolute_tail_ranks_are_conservative_with_ties(self):
        votes = [[30, 70], [30, 70], [70, 30], [70, 30]]
        data = fixture(votes, minutes=[0, 0, 1, 3])
        prepared = prepare(data, 'place_size')
        residuals = fraction_residuals(votes, [(0, 1, 2, 3)])
        values = []
        for assign in permutations(range(4)):
            scores, _ = fraction_scores(residuals, [0, 0, 1, 3], 400, list(assign))
            values.append([abs(value) for value in scores[0]])
            actual = self.evaluate(prepared, assign=list(assign))[0][0]
            np.testing.assert_allclose(actual, [float(value) for value in values[-1]], atol=1e-12)
        for statistic in range(3):
            tails = [Fraction(sum(other[statistic] >= row[statistic] for other in values), 24)
                     for row in values]
            for alpha in set(tails):
                probability = Fraction(sum(value <= alpha for value in tails), 24)
                self.assertLessEqual(probability, alpha)

    def test_midrank_minute_ties_empty_minutes_and_fixed_checkpoints(self):
        time = timing(np.asarray([10, 10, 12, 14]))
        np.testing.assert_array_equal(time['counts'], [2, 0, 1, 0, 1])
        np.testing.assert_array_equal(time['index'], [0, 0, 2, 4])
        np.testing.assert_allclose(time['weights'], [-0.25, 0, 0.125, 0.25, 0.375])
        self.assertEqual(time['checkpoints'][0], -1)
        np.testing.assert_array_equal(time['checkpoints'][1:51], 0)
        np.testing.assert_array_equal(time['checkpoints'][51:76], 2)
        np.testing.assert_array_equal(time['checkpoints'][76:], 4)
        np.testing.assert_array_equal(minute_values([1, 2, 3, 4], time)[:, 0], [3, 0, 3, 0, 4])

    def test_early_and_late_advantages_reverse_gradual_sign(self):
        data = fixture([[49, 51]] * 50 + [[51, 49]] * 50)
        prepared = prepare(data, 'place_size')
        actual, signed, _, _, _ = self.evaluate(prepared)
        self.assertAlmostEqual(signed[0, 0], 0.25, places=13)
        self.assertAlmostEqual(signed[1, 0], -0.25, places=13)
        self.assertAlmostEqual(actual[0, 1], 0.5, places=13)
        self.assertAlmostEqual(actual[0, 2], 0.01, places=13)
        variance = gradual_variance(prepared, 'first_time')[0]
        self.assertGreater(signed[0, 0] / np.sqrt(variance), 8)
        # Reversing only chronology reverses direction without changing totals.
        data['first_time'] = data['first_time'][::-1].copy()
        reverse = self.evaluate(prepare(data, 'place_size'))
        np.testing.assert_allclose(reverse[0], actual, atol=1e-12)
        self.assertAlmostEqual(reverse[1][0, 0], -signed[0, 0], places=13)

    def test_abrupt_one_minute_contribution_identifies_actual_lot(self):
        data = fixture([[49, 51]] * 9 + [[59, 41]])
        prepared = prepare(data, 'place_size')
        actual, signed, _, mi, cumulative = self.evaluate(prepared)
        self.assertAlmostEqual(actual[0, 2], 0.9, places=13)
        self.assertAlmostEqual(signed[0, 2], 0.9, places=13)
        self.assertEqual(mi[0], 9)
        self.assertEqual(mi[1], 9)
        np.testing.assert_allclose(cumulative[-1], 0, atol=1e-12)

    def test_legitimate_between_place_heterogeneity_is_conditioned_out(self):
        data = fixture([[20, 80]] * 4 + [[80, 20]] * 4,
                       places=[1] * 4 + [2] * 4)
        zone = prepare(data, 'zone_size')
        place = prepare(data, 'place_size')
        zone_score = self.evaluate(zone)[0]
        self.assertGreater(zone_score[0, 0], 0)
        self.assertGreater(zone_score[0, 1], 0)
        np.testing.assert_array_equal(place['numerator'], 0)
        np.testing.assert_array_equal(place['residual'], 0)
        np.testing.assert_array_equal(self.evaluate(place)[0], 0)
        np.testing.assert_array_equal(gradual_variance(place, 'first_time'), 0)

    def test_exact_fractional_proportions_cannot_create_float_support(self):
        data = fixture([[10, 50], [20, 100], [30, 150]])
        prepared = prepare(data, 'place_size')
        np.testing.assert_array_equal(prepared['numerator'], 0)
        np.testing.assert_array_equal(prepared['residual'], 0)
        np.testing.assert_array_equal(prepared['variable'], False)
        np.testing.assert_array_equal(gradual_variance(prepared, 'first_time'), 0)

    def test_singletons_and_absent_candidate_are_not_evidence_of_variation(self):
        data = fixture([[30, 70, 0], [60, 40, 0], [10, 90, 0]], places=[1, 1, 2])
        prepared = prepare(data, 'place_size')
        np.testing.assert_array_equal(prepared['residual'][2], 0)
        np.testing.assert_array_equal(prepared['residual'][:, 2], 0)
        self.assertEqual(gradual_variance(prepared, 'first_time')[2], 0)
        for repetition in range(20):
            draw = assignment(prepared, 20261028, 1, 1, repetition)
            self.assertEqual(draw[2], 2)
        all_singletons = prepare(fixture([[30, 70], [60, 40]], places=[1, 2]), 'place_size')
        np.testing.assert_array_equal(self.evaluate(all_singletons)[0], 0)
        np.testing.assert_array_equal(assignment(all_singletons, 9, 2, 1, 0), [0, 1])

    def test_timestamp_tie_has_no_support_but_paired_bu_can_vary(self):
        data = fixture([[20, 80], [40, 60], [60, 40], [80, 20]],
                       minutes=[0, 0, 0, 0], bu_minutes=[0, 1, 2, 3])
        data['first_time'] += np.asarray([1, 10, 20, 59])
        prepared = prepare(data, 'place_size')
        self.assertFalse(prepared['sources']['first_time']['time_varied'][0])
        self.assertTrue(prepared['sources']['bu_time']['time_varied'][0])
        np.testing.assert_array_equal(self.evaluate(prepared)[0], 0)
        np.testing.assert_array_equal(gradual_variance(prepared, 'first_time'), 0)
        self.assertTrue(np.all(gradual_variance(prepared, 'bu_time') > 0))

    def test_assignment_preserves_groups_whole_payload_and_accounting(self):
        data = small_fixture()
        prepared = prepare(data, 'place_size')
        original_sums = data['candidate_votes'].sum(axis=0)
        seen = set()
        for repetition in range(100):
            draw = assignment(prepared, 20261028, 1, 1, repetition)
            np.testing.assert_array_equal(np.sort(draw), np.arange(6))
            np.testing.assert_array_equal(prepared['labels'][draw], prepared['labels'])
            votes = data['candidate_votes'][draw]
            nominal = data['nominal'][draw]
            turnout = data['turnout'][draw]
            np.testing.assert_array_equal(votes.sum(axis=0), original_sums)
            np.testing.assert_array_equal(votes.sum(axis=1), nominal)
            np.testing.assert_array_equal(nominal + data['blank'][draw] + data['null'][draw], turnout)
            np.testing.assert_array_equal(votes[0], data['candidate_votes'][draw[0]])
            seen.add(tuple(draw))
        self.assertGreater(len(seen), 25)

    def test_repetition_seed_matches_spawn_and_is_schedule_independent(self):
        prepared = prepare(fixture([[20, 80], [40, 60], [60, 40], [80, 20]]), 'place_size')
        children = np.random.SeedSequence([20261028, 1, 1]).spawn(10)
        sequential = [assignment(prepared, 20261028, 1, 1, rep) for rep in range(10)]
        for rep in [9, 3, 1, 0, 8, 5, 7, 2, 4, 6]:
            direct = assignment(prepared, 20261028, 1, 1, rep)
            expected = np.random.default_rng(children[rep]).permutation(4)
            np.testing.assert_array_equal(direct, sequential[rep])
            np.testing.assert_array_equal(direct, expected)

    def test_size_control_and_no_size_sensitivity_are_distinct(self):
        data = fixture([[20, 80], [80, 20]])
        data['aptos'] = np.asarray([150, 300])
        sized = prepare(data, 'place_size')
        broad = prepare(data, 'place_no_size')
        np.testing.assert_array_equal(sized['sizes'], [1, 1])
        np.testing.assert_array_equal(broad['sizes'], [2])
        np.testing.assert_array_equal(sized['residual'], 0)
        self.assertGreater(self.evaluate(broad)[0][0, 0], 0)

    def test_exclusions_are_exclusive_and_not_candidate_selected(self):
        data = fixture([[40, 60]] * 8)
        data['installed'][0] = False
        data['aptos'][0:2] = 49
        data['turnout'][2] = 0
        data['nominal'][3] = 49
        data['place'][4] = -1
        data['first_time'][5] = -1
        data['bu_time'][6] = -1
        mask, reasons, basic = cohort(data)
        self.assertEqual(reasons.tolist(), [
            'section_status', 'aptos_below_50', 'nonpositive_turnout',
            'nominal_below_floor', 'missing_place', 'missing_time',
            'missing_time', 'eligible',
        ])
        np.testing.assert_array_equal(np.flatnonzero(mask), [7])
        np.testing.assert_array_equal(np.flatnonzero(basic), [4, 5, 6, 7])
        data['candidate_votes'][:] = 0
        np.testing.assert_array_equal(cohort(data)[0], mask)

    def test_holm_uses_full_family_including_na_placeholders(self):
        # Three N/A references are p=1 in the fixed family, not omitted tests.
        pvalues = [0.001, 0.01, 1.0, 1.0, 1.0]
        np.testing.assert_allclose(holm(pvalues), [0.005, 0.04, 1, 1, 1])
        # Exhaustive 90-test example: a single minimum-rank p=.0002 -> .018.
        pvalues = [1.0] * 90
        pvalues[37] = 0.0002
        adjusted = holm(pvalues)
        self.assertAlmostEqual(adjusted[37], 0.018, places=13)
        self.assertEqual(sum(adjusted < 0.05), 1)

    def test_holm_ties_ordering_and_invalid_inputs(self):
        np.testing.assert_allclose(holm([0.04, 0.01, 0.01, 0.8]), [0.08, 0.04, 0.04, 0.8])
        for invalid in [[-1], [1.01], [float('nan')], [float('inf')]]:
            with self.assertRaises(ValueError):
                holm(invalid)

    def test_pair_has_signed_variance_but_all_absolute_scores_constant(self):
        prepared = prepare(fixture([[40, 60], [60, 40]]), 'place_size')
        observed = self.evaluate(prepared)[0][0]
        self.assertGreater(gradual_variance(prepared, 'first_time')[0], 0)
        flags, reasons = score_variability(prepared, 'first_time', 0,
                                           observed[None, :], observed)
        np.testing.assert_array_equal(flags, [False, False, False])
        self.assertEqual(reasons, ['exact_enumeration_constant'] * 3)

    def test_exact_enumeration_and_sampled_witness_are_distinct_proofs(self):
        prepared = prepare(fixture([[40, 60], [50, 50], [60, 40]]), 'place_size')
        observed = self.evaluate(prepared)[0][0]
        flags, reasons = score_variability(prepared, 'first_time', 0,
                                           observed[None, :], observed)
        np.testing.assert_array_equal(flags, [True, False, False])
        self.assertEqual(reasons, ['exact_enumeration_variable',
                                  'exact_enumeration_constant',
                                  'exact_enumeration_constant'])
        # With a tied first minute, exchanging the final zero residual makes
        # every minute residual zero, giving an actual witness for all scores.
        tied = prepare(fixture([[40, 60], [50, 50], [60, 40]], minutes=[0, 0, 1]),
                       'place_size')
        observed = self.evaluate(tied)[0][0]
        other = self.evaluate(tied, assign=[0, 2, 1])[0][0]
        flags, reasons = score_variability(tied, 'first_time', 0,
                                           other[None, :], observed, max_exact=0)
        np.testing.assert_array_equal(flags, True)
        self.assertEqual(reasons, ['sampled_distinct_scores'] * 3)

    def test_unsampled_large_orbit_is_unresolved_not_constant(self):
        prepared = prepare(fixture([[value, 100-value] for value in range(40, 49)]),
                           'place_size')
        observed = self.evaluate(prepared)[0][0]
        with self.assertRaisesRegex(ArithmeticError, 'Unresolved absolute-score variability'):
            score_variability(prepared, 'first_time', 0,
                              observed[None, :], observed)
        # Exact proportionality proves no informative groups without needing
        # to enumerate even an empty permitted orbit.
        constant = prepare(fixture([[40, 60]] * 9), 'place_size')
        flags, reasons = score_variability(constant, 'first_time', 0,
                                           np.zeros((1, 3)), np.zeros(3), max_exact=0)
        np.testing.assert_array_equal(flags, False)
        self.assertEqual(reasons, ['no_informative_groups'] * 3)

    def test_invalid_temporal_scope_and_empty_cohort_fail(self):
        with self.assertRaises(ValueError):
            timing(np.asarray([0, 7 * 24 * 60 + 1]))
        data = fixture([[20, 80], [80, 20]])
        with self.assertRaises(ValueError):
            prepare(data, 'unknown')
        data['installed'][:] = False
        with self.assertRaises(ValueError):
            prepare(data, 'place_size')


if __name__ == '__main__':
    unittest.main()
