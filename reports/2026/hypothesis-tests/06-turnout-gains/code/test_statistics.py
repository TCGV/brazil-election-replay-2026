"""Synthetic controls and finite-reference oracles; no election rows are loaded."""
from fractions import Fraction
from itertools import permutations
import math
import unittest

import numpy as np

from turnout_statistics import (MODELS, assignment, eligibility, holm,
    measures, pair_sections, prepare, proportion_band, rational_average_ranks,
    score, score_variability)


CANDIDATES = {1: [13,14,16,21,22,27,28,29,30,35,55,70,80], 2: [13,22]}


def round_data(turn, v13, v22, *, sections=None, places=None, aptos=None,
               turnout=None, other=None, ufs=None):
    """Original-array-shaped fixture with all presidential vote categories."""
    a13=np.asarray(v13,dtype=np.int64);a22=np.asarray(v22,dtype=np.int64)
    n=len(a13)
    matrix=np.zeros((n,len(CANDIDATES[turn])),dtype=np.int64)
    matrix[:,CANDIDATES[turn].index(13)]=a13
    matrix[:,CANDIDATES[turn].index(22)]=a22
    if other is not None:
        matrix[:,CANDIDATES[turn].index(14)]=other
    nominal=matrix.sum(axis=1)
    a=np.full(n,2000,dtype=np.int64) if aptos is None else np.asarray(aptos,dtype=np.int64)
    t=nominal+100 if turnout is None else np.asarray(turnout,dtype=np.int64)
    if np.any(t<nominal):
        raise ValueError('Fixture turnout must cover nominal votes')
    return dict(turno=turn,election_code=6256+turn,
        uf=np.asarray(ufs if ufs is not None else ['SP']*n,dtype='U2'),
        municipality=np.full(n,71072,dtype=np.int64),zone=np.ones(n,dtype=np.int64),
        section=np.asarray(sections if sections is not None else np.arange(1,n+1),dtype=np.int64),
        place=np.asarray(places if places is not None else np.ones(n),dtype=np.int64),
        source_line=np.arange(2,n+2),aptos=a,turnout=t,abstentions=a-t,
        nominal=nominal,blank=t-nominal,null_votes=np.zeros(n,dtype=np.int64),
        legend=np.zeros(n,dtype=np.int64),separate=np.zeros(n,dtype=np.int64),
        installed=np.ones(n,dtype=bool),cancelled=np.zeros(n,dtype=bool),
        candidate_numbers=list(CANDIDATES[turn]),candidate_votes=matrix)


def pairs_xy(x,y,*,places=None,ufs=None):
    """Identical baseline, fixed F1=F2=1000; x/y expressed in pp."""
    n=len(x)
    if len(y)!=n:
        raise ValueError('Fixture lengths differ')
    v2=500+np.rint(np.asarray(y)*10).astype(np.int64)
    a=round_data(1,[500]*n,[500]*n,other=[100]*n,
                 turnout=[1200]*n,places=places,ufs=ufs)
    b=round_data(2,v2,1000-v2,turnout=1200+np.rint(np.asarray(x)*20).astype(np.int64),
                 places=places,ufs=ufs)
    return pair_sections([a,b])['pairs']


def rational_residuals(values,labels):
    out=[]
    for i in range(len(values)):
        group=[values[j] for j in range(len(values)) if labels[j]==labels[i]]
        out.append(values[i]-sum(group,Fraction())/len(group))
    return out


def rational_ranks(values,labels):
    out=[]
    for i,value in enumerate(values):
        group=[values[j] for j in range(len(values)) if labels[j]==labels[i]]
        less=sum(other<value for other in group)
        equal=sum(other==value for other in group)
        out.append(Fraction(2*less+equal+1,2))
    return rational_residuals(out,labels)


def oracle_correlation(x,y,source):
    cross=sum((left*y[source[i]] for i,left in enumerate(x)),Fraction())
    sx=sum((value*value for value in x),Fraction())
    sy=sum((value*value for value in y),Fraction())
    return float(cross)/math.sqrt(float(sx*sy)) if sx and sy else 0.0


