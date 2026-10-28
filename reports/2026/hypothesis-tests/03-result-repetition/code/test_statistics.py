"""Independent exact-enumeration and synthetic controls for H3 statistics.

These small, artificial examples are implementation tests, not election results.
"""
from collections import Counter
from fractions import Fraction
from functools import lru_cache
import importlib.util
from math import comb
from pathlib import Path
import unittest

import numpy as np

SPEC = importlib.util.spec_from_file_location('h3_collision_statistics', Path(__file__).with_name('collision_statistics.py'))
STATS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATS)


def partitions(n, maximum=None):
    if n == 0:
        yield ()
        return
    for first in range(min(n, n if maximum is None else maximum), 0, -1):
        for rest in partitions(n - first, first):
            yield (first,) + rest


@lru_cache(maxsize=None)
def collision_distribution(a, b):
    """Enumerate each distinct A assignment once, fixing the B positions."""
    if sum(a) != sum(b) or any(value <= 0 for value in (*a, *b)):
        raise ValueError('Positive margins with equal totals required')
    groups = [j for j, size in enumerate(b) for _ in range(size)]
    remaining = list(a)
    cells = [[0] * len(a) for _ in b]
    counts = Counter()

    def visit(position, collisions):
        if position == len(groups):
            counts[collisions] += 1
            return
        group = groups[position]
        for label, left in enumerate(remaining):
            if left:
                increment = cells[group][label]
                remaining[label] -= 1
                cells[group][label] += 1
                visit(position + 1, collisions + increment)
                cells[group][label] -= 1
                remaining[label] += 1

    visit(0, 0)
    total = sum(counts.values())
    return {value: Fraction(count, total) for value, count in counts.items()}


def distribution_moments(distribution):
    mean = sum(value * probability for value, probability in distribution.items())
    variance = sum((value - mean) ** 2 * probability for value, probability in distribution.items())
    return mean, variance


def synthetic_round(candidate_vectors, specials=None, aptos=None, **changes):
    vectors = np.asarray(candidate_vectors, dtype=np.int32)
    n = len(vectors)
    special = np.asarray(specials if specials is not None else np.zeros((n, 4)), dtype=np.int32)
    nominal = vectors.sum(axis=1, dtype=np.int32)
    turnout = nominal + special.sum(axis=1, dtype=np.int32)
    registered = np.asarray(aptos if aptos is not None else np.full(n, 500), dtype=np.int32)
    data = dict(election_code=6257, turno=1, candidate_numbers=list(range(1, vectors.shape[1]+1)),
                candidate_votes=vectors, uf=np.full(n, 'SP'), municipality=np.full(n, 71072, dtype=np.int32),
                zone=np.ones(n, dtype=np.int32), section=np.arange(1, n+1, dtype=np.int32),
                place=np.ones(n, dtype=np.int32), source_line=np.arange(2, n+2, dtype=np.int32),
                aptos=registered, turnout=turnout, abstentions=registered-turnout, nominal=nominal,
                blank=special[:, 0], null_votes=special[:, 1], legend=special[:, 2], separate=special[:, 3],
                installed=np.ones(n, dtype=bool), cancelled=np.zeros(n, dtype=bool))
    data.update(changes)
    return data


def special_vectors(data):
    return np.column_stack([data[field] for field in ('blank','null_votes','legend','separate','turnout')])


