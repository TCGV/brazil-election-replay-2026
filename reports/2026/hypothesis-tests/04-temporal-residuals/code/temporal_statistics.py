"""Conditional temporal references; complete section payloads share assignments.

No election observations or p-value decisions are embedded in this module.
"""
from __future__ import annotations

from itertools import permutations, product

import numpy as np

MODELS = {'zone_size': 0, 'place_size': 1}
SOURCES = ('first_time', 'bu_time')
STATISTICS = ('G', 'C', 'M')
P_TOLERANCE = 1e-12
RESIDUAL_CLOSURE_VOTES = 1e-6


def cohort(data, min_nominal=50):
    """Exclusive exclusions, independent of candidate votes."""
    n = len(data['aptos'])
    reasons = np.full(n, 'eligible', dtype='U20')
    remaining = np.ones(n, dtype=bool)
    criteria = (
        ('section_status', ~data['installed'] | data['cancelled']),
        ('aptos_below_50', data['aptos'] < 50),
        ('nonpositive_turnout', data['turnout'] <= 0),
        ('nominal_below_floor', data['nominal'] < min_nominal),
        ('missing_place', data['place'] < 0),
        ('missing_time', (data['first_time'] < 0) | (data['bu_time'] < 0)),
    )
    basic = None
    for name, excluded in criteria:
        mask = remaining & excluded
        reasons[mask] = name
        remaining[mask] = False
        if name == 'nominal_below_floor':
            basic = remaining.copy()
    return remaining, reasons, basic