class PairingAndCohortTests(unittest.TestCase):
    def test_physical_pairing_ignores_election_code_and_input_order(self):
        a=round_data(1,[500,510,520],[500,490,480],sections=[3,1,4])
        b=round_data(2,[530,540,550],[470,460,450],sections=[4,1,5])
        matched=pair_sections([b,a]);p=matched['pairs']
        self.assertEqual(p['section'].tolist(),[1,4])
        self.assertEqual(p['v13_1'].tolist(),[510,520])
        self.assertEqual(p['v13_2'].tolist(),[540,530])
        self.assertEqual((p['election_1'],p['election_2']),(6257,6258))
        self.assertEqual([rd['section'][ids].tolist() for _,rd,ids in matched['unmatched']],[[3],[5]])
        self.assertEqual(p['blank_1'].tolist(),[100,100])
        for category in ('null_votes','legend','separate'):
            np.testing.assert_array_equal(p[f'{category}_1'],[0,0])

    def test_geographic_components_avoid_false_section_matches(self):
        a=round_data(1,[500,510],[500,490],sections=[1,1],ufs=['SP','RJ'])
        b=round_data(2,[520,530],[480,470],sections=[1,1],ufs=['RJ','SP'])
        p=pair_sections([a,b])['pairs']
        self.assertEqual(list(zip(p['uf'],p['v13_1'],p['v13_2'])),
                         [('RJ',510,520),('SP',500,530)])

    def test_ambiguity_and_missing_or_duplicate_rounds_are_rejected(self):
        a=round_data(1,[500,500],[500,500],sections=[1,1])
        b=round_data(2,[500],[500])
        with self.assertRaises(ValueError):pair_sections([a,b])
        with self.assertRaises(ValueError):pair_sections([b])
        with self.assertRaises(ValueError):pair_sections([round_data(1,[500],[500]),b,b])
        b['candidate_numbers']=[13,14]
        with self.assertRaises(ValueError):pair_sections([round_data(1,[500],[500]),b])

    def test_exclusions_are_exclusive_and_ratio_boundary_is_inclusive(self):
        p=pairs_xy([0]*11,[0]*11)
        p['installed_1'][0]=False;p['aptos_1'][0]=1
        p['aptos_2'][1]=49;p['turnout_1'][2]=0
        p['nominal_2'][3]=49;p['f_1'][4]=49
        p['place_2'][5]=-1;p['place_2'][6]=2
        p['aptos_2'][7]=2501;p['aptos_2'][8]=2500
        p['abstentions_2'][8]=p['aptos_2'][8]-p['turnout_2'][8]
        p['uf'][10]='ZZ'
        mask,reasons,basic=eligibility(p)
        self.assertEqual(reasons[:9].tolist(),['section_status','aptos_below_50',
            'nonpositive_turnout','nominal_below_50','finalists_below_floor',
            'missing_place','changed_place','aptos_ratio','eligible'])
        self.assertEqual(np.flatnonzero(mask).tolist(),[8,9,10])
        self.assertEqual(np.flatnonzero(basic).tolist(),list(range(4,11)))
        mask,reasons,_=eligibility(p,unchanged_aptos=True,domestic_only=True)
        self.assertEqual(np.flatnonzero(mask).tolist(),[9])
        self.assertEqual(reasons[8],'changed_aptos')
        self.assertNotEqual(reasons[10],'eligible')

    def test_accounting_identity_failure_in_cohort_interrupts(self):
        p=pairs_xy([-1,1],[-1,1]);p['abstentions_2'][0]+=1
        with self.assertRaises((ValueError,ArithmeticError)):
            prepare(p,'zone_baseline')
        p['installed_1'][0]=False
        # Invalid excluded rows must not silently become eligible or affect support.
        got=prepare(p,'zone_baseline')
        self.assertEqual(got['ids'].tolist(),[1])

    def test_optional_filters_change_cohort_without_inventing_pairs(self):
        p=pairs_xy([-1,0,1],[-1,0,1],ufs=['SP','ZZ','SP'])
        p['aptos_2'][0]=2001;p['abstentions_2'][0]+=1
        self.assertEqual(prepare(p,'zone_baseline',unchanged_aptos=True)['ids'].tolist(),[1,2])
        self.assertEqual(prepare(p,'zone_baseline',domestic_only=True)['ids'].tolist(),[0,1])
        p['f_1'][2]=99
        self.assertNotIn(2,prepare(p,'zone_baseline',finalist_floor=100)['ids'])