class ExactMomentTests(unittest.TestCase):
    def test_exact_moments_match_all_small_margin_assignments(self):
        configurations = 0
        for n in range(1, 7):
            for a in partitions(n):
                for b in partitions(n):
                    with self.subTest(a=a, b=b):
                        expected = distribution_moments(collision_distribution(a, b))
                        actual = STATS.moments(a, b)
                        self.assertTrue(all(isinstance(value, Fraction) for value in actual))
                        self.assertEqual(actual, expected)
                        self.assertEqual(STATS.moments(b, a), expected, 'The collision statistic is symmetric in the two blocks')
                    configurations += 1
        self.assertEqual(configurations, 209)

    def test_cantelli_is_conservative_at_every_attainable_small_threshold(self):
        for n in range(1, 7):
            for a in partitions(n):
                for b in partitions(n):
                    distribution = collision_distribution(a, b)
                    mean, variance = distribution_moments(distribution)
                    bounds = {value: STATS.cantelli_bound(value, mean, variance) for value in distribution}
                    effective = {value: Fraction(1) if bound is None else bound for value, bound in bounds.items()}
                    for level in set(effective.values()):
                        rejected = sum(probability for value, probability in distribution.items() if effective[value] <= level)
                        self.assertLessEqual(rejected, level, (a, b, level, rejected))

    def test_small_and_constant_strata_are_not_evidence_of_naturalness(self):
        for a, b, observed in [((1,), (1,), 0), ((2,), (2,), 1), ((1,1), (2,), 0), ((1,1), (1,1), 0)]:
            mean, variance = STATS.moments(a, b)
            self.assertEqual((mean, variance), (Fraction(observed), Fraction(0)))
            self.assertIsNone(STATS.cantelli_bound(observed, mean, variance))
            with self.assertRaises(ArithmeticError):
                STATS.cantelli_bound(observed+1, mean, variance)
        self.assertEqual(STATS.moments((), ()), (Fraction(0), Fraction(0)))
        with self.assertRaises(ValueError):
            STATS.moments((2,), (3,))

    def test_known_moments_cantelli_and_fixed_holm_family(self):
        mean, variance = STATS.moments((2,2), (2,2))
        self.assertEqual(mean, Fraction(2,3))
        self.assertEqual(variance, Fraction(8,9))
        self.assertEqual(STATS.cantelli_bound(2, mean, variance), Fraction(1,3))
        self.assertEqual(STATS.cantelli_bound(0, mean, variance), Fraction(1))
        self.assertEqual(STATS.holm_bounds([Fraction(1,50), None]), [Fraction(1,25), None])
        self.assertEqual(STATS.holm_bounds([Fraction(1,100), Fraction(3,100)]), [Fraction(1,50), Fraction(3,100)])