def prepare(data, model, min_nominal=50):
    if model not in {*MODELS, 'place_no_size'}:
        raise ValueError('Unknown grouping model')
    mask, reasons, basic = cohort(data, min_nominal)
    ids = np.flatnonzero(mask)
    if not len(ids):
        raise ValueError('Empty temporal cohort')
    uf, uf_id = np.unique(data['uf'][ids], return_inverse=True)
    band = np.floor(np.log(data['aptos'][ids]) / np.log(1.25)).astype(np.int32)
    columns = [uf_id, data['municipality'][ids], data['zone'][ids]]
    if model != 'zone_size':
        columns.append(data['place'][ids])
    if model != 'place_no_size':
        columns.append(band)
    keys, first, labels, sizes = np.unique(np.column_stack(columns), axis=0,
        return_index=True, return_inverse=True, return_counts=True)
    order = np.argsort(labels, kind='stable')
    starts = np.r_[0, np.cumsum(sizes)]
    nominal = data['nominal'][ids].astype(np.int64)
    votes = data['candidate_votes'][ids].astype(np.int64)
    group_n = np.bincount(labels, weights=nominal).astype(np.int64)
    group_v = np.column_stack([np.bincount(labels, weights=votes[:, k]).astype(np.int64)
                               for k in range(votes.shape[1])])
    # Integer numerator identifies proportional/constant groups without float noise.
    if int(group_n.max()) * int(max(votes.max(), nominal.max(), group_v.max())) > np.iinfo(np.int64).max:
        raise ValueError('Residual cross-products would overflow int64')
    numerator = votes * group_n[labels, None] - group_v[labels] * nominal[:, None]
    residual = numerator / group_n[labels, None]
    closure = np.array([np.bincount(labels, weights=residual[:, k], minlength=len(sizes))
                        for k in range(votes.shape[1])])
    if np.max(np.abs(closure)) > RESIDUAL_CLOSURE_VOTES or np.max(np.abs(residual.sum(axis=0))) > RESIDUAL_CLOSURE_VOTES:
        raise ArithmeticError('Residuals fail final/group closure')
    variable = np.column_stack([np.bincount(labels, weights=numerator[:, k] != 0,
                                           minlength=len(sizes)) > 0 for k in range(votes.shape[1])])
    buckets = []
    for size in sorted(set(sizes.tolist()) - {1}):
        selected = np.flatnonzero(sizes == size)
        buckets.append(np.asarray([order[starts[g]:starts[g+1]] for g in selected], dtype=np.int32))
    return dict(data=data, ids=ids, reasons=reasons, basic=basic, model=model,
        labels=labels, sizes=sizes, first=first, order=order, starts=starts, keys=keys,
        group_n=group_n, group_v=group_v, nominal=nominal, votes=votes,
        numerator=numerator, residual=residual, variable=variable, buckets=buckets,
        final_nominal=int(nominal.sum()), uf_values=uf,
        band=band, sources={source: timing(data[source][ids] // 60, labels, sizes)
                            for source in SOURCES})


def timing(minutes, labels=None, sizes=None):
    minimum, maximum = int(minutes.min()), int(minutes.max())
    if maximum - minimum > 60 * 24 * 7:
        raise ValueError('Temporal range exceeds seven days; inspect source times')
    index = (minutes - minimum).astype(np.int32)
    counts = np.bincount(index, minlength=maximum-minimum+1)
    cumulative = counts.cumsum()
    weights = (cumulative - counts / 2) / len(minutes) - 0.5
    checkpoints = np.r_[-1, np.searchsorted(cumulative,
        np.ceil(np.arange(1, 101) * len(minutes) / 100).astype(np.int64), side='left')]
    result = dict(minute_min=minimum, index=index, counts=counts, cumulative=cumulative,
                  weights=weights, checkpoints=checkpoints, minutes=minutes)
    if labels is not None:
        ng = len(sizes)
        low = np.full(ng, maximum, dtype=np.int64)
        high = np.full(ng, minimum, dtype=np.int64)
        np.minimum.at(low, labels, minutes)
        np.maximum.at(high, labels, minutes)
        pairs = np.unique(np.column_stack([labels, minutes]), axis=0)
        distinct = np.bincount(pairs[:, 0], minlength=ng)
        result.update(group_min=low, group_max=high, group_distinct=distinct,
                      time_varied=distinct >= 2)
    return result


def minute_values(values, time):
    values = np.asarray(values)
    if values.ndim == 1:
        values = values[:, None]
    return np.column_stack([np.bincount(time['index'], weights=values[:, k],
                                       minlength=len(time['counts'])) for k in range(values.shape[1])])


def scores_from_minutes(arrivals, time, final_nominal):
    cumulative = arrivals.cumsum(axis=0)
    g = time['weights'] @ arrivals * (100 / final_nominal)
    ci = np.argmax(np.abs(cumulative), axis=0)
    mi = np.argmax(np.abs(arrivals), axis=0)
    j = np.arange(arrivals.shape[1])
    signed = np.column_stack([g, cumulative[ci, j] * (100 / final_nominal),
                              arrivals[mi, j] * (100 / final_nominal)])
    return np.abs(signed), signed, ci, mi, cumulative


def assignment(prepared, seed, turn, model_id, repetition):
    rng = np.random.default_rng(np.random.SeedSequence([seed, turn, model_id], spawn_key=(repetition,)))
    result = np.arange(len(prepared['ids']), dtype=np.int32)
    for bucket in prepared['buckets']:
        result[bucket.ravel()] = rng.permuted(bucket, axis=1).ravel()
    return result


def gradual_variance(prepared, source):
    """Finite-permutation variance of the signed G, evaluated in float64."""
    labels, sizes = prepared['labels'], prepared['sizes']
    weights = prepared['sources'][source]['weights'][prepared['sources'][source]['index']]
    mean = np.bincount(labels, weights=weights) / sizes
    ss_w = np.bincount(labels, weights=(weights-mean[labels])**2)
    ss_r = np.column_stack([np.bincount(labels, weights=prepared['residual'][:, k]**2)
                            for k in range(prepared['votes'].shape[1])])
    terms = np.zeros_like(ss_r)
    use = sizes > 1
    terms[use] = ss_r[use] * (ss_w[use] / (sizes[use]-1))[:, None]
    return terms.sum(axis=0) * (100/prepared['final_nominal'])**2


def score_variability(prepared, source, k, sampled_scores, observed_scores,
                      max_exact=40320):
    """Prove applicability separately for each absolute G/C/M statistic.

    ``sampled_scores`` is B-by-3 and ``observed_scores`` has three entries.
    Distinct realized scores establish variability. Failure to see distinct
    values does not establish constancy: enumerate the relevant finite orbit
    when it is small, otherwise stop with an explicit unresolved-support error.
    Only candidate-variable groups spanning multiple minutes can affect a score.
    """
    sampled = np.asarray(sampled_scores, dtype=float)
    observed = np.asarray(observed_scores, dtype=float)
    if sampled.ndim != 2 or sampled.shape[1] != 3 or observed.shape != (3,):
        raise ValueError('Expected B-by-3 sampled and three observed scores')
    if not np.all(np.isfinite(sampled)) or not np.all(np.isfinite(observed)):
        raise ValueError('Scores must be finite')
    if not 0 <= k < prepared['residual'].shape[1] or max_exact < 0:
        raise ValueError('Invalid candidate index or enumeration limit')
    time = prepared['sources'][source]
    relevant = prepared['variable'][:, k] & time['time_varied']
    if not np.any(relevant):
        return np.zeros(3, dtype=bool), ['no_informative_groups'] * 3

    realized = np.vstack([observed, sampled])
    flags = np.ptp(realized, axis=0) > P_TOLERANCE
    reasons = ['sampled_distinct_scores' if flag else '' for flag in flags]
    if np.all(flags):
        return flags, reasons

    groups = []
    combinations = 1
    for group in np.flatnonzero(relevant):
        members = prepared['order'][prepared['starts'][group]:prepared['starts'][group+1]]
        groups.append(members)
        # Stop multiplying immediately when the finite orbit exceeds the cap;
        # do not allocate or construct permutations of a large group.
        for factor in range(2, len(members) + 1):
            combinations *= factor
            if combinations > max_exact:
                unresolved = ','.join(STATISTICS[index] for index in np.flatnonzero(~flags))
                raise ArithmeticError(
                    f'Unresolved absolute-score variability for {unresolved}: '
                    f'no sampled witness and exact orbit exceeds {max_exact}')

    # Remove invariant groups once. Enumeration then touches only the small
    # relevant orbit rather than copying the entire original section payload.
    slots = np.concatenate(groups)
    residual = prepared['residual'][:, k]
    slot_minutes = time['index'][slots]
    fixed = minute_values(residual, time)[:, 0] - np.bincount(
        slot_minutes, weights=residual[slots], minlength=len(time['counts']))
    lower = np.full(3, np.inf)
    upper = np.full(3, -np.inf)
    for draw in product(*(permutations(members.tolist()) for members in groups)):
        sources = np.fromiter((index for group in draw for index in group), dtype=np.int64)
        arrivals = fixed + np.bincount(slot_minutes, weights=residual[sources],
                                      minlength=len(time['counts']))
        scores = scores_from_minutes(arrivals[:, None], time,
                                     prepared['final_nominal'])[0][0]
        lower = np.minimum(lower, scores)
        upper = np.maximum(upper, scores)
        # A witness suffices for variability; only a claim of constancy needs
        # every assignment in the orbit.
        if np.all(flags | (upper-lower > P_TOLERANCE)):
            break
    for index in np.flatnonzero(~flags):
        flags[index] = upper[index] - lower[index] > P_TOLERANCE
        reasons[index] = ('exact_enumeration_variable' if flags[index]
                          else 'exact_enumeration_constant')
    return flags, reasons


def holm(pvalues):
    p = np.asarray(pvalues, dtype=float)
    if np.any(~np.isfinite(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError('Invalid p-values')
    order = np.argsort(p, kind='stable')
    adjusted = np.minimum(1, np.maximum.accumulate(p[order] * np.arange(len(p), 0, -1)))
    result = np.empty_like(p)
    result[order] = adjusted
    return result
