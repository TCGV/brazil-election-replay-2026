"""Synthetic finite-reference controls; no election observations are imported."""
from fractions import Fraction
from itertools import permutations
import math
import unittest

import numpy as np

from pair_statistics import (MODELS, assignment, changes, concentration, eligibility,
    holm, median_without_self, pair_sections, preference_band, prepare,
    score_variability, screening)

CANDIDATES = {1: [13,14,16,21,22,27,28,29,30,35,55,70,80], 2: [13,22]}


def round_data(turn, v13, v22, *, sections=None, places=None, aptos=None,
               other=None, ufs=None):
    v13=np.asarray(v13,dtype=np.int64);v22=np.asarray(v22,dtype=np.int64)
    n=len(v13)
    matrix=np.zeros((n,len(CANDIDATES[turn])),dtype=np.int64)
    matrix[:,CANDIDATES[turn].index(13)]=v13
    matrix[:,CANDIDATES[turn].index(22)]=v22
    if other is not None:
        matrix[:,CANDIDATES[turn].index(14)]=other
    nominal=matrix.sum(axis=1)
    a=np.full(n,400,dtype=np.int64) if aptos is None else np.asarray(aptos,dtype=np.int64)
    return dict(turno=turn,election_code=6256+turn,
        uf=np.asarray(ufs if ufs is not None else ['SP']*n,dtype='U2'),
        municipality=np.full(n,71072,dtype=np.int64),zone=np.full(n,1,dtype=np.int64),
        section=np.asarray(sections if sections is not None else np.arange(1,n+1),dtype=np.int64),
        place=np.asarray(places if places is not None else np.ones(n),dtype=np.int64),
        source_line=np.arange(2,n+2),aptos=a,nominal=nominal,turnout=nominal+10,
        abstentions=a-nominal-10,installed=np.ones(n,dtype=bool),cancelled=np.zeros(n,dtype=bool),
        candidate_numbers=list(CANDIDATES[turn]),candidate_votes=matrix)


def pairs_from_deltas(deltas, places=None, q1_counts=None):
    """F1=F2=200; half a point per extra candidate-13 vote."""
    n=len(deltas)
    first=np.asarray(q1_counts if q1_counts is not None else [100]*n,dtype=np.int64)
    second=first+np.rint(np.asarray(deltas)*2).astype(np.int64)
    return pair_sections([round_data(1,first,200-first,places=places),
                          round_data(2,second,200-second,places=places)])['pairs']


