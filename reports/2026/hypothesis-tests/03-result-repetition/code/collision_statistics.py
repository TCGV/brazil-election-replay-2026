"""Exact finite-reference moments and integer result-signature helpers for H3.

The reference randomizes whole candidate vectors relative to fixed special-vote
vectors within a stratum whose nominal total is fixed. Its collision statistic
counts within-stratum unordered pairs. It does not model natural elections.
"""
from fractions import Fraction
from math import comb, log
from operator import index

import numpy as np


def _counts(values):
    counts = [index(value) for value in values]
    if any(value < 0 for value in counts):
        raise ValueError('Negative multiplicity')
    return [value for value in counts if value]


def pair_count(counts):
    return sum(comb(value, 2) for value in _counts(counts))


def _falling(n, k):
    if n < k:
        return 0
    result = 1
    for offset in range(k):
        result *= n-offset
    return result


def moments(a_counts, b_counts):
    """Return exact (mean, variance) of the within-stratum collision count.

    A labels have multiplicities a_i, B labels have b_j, and A is uniformly
    redistributed among B positions. For B-equal position-pair indicators,
    distinct pairs either share one position or have four distinct positions.
    The corresponding A-equality probabilities are p3 and p22 below.
    """
    a, b = _counts(a_counts), _counts(b_counts)
    n = sum(a)
    if n != sum(b):
        raise ValueError('Margins must have equal totals')
    if n < 2:
        return Fraction(0), Fraction(0)
    ma, mb = pair_count(a), pair_count(b)
    mean = Fraction(ma*mb, comb(n, 2))
    s2 = sum(_falling(value, 2) for value in a)
    p2 = Fraction(s2, _falling(n, 2))
    variance = mb*p2*(1-p2)
    shared = 3*sum(comb(value, 3) for value in b)
    disjoint = comb(mb, 2)-shared
    if shared:
        p3 = Fraction(sum(_falling(value, 3) for value in a), _falling(n, 3))
        variance += 2*shared*(p3-p2*p2)
    if disjoint:
        numerator = (sum(_falling(value, 4) for value in a) + s2*s2
                     - sum(_falling(value, 2)**2 for value in a))
        p22 = Fraction(numerator, _falling(n, 4))
        variance += 2*disjoint*(p22-p2*p2)
    if variance < 0:
        raise ArithmeticError('Negative exact variance')
    return mean, variance


def cantelli_bound(observed, mean, variance):
    """Conservative one-sided bound, or None for a constant reference.

    A constant reference must equal the observed statistic: the observed row
    pairing is itself one of its possible assignments. An inconsistent value
    indicates a programming/reference error, not a zero-probability result.
    """
    observed, mean, variance = map(Fraction, (observed, mean, variance))
    if observed < 0 or variance < 0:
        raise ValueError('Nonnegative collision counts and variance required')
    if variance == 0:
        if observed != mean:
            raise ArithmeticError('Observed statistic outside constant reference')
        return None
    if observed <= mean:
        return Fraction(1)
    return variance/(variance+(observed-mean)**2)


def holm_bounds(bounds):
    """Adjust the fixed family; None occupies a p=1 slot and remains None."""
    bounds = list(bounds)
    values = [Fraction(1) if value is None else Fraction(value) for value in bounds]
    if any(not 0 <= value <= 1 for value in values):
        raise ValueError('Bounds outside [0, 1]')
    adjusted = [None]*len(values)
    running = Fraction(0)
    for rank, position in enumerate(sorted(range(len(values)), key=values.__getitem__)):
        running = max(running, (len(values)-rank)*values[position])
        if bounds[position] is not None:
            adjusted[position] = min(Fraction(1), running)
    return adjusted


def population_masks(data, min_nominal=50):
    """All overlaps its four mutually exclusive, exhaustive positive/zero views."""
    active_status = data['installed'] & ~data['cancelled']
    positive = data['turnout'] > 0
    eligible = active_status & positive & (data['aptos'] >= 50) & (data['nominal'] >= min_nominal)
    return {
        'all': np.ones(len(positive), dtype=bool),
        'eligible': eligible,
        'small_positive': active_status & positive & ~eligible,
        'zero_activity': data['turnout'] == 0,
        'other_positive': positive & ~active_status,
    }