class MeasuresAndDecompositionTests(unittest.TestCase):
    def test_symmetric_components_match_independent_fraction_identity(self):
        a=round_data(1,[300,500],[400,300],other=[100,100],
                     turnout=[1000,1200],aptos=[2000,2000])
        b=round_data(2,[500,600],[400,400],turnout=[1300,1400],aptos=[2000,2400])
        p=pair_sections([a,b])['pairs'];m=measures(p,np.arange(2))
        for candidate in (13,22):
            for i in range(2):
                a1,a2=(int(p[f'aptos_{turn}'][i]) for turn in (1,2))
                t1,t2=(int(p[f'turnout_{turn}'][i]) for turn in (1,2))
                v1,v2=(int(p[f'v{candidate}_{turn}'][i]) for turn in (1,2))
                t_first,t_second=Fraction(t1,a1),Fraction(t2,a2)
                s_first,s_second=Fraction(v1,t1),Fraction(v2,t2)
                gain=100*(Fraction(v2,a2)-Fraction(v1,a1))
                turnout=100*(s_first+s_second)/2*(t_second-t_first)
                composition=100*(t_first+t_second)/2*(s_second-s_first)
                self.assertEqual(gain,turnout+composition)
                for key,wanted in ((f'gain{candidate}_aptos_pp',gain),
                        (f'turnout{candidate}_component_pp',turnout),
                        (f'composition{candidate}_component_pp',composition),
                        (f'gain{candidate}_equiv_votes',gain*a1/100),
                        (f'turnout{candidate}_equiv_votes',turnout*a1/100),
                        (f'composition{candidate}_equiv_votes',composition*a1/100)):
                    self.assertAlmostEqual(float(m[key][i]),float(wanted),places=11)
                self.assertEqual(m[f'gain{candidate}_count'][i],v2-v1)
                if a1==a2:
                    self.assertAlmostEqual(m[f'gain{candidate}_equiv_votes'][i],v2-v1,places=11)
                else:
                    self.assertNotAlmostEqual(m[f'gain{candidate}_equiv_votes'][i],v2-v1)

    def test_symmetric_decomposition_reverses_sign_if_rounds_are_reversed(self):
        p=pairs_xy([-3,4],[-2,5]);forward=measures(p,np.arange(2))
        reverse=dict(p)
        for key,value in p.items():
            if key.endswith('_1') and key[:-2]+'_2' in p:
                reverse[key]=p[key[:-2]+'_2']
                reverse[key[:-2]+'_2']=value
        backward=measures(reverse,np.arange(2))
        for candidate in (13,22):
            for key in (f'gain{candidate}_aptos_pp',f'turnout{candidate}_component_pp',
                        f'composition{candidate}_component_pp'):
                np.testing.assert_allclose(backward[key],-forward[key],atol=1e-12,rtol=0)

    def test_count_identity_includes_other_nominal_and_all_special_categories(self):
        a=round_data(1,[400],[400],other=[300],turnout=[1200])
        b=round_data(2,[700],[500],turnout=[1300])
        a['null_votes'][0]=7;a['separate'][0]=2;a['blank'][0]-=9
        b['null_votes'][0]=11;b['separate'][0]=3;b['blank'][0]-=14
        p=pair_sections([a,b])['pairs'];m=measures(p,np.array([0]))
        residual=[]
        for turn in (1,2):
            residual.append(int(p[f'nominal_{turn}'][0]-p[f'f_{turn}'][0])+
                sum(int(p[f'{field}_{turn}'][0]) for field in ('blank','null_votes','legend','separate')))
        self.assertEqual(int(m['gain13_count'][0]+m['gain22_count'][0]),
                         int(p['turnout_2'][0]-p['turnout_1'][0])-(residual[1]-residual[0]))

    def test_rate_changes_use_each_round_denominator(self):
        a=round_data(1,[500],[500],aptos=[2000],turnout=[1200])
        b=round_data(2,[600],[400],aptos=[2400],turnout=[1440])
        p=pair_sections([a,b])['pairs'];m=measures(p,np.array([0]))
        self.assertAlmostEqual(float(m['x'][0]),0,places=14)
        self.assertAlmostEqual(float(m['y'][0]),10,places=13)
        self.assertEqual(int(p['turnout_2'][0]-p['turnout_1'][0]),240)
        self.assertEqual(int(p['abstentions_2'][0]-p['abstentions_1'][0]),160)

    def test_elimination_of_other_candidates_can_increase_both_without_preference_change(self):
        a=round_data(1,[400],[400],other=[400],turnout=[1200])
        b=round_data(2,[600],[600],turnout=[1200])
        p=pair_sections([a,b])['pairs'];m=measures(p,np.array([0]))
        self.assertAlmostEqual(m['x'][0],0)
        self.assertAlmostEqual(m['y'][0],0)
        self.assertEqual(int(p['v13_2'][0]-p['v13_1'][0]),200)
        self.assertEqual(int(p['v22_2'][0]-p['v22_1'][0]),200)

    def test_turnout_can_raise_both_candidate_counts_without_informative_preference_change(self):
        a=round_data(1,[500,500],[500,500],turnout=[1200,1200])
        b=round_data(2,[550,600],[550,600],turnout=[1300,1400])
        p=pair_sections([a,b])['pairs'];m=measures(p,np.arange(2))
        np.testing.assert_allclose(m['x'],[5,10])
        np.testing.assert_array_equal(m['y'],[0,0])
        self.assertFalse(prepare(p,'zone_baseline')['support'].any())

    def test_complementary_finalist_change_is_not_full_nominal_share_change(self):
        a=round_data(1,[400,500],[400,500],other=[400,100])
        b=round_data(2,[600,600],[600,400])
        p=pair_sections([a,b])['pairs'];m=measures(p,np.arange(2))
        for i in range(2):
            d22=100*(Fraction(int(p['v22_2'][i]),int(p['f_2'][i]))-
                     Fraction(int(p['v22_1'][i]),int(p['f_1'][i])))
            self.assertAlmostEqual(float(d22),-float(m['y'][i]),places=12)
        self.assertAlmostEqual(m['y'][0],0)
        self.assertGreater(100*(p['v13_2'][0]/p['nominal_2'][0]-p['v13_1'][0]/p['nominal_1'][0]),0)

    def test_proportion_bands_use_exact_integer_boundaries(self):
        values=np.array([0,499,500,999,1000,9999,10000],dtype=np.int64)
        totals=np.full(len(values),10000,dtype=np.int64)
        self.assertEqual(proportion_band(values,totals).tolist(),[0,0,1,1,2,19,19])
        self.assertEqual(proportion_band(values,totals,40).tolist(),[0,1,2,3,4,39,39])
        with self.assertRaises(ValueError):proportion_band(values,totals,0)
        with self.assertRaises(ValueError):proportion_band(values,np.zeros_like(totals))

    def test_average_rank_helper_treats_equivalent_fractions_as_ties(self):
        numerator=np.array([2,1,3,-1,0],dtype=np.int64)
        denominator=np.array([6,3,6,2,3],dtype=np.int64)
        np.testing.assert_array_equal(rational_average_ranks(numerator,denominator),[3.5,3.5,5,1,2])
        with self.assertRaises(ValueError):rational_average_ranks(numerator,np.zeros_like(denominator))