def fraction_median(values):
    values=sorted(Fraction(value) for value in values);n=len(values)
    return values[n//2] if n%2 else (values[n//2-1]+values[n//2])/2


def oracle_concentration(prepared, delta, source):
    """Independent rational squared scores from slot and source indices."""
    groups=prepared['group']['labels'];place=prepared['place']['labels']
    residual=[]
    for i in range(len(delta)):
        peers=[delta[j] for j in range(len(delta)) if groups[j]==groups[i]]
        residual.append(delta[i]-sum(peers,Fraction())/len(peers))
    total=Fraction();maximum=Fraction();target_sections=0
    for local,size in enumerate(prepared['place']['sizes']):
        if not prepared['targets'][local]:
            continue
        slots=[i for i in range(len(delta)) if place[i]==local]
        summed=sum((residual[source[i]] for i in slots),Fraction())
        contribution=summed*summed/int(size)
        total+=contribution;maximum=max(maximum,contribution);target_sections+=int(size)
    if not target_sections:
        return np.zeros(2)
    return np.array([math.sqrt(float(total/target_sections)),math.sqrt(float(maximum))])


class PairingAndEligibilityTests(unittest.TestCase):
    def test_physical_keys_pair_across_election_codes_without_source_order(self):
        a=round_data(1,[70,90,100],[130,110,100],sections=[3,1,4])
        b=round_data(2,[110,95,80],[90,105,120],sections=[4,1,5])
        matched=pair_sections([b,a]);pairs=matched['pairs']
        self.assertEqual(pairs['section'].tolist(),[1,4])
        self.assertEqual(pairs['v13_1'].tolist(),[90,100])
        self.assertEqual(pairs['v13_2'].tolist(),[95,110])
        self.assertEqual((pairs['election_1'],pairs['election_2']),(6257,6258))
        self.assertEqual([rd['section'][ids].tolist() for _,rd,ids in matched['unmatched']],[[3],[5]])
        self.assertEqual(len(matched['rounds'][0]['candidate_numbers']),13)

    def test_geographic_key_components_prevent_false_section_matches(self):
        a=round_data(1,[100,90],[100,110],sections=[1,1],ufs=['SP','RJ'])
        b=round_data(2,[110,120],[90,80],sections=[1,1],ufs=['RJ','SP'])
        paired=pair_sections([a,b])['pairs']
        self.assertEqual(list(zip(paired['uf'],paired['v13_1'],paired['v13_2'])),
                         [('RJ',90,110),('SP',100,120)])

    def test_ambiguous_keys_missing_round_and_unexpected_finalists_fail(self):
        a=round_data(1,[100,90],[100,110],sections=[1,1])
        b=round_data(2,[100],[100])
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            pair_sections([a,b])
        with self.assertRaisesRegex(ValueError,'exactly one'):
            pair_sections([b])
        with self.assertRaisesRegex(ValueError,'exactly one'):
            pair_sections([b,b,round_data(1,[100],[100])])
        b['candidate_numbers']=[13,14]
        with self.assertRaisesRegex(ValueError,'Finalists'):
            pair_sections([round_data(1,[100],[100]),b])

    def test_exclusions_are_exclusive_and_ratio_boundary_is_exact(self):
        pairs=pairs_from_deltas([0]*10)
        pairs['installed_1'][0]=False;pairs['aptos_1'][0]=1
        pairs['aptos_2'][1]=49;pairs['turnout_1'][2]=0
        pairs['nominal_2'][3]=49;pairs['f_1'][4]=49
        pairs['place_2'][5]=-1;pairs['place_2'][6]=2
        pairs['aptos_2'][7]=501;pairs['aptos_2'][8]=500
        mask,reasons,basic=eligibility(pairs)
        self.assertEqual(reasons.tolist(),['section_status','aptos_below_50','nonpositive_turnout',
            'nominal_below_50','finalists_below_floor','missing_place','changed_place','aptos_ratio',
            'eligible','eligible'])
        self.assertEqual(np.flatnonzero(mask).tolist(),[8,9])
        self.assertEqual(np.flatnonzero(basic).tolist(),list(range(4,10)))
        mask,reasons,_=eligibility(pairs,unchanged_aptos=True)
        self.assertEqual(np.flatnonzero(mask).tolist(),[9])
        self.assertEqual(reasons[8],'changed_aptos')
        pairs['aptos_1'][8]=500;pairs['aptos_2'][8]=400
        self.assertTrue(eligibility(pairs)[0][8])

    def test_conditional_complement_and_minor_candidate_denominator_effect(self):
        a=round_data(1,[100,80],[100,120],other=[100,100])
        b=round_data(2,[100,100],[100,100])
        pairs=pair_sections([a,b])['pairs'];out=changes(pairs,np.arange(2))
        np.testing.assert_allclose(out['delta'],[0,10],atol=1e-14)
        self.assertAlmostEqual(out['dp13'][0],float(Fraction(50,3)),places=12)
        self.assertAlmostEqual(out['dp22'][0],float(Fraction(50,3)),places=12)
        for i in range(2):
            d22=100*(Fraction(int(pairs['v22_2'][i]),int(pairs['f_2'][i]))-
                     Fraction(int(pairs['v22_1'][i]),int(pairs['f_1'][i])))
            self.assertAlmostEqual(float(d22),-out['delta'][i],places=12)
        self.assertNotAlmostEqual(out['dp13'][0],-out['dp22'][0])

    def test_change_cross_products_keep_supported_large_counts_exact(self):
        pairs=pair_sections([
            round_data(1,[500_000_000],[1_500_000_000],aptos=[2_000_000_100]),
            round_data(2,[1_500_000_000],[500_000_000],aptos=[2_000_000_100])])['pairs']
        out=changes(pairs,np.array([0]))
        self.assertEqual(out['numerator'].tolist(),[1])
        self.assertEqual(out['denominator'].tolist(),[2])
        self.assertEqual(out['delta'].tolist(),[50.0])
        pairs['f_1'][0]=3_100_000_000;pairs['f_2'][0]=3_100_000_000
        with self.assertRaisesRegex(ValueError,'overflow'):
            changes(pairs,np.array([0]))

    def test_initial_preference_bins_use_integer_boundaries_and_endpoint(self):
        votes=np.array([0,499,500,999,1000,9999,10000],dtype=np.int64)
        total=np.full(len(votes),10000,dtype=np.int64)
        self.assertEqual(preference_band(votes,total).tolist(),[0,0,1,1,2,19,19])
        self.assertEqual(preference_band(votes,total,40).tolist(),[0,1,2,3,4,39,39])
        with self.assertRaises(ValueError):preference_band(votes,total,0)
        with self.assertRaises(ValueError):preference_band(votes,np.zeros_like(total))


class ScreeningTests(unittest.TestCase):
    def test_leave_one_out_matches_fraction_oracle_for_parities_and_ties(self):
        rng=np.random.default_rng(20261029)
        for n in range(2,22):
            values=rng.integers(-4,5,size=n).tolist()
            expected=[float(fraction_median(values[:i]+values[i+1:])) for i in range(n)]
            np.testing.assert_allclose(median_without_self(values),expected,atol=0,rtol=0)
        self.assertEqual(median_without_self([0,10,100]).tolist(),[55,50,5])
        self.assertEqual(median_without_self([0,0,1,1]).tolist(),[1,1,0,0])
        with self.assertRaises(ValueError):median_without_self([10])

    def test_priority_is_ten_pp_against_other_four_not_own_median(self):
        pairs=pairs_from_deltas([0,0,0,0,10])
        out=screening(pairs,np.arange(5))
        self.assertEqual(out['strict_peer_count'].tolist(),[4]*5)
        self.assertEqual(out['strict_priority'].tolist(),[False]*4+[True])
        self.assertEqual(out['strict_median'].tolist(),[0]*5)
        pairs=pairs_from_deltas([0,0,0,0,9.5])
        self.assertFalse(screening(pairs,np.arange(5))['strict_priority'].any())

    def test_insufficient_peers_are_nan_not_cleared_and_baseline_can_remove_support(self):
        pairs=pairs_from_deltas([0,0,0,10])
        out=screening(pairs,np.arange(4))
        self.assertTrue(np.isnan(out['strict_median']).all())
        self.assertEqual(out['strict_peer_count'].tolist(),[3]*4)
        self.assertFalse(out['strict_priority'].any())
        pairs=pairs_from_deltas([0,0,0,0,10],q1_counts=[100,100,100,100,80])
        out=screening(pairs,np.arange(5))
        self.assertEqual(out['strict_peer_count'][-1],0)
        self.assertTrue(np.isnan(out['strict_contrast'][-1]))
        self.assertTrue(out['broad_priority'][-1])

    def test_exact_fractional_changes_cannot_create_false_group_variation(self):
        a=round_data(1,[30,60,90],[30,60,90],places=[1,1,2])
        b=round_data(2,[40,80,120],[20,40,60],places=[1,1,2])
        prepared=prepare(pair_sections([a,b])['pairs'],'zone_size',min_target=1)
        self.assertEqual(prepared['change']['numerator'].tolist(),[1,1,1])
        self.assertEqual(prepared['change']['denominator'].tolist(),[6,6,6])
        self.assertFalse(prepared['variable'].any())
        self.assertFalse(prepared['potential'].any())
        np.testing.assert_array_equal(prepared['residual'],np.zeros(3))

    def test_legitimate_initial_preference_heterogeneity_is_conditioned_out(self):
        pairs=pairs_from_deltas([10]*3+[-10]*3,places=[1]*3+[2]*3,
                                q1_counts=[40]*3+[160]*3)
        coarse=prepare(pairs,'zone_size',min_target=3)
        adjusted=prepare(pairs,'zone_size_baseline',min_target=3)
        np.testing.assert_allclose(concentration(coarse)[0],[10,10*math.sqrt(3)])
        np.testing.assert_allclose(concentration(adjusted)[0],[0,0])
        self.assertTrue(coarse['potential'].any())
        self.assertFalse(adjusted['potential'].any())
        self.assertEqual(adjusted['group']['sizes'].tolist(),[3,3])


class ConcentrationAndReferenceTests(unittest.TestCase):
    def setUp(self):
        self.pairs=pairs_from_deltas([-10,-10,-10,10,10,10],places=[1,1,1,2,2,2])
        self.prepared=prepare(self.pairs,'zone_size_baseline',min_target=3)

    def test_all_720_assignments_match_independent_rational_squared_oracle(self):
        p=self.prepared;delta=[Fraction(value) for value in [-10,-10,-10,10,10,10]]
        observed=concentration(p)[0]
        values=[]
        for source in permutations(range(6)):
            got=concentration(p,p['residual'][list(source)])[0]
            expected=oracle_concentration(p,delta,source)
            np.testing.assert_allclose(got,expected,atol=1e-12,rtol=1e-14)
            values.append(got)
        values=np.asarray(values)
        self.assertEqual(np.count_nonzero(values[:,0]>=observed[0]-1e-12),72)
        np.testing.assert_allclose(observed,[10,10*math.sqrt(3)])
        self.assertAlmostEqual(np.mean(values[:,0]**2),20.0,places=12)

    def test_assignment_preserves_both_rounds_and_spawn_schedule(self):
        for model,model_id in MODELS.items():
            p=prepare(self.pairs,model,min_target=3)
            captured={rep:assignment(p,20261029,model_id,rep) for rep in [8,0,3,1]}
            for rep,permutation in captured.items():
                np.testing.assert_array_equal(np.sort(permutation),np.arange(6))
                np.testing.assert_array_equal(p['group']['labels'][permutation],p['group']['labels'])
                np.testing.assert_array_equal(assignment(p,20261029,model_id,rep),permutation)
                rng=np.random.default_rng(np.random.SeedSequence([20261029,model_id]).spawn(9)[rep])
                direct=np.arange(6,dtype=np.int32)
                for bucket in p['buckets']:
                    direct[bucket.ravel()]=rng.permuted(bucket,axis=1).ravel()
                np.testing.assert_array_equal(permutation,direct)
                for turn in (1,2):
                    shuffled={name:self.pairs[name][p['ids']][permutation] for name in
                              (f'v13_{turn}',f'v22_{turn}',f'f_{turn}',f'nominal_{turn}',f'turnout_{turn}')}
                    np.testing.assert_array_equal(shuffled[f'v13_{turn}']+shuffled[f'v22_{turn}'],shuffled[f'f_{turn}'])
                    np.testing.assert_array_equal(shuffled[f'nominal_{turn}']+10,shuffled[f'turnout_{turn}'])
                    self.assertEqual(int(shuffled[f'f_{turn}'].sum()),1200)
                self.assertAlmostEqual(float(p['residual'][permutation].sum()),0)
            self.assertGreater(len({tuple(x) for x in captured.values()}),1)

    def test_one_target_and_one_non_target_can_supply_movable_information(self):
        p=prepare(pairs_from_deltas([-10,0,10],places=[1,1,2]),'zone_size',min_target=2)
        self.assertEqual(p['targets'].tolist(),[True,False])
        self.assertTrue(p['potential'].any())
        scores=[concentration(p,p['residual'][list(source)])[0] for source in permutations(range(3))]
        flags,reasons=score_variability(p,np.asarray(scores),concentration(p)[0])
        self.assertTrue(flags.all())
        self.assertEqual(reasons,['sampled_distinct_scores']*2)

    def test_constant_absolute_scores_require_finite_enumeration(self):
        p=prepare(pairs_from_deltas([-5,5],places=[1,2]),'zone_size',min_target=1)
        self.assertTrue(p['potential'].any())
        obs=concentration(p)[0]
        np.testing.assert_allclose(obs,[5,5])
        flags,reasons=score_variability(p,np.array([obs]),obs)
        self.assertFalse(flags.any())
        self.assertEqual(reasons,['exact_enumeration_constant']*2)

    def test_constant_sample_does_not_prove_constancy_of_a_variable_orbit(self):
        obs=concentration(self.prepared)[0]
        flags,reasons=score_variability(self.prepared,np.array([obs,obs]),obs)
        self.assertTrue(flags.all())
        self.assertEqual(reasons,['exact_enumeration_variable']*2)

    def test_unresolved_large_orbit_fails_instead_of_declaring_non_detection(self):
        p=prepare(pairs_from_deltas([-4,-3,-2,-1,0,1,2,3,4],places=[1]*4+[2]*5),
                  'zone_size',min_target=1)
        obs=concentration(p)[0]
        with self.assertRaisesRegex(ArithmeticError,'orbit too large'):
            score_variability(p,np.array([obs]),obs)

    def test_no_targets_or_movable_groups_are_non_applicable(self):
        p=prepare(pairs_from_deltas([-5,0,5],places=[1,2,3]),'zone_size',min_target=2)
        values=concentration(p)[0]
        np.testing.assert_array_equal(values,[0,0])
        self.assertEqual(score_variability(p,np.array([values]),values)[1],['no_targets']*2)
        p=prepare(pairs_from_deltas([-5,0,5],places=[1,1,1]),'zone_size',min_target=2)
        values=concentration(p)[0]
        self.assertEqual(score_variability(p,np.array([values]),values)[1],['no_movable_variable_groups']*2)

    def test_empty_cohort_invalid_models_and_nonfinite_scores_fail(self):
        pairs=pairs_from_deltas([0]);pairs['installed_1'][:]=False
        with self.assertRaisesRegex(ValueError,'Empty'):
            prepare(pairs,'zone_size')
        with self.assertRaises(ValueError):prepare(self.pairs,'unknown')
        with self.assertRaises(ValueError):prepare(self.pairs,'zone_size',min_target=0)
        with self.assertRaises(ValueError):score_variability(self.prepared,np.array([[np.nan,0]]),np.zeros(2))
        with self.assertRaises(ValueError):score_variability(self.prepared,np.zeros((1,2)),np.array([np.inf,0]))

    def test_holm_fixed_family_ties_and_na_placeholder(self):
        np.testing.assert_allclose(holm([1,.2,.0002,.03]),[1,.4,.0008,.09])
        np.testing.assert_allclose(holm([.02,.02,.04,.6]),[.08,.08,.08,.6])
        for invalid in ([np.nan],[np.inf],[-.1],[1.1]):
            with self.assertRaises(ValueError):holm(invalid)


if __name__=='__main__':
    unittest.main()