def signature_matrix(data, extended=False):
    """Full integer counts, not rounded shares, winners or unordered counts."""
    numbers = np.asarray(data['candidate_numbers'])
    candidates = np.asarray(data['candidate_votes'])
    if candidates.ndim != 2 or candidates.shape[1] != len(numbers) or len(set(map(int, numbers))) != len(numbers):
        raise ValueError('Invalid candidate matrix or repeated candidate number')
    candidates = candidates[:, np.argsort(numbers)]
    parts = [candidates, *[data[name] for name in ('blank','null_votes','legend','separate','turnout')]]
    if extended:
        parts.extend(data[name] for name in ('aptos','abstentions'))
    if any(not np.issubdtype(np.asarray(part).dtype, np.integer) for part in parts):
        raise ValueError('Signature counts must be integers')
    matrix = np.column_stack(parts).astype(np.int64, copy=False)
    if np.any(matrix < 0):
        raise ValueError('Signature counts must be nonnegative')
    if not np.array_equal(candidates.sum(axis=1, dtype=np.int64), data['nominal']):
        raise ValueError('Candidate vector does not reconcile to nominal total')
    total = data['nominal'].astype(np.int64)
    for field in ('blank','null_votes','legend','separate'):
        total = total + data[field]
    if not np.array_equal(total, data['turnout']):
        raise ValueError('Signature vote categories do not reconcile to turnout')
    return matrix


def inventory(signatures, selected=None):
    matrix = np.asarray(signatures)
    if matrix.ndim != 2:
        raise ValueError('Signatures must form a two-dimensional matrix')
    indices = np.arange(len(matrix)) if selected is None else np.arange(len(matrix))[selected]
    unique, inverse, counts = np.unique(matrix[indices], axis=0, return_inverse=True, return_counts=True)
    repeated = counts >= 2
    return dict(rows=int(len(indices)), distinct_signatures=int(len(counts)),
                repeated_groups=int(repeated.sum()), repeated_sections=int(counts[repeated].sum()),
                collision_pairs=pair_count(counts), max_multiplicity=int(counts.max()) if len(counts) else 0,
                indices=indices, unique=unique, inverse=inverse, counts=counts)


def group_strata(data, selected, include_zone=True, include_size=True, ratio=1.25):
    """Return strict local/exact-nominal strata, including singletons."""
    if ratio <= 1:
        raise ValueError('Size-band ratio must exceed one')
    ids = np.arange(len(data['aptos']))[selected]
    if not len(ids):
        return []
    if np.any(data['aptos'][ids] <= 0):
        raise ValueError('Positive electorate required for size bands')
    bands = np.floor(np.log(data['aptos'][ids])/log(ratio)).astype(np.int64) if include_size else np.zeros(len(ids), dtype=np.int64)
    zones = data['zone'][ids] if include_zone else np.zeros(len(ids), dtype=np.int64)
    nominal = data['nominal'][ids]
    order = np.lexsort((bands,nominal,zones,data['municipality'][ids],data['uf'][ids]))
    ids, bands, zones, nominal = ids[order], bands[order], zones[order], nominal[order]
    cuts = np.flatnonzero((data['uf'][ids[1:]] != data['uf'][ids[:-1]])
        | (data['municipality'][ids[1:]] != data['municipality'][ids[:-1]])
        | (zones[1:] != zones[:-1]) | (nominal[1:] != nominal[:-1]) | (bands[1:] != bands[:-1]))+1
    records = []
    for start, stop in zip(np.r_[0,cuts], np.r_[cuts,len(ids)]):
        i = ids[start]
        records.append(dict(key=(str(data['uf'][i]),int(data['municipality'][i]),
                                 int(zones[start]) if include_zone else None,int(nominal[start]),
                                 int(bands[start]) if include_size else None), indices=ids[start:stop]))
    return records


def stratum_statistics(a_vectors, b_vectors):
    a, b = np.asarray(a_vectors), np.asarray(b_vectors)
    if a.ndim != 2 or b.ndim != 2 or len(a) != len(b):
        raise ValueError('Two matrices with equal row counts required')
    a_counts = np.unique(a,axis=0,return_counts=True)[1]
    b_counts = np.unique(b,axis=0,return_counts=True)[1]
    full_counts = np.unique(np.column_stack((a,b)),axis=0,return_counts=True)[1]
    mean, variance = moments(a_counts,b_counts)
    return dict(n=len(a),a_unique=len(a_counts),b_unique=len(b_counts),
                a_pairs=pair_count(a_counts),b_pairs=pair_count(b_counts),
                observed_pairs=pair_count(full_counts),expected_pairs=mean,variance=variance)