class SignatureAndControlTests(unittest.TestCase):
    def test_full_counts_keep_candidate_identity_and_unequal_denominators(self):
        data = synthetic_round([[60,40], [60,40], [120,80], [40,60]])
        result = STATS.inventory(STATS.signature_matrix(data))
        self.assertEqual(result['repeated_groups'], 1)
        self.assertEqual(result['repeated_sections'], 2)
        self.assertEqual(result['collision_pairs'], 1)
        self.assertEqual(result['distinct_signatures'], 3)
        self.assertEqual(result['max_multiplicity'], 2)
        self.assertEqual(len(set(map(int, data['section']))), 4, 'Equal payloads belong to distinct section keys')
        reordered = dict(data, candidate_numbers=[2,1], candidate_votes=data['candidate_votes'][:, ::-1])
        np.testing.assert_array_equal(STATS.signature_matrix(data), STATS.signature_matrix(reordered))

    def test_special_categories_and_minor_candidates_are_part_of_signature(self):
        data = synthetic_round([[60,39,1], [60,39,1], [60,40,0], [60,39,1]],
                               specials=[[1,2,0,0], [2,1,0,0], [1,2,0,0], [1,1,0,1]])
        self.assertEqual(STATS.inventory(STATS.signature_matrix(data))['collision_pairs'], 0)
        data['turnout'][0] += 1
        with self.assertRaisesRegex(ValueError, 'reconcile'):
            STATS.signature_matrix(data)

    def test_all_zero_small_and_positive_views_are_preserved_and_partitioned(self):
        data = synthetic_round([[60,40], [60,40], [3,2], [3,2], [0,0], [0,0], [4,6], [4,6]],
                               aptos=[500,500,20,20,10,20,500,500])
        data['installed'][4:] = False
        data['abstentions'][4:6] = 0  # Preserve uninstalled auxiliary exceptions rather than repairing them.
        masks = STATS.population_masks(data)
        partition = np.zeros(8, dtype=np.int8)
        for name in ('eligible','small_positive','zero_activity','other_positive'):
            self.assertEqual(int(masks[name].sum()), 2)
            partition += masks[name]
        np.testing.assert_array_equal(partition, np.ones(8, dtype=np.int8))
        signatures = STATS.signature_matrix(data)
        result = STATS.inventory(signatures)
        self.assertEqual((result['repeated_groups'], result['repeated_sections'], result['collision_pairs']), (4,8,4))
        for name in ('eligible','small_positive','zero_activity','other_positive'):
            self.assertEqual(STATS.inventory(signatures, masks[name])['collision_pairs'], 1)
        self.assertEqual(STATS.inventory(STATS.signature_matrix(data, extended=True))['collision_pairs'], 3)

    def test_pairs_are_unordered_overlapping_and_empty_views_remain_empty(self):
        data = synthetic_round([[60,40]]*4)
        result = STATS.inventory(STATS.signature_matrix(data))
        self.assertEqual((result['repeated_groups'], result['repeated_sections'], result['collision_pairs']), (1,4,6))
        empty = STATS.inventory(STATS.signature_matrix(data), np.zeros(4, dtype=bool))
        self.assertEqual((empty['rows'], empty['collision_pairs'], empty['max_multiplicity']), (0,0,0))

    def test_strata_keep_exact_nominal_locality_size_and_singletons(self):
        data = synthetic_round([[60,40]]*4+[[60,41]], aptos=[500,500,500,625,500])
        data['zone'][2] = 2
        selected = STATS.population_masks(data)['eligible']
        sizes = lambda **kw: sorted(len(group['indices']) for group in STATS.group_strata(data, selected, **kw))
        self.assertEqual(sizes(), [1,1,1,2])
        self.assertEqual(sizes(include_size=False), [1,1,3])
        self.assertEqual(sizes(include_zone=False), [1,1,3])
        self.assertEqual(sizes(include_zone=False, include_size=False), [1,4])

    def test_coherent_full_payload_cloning_is_a_positive_control(self):
        vectors = [[value,200-value] for value in range(100)]
        specials = [[value,0,0,0] for value in range(100)]
        for position in range(91, 100):
            vectors[position] = vectors[0].copy()
            specials[position] = specials[0].copy()
        data = synthetic_round(vectors, specials)
        np.testing.assert_array_equal(data['aptos'], data['turnout']+data['abstentions'])
        np.testing.assert_array_equal(data['turnout'], data['candidate_votes'].sum(axis=1)+data['blank'])
        result = STATS.stratum_statistics(data['candidate_votes'], special_vectors(data))
        self.assertEqual(result['observed_pairs'], 45)
        self.assertEqual(result['expected_pairs'], Fraction(9,22))
        bound = STATS.cantelli_bound(result['observed_pairs'], result['expected_pairs'], result['variance'])
        self.assertLess(bound, Fraction(1,1000))
        self.assertLess(STATS.holm_bounds([bound,None])[0], Fraction(1,20))

    def test_repeated_candidate_block_is_invisible_when_other_block_is_constant(self):
        vectors = [[value,200-value] for value in range(100)]
        for position in range(91, 100):
            vectors[position] = vectors[0].copy()
        data = synthetic_round(vectors)
        result = STATS.stratum_statistics(data['candidate_votes'], special_vectors(data))
        self.assertEqual(result['observed_pairs'], 45)
        self.assertEqual(result['expected_pairs'], Fraction(45))
        self.assertEqual(result['variance'], Fraction(0))
        self.assertIsNone(STATS.cantelli_bound(result['observed_pairs'], result['expected_pairs'], result['variance']))

    def test_unobserved_community_mixture_can_create_association_without_a_cause_label(self):
        data = synthetic_round([[80,120]]*50+[[120,80]]*50,
                               specials=[[10,0,0,0]]*50+[[20,0,0,0]]*50)
        mixed = STATS.stratum_statistics(data['candidate_votes'], special_vectors(data))
        bound = STATS.cantelli_bound(mixed['observed_pairs'], mixed['expected_pairs'], mixed['variance'])
        self.assertLess(bound, Fraction(1,20))
        data['zone'][50:] = 2
        observed = 0
        expected = Fraction(0)
        variance = Fraction(0)
        for group in STATS.group_strata(data, STATS.population_masks(data)['eligible']):
            ids = group['indices']
            result = STATS.stratum_statistics(data['candidate_votes'][ids], special_vectors(data)[ids])
            observed += result['observed_pairs']
            expected += result['expected_pairs']
            variance += result['variance']
        self.assertEqual(observed, mixed['observed_pairs'])
        self.assertEqual(expected, observed)
        self.assertEqual(variance, 0)
        self.assertIsNone(STATS.cantelli_bound(observed, expected, variance))


if __name__ == '__main__':
    unittest.main()