class AssociationReferenceTests(unittest.TestCase):
    def test_each_initial_rate_control_can_separate_otherwise_same_geography(self):
        for control in ('turnout','preference','other'):
            with self.subTest(control=control):
                p=pairs_xy([-5,-3,-1,1,3,5],[-1,2,-3,4,-5,0])
                if control=='turnout':
                    p['turnout_1'][3:]=1300
                    p['abstentions_1'][3:]=700
                    p['blank_1'][3:]=200
                elif control=='preference':
                    p['v13_1'][3:]=550;p['v22_1'][3:]=450
                else:
                    p['nominal_1'][3:]=1200;p['blank_1'][3:]=0
                prepared=prepare(p,'zone_baseline')
                self.assertEqual(prepared['group']['sizes'].tolist(),[3,3])
                expected={'turnout':'initial_turnout_band',
                          'preference':'initial_preference_band',
                          'other':'initial_other_band'}[control]
                self.assertNotEqual(prepared[expected][0],prepared[expected][-1])

    def test_second_share_sensitivity_changes_outcome_but_keeps_initial_controls(self):
        p=pairs_xy([-3,-1,1,3],[0,1,2,3])
        p['v13_1']=np.array([501,510,520,540]);p['v22_1']=1000-p['v13_1']
        change=prepare(p,'zone_baseline')
        second=prepare(p,'zone_baseline',outcome='second_share')
        np.testing.assert_array_equal(change['group']['labels'],second['group']['labels'])
        np.testing.assert_allclose(second['measures']['y'],[50,51,52,53])
        np.testing.assert_allclose(second['measures']['delta_q'],[-.1,0,0,-1],atol=1e-14)
        self.assertAlmostEqual(score(second)[0],1,places=13)
        self.assertLess(score(change)[0],0)

    def test_positive_and_negative_linear_and_rank_association(self):
        x=[-5,-3,-1,1,3,5]
        for sign in (-1,1):
            p=prepare(pairs_xy(x,[sign*v for v in x]),'zone_baseline')
            np.testing.assert_allclose(score(p),[sign,sign],atol=1e-14)
            self.assertAlmostEqual(p['beta'],sign,places=13)
            self.assertTrue(p['support'].all())

    def test_all_720_assignments_match_independent_fraction_oracle(self):
        x=[-5,-3,-1,1,3,5];y=[-1,2,-3,4,-5,0]
        p=prepare(pairs_xy(x,y),'zone_baseline')
        labels=p['group']['labels']
        fx=[Fraction(v) for v in x];fy=[Fraction(v) for v in y]
        rx=rational_residuals(fx,labels);ry=rational_residuals(fy,labels)
        rank_x=rational_ranks(fx,labels);rank_y=rational_ranks(fy,labels)
        scores=[]
        for source in permutations(range(6)):
            expected=[oracle_correlation(rx,ry,source),oracle_correlation(rank_x,rank_y,source)]
            actual=score(p,np.asarray(source,dtype=np.int32))
            np.testing.assert_allclose(actual,expected,atol=1e-14,rtol=0)
            scores.append(np.abs(actual))
        flags,reasons=score_variability(p,np.asarray(scores),np.abs(score(p)))
        self.assertTrue(flags.all())

    def test_within_stratum_centering_excludes_between_locality_association(self):
        p=pairs_xy([-3,-2,-1,1,2,3],[-3,-3,-3,3,3,3],places=[1,1,1,2,2,2])
        zone=prepare(p,'zone_baseline');place=prepare(p,'place_baseline')
        self.assertGreater(score(zone)[0],.9)
        self.assertFalse(place['support'].any())
        np.testing.assert_array_equal(score(place),[0,0])

    def test_rational_ties_have_identical_centered_midrank(self):
        p=pairs_xy([0,0,0,0],[0,0,0,0])
        p['aptos_2']=np.array([1600,2000,2000,2400])
        p['turnout_2']=np.array([1120,1400,1600,1920])
        p['abstentions_2']=p['aptos_2']-p['turnout_2']
        p['v13_2']=np.array([600,800,750,900])
        p['v22_2']=np.array([300,400,250,300])
        p['f_2']=p['v13_2']+p['v22_2'];p['nominal_2']=p['f_2'].copy()
        p['blank_2']=p['turnout_2']-p['nominal_2']
        prepared=prepare(p,'zone_baseline')
        np.testing.assert_array_equal(prepared['rank_x'],[-1,-1,1,1])
        np.testing.assert_array_equal(prepared['rank_y'],[-1,-1,1,1])
        np.testing.assert_allclose(score(prepared),[1,1],atol=1e-14)

    def test_constant_rational_change_cannot_create_fake_support(self):
        p=pairs_xy([0,0,0],[0,0,0])
        p['aptos_2']=np.array([1600,2000,2400])
        p['turnout_2']=np.array([1120,1400,1680])
        p['abstentions_2']=p['aptos_2']-p['turnout_2']
        p['blank_2']=p['turnout_2']-p['nominal_2']
        p['v13_2']=np.array([600,700,800]);p['v22_2']=1000-p['v13_2']
        prepared=prepare(p,'zone_baseline')
        self.assertFalse(prepared['support'].any())

    def test_permutation_preserves_stratum_and_internal_trajectory_pairing(self):
        p=pairs_xy([-5,-3,-1,1,3,5],[-1,2,-3,4,-5,0],places=[1,1,1,2,2,2])
        prepared=prepare(p,'place_baseline')
        labels=prepared['group']['labels']
        for repetition in range(8):
            got=assignment(prepared,20261029,1,repetition)
            self.assertEqual(sorted(got.tolist()),list(range(6)))
            np.testing.assert_array_equal(labels[got],labels)
            # One assignment is applied to y and its within-stratum ranks.
            expected=np.array([
                np.dot(prepared['rx'],prepared['ry'][got])/
                    math.sqrt(np.dot(prepared['rx'],prepared['rx'])*np.dot(prepared['ry'],prepared['ry'])),
                np.dot(prepared['rank_x'],prepared['rank_y'][got])/
                    math.sqrt(np.dot(prepared['rank_x'],prepared['rank_x'])*np.dot(prepared['rank_y'],prepared['rank_y']))])
            np.testing.assert_allclose(score(prepared,got),expected,atol=1e-14)
            np.testing.assert_array_equal(got,assignment(prepared,20261029,1,repetition))

    def test_seed_schedule_and_bucket_order_match_explicit_assignment(self):
        p=pairs_xy([-5,-3,-1,1,3,5],[-1,2,-3,4,-5,0],places=[1,1,2,2,2,3])
        prepared=prepare(p,'place_baseline')
        rng=np.random.default_rng(np.random.SeedSequence([20261029,6,1],spawn_key=(4,)))
        expected=np.arange(6,dtype=np.int32)
        for bucket in prepared['buckets']:
            expected[bucket.ravel()]=rng.permuted(bucket,axis=1).ravel()
        np.testing.assert_array_equal(assignment(prepared,20261029,1,4),expected)
        self.assertEqual([bucket.shape[1] for bucket in prepared['buckets']],[2,3])
        self.assertEqual(expected[-1],5)  # Unsupported singleton remains fixed.

    def test_two_member_signed_variation_has_constant_absolute_score(self):
        prepared=prepare(pairs_xy([-1,1],[-1,1]),'zone_baseline')
        signed=np.array([score(prepared,np.array([0,1])),score(prepared,np.array([1,0]))])
        np.testing.assert_allclose(signed,[[1,1],[-1,-1]],atol=1e-14)
        flags,reasons=score_variability(prepared,np.abs(signed),np.abs(score(prepared)))
        self.assertFalse(flags.any())
        self.assertTrue(all('constant' in reason for reason in reasons))

    def test_exact_fallback_detects_variability_below_float_tolerance(self):
        p=pairs_xy([1,2,1,2],[1,2,1,2])
        # The last two turnout-rate changes differ by roughly 1e-14 pp.
        # Their exact covariance contribution still varies when interchanged.
        p['aptos_1'][2:]=100000000
        p['turnout_1'][2:]=50000000
        p['abstentions_1'][2:]=50000000
        p['blank_1'][2:]=p['turnout_1'][2:]-p['nominal_1'][2:]
        p['aptos_2'][2:]=[100000001,100000003]
        p['turnout_2'][2:]=[50000001,50000002]
        p['abstentions_2'][2:]=p['aptos_2'][2:]-p['turnout_2'][2:]
        p['blank_2'][2:]=p['turnout_2'][2:]-p['nominal_2'][2:]
        prepared=prepare(p,'zone_baseline')
        observed=np.abs(score(prepared))
        swapped=np.abs(score(prepared,np.array([0,1,3,2],dtype=np.int32)))
        self.assertLess(abs(observed[0]-swapped[0]),1e-12)
        flags,reasons=score_variability(prepared,observed[None,:],observed)
        self.assertTrue(flags.all())
        self.assertEqual(reasons,['exact_enumeration_variable']*2)

    def test_no_support_is_not_applicable_and_large_unresolved_orbit_raises(self):
        empty=prepare(pairs_xy([-1,1],[0,0]),'zone_baseline')
        flags,reasons=score_variability(empty,np.zeros((2,2)),np.zeros(2))
        self.assertFalse(flags.any())
        self.assertTrue(all(reasons))
        prepared=prepare(pairs_xy([-4,-3,-2,-1,0,1,2,3,4],[-4,-3,-2,-1,0,1,2,3,4]),'zone_baseline')
        observed=np.abs(score(prepared))
        with self.assertRaises(ArithmeticError):
            score_variability(prepared,np.tile(observed,(2,1)),observed,max_exact=40320)

    def test_holm_is_familywise_monotone_and_validates_input(self):
        np.testing.assert_allclose(holm([.01,.04,.03,.9]),[.04,.09,.09,.9])
        np.testing.assert_allclose(holm([.0002]*4),[.0008]*4)
        for invalid in ([float('nan')],[-.1],[1.1]):
            with self.assertRaises(ValueError):holm(invalid)

    def test_invalid_model_and_outcome_fail_explicitly(self):
        p=pairs_xy([-1,1],[-1,1])
        with self.assertRaises(ValueError):prepare(p,'unknown')
        with self.assertRaises(ValueError):prepare(p,'zone_baseline',outcome='unknown')
        self.assertEqual(MODELS,{'zone_baseline':0,'place_baseline':1})


if __name__=='__main__':
    unittest.main()
