"""Artificial H7 controls and finite rational allocation oracles.

The original-array fixture shape adapts the H6 tests at commit cb32076;
all scenarios here are synthetic and never load the election CSVs.
"""
from fractions import Fraction
from itertools import permutations
import math
import unittest

import numpy as np

from regularity_statistics import (MODELS, STATISTICS, TAILS, aggregate,
    assignment, eligibility, fraction99, holm, municipality_metrics, pair_sections,
    prepare, score, score_variability, section_changes)


CANDIDATES = {1: [13,14,16,21,22,27,28,29,30,35,55,70,80], 2: [13,22]}


def round_data(turn, v13, v22, *, municipalities=None, sections=None,
               places=None, aptos=None, turnout=None, other=None, ufs=None,
               zones=None):
    """Original-array-shaped fixture with every presidential vote category."""
    a13, a22 = np.asarray(v13,dtype=np.int64), np.asarray(v22,dtype=np.int64)
    n = len(a13)
    matrix = np.zeros((n,len(CANDIDATES[turn])),dtype=np.int64)
    matrix[:,CANDIDATES[turn].index(13)] = a13
    matrix[:,CANDIDATES[turn].index(22)] = a22
    if other is not None:
        matrix[:,CANDIDATES[turn].index(14)] = other
    nominal = matrix.sum(axis=1)
    a = np.full(n,2000,dtype=np.int64) if aptos is None else np.asarray(aptos,dtype=np.int64)
    t = nominal+100 if turnout is None else np.asarray(turnout,dtype=np.int64)
    if np.any(t<nominal) or np.any(a<t):
        raise ValueError('Artificial fixture must reconcile turnout and electorate')
    return dict(turno=turn,election_code=6256+turn,
        uf=np.asarray(ufs if ufs is not None else ['SP']*n,dtype='U2'),
        municipality=np.asarray(municipalities if municipalities is not None else [71072]*n,dtype=np.int64),
        zone=np.asarray(zones if zones is not None else [1]*n,dtype=np.int64),
        section=np.asarray(sections if sections is not None else np.arange(1,n+1),dtype=np.int64),
        place=np.asarray(places if places is not None else [1]*n,dtype=np.int64),
        source_line=np.arange(2,n+2),aptos=a,turnout=t,abstentions=a-t,
        nominal=nominal,blank=t-nominal,null_votes=np.zeros(n,dtype=np.int64),
        legend=np.zeros(n,dtype=np.int64),separate=np.zeros(n,dtype=np.int64),
        installed=np.ones(n,dtype=bool),cancelled=np.zeros(n,dtype=bool),
        candidate_numbers=list(CANDIDATES[turn]),candidate_votes=matrix)


