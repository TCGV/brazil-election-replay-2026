"""H6 paired-turnout associations, arithmetic accounting and finite references.

Physical-key pairing and the eligibility sequence adapt H5's
``05-inter-round-localization/code/pair_statistics.py``. All H6 measures,
baseline grouping, trajectory permutations and rank calculations are local.
Array positions in a prepared object always refer to its entire eligible
cohort. Unsupported rows have zero residuals and identity assignments.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import permutations, product

import numpy as np


MODELS = {'zone_baseline': 0, 'place_baseline': 1}
STATISTICS = ('linear', 'rank')
EPS = 1e-12
KEY_FIELDS = ('uf', 'municipality', 'zone', 'section')
CATEGORY_FIELDS = ('nominal', 'blank', 'null_votes', 'legend', 'separate')


def physical_keys(data):
    keys = np.empty(len(data['uf']), dtype=[
        ('uf', 'U2'), ('municipality', 'i4'), ('zone', 'i4'), ('section', 'i4')])
    for field in KEY_FIELDS:
        keys[field] = data[field]
    if len(np.unique(keys)) != len(keys):
        raise ValueError('Ambiguous physical section key within one round')
    return keys


def pair_sections(rounds):
    first = [rd for rd in rounds if int(rd['turno']) == 1]
    second = [rd for rd in rounds if int(rd['turno']) == 2]
    if len(first) != 1 or len(second) != 1:
        raise ValueError('Require exactly one presidential election per round')
    a, b = first[0], second[0]
    if not {13, 22} <= set(a['candidate_numbers']) or set(b['candidate_numbers']) != {13, 22}:
        raise ValueError('Finalists must exist in both rounds and exhaust round 2 nominal votes')
    ka, kb = physical_keys(a), physical_keys(b)
    keys, ia, ib = np.intersect1d(ka, kb, assume_unique=True, return_indices=True)
    pairs = {field: keys[field] for field in KEY_FIELDS}
    fields = ('place', 'source_line', 'aptos', 'turnout', 'abstentions',
              *CATEGORY_FIELDS, 'installed', 'cancelled')
    for turn, rd, indices in ((1, a, ia), (2, b, ib)):
        for field in fields:
            pairs[f'{field}_{turn}'] = rd[field][indices]
        for candidate in (13, 22):
            pairs[f'v{candidate}_{turn}'] = rd['candidate_votes'][
                indices, rd['candidate_numbers'].index(candidate)].astype(np.int64)
        pairs[f'f_{turn}'] = pairs[f'v13_{turn}'] + pairs[f'v22_{turn}']
    only_a = np.setdiff1d(np.arange(len(ka)), ia, assume_unique=True)
    only_b = np.setdiff1d(np.arange(len(kb)), ib, assume_unique=True)
    pairs.update(election_1=int(a['election_code']), election_2=int(b['election_code']))
    return dict(pairs=pairs, unmatched=[(1, a, only_a), (2, b, only_b)],
                rounds=(a, b), matched_indices=(ia, ib))


def eligibility(pairs, finalist_floor=50, unchanged_aptos=False, domestic_only=False):
    if finalist_floor < 1:
        raise ValueError('Positive finalist floor required')
    n = len(pairs['uf'])
    remaining = np.ones(n, dtype=bool)
    reasons = np.full(n, 'eligible', dtype='U24')
    a1 = pairs['aptos_1'].astype(np.int64)
    a2 = pairs['aptos_2'].astype(np.int64)
    criteria = [
        ('section_status', ~pairs['installed_1'] | ~pairs['installed_2'] |
         pairs['cancelled_1'] | pairs['cancelled_2']),
        ('aptos_below_50', (a1 < 50) | (a2 < 50)),
        ('nonpositive_turnout', (pairs['turnout_1'] <= 0) | (pairs['turnout_2'] <= 0)),
        ('nominal_below_50', (pairs['nominal_1'] < 50) | (pairs['nominal_2'] < 50)),
        ('finalists_below_floor', pairs['f_1'] < finalist_floor),
        ('missing_place', (pairs['place_1'] < 0) | (pairs['place_2'] < 0)),
        ('changed_place', pairs['place_1'] != pairs['place_2']),
        ('aptos_ratio', 4 * np.maximum(a1, a2) > 5 * np.minimum(a1, a2)),
    ]
    if unchanged_aptos:
        criteria.append(('changed_aptos', a1 != a2))
    if domestic_only:
        criteria.append(('exterior', pairs['uf'] == 'ZZ'))
    basic = None
    for name, excluded in criteria:
        take = remaining & excluded
        reasons[take] = name
        remaining[take] = False
        if name == 'nominal_below_50':
            basic = remaining.copy()
    return remaining, reasons, basic


def proportion_band(numerator, denominator, bins=20):
    numerator = np.asarray(numerator, dtype=np.int64)
    denominator = np.asarray(denominator, dtype=np.int64)
    if (bins < 1 or np.any(denominator <= 0) or np.any(numerator < 0) or
            np.any(numerator > denominator)):
        raise ValueError('Valid proportions and positive bin count required')
    if numerator.size and int(numerator.max()) * int(bins) > np.iinfo(np.int64).max:
        raise OverflowError('Proportion band product exceeds int64')
    return np.minimum(bins - 1, bins * numerator // denominator).astype(np.int32)


def _ratio_change(first_n, first_d, second_n, second_d):
    """Reduced exact unscaled change and its value in percentage points."""
    values = [np.asarray(v, dtype=np.int64) for v in
              (first_n, first_d, second_n, second_d)]
    n1, d1, n2, d2 = values
    if np.any(d1 <= 0) or np.any(d2 <= 0):
        raise ValueError('Undefined rate with nonpositive denominator')
    if np.any(n1 < 0) or np.any(n2 < 0) or np.any(n1 > d1) or np.any(n2 > d2):
        raise ValueError('Rate numerator outside denominator')
    if n1.size:
        limit = np.iinfo(np.int64).max
        for left, right in ((n2, d1), (n1, d2), (d1, d2)):
            if int(left.max()) * int(right.max()) > limit:
                raise OverflowError('Exact rate cross-product exceeds int64')
    numerator = n2 * d1 - n1 * d2
    denominator = d1 * d2
    divisor = np.gcd(np.abs(numerator), denominator)
    numerator = numerator // divisor
    denominator = denominator // divisor
    return 100.0 * numerator / denominator, numerator, denominator


def _audit_cohort(pairs, ids):
    for turn in (1, 2):
        get = lambda field: pairs[f'{field}_{turn}'][ids].astype(np.int64)
        if not np.array_equal(get('aptos'), get('turnout') + get('abstentions')):
            raise ValueError('Cohort electorate identity aptos = turnout + abstentions failed')
        if not np.array_equal(get('turnout'), sum(get(field) for field in CATEGORY_FIELDS)):
            raise ValueError('Cohort vote categories do not equal turnout')
        if not np.array_equal(get('f'), get('v13') + get('v22')):
            raise ValueError('Cohort finalist sum inconsistent')
        if np.any(get('f') > get('nominal')):
            raise ValueError('Finalists exceed nominal votes')


def measures(pairs, ids, outcome='change'):
    ids = np.asarray(ids, dtype=np.int64)
    if outcome not in ('change', 'second_share'):
        raise ValueError('Unknown preference outcome')
    _audit_cohort(pairs, ids)
    get = lambda field, turn: pairs[f'{field}_{turn}'][ids].astype(np.int64)
    a1, a2 = get('aptos', 1), get('aptos', 2)
    t1, t2 = get('turnout', 1), get('turnout', 2)
    f1, f2 = get('f', 1), get('f', 2)
    x, xn, xd = _ratio_change(t1, a1, t2, a2)
    dy, yn, yd = _ratio_change(get('v13', 1), f1, get('v13', 2), f2)
    q1 = 100 * get('v13', 1) / f1
    q2 = 100 * get('v13', 2) / f2
    if outcome == 'second_share':
        divisor = np.gcd(get('v13', 2), f2)
        yn, yd = get('v13', 2) // divisor, f2 // divisor
    result = dict(
        x=x, y=dy if outcome == 'change' else q2, q1=q1, q2=q2, delta_q=dy,
        x_numerator=xn, x_denominator=xd, y_numerator=yn, y_denominator=yd,
        turnout_rate1=100 * t1 / a1, turnout_rate2=100 * t2 / a2,
        abstention_rate1=100 * get('abstentions', 1) / a1,
        abstention_rate2=100 * get('abstentions', 2) / a2,
        other_1=get('nominal', 1) - f1, other_2=get('nominal', 2) - f2)
    for candidate in (13, 22):
        v1, v2 = get(f'v{candidate}', 1), get(f'v{candidate}', 2)
        tr1, tr2 = t1 / a1, t2 / a2
        s1, s2 = v1 / t1, v2 / t2
        gain_pp = 100 * (v2 / a2 - v1 / a1)
        turnout_pp = 100 * (s1 + s2) / 2 * (tr2 - tr1)
        composition_pp = 100 * (tr1 + tr2) / 2 * (s2 - s1)
        if not np.allclose(gain_pp, turnout_pp + composition_pp, atol=1e-11, rtol=1e-12):
            raise ArithmeticError('Symmetric arithmetic decomposition failed')
        result.update({
            f'gain{candidate}_count': v2 - v1,
            f'gain{candidate}_nominal_pp': 100 *
            (v2 / get('nominal', 2) - v1 / get('nominal', 1)),
            f'gain{candidate}_aptos_pp': gain_pp,
            f'turnout{candidate}_component_pp': turnout_pp,
            f'composition{candidate}_component_pp': composition_pp,
            f'gain{candidate}_equiv_votes': gain_pp * a1 / 100,
            f'turnout{candidate}_equiv_votes': turnout_pp * a1 / 100,
            f'composition{candidate}_equiv_votes': composition_pp * a1 / 100,
        })
    return result


def grouping(columns):
    keys, first, labels, sizes = np.unique(
        np.column_stack(columns), axis=0, return_index=True,
        return_inverse=True, return_counts=True)
    order = np.argsort(labels, kind='stable')
    starts = np.r_[0, np.cumsum(sizes)]
    return dict(keys=keys, first=first, labels=labels, sizes=sizes,
                order=order, starts=starts)


def rational_average_ranks(numerators, denominators):
    """Average one-based ranks with exact rational ordering and equality."""
    numerators = np.asarray(numerators)
    denominators = np.asarray(denominators)
    if numerators.ndim != 1 or numerators.shape != denominators.shape or np.any(denominators <= 0):
        raise ValueError('Expected equal one-dimensional rational arrays')
    fractions = [Fraction(int(n), int(d)) for n, d in zip(numerators, denominators)]
    order = sorted(range(len(fractions)), key=fractions.__getitem__)
    ranks = np.empty(len(order), dtype=float)
    left = 0
    while left < len(order):
        right = left + 1
        while right < len(order) and fractions[order[left]] == fractions[order[right]]:
            right += 1
        ranks[order[left:right]] = (left + 1 + right) / 2
        left = right
    return ranks


def _variation(labels, numerator, denominator, count):
    unique = np.unique(np.column_stack([labels, numerator, denominator]), axis=0)
    return np.bincount(unique[:, 0], minlength=count) > 1


def prepare(pairs, model, bins=20, unchanged_aptos=False, finalist_floor=50,
            domestic_only=False, outcome='change'):
    if model not in MODELS:
        raise ValueError('Unknown conditional reference')
    mask, reasons, basic = eligibility(pairs, finalist_floor, unchanged_aptos, domestic_only)
    ids = np.flatnonzero(mask)
    if not len(ids):
        raise ValueError('Empty paired cohort')
    value = measures(pairs, ids, outcome)
    _, uf_id = np.unique(pairs['uf'][ids], return_inverse=True)
    band = np.floor(np.log(pairs['aptos_1'][ids]) / np.log(1.25)).astype(np.int32)
    turnout_band = proportion_band(pairs['turnout_1'][ids], pairs['aptos_1'][ids], bins)
    preference_band = proportion_band(pairs['v13_1'][ids], pairs['f_1'][ids], bins)
    other_band = proportion_band(value['other_1'], pairs['turnout_1'][ids], bins)
    columns = [uf_id, pairs['municipality'][ids], pairs['zone'][ids],
               band, turnout_band, preference_band, other_band]
    if model == 'place_baseline':
        columns.append(pairs['place_1'][ids])
    group = grouping(columns)
    labels, sizes = group['labels'], group['sizes']
    count = len(sizes)
    variable_x = _variation(labels, value['x_numerator'], value['x_denominator'], count)
    variable_y = _variation(labels, value['y_numerator'], value['y_denominator'], count)
    informative = (sizes >= 2) & variable_x & variable_y
    status = np.full(count, 'informative', dtype='U16')
    status[~variable_x & ~variable_y] = 'constant_both'
    status[~variable_x & variable_y] = 'constant_x'
    status[variable_x & ~variable_y] = 'constant_y'
    status[sizes == 1] = 'singleton'
    support = informative[labels]
    mean_x = np.bincount(labels, weights=value['x'], minlength=count) / sizes
    mean_y = np.bincount(labels, weights=value['y'], minlength=count) / sizes
    raw_rx = value['x'] - mean_x[labels]
    raw_ry = value['y'] - mean_y[labels]
    # Exact constant groups must remain zero rather than summation roundoff.
    raw_rx[~variable_x[labels]] = 0
    raw_ry[~variable_y[labels]] = 0
    ss_x = np.bincount(labels, weights=raw_rx ** 2, minlength=count)
    ss_y = np.bincount(labels, weights=raw_ry ** 2, minlength=count)
    covariance = np.bincount(labels, weights=raw_rx * raw_ry, minlength=count)
    rx, ry = raw_rx.copy(), raw_ry.copy()
    rx[~support], ry[~support] = 0, 0
    rank_x, rank_y = np.zeros(len(ids)), np.zeros(len(ids))
    for g in np.flatnonzero(informative):
        members = group['order'][group['starts'][g]:group['starts'][g + 1]]
        rank_x[members] = rational_average_ranks(
            value['x_numerator'][members], value['x_denominator'][members]) - (sizes[g] + 1) / 2
        rank_y[members] = rational_average_ranks(
            value['y_numerator'][members], value['y_denominator'][members]) - (sizes[g] + 1) / 2
    buckets = []
    for size in sorted(set(sizes[informative].tolist())):
        selected = np.flatnonzero(informative & (sizes == size))
        buckets.append(np.asarray([
            group['order'][group['starts'][g]:group['starts'][g + 1]]
            for g in selected], dtype=np.int32))
    linear_denominator = np.sqrt(np.dot(rx, rx) * np.dot(ry, ry))
    rank_denominator = np.sqrt(np.dot(rank_x, rank_x) * np.dot(rank_y, rank_y))
    beta = float(np.dot(rx, ry) / np.dot(rx, rx)) if np.any(support) else None
    return dict(
        pairs=pairs, ids=ids, reasons=reasons, basic=basic, model=model, bins=bins,
        outcome=outcome, measures=value, group=group, band=band,
        initial_turnout_band=turnout_band, initial_preference_band=preference_band,
        initial_other_band=other_band, variable_x=variable_x, variable_y=variable_y,
        informative=informative, group_status=status, support=support,
        informative_ids=np.flatnonzero(support), mean_x=mean_x, mean_y=mean_y,
        ss_x=ss_x, ss_y=ss_y, covariance=covariance, rx=rx, ry=ry,
        rank_x=rank_x, rank_y=rank_y, buckets=buckets,
        linear_denominator=linear_denominator, rank_denominator=rank_denominator,
        beta=beta)


def assignment(prepared, seed, model_id, repetition):
    if model_id != MODELS[prepared['model']] or repetition < 0:
        raise ValueError('Model ID or repetition does not match prepared reference')
    rng = np.random.default_rng(np.random.SeedSequence([seed, 6, model_id], spawn_key=(repetition,)))
    result = np.arange(len(prepared['ids']), dtype=np.int32)
    for bucket in prepared['buckets']:
        result[bucket.ravel()] = rng.permuted(bucket, axis=1).ravel()
    return result


def score(prepared, assigned=None):
    if assigned is None:
        y, rank_y = prepared['ry'], prepared['rank_y']
    else:
        assigned = np.asarray(assigned)
        if assigned.shape != prepared['ry'].shape or not np.issubdtype(assigned.dtype, np.integer):
            raise ValueError('Expected one integer source index per cohort row')
        y, rank_y = prepared['ry'][assigned], prepared['rank_y'][assigned]
    denominators = np.array([prepared['linear_denominator'], prepared['rank_denominator']])
    numerators = np.array([np.dot(prepared['rx'], y), np.dot(prepared['rank_x'], rank_y)])
    values = np.divide(numerators, denominators, out=np.zeros(2), where=denominators > 0)
    if np.any(np.abs(values) > 1 + 1e-10):
        raise ArithmeticError('Correlation outside unit interval')
    return np.clip(values, -1, 1)


def score_variability(prepared, sampled, observed, max_exact=40320):
    """Prove variability of each ABSOLUTE statistic, not merely its sign."""
    sampled = np.asarray(sampled, dtype=float)
    observed = np.asarray(observed, dtype=float)
    if (sampled.ndim != 2 or sampled.shape[1] != 2 or observed.shape != (2,) or
            np.any(~np.isfinite(sampled)) or np.any(~np.isfinite(observed)) or
            np.any(sampled < 0) or np.any(observed < 0) or max_exact < 0):
        raise ValueError('Expected finite nonnegative B-by-two absolute scores')
    if not np.any(prepared['informative']):
        return np.zeros(2, dtype=bool), ['no_informative_groups'] * 2
    flags = np.ptp(np.vstack([observed, sampled]), axis=0) > EPS
    reasons = ['sampled_distinct_scores' if flag else '' for flag in flags]
    if np.all(flags):
        return flags, reasons
    groups = []
    orbit = 1
    group = prepared['group']
    for g in np.flatnonzero(prepared['informative']):
        members = group['order'][group['starts'][g]:group['starts'][g + 1]]
        groups.append(members)
        for factor in range(2, len(members) + 1):
            orbit *= factor
            if orbit > max_exact:
                raise ArithmeticError('Unresolved absolute correlation variability; exact orbit too large')
    # Enumeration proves constancy algebraically. A range smaller than EPS is
    # not a proof: genuinely different rational covariances can be arbitrarily
    # close. Denominators of both correlations are fixed under the assignments,
    # so compare their exact absolute covariance numerators instead.
    exact_x, exact_y, doubled_rank_x, doubled_rank_y = {}, {}, {}, {}
    value = prepared['measures']
    for members in groups:
        xx = [Fraction(int(value['x_numerator'][i]), int(value['x_denominator'][i]))
              for i in members]
        yy = [Fraction(int(value['y_numerator'][i]), int(value['y_denominator'][i]))
              for i in members]
        mx, my = sum(xx) / len(members), sum(yy) / len(members)
        for i, x, y in zip(members, xx, yy):
            exact_x[int(i)], exact_y[int(i)] = x - mx, y - my
            # Average ranks are integers or half-integers and are exactly
            # representable here; doubling makes the covariance integral.
            doubled_rank_x[int(i)] = int(2 * prepared['rank_x'][i])
            doubled_rank_y[int(i)] = int(2 * prepared['rank_y'][i])
    first_exact = None
    for draw in product(*(permutations(m.tolist()) for m in groups)):
        linear_covariance, rank_covariance = Fraction(0), 0
        for members, source in zip(groups, draw):
            for target, donor in zip(members, source):
                linear_covariance += exact_x[int(target)] * exact_y[int(donor)]
                rank_covariance += doubled_rank_x[int(target)] * doubled_rank_y[int(donor)]
        exact = (abs(linear_covariance), abs(rank_covariance))
        if first_exact is None:
            first_exact = exact
        for k in np.flatnonzero(~flags):
            if exact[k] != first_exact[k]:
                flags[k] = True
                reasons[k] = 'exact_enumeration_variable'
        if np.all(flags):
            break
    for k in np.flatnonzero(~flags):
        reasons[k] = 'exact_enumeration_constant'
    return flags, reasons


def holm(pvalues):
    p = np.asarray(pvalues, dtype=float)
    if p.ndim != 1 or np.any(~np.isfinite(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError('Invalid p-values')
    order = np.argsort(p, kind='stable')
    adjusted = np.minimum(1, np.maximum.accumulate(p[order] * np.arange(len(p), 0, -1)))
    result = np.empty_like(p)
    result[order] = adjusted
    return result
