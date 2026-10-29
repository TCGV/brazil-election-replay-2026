"""H7 municipality definitions and paired-payload territorial allocation.

Physical-key pairing, exclusive eligibility and category auditing adapt H6's
``06-turnout-gains/code/turnout_statistics.py`` at commit cb32076a0eea70a35782fbabba7777a5e49c94fc.
The H7 aggregation, exact municipal comparisons and allocation scores are local.
No territorial allocation is a causal model or an external source authentication.

An assigned unit index represents the complete original paired section or
polling-place block. COUNT_FIELDS is the sufficient count projection needed
by these scores: individual nonfinalist nominations enter only through the
aggregate O = nominal - v13 - v22. The original full candidate vectors remain
rejoinable through pairs, ids and unit_labels/physical keys; no component is
shuffled independently and this projection does not identify voter flows.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import permutations, product

import numpy as np


MODELS = {'section': 0, 'place_block': 1}
STATISTICS = ('Ucount', 'Unominal', 'Uconditional', 'Rlow', 'Jhigh')
TAILS = ('upper', 'upper', 'upper', 'lower', 'upper')
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


COUNT_BASES = ('aptos', 'turnout', 'abstentions', 'nominal', 'blank',
               'null_votes', 'legend', 'separate', 'v13', 'v22', 'f')
COUNT_FIELDS = tuple(f'{field}_{turn}' for turn in (1, 2) for field in COUNT_BASES)
FAST_COUNT_FIELDS = ('v13_1', 'v22_1', 'v13_2', 'v22_2', 'nominal_1', 'nominal_2')


def grouping(columns):
    keys, first, labels, sizes = np.unique(
        np.column_stack(columns), axis=0, return_index=True,
        return_inverse=True, return_counts=True)
    order = np.argsort(labels, kind='stable')
    return dict(keys=keys, first=first, labels=labels, sizes=sizes,
                order=order, starts=np.r_[0, np.cumsum(sizes)])


def integer_group_sum(values, labels, count):
    """Exact nonnegative counts through float bincount, with a proved bound.

    Every intermediate sum is an integer no larger than the global total;
    below 2**53, every such integer is represented exactly by float64.
    """
    values = np.asarray(values, dtype=np.int64)
    if np.any(values < 0) or sum(map(int, values)) > 2**53:
        raise OverflowError('Nonnegative aggregate counts must not exceed 2**53')
    return np.bincount(labels, weights=values, minlength=count).astype(np.int64)


def _cross_difference(a, b, c, d):
    a, b, c, d = [np.asarray(value, dtype=np.int64) for value in (a, b, c, d)]
    if a.size:
        largest = lambda values: max(abs(int(values.min())), abs(int(values.max())))
        bound = largest(a) * largest(b) + largest(c) * largest(d)
        if bound > np.iinfo(np.int64).max:
            raise OverflowError('Exact comparison products exceed int64')
    return a * b - c * d


def _reduce_ratio(numerator, denominator, defined):
    numerator = np.asarray(numerator, dtype=np.int64)
    denominator = np.asarray(denominator, dtype=np.int64)
    defined = np.asarray(defined, dtype=bool)
    n, d = numerator.copy(), denominator.copy()
    n[~defined], d[~defined] = 0, 0
    divisor = np.gcd(np.abs(n), np.where(defined, d, 1))
    n[defined] //= divisor[defined]
    d[defined] //= divisor[defined]
    value = np.full(n.shape, np.nan)
    np.divide(100.0 * n, d, out=value, where=defined)
    return value, n, d


def municipality_metrics(counts):
    """Exact direction comparisons; displayed rates are percentage points.

    Optional present_1/present_2 prevent a missing round being fabricated as
    zero. Undefined signs are zero only alongside an explicit defined=False.
    """
    get = lambda field: np.atleast_1d(np.asarray(counts[field], dtype=np.int64))
    l1, b1, l2, b2 = (get(field) for field in ('v13_1', 'v22_1', 'v13_2', 'v22_2'))
    n1, n2 = get('nominal_1'), get('nominal_2')
    f1, f2 = l1 + b1, l2 + b2
    if any(np.any(values < 0) for values in (l1, b1, l2, b2, n1, n2)):
        raise ValueError('Municipal count fields must be nonnegative')
    if np.any(f1 > n1) or np.any(f2 > n2):
        raise ValueError('Municipal finalists exceed nominal votes')
    present1 = np.broadcast_to(np.asarray(counts.get('present_1', True), dtype=bool), l1.shape)
    present2 = np.broadcast_to(np.asarray(counts.get('present_2', True), dtype=bool), l1.shape)
    present = present1 & present2
    nominal_defined = present & (n1 > 0) & (n2 > 0)
    relative_defined = present & (l1 > 0) & (b1 > 0)
    conditional_defined = present & (f1 > 0) & (f2 > 0)
    gain13, gain22 = l2 - l1, b2 - b1
    count_advantage = gain13 - gain22
    nominal_num = _cross_difference(l2 - b2, n1, l1 - b1, n2)
    nominal_den = _cross_difference(n1, n2, np.zeros_like(n1), n1)
    conditional_num = _cross_difference(l2, f1, l1, f2)
    conditional_den = _cross_difference(f1, f2, np.zeros_like(f1), f1)
    relative_num = _cross_difference(l2, b1, b2, l1)
    relative_den = _cross_difference(l1, b1, np.zeros_like(l1), l1)
    nominal, nn, nd = _reduce_ratio(nominal_num, nominal_den, nominal_defined)
    conditional, cn, cd = _reduce_ratio(conditional_num, conditional_den, conditional_defined)
    relative, rn, rd = _reduce_ratio(relative_num, relative_den, relative_defined)
    ratio = lambda top, bottom: np.divide(100.0 * top, bottom,
        out=np.full(top.shape, np.nan), where=bottom > 0)
    q1, q2 = ratio(l1, f1), ratio(l2, f2)
    q1[~present1], q2[~present2] = np.nan, np.nan
    nominal13 = ratio(l2, n2) - ratio(l1, n1)
    nominal22 = ratio(b2, n2) - ratio(b1, n1)
    relative13, relative22 = ratio(l2 - l1, l1), ratio(b2 - b1, b1)
    for values in (nominal13, nominal22, relative13, relative22):
        values[~present] = np.nan
    signs = lambda numerator, valid: np.where(valid, np.sign(numerator), 0).astype(np.int8)
    result = dict(gain13=gain13, gain22=gain22, count_advantage=count_advantage,
        nominal_gain13=nominal13, nominal_gain22=nominal22, nominal_advantage=nominal,
        relative_gain13=relative13, relative_gain22=relative22, relative_advantage=relative,
        q1=q1, q2=q2, delta=conditional, nominal_num=nn, nominal_den=nd,
        conditional_num=cn, conditional_den=cd, relative_num=rn, relative_den=rd,
        sign_count=signs(count_advantage, present), sign_nominal=signs(nominal_num, nominal_defined),
        sign_relative=signs(relative_num, relative_defined), sign_conditional=signs(conditional_num, conditional_defined),
        defined_count=present, defined_nominal=nominal_defined, defined_relative=relative_defined,
        defined_conditional=conditional_defined)
    both = relative_defined & conditional_defined
    if not np.array_equal(result['sign_relative'][both], result['sign_conditional'][both]):
        raise ArithmeticError('Relative-growth and conditional-share directions differ')
    return result


def fraction99(numerator, denominator):
    numerator, denominator = int(numerator), int(denominator)
    if numerator < 0 or denominator < 0 or numerator > denominator:
        raise ValueError('Expected a nonnegative fraction bounded by one')
    return None if denominator == 0 else 100 * numerator >= 99 * denominator


def section_changes(pairs, ids):
    ids = np.asarray(ids, dtype=np.int64)
    _audit_cohort(pairs, ids)
    first, second = pairs['f_1'][ids], pairs['f_2'][ids]
    delta, numerator, denominator = _ratio_change(
        pairs['v13_1'][ids], first, pairs['v13_2'][ids], second)
    return dict(delta=delta, numerator=numerator, denominator=denominator,
        q1=100 * pairs['v13_1'][ids] / first,
        q2=100 * pairs['v13_2'][ids] / second)


def _sum_fields(source, labels, count, fields=COUNT_FIELDS):
    return {field: integer_group_sum(source[field], labels, count) for field in fields}


def _validate_allocation_bounds(units):
    """Every destination is bounded by the conserved countrywide payload."""
    totals = {field: sum(map(int, units[field])) for field in COUNT_FIELDS}
    if any(value > 2**53 for value in totals.values()):
        raise OverflowError('Conserved allocation counts exceed exact float64 integers')
    n1, n2 = totals['nominal_1'], totals['nominal_2']
    f1, f2 = totals['f_1'], totals['f_2']
    l1, l2 = totals['v13_1'], totals['v13_2']
    b1, b2 = totals['v22_1'], totals['v22_2']
    bounds = (f2 * n1 + f1 * n2, l2 * f1 + l1 * f2, l2 * b1 + b2 * l1)
    if max(bounds, default=0) > np.iinfo(np.int64).max:
        raise OverflowError('Some possible municipal comparison products exceed int64')


def _assigned(prepared, assigned):
    length = len(prepared['units']['ns'])
    if assigned is None:
        return np.arange(length, dtype=np.int32)
    assigned = np.asarray(assigned)
    if assigned.shape != (length,) or not np.issubdtype(assigned.dtype, np.integer):
        raise ValueError('Expected one integer source unit per destination slot')
    if np.any(assigned < 0) or np.any(assigned >= length):
        raise ValueError('Assignment index outside available units')
    return assigned


def aggregate(prepared, assigned=None):
    assigned = _assigned(prepared, assigned)
    units, labels, count = prepared['units'], prepared['unit_municipality'], prepared['mun_count']
    result = _sum_fields({field: units[field][assigned] for field in COUNT_FIELDS}, labels, count)
    result['ns'] = integer_group_sum(units['ns'][assigned], labels, count)
    result['units'] = np.bincount(labels, minlength=count).astype(np.int64)
    result['delta_sum'] = np.bincount(labels, weights=units['delta_sum'][assigned], minlength=count)
    result['residual_sum'] = np.bincount(labels, weights=prepared['unit_residual'][assigned], minlength=count)
    result['delta_mean'] = result['delta_sum'] / result['ns']
    result['residual_mean'] = result['residual_sum'] / result['ns']
    result['metrics'] = municipality_metrics(result)
    return result


def prepare(pairs, model, bins=20, finalist_floor=50, unchanged_aptos=False, min_target=5):
    if model not in MODELS or min_target < 1:
        raise ValueError('Known allocation model and positive target floor required')
    mask, reasons, basic = eligibility(pairs, finalist_floor, unchanged_aptos, domestic_only=True)
    ids = np.flatnonzero(mask)
    if not len(ids):
        raise ValueError('Empty domestic paired cohort')
    change = section_changes(pairs, ids)
    ufs, uf_labels = np.unique(pairs['uf'][ids], return_inverse=True)
    municipality_group = grouping([uf_labels, pairs['municipality'][ids]])
    municipal_labels = municipality_group['labels']
    mun_count = len(municipality_group['sizes'])
    first = municipality_group['first']
    municipal_uf = pairs['uf'][ids[first]]
    municipal_codes = pairs['municipality'][ids[first]]
    targets = municipality_group['sizes'] >= min_target
    if model == 'section':
        unit_labels = np.arange(len(ids), dtype=np.int64)
        unit_first = np.arange(len(ids), dtype=np.int64)
        ns = np.ones(len(ids), dtype=np.int64)
        units = {field: pairs[field][ids].astype(np.int64) for field in COUNT_FIELDS}
        unit_municipality = municipal_labels.copy()
        delta_sum = change['delta'].copy()
    else:
        unit_group = grouping([uf_labels, pairs['municipality'][ids], pairs['zone'][ids], pairs['place_1'][ids]])
        unit_labels, unit_first, ns = unit_group['labels'], unit_group['first'], unit_group['sizes']
        units = _sum_fields({field: pairs[field][ids] for field in COUNT_FIELDS}, unit_labels, len(ns))
        unit_municipality = municipal_labels[unit_first]
        delta_sum = np.bincount(unit_labels, weights=change['delta'], minlength=len(ns))
    units.update(ns=ns.astype(np.int64), delta_sum=delta_sum,
        uf=pairs['uf'][ids[unit_first]], municipality=pairs['municipality'][ids[unit_first]],
        zone=pairs['zone'][ids[unit_first]], place=pairs['place_1'][ids[unit_first]],
        section=pairs['section'][ids[unit_first]] if model == 'section' else np.full(len(ns), -1, dtype=np.int32))
    _validate_allocation_bounds(units)
    band = np.floor(np.log(units['aptos_1']) / np.log(1.25)).astype(np.int32)
    turnout_band = proportion_band(units['turnout_1'], units['aptos_1'], bins)
    preference_band = proportion_band(units['v13_1'], units['f_1'], bins)
    other_band = proportion_band(units['nominal_1'] - units['f_1'], units['turnout_1'], bins)
    _, unit_uf_labels = np.unique(units['uf'], return_inverse=True)
    group = grouping([unit_uf_labels, band, turnout_band, preference_band, other_band])
    labels, sizes = group['labels'], group['sizes']
    group_count = len(sizes)
    distinct_municipalities = np.unique(np.column_stack([labels, unit_municipality]), axis=0)
    group_municipalities = np.bincount(distinct_municipalities[:, 0], minlength=group_count)
    movable = group_municipalities >= 2
    reachable = np.bincount(labels, weights=targets[unit_municipality], minlength=group_count) > 0
    total_ns = integer_group_sum(units['ns'], labels, group_count)
    total_delta = np.bincount(labels, weights=delta_sum, minlength=group_count)
    group_mean = total_delta / total_ns
    residual = delta_sum - group_mean[labels] * units['ns']
    buckets = []
    for size in sorted(set(sizes[movable].tolist())):
        selected = np.flatnonzero(movable & (sizes == size))
        buckets.append(np.asarray([group['order'][group['starts'][g]:group['starts'][g + 1]]
                                  for g in selected], dtype=np.int32))
    original_counts = _sum_fields({field: pairs[field][ids] for field in COUNT_FIELDS}, municipal_labels, mun_count)
    order = []
    edges = []
    for uf in sorted(set(municipal_uf.tolist())):
        members = np.flatnonzero(targets & (municipal_uf == uf)).tolist()
        members.sort(key=lambda i: (Fraction(int(original_counts['v13_1'][i]), int(original_counts['f_1'][i])),
                                    int(municipal_codes[i])))
        order.extend(members)
        edges.extend(zip(members[:-1], members[1:]))
    prepared = dict(pairs=pairs, ids=ids, reasons=reasons, basic=basic, change=change,
        model=model, bins=bins, finalist_floor=finalist_floor, unchanged_aptos=unchanged_aptos,
        min_target=min_target, units=units, unit_count=len(ns), unit_labels=unit_labels,
        unit_first=unit_first, unit_municipality=unit_municipality, group=group,
        group_municipalities=group_municipalities, group_movable=movable,
        group_target_reachable=reachable, group_mean=group_mean,
        unit_residual=residual, unit_size_band=band, unit_turnout_band=turnout_band,
        unit_preference_band=preference_band, unit_other_band=other_band,
        municipality_group=municipality_group, mun_count=mun_count, targets=targets,
        profile_order=np.asarray(order, dtype=np.int32), edges=np.asarray(edges, dtype=np.int32).reshape(-1, 2),
        buckets=buckets)
    municipal = aggregate(prepared)
    municipal.update(uf=municipal_uf, municipality=municipal_codes)
    prepared['municipal'] = municipal
    return prepared


def assignment(prepared, seed, model_id, repetition):
    if model_id != MODELS[prepared['model']] or repetition < 0:
        raise ValueError('Model ID or repetition does not match prepared reference')
    rng = np.random.default_rng(np.random.SeedSequence([seed, 7, model_id], spawn_key=(repetition,)))
    result = np.arange(len(prepared['units']['ns']), dtype=np.int32)
    for bucket in prepared['buckets']:
        result[bucket.ravel()] = rng.permuted(bucket, axis=1).ravel()
    return result


def simulation_state(prepared):
    result = {name: prepared[name] for name in
              ('model', 'buckets', 'targets', 'edges', 'mun_count', 'unit_municipality', 'unit_residual')}
    result['units'] = {field: prepared['units'][field] for field in (*FAST_COUNT_FIELDS, 'ns')}
    return result


def edge_contrasts(prepared, aggregated=None):
    aggregated = aggregate(prepared) if aggregated is None else aggregated
    left, right = prepared['edges'].T
    difference = aggregated['residual_mean'][left] - aggregated['residual_mean'][right]
    scale = np.sqrt(1.0 / aggregated['ns'][left] + 1.0 / aggregated['ns'][right])
    signed = difference / scale
    return dict(left=left, right=right, difference=difference, signed_score=signed,
                score=np.abs(signed), n_left=aggregated['ns'][left], n_right=aggregated['ns'][right])


def score(prepared, assigned=None):
    assigned = _assigned(prepared, assigned)
    target = prepared['targets']
    if not np.any(target):
        return np.zeros(5)
    units, labels, count = prepared['units'], prepared['unit_municipality'], prepared['mun_count']
    # The global count bound is checked in prepare/aggregation. Every simulated
    # destination total is bounded by these same nonnegative national totals.
    counts = {field: np.bincount(labels, weights=units[field][assigned], minlength=count).astype(np.int64)
              for field in FAST_COUNT_FIELDS}
    l1, b1, l2, b2 = (counts[field] for field in ('v13_1', 'v22_1', 'v13_2', 'v22_2'))
    count_sign = np.sign((l2 - l1) - (b2 - b1))
    nominal_sign = np.sign(_cross_difference(l2 - b2, counts['nominal_1'], l1 - b1, counts['nominal_2']))
    conditional_sign = np.sign(_cross_difference(l2, l1 + b1, l1, l2 + b2))
    prevalence = lambda signs: max(np.count_nonzero(signs[target] > 0), np.count_nonzero(signs[target] < 0)) / int(target.sum())
    ns = np.bincount(labels, weights=units['ns'][assigned], minlength=count)
    sums = np.bincount(labels, weights=prepared['unit_residual'][assigned], minlength=count)
    means = sums / ns
    rms = np.sqrt(np.sum(sums[target] ** 2 / ns[target]) / np.sum(ns[target]))
    left, right = prepared['edges'].T
    jump = np.max(np.abs(means[left] - means[right]) /
                  np.sqrt(1.0 / ns[left] + 1.0 / ns[right])) if len(left) else 0.0
    return np.asarray([prevalence(count_sign), prevalence(nominal_sign), prevalence(conditional_sign), rms, jump])


def _exact_unit_residuals(prepared):
    changes = prepared['change']
    exact_delta = [100 * Fraction(int(n), int(d)) for n, d in
                   zip(changes['numerator'], changes['denominator'])]
    unit_delta = [Fraction(0) for _ in range(prepared['unit_count'])]
    for value, unit in zip(exact_delta, prepared['unit_labels']):
        unit_delta[int(unit)] += value
    group = prepared['group']
    residual = [Fraction(0) for _ in unit_delta]
    for g in range(len(group['sizes'])):
        members = group['order'][group['starts'][g]:group['starts'][g + 1]]
        n = sum(int(prepared['units']['ns'][i]) for i in members)
        mean = sum((unit_delta[int(i)] for i in members), Fraction(0)) / n
        for i in members:
            residual[int(i)] = unit_delta[int(i)] - mean * int(prepared['units']['ns'][i])
    return residual


def _exact_score_squares(prepared, assigned, residual):
    labels, units = prepared['unit_municipality'], prepared['units']
    count = prepared['mun_count']
    sums = [Fraction(0) for _ in range(count)]
    n = [0] * count
    raw = {field: [0] * count for field in FAST_COUNT_FIELDS}
    for slot, donor in enumerate(assigned):
        m, donor = int(labels[slot]), int(donor)
        n[m] += int(units['ns'][donor])
        sums[m] += residual[donor]
        for field in FAST_COUNT_FIELDS:
            raw[field][m] += int(units[field][donor])
    targets = np.flatnonzero(prepared['targets']).tolist()
    signs = [[], [], []]
    for m in targets:
        l1, b1, l2, b2 = (raw[field][m] for field in ('v13_1', 'v22_1', 'v13_2', 'v22_2'))
        n1, n2 = raw['nominal_1'][m], raw['nominal_2'][m]
        for output, value in zip(signs, ((l2-l1)-(b2-b1), (l2-b2)*n1-(l1-b1)*n2,
                                         l2*(l1+b1)-l1*(l2+b2))):
            output.append((value > 0) - (value < 0))
    prevalence = [Fraction(max(values.count(1), values.count(-1)), len(targets)) for values in signs]
    rms_squared = sum((sums[m] ** 2 / n[m] for m in targets), Fraction(0)) / sum(n[m] for m in targets)
    jump_squared = max(((sums[int(l)] / n[int(l)] - sums[int(r)] / n[int(r)]) ** 2 /
                        (Fraction(1, n[int(l)]) + Fraction(1, n[int(r)]))
                       for l, r in prepared['edges']), default=Fraction(0))
    return (*prevalence, rms_squared, jump_squared)


def score_variability(prepared, sampled, observed, max_exact=40320):
    sampled, observed = np.asarray(sampled, dtype=float), np.asarray(observed, dtype=float)
    if (sampled.ndim != 2 or sampled.shape[1] != 5 or observed.shape != (5,) or
            np.any(~np.isfinite(sampled)) or np.any(~np.isfinite(observed)) or
            np.any(sampled < 0) or np.any(observed < 0) or max_exact < 0):
        raise ValueError('Expected nonnegative B-by-five scores')
    if not np.any(prepared['targets']):
        return np.zeros(5, dtype=bool), ['no_target_municipalities'] * 5
    flags = np.ptp(np.vstack([observed, sampled]), axis=0) > EPS
    reasons = ['sampled_distinct_scores' if flag else '' for flag in flags]
    if not len(prepared['edges']):
        flags[4], reasons[4] = False, 'no_adjacent_target_municipality_pairs'
    relevant = prepared['group_movable'] & prepared['group_target_reachable']
    if not np.any(relevant):
        return np.zeros(5, dtype=bool), [
            'no_adjacent_target_municipality_pairs' if k == 4 and not len(prepared['edges'])
            else 'no_cross_target_municipality_mobility' for k in range(5)]
    unresolved = np.array([not flag and not reason for flag, reason in zip(flags, reasons)])
    if not np.any(unresolved):
        return flags, reasons
    groups, orbit = [], 1
    group = prepared['group']
    for g in np.flatnonzero(relevant):
        members = group['order'][group['starts'][g]:group['starts'][g + 1]]
        groups.append(members)
        for factor in range(2, len(members) + 1):
            orbit *= factor
            if orbit > max_exact:
                for k in np.flatnonzero(unresolved):
                    reasons[k] = 'unresolved_large_orbit'
                return flags, reasons
    # Limit work on a potentially giant, fixed backdrop; unresolved is an
    # explicit nondecision, never an invented assertion of exact constancy.
    if len(prepared['ids']) > 5000:
        for k in np.flatnonzero(unresolved):
            reasons[k] = 'unresolved_exact_backdrop_too_large'
        return flags, reasons
    residual = _exact_unit_residuals(prepared)
    baseline = None
    for draw in product(*(permutations(m.tolist()) for m in groups)):
        assigned = np.arange(prepared['unit_count'], dtype=np.int32)
        for members, source in zip(groups, draw):
            assigned[members] = source
        exact = _exact_score_squares(prepared, assigned, residual)
        if baseline is None:
            baseline = exact
        for k in np.flatnonzero(unresolved & ~flags):
            if exact[k] != baseline[k]:
                flags[k], reasons[k] = True, 'exact_enumeration_variable'
        if np.all(flags | ~unresolved):
            break
    for k in np.flatnonzero(unresolved & ~flags):
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