def paired_fixture(swings=(-2,-2,4,4), *, ufs=None):
    """Two municipalities, two intact blocks each; blocks have 2/3 sections.

    Initial A1 of each block is 4000/4500, in the same ratio-1.25 band;
    every block has the same initial turnout, finalist, and other shares.
    The resulting place-block randomization has 4! assignments.
    """
    municipalities = [100]*5+[200]*5
    places = [10]*2+[20]*3+[30]*2+[40]*3
    a = np.array([2000]*2+[1500]*3+[2000]*2+[1500]*3,dtype=np.int64)
    f = a//2
    one = f//2
    repeated_swings = np.repeat(np.asarray(swings,dtype=float),[2,3,2,3])
    shifted = one+np.rint(f*repeated_swings/100).astype(np.int64)
    shared = dict(municipalities=municipalities,places=places,aptos=a,
        turnout=3*a//5,sections=[1,2,3,4,5]*2,ufs=ufs)
    r1 = round_data(1,one,one,other=a//20,**shared)
    r2 = round_data(2,shifted,f-shifted,**shared)
    return pair_sections([r1,r2])['pairs']


def exact_scores(prepared, source):
    """Independent small-fixture oracle: rational aggregation and squared scores."""
    unit = prepared['units']
    destination = np.asarray(prepared['unit_municipality'])
    target = np.flatnonzero(prepared['targets'])
    m = len(prepared['municipal']['uf'])
    rows = [dict(n=0,delta=Fraction(),residual=Fraction(),
                 v13_1=0,v22_1=0,v13_2=0,v22_2=0,nominal_1=0,nominal_2=0)
            for _ in range(m)]
    # This fixture's exact stratum mean is one pp. Unit values are integer
    # multiples of pp, so derive exact block residuals independently.
    mean = Fraction(1)
    for slot, donor in enumerate(source):
        row = rows[int(destination[slot])]
        n = int(unit['ns'][donor])
        delta = Fraction(str(float(unit['delta_sum'][donor])))
        row['n'] += n
        row['delta'] += delta
        row['residual'] += delta-mean*n
        for field in ('v13_1','v22_1','v13_2','v22_2','nominal_1','nominal_2'):
            row[field] += int(unit[field][donor])
    signs = [[],[],[]]
    for i in target:
        row = rows[int(i)]
        count = row['v13_2']-row['v13_1']-row['v22_2']+row['v22_1']
        nominal = ((Fraction(row['v13_2']-row['v22_2'],row['nominal_2']))-
                   Fraction(row['v13_1']-row['v22_1'],row['nominal_1']))
        conditional = (Fraction(row['v13_2'],row['v13_2']+row['v22_2'])-
                       Fraction(row['v13_1'],row['v13_1']+row['v22_1']))
        for values, value in zip(signs,(count,nominal,conditional)):
            values.append((value>0)-(value<0))
    prevalence = [Fraction(max(values.count(1),values.count(-1)),len(target))
                  if len(target) else Fraction() for values in signs]
    total_n = sum(rows[int(i)]['n'] for i in target)
    rms_squared = (sum((rows[int(i)]['residual']**2/rows[int(i)]['n']
                        for i in target),Fraction())/total_n if total_n else Fraction())
    jump_squared = []
    for left, right in prepared['edges']:
        a,b = rows[int(left)],rows[int(right)]
        difference = a['residual']/a['n']-b['residual']/b['n']
        jump_squared.append(difference**2/(Fraction(1,a['n'])+Fraction(1,b['n'])))
    return np.array([*[float(value) for value in prevalence],
        math.sqrt(float(rms_squared)),math.sqrt(float(max(jump_squared,default=Fraction())))])


class PhysicalPairingTests(unittest.TestCase):
    def test_physical_join_ignores_turn_code_and_source_order(self):
        first = round_data(1,[500,510,520],[500,490,480],sections=[3,1,4])
        second = round_data(2,[530,540,550],[470,460,450],sections=[4,1,5])
        got = pair_sections([second,first])
        self.assertEqual(got['pairs']['section'].tolist(),[1,4])
        self.assertEqual(got['pairs']['v13_1'].tolist(),[510,520])
        self.assertEqual(got['pairs']['v13_2'].tolist(),[540,530])
        self.assertEqual([rd['section'][ids].tolist() for _,rd,ids in got['unmatched']],[[3],[5]])

    def test_ambiguous_and_missing_round_keys_raise(self):
        first = round_data(1,[500,500],[500,500],sections=[1,1])
        second = round_data(2,[500],[500])
        with self.assertRaises(ValueError):pair_sections([first,second])
        with self.assertRaises(ValueError):pair_sections([second])
        first = round_data(1,[500],[500])
        with self.assertRaises(ValueError):pair_sections([first,second,second])

    def test_municipal_and_uf_components_prevent_false_matches(self):
        first = round_data(1,[500,510],[500,490],sections=[1,1],municipalities=[10,20])
        second = round_data(2,[520,530],[480,470],sections=[1,1],municipalities=[20,10])
        pairs = pair_sections([first,second])['pairs']
        self.assertEqual(list(zip(pairs['municipality'],pairs['v13_1'],pairs['v13_2'])),
            [(10,500,530),(20,510,520)])

    def test_eligibility_uses_exclusive_priority_and_domestic_formal_cohort(self):
        pairs = paired_fixture()
        pairs['installed_1'][0] = False
        pairs['aptos_1'][0] = 1
        pairs['aptos_2'][1] = 49
        pairs['place_2'][2] = -1
        pairs['place_2'][3] = 55
        pairs['uf'][-1] = 'ZZ'
        mask,reasons,_ = eligibility(pairs)
        self.assertEqual(reasons[:4].tolist(),['section_status','aptos_below_50','missing_place','changed_place'])
        self.assertTrue(mask[-1])
        prepared = prepare(pairs,'section',min_target=1)
        self.assertNotIn(9,prepared['ids'].tolist())

    def test_eligible_accounting_failure_interrupts_without_silent_drop(self):
        pairs = paired_fixture()
        pairs['abstentions_2'][0] += 1
        with self.assertRaises((ValueError,ArithmeticError)):
            prepare(pairs,'section')
        pairs['installed_1'][0] = False
        self.assertNotIn(0,prepare(pairs,'section',min_target=1)['ids'].tolist())


class MunicipalDefinitionTests(unittest.TestCase):
    @staticmethod
    def counts(first13,first22,first_nominal,second13,second22,second_nominal,**extra):
        return dict(v13_1=np.atleast_1d(first13),v22_1=np.atleast_1d(first22),
            nominal_1=np.atleast_1d(first_nominal),v13_2=np.atleast_1d(second13),
            v22_2=np.atleast_1d(second22),nominal_2=np.atleast_1d(second_nominal),**extra)

    def test_count_and_share_advantage_can_have_opposite_directions(self):
        counts = self.counts(400,600,1000,780,1020,1800)
        result = municipality_metrics(counts)
        self.assertEqual(int(result['count_advantage'][0]),-40)
        self.assertEqual(int(result['sign_count'][0]),-1)
        self.assertEqual(int(result['sign_nominal'][0]),1)
        self.assertEqual(int(result['sign_conditional'][0]),1)

    def test_nominal_and_conditional_advantage_can_have_opposite_directions(self):
        result = municipality_metrics(self.counts(400,600,2000,440,560,1000))
        self.assertAlmostEqual(result['nominal_advantage'][0],-2.0)
        self.assertAlmostEqual(result['delta'][0],4.0)
        self.assertEqual(int(result['sign_nominal'][0]),-1)
        self.assertEqual(int(result['sign_conditional'][0]),1)
        self.assertEqual(int(result['sign_count'][0]),1)

    def test_exit_of_other_candidates_changes_both_nominal_shares_without_preference_change(self):
        result = municipality_metrics(self.counts(400,600,2000,400,600,1000))
        self.assertAlmostEqual(result['nominal_gain13'][0],20.0)
        self.assertAlmostEqual(result['nominal_gain22'][0],30.0)
        self.assertAlmostEqual(result['delta'][0],0.0)
        self.assertEqual(int(result['sign_nominal'][0]),-1)
        self.assertEqual(int(result['sign_conditional'][0]),0)

    def test_relative_growth_direction_is_conditional_direction_and_not_extra_evidence(self):
        counts = self.counts([400,600,500],[600,400,500],[2000,1500,1000],
            [440,550,600],[560,450,600],[1000,1000,1200])
        result = municipality_metrics(counts)
        self.assertEqual(result['sign_relative'].tolist(),[1,-1,0])
        np.testing.assert_array_equal(result['sign_relative'],result['sign_conditional'])
        for i in range(3):
            lhs = Fraction(int(counts['v13_2'][i]),int(counts['v13_1'][i]))-Fraction(int(counts['v22_2'][i]),int(counts['v22_1'][i]))
            rhs = Fraction(int(result['relative_num'][i]),int(result['relative_den'][i]))
            self.assertEqual(lhs,rhs)

    def test_mechanical_identities_hold_as_exact_fractions(self):
        counts = self.counts([400,600,500],[600,400,500],[2000,1500,1000],
            [440,550,600],[560,450,600],[1000,1000,1200])
        result = municipality_metrics(counts)
        for i in range(3):
            l1,b1,l2,b2,n1,n2 = (int(counts[field][i]) for field in
                ('v13_1','v22_1','v13_2','v22_2','nominal_1','nominal_2'))
            f1,f2 = l1+b1,l2+b2
            q1,q2 = Fraction(l1,f1),Fraction(l2,f2)
            nominal = Fraction(l2-b2,n2)-Fraction(l1-b1,n1)
            self.assertEqual(nominal,2*(q2-q1)+(1-Fraction(f1,n1))*(2*q1-1))
            self.assertEqual((l2-l1)-(b2-b1),2*f2*(q2-q1)+(f2-f1)*(2*q1-1))
            self.assertEqual(nominal,Fraction(int(result['nominal_num'][i]),int(result['nominal_den'][i])))

    def test_zero_initial_candidate_has_undefined_relative_growth_without_pseudocount(self):
        result = municipality_metrics(self.counts(0,1000,1000,100,900,1000))
        self.assertFalse(result['defined_relative'][0])
        self.assertTrue(np.isnan(result['relative_gain13'][0]))
        self.assertTrue(np.isnan(result['relative_advantage'][0]))
        self.assertEqual(int(result['relative_den'][0]),0)
        self.assertTrue(result['defined_conditional'][0])
        self.assertEqual(int(result['sign_conditional'][0]),1)

    def test_zero_denominators_and_absent_rounds_are_distinguished(self):
        zero = municipality_metrics(self.counts(0,0,0,100,100,200))
        self.assertTrue(zero['defined_count'][0])
        for field in ('nominal','conditional','relative'):
            self.assertFalse(zero[f'defined_{field}'][0])
            self.assertEqual(int(zero[f'sign_{field}'][0]),0)
        absent = municipality_metrics(self.counts(500,500,1100,0,0,0,present_2=[False]))
        self.assertFalse(absent['defined_count'][0])
        self.assertEqual(int(absent['sign_count'][0]),0)
        self.assertEqual(absent['q1'][0],50.0)
        self.assertTrue(np.isnan(absent['q2'][0]))
        self.assertTrue(np.isnan(absent['delta'][0]))

    def test_exact_ties_stay_in_the_prevalence_denominator(self):
        result = municipality_metrics(self.counts(500,500,1000,600,600,1200))
        self.assertEqual(int(result['sign_count'][0]),0)
        self.assertEqual(int(result['sign_nominal'][0]),0)
        self.assertEqual(int(result['sign_relative'][0]),0)
        self.assertEqual(int(result['sign_conditional'][0]),0)

    def test_99_percent_comparison_does_not_round_98_995_to_99(self):
        self.assertEqual(round(100*19799/20000,2),99.0)
        self.assertFalse(fraction99(19799,20000))
        self.assertTrue(fraction99(19800,20000))
        self.assertTrue(fraction99(19801,20000))
        self.assertIsNone(fraction99(0,0))
        for numerator,denominator in ((-1,5),(6,5),(0,-1)):
            with self.assertRaises(ValueError):fraction99(numerator,denominator)

    def test_comparison_products_never_silently_overflow(self):
        big = 2**50
        with self.assertRaises(OverflowError):
            municipality_metrics(self.counts(big+1,big,2*big+1,big+2,big,2*big+2))
        with self.assertRaises(ValueError):
            municipality_metrics(self.counts(10,10,19,10,10,20))


class CompleteBlockAndScoreTests(unittest.TestCase):
    def test_prespecified_model_statistics_and_tails(self):
        self.assertEqual(MODELS,{'section':0,'place_block':1})
        self.assertEqual(tuple(STATISTICS),('Ucount','Unominal','Uconditional','Rlow','Jhigh'))
        self.assertEqual(tuple(TAILS),('upper','upper','upper','lower','upper'))

    def test_block_aggregation_keeps_every_category_and_section_count(self):
        prepared = prepare(paired_fixture(),'place_block')
        unit = prepared['units']
        self.assertEqual(unit['ns'].tolist(),[2,3,2,3])
        self.assertEqual(unit['aptos_1'].tolist(),[4000,4500,4000,4500])
        self.assertEqual(unit['turnout_1'].tolist(),[2400,2700,2400,2700])
        self.assertEqual(unit['nominal_1'].tolist(),[2200,2475,2200,2475])
        self.assertEqual(unit['blank_1'].tolist(),[200,225,200,225])
        np.testing.assert_allclose(unit['delta_sum'],[-4,-6,8,12],atol=1e-12)
        self.assertEqual(len(prepared['group']['sizes']),1)

    def test_unit_ns_and_residual_move_with_complete_pair_payload(self):
        prepared = prepare(paired_fixture(),'place_block')
        assigned = np.array([1,3,0,2],dtype=np.int32)
        original = aggregate(prepared)
        changed = aggregate(prepared,assigned)
        self.assertEqual(original['ns'].tolist(),[5,5])
        self.assertEqual(changed['ns'].tolist(),[6,4])
        self.assertEqual(changed['units'].tolist(),[2,2])
        self.assertEqual(int(prepared['targets'].sum()),2)
        self.assertTrue(prepared['targets'][1])
        self.assertLess(changed['ns'][1],5)
        for field in ('aptos_1','aptos_2','turnout_1','turnout_2','nominal_1','nominal_2',
                      'v13_1','v13_2','v22_1','v22_2','blank_1','blank_2','null_votes_1','null_votes_2'):
            self.assertEqual(int(changed[field].sum()),int(original[field].sum()),field)

    def test_all_24_block_allocations_match_independent_rational_oracle(self):
        prepared = prepare(paired_fixture(),'place_block')
        for values in permutations(range(4)):
            assigned = np.array(values,dtype=np.int32)
            np.testing.assert_allclose(score(prepared,assigned),exact_scores(prepared,assigned),
                rtol=1e-12,atol=1e-12,err_msg=f'assignment={values}')

    def test_constructed_uniform_allocation_has_lower_rms_and_profile_contrast(self):
        prepared = prepare(paired_fixture(),'place_block')
        observed = score(prepared)
        uniform = score(prepared,np.array([0,2,1,3],dtype=np.int32))
        self.assertAlmostEqual(observed[3],3.0)
        self.assertAlmostEqual(observed[4],6/math.sqrt(2/5))
        self.assertLess(uniform[3],1e-12)
        self.assertLess(uniform[4],1e-12)
        self.assertGreater(uniform[0],observed[0])

    def test_profile_contrast_uses_section_scale_and_is_not_z_score(self):
        prepared = prepare(paired_fixture(),'place_block')
        got = aggregate(prepared)
        left,right = prepared['edges'][0]
        expected = (abs(got['residual_mean'][left]-got['residual_mean'][right])/
            math.sqrt(1/got['ns'][left]+1/got['ns'][right]))
        self.assertAlmostEqual(score(prepared)[4],expected)
        self.assertGreater(score(prepared)[4],1)

    def test_original_prevalence_does_not_depend_on_allocation_unit_model(self):
        pairs = paired_fixture()
        a,b = prepare(pairs,'section'),prepare(pairs,'place_block')
        np.testing.assert_array_equal(score(a)[:3],score(b)[:3])
        self.assertEqual(a['municipal']['municipality'].tolist(),b['municipal']['municipality'].tolist())

    def test_seeded_assignment_is_repeatable_and_group_preserving(self):
        prepared = prepare(paired_fixture(),'place_block')
        got = assignment(prepared,20261029,1,0)
        np.testing.assert_array_equal(got,assignment(prepared,20261029,1,0))
        self.assertEqual(sorted(got.tolist()),list(range(len(got))))
        self.assertEqual(prepared['group']['labels'].tolist(),prepared['group']['labels'][got].tolist())
        with self.assertRaises(ValueError):assignment(prepared,20261029,0,0)
        with self.assertRaises(ValueError):assignment(prepared,20261029,1,-1)

    def test_holm_preserves_dependent_fixed_family(self):
        values = [.001,.003,.01,.2,1.0,.5,.003,.1,.02,.07]
        # Independent sorted-step-down reconstruction avoids assuming order.
        order = sorted(range(len(values)),key=lambda i:(values[i],i))
        reference = [0.0]*len(values)
        maximum = 0.0
        for j,i in enumerate(order):
            maximum = max(maximum,(len(values)-j)*values[i])
            reference[i] = min(1,maximum)
        np.testing.assert_allclose(holm(values),reference)
        self.assertTrue(np.all(holm(values)>=values))

    def test_profile_adjacency_is_initial_preference_order_with_code_ties_within_uf(self):
        l1 = np.array([501,500,499,500,500])
        shared = dict(municipalities=[200,100,300,50,10],ufs=['SP']*4+['RJ'],sections=[1]*5)
        first = round_data(1,l1,1000-l1,**shared)
        second = round_data(2,l1+5,995-l1,**shared)
        prepared = prepare(pair_sections([first,second])['pairs'],'section',min_target=1)
        municipal = prepared['municipal']
        edges = [(str(municipal['uf'][l]),int(municipal['municipality'][l]),
                  str(municipal['uf'][r]),int(municipal['municipality'][r]))
                 for l,r in prepared['edges']]
        self.assertEqual(edges,[('SP',300,'SP',50),('SP',50,'SP',100),('SP',100,'SP',200)])

    def test_no_targets_and_no_adjacencies_are_explicit_nonapplicability(self):
        pairs = paired_fixture()
        none = prepare(pairs,'place_block',min_target=10)
        self.assertFalse(np.any(none['targets']))
        np.testing.assert_array_equal(score(none),np.zeros(5))
        flags,reasons = score_variability(none,np.zeros((2,5)),score(none))
        self.assertFalse(flags.any())
        self.assertTrue(all(reason=='no_target_municipalities' for reason in reasons))
        pairs['uf'][5:] = 'RJ'
        separate = prepare(pairs,'place_block')
        self.assertEqual(len(separate['edges']),0)
        flags,reasons = score_variability(separate,np.tile(score(separate),(2,1)),score(separate))
        self.assertFalse(flags[4])
        self.assertEqual(reasons[4],'no_adjacent_target_municipality_pairs')

    def test_no_cross_municipality_mobility_is_proved_constant(self):
        pairs = paired_fixture()
        pairs['municipality'][:] = 100
        pairs['section'][:] = np.arange(1,11)
        prepared = prepare(pairs,'place_block')
        self.assertFalse(prepared['group_movable'].any())
        np.testing.assert_array_equal(assignment(prepared,20261029,1,0),np.arange(4))
        flags,reasons = score_variability(prepared,np.tile(score(prepared),(2,1)),score(prepared))
        self.assertFalse(flags.any())
        self.assertTrue(all(reason in {'no_cross_target_municipality_mobility',
            'no_adjacent_target_municipality_pairs'} for reason in reasons))

    def test_exact_orbit_proves_variation_or_constancy_without_monte_carlo_witness(self):
        prepared = prepare(paired_fixture(),'place_block')
        observed = score(prepared)
        flags,reasons = score_variability(prepared,np.tile(observed,(2,1)),observed)
        self.assertTrue(flags.all())
        self.assertTrue(all(reason=='exact_enumeration_variable' for reason in reasons))
        identical = prepare(paired_fixture(swings=(2,2,2,2)),'place_block')
        constant = score(identical)
        flags,reasons = score_variability(identical,np.tile(constant,(2,1)),constant)
        self.assertFalse(flags.any())
        self.assertTrue(all(reason=='exact_enumeration_constant' for reason in reasons))

    def test_unresolved_large_orbit_is_not_nondetection_or_constant_proof(self):
        prepared = prepare(paired_fixture(),'place_block')
        observed = score(prepared)
        flags,reasons = score_variability(prepared,np.tile(observed,(2,1)),observed,max_exact=1)
        self.assertFalse(flags.any())
        self.assertTrue(all(reason=='unresolved_large_orbit' for reason in reasons))


if __name__ == '__main__':
    unittest.main()
