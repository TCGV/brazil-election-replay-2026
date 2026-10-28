"""Synthetic H2 controls: detection, legitimate heterogeneity, and reference integrity.

These fixtures are not observations from the election. No source CSV is read or
changed. Run with unittest discovery in this hypothesis's code directory.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np


SPEC = importlib.util.spec_from_file_location('h2_primary_analysis', Path(__file__).with_name('run_analysis.py'))
ANALYSIS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYSIS)


def fixture(n=40):
    """Two-candidate sections with complete, internally consistent quantities."""
    return dict(
        election_code=6257, turno=1, candidate_numbers=np.array([13, 22], dtype=np.int32),
        uf=np.full(n, 'SP', dtype='U2'), municipality=np.full(n, 71072, dtype=np.int32),
        zone=np.ones(n, dtype=np.int32), section=np.arange(1, n+1, dtype=np.int32),
        place=np.ones(n, dtype=np.int32), source_line=np.arange(2, n+2, dtype=np.int32),
        aptos=np.full(n, 200, dtype=np.int32), turnout=np.full(n, 140, dtype=np.int32),
        abstentions=np.full(n, 60, dtype=np.int32), nominal=np.full(n, 140, dtype=np.int32),
        blank=np.zeros(n, dtype=np.int32), null_votes=np.zeros(n, dtype=np.int32),
        legend=np.zeros(n, dtype=np.int32), separate=np.zeros(n, dtype=np.int32),
        candidate_votes=np.tile(np.array([70, 70], dtype=np.int32), (n, 1)),
        installed=np.ones(n, dtype=bool), cancelled=np.zeros(n, dtype=bool),
    )


def set_counts(data, index, aptos=200, turnout=140, nominal=None, candidate13=None,
               blank=0, null_votes=0):
    nominal = turnout-blank-null_votes if nominal is None else nominal
    candidate13 = nominal//2 if candidate13 is None else candidate13
    data['aptos'][index] = aptos
    data['turnout'][index] = turnout
    data['abstentions'][index] = aptos-turnout
    data['nominal'][index] = nominal
    data['blank'][index] = blank
    data['null_votes'][index] = null_votes
    data['candidate_votes'][index] = [candidate13, nominal-candidate13]


def candidate(screen, number=13):
    return next(result for result in screen['candidates'] if result['candidate']==number)


class ScreeningControls(unittest.TestCase):
    def screen(self, data, config=None, detailed=True):
        return ANALYSIS.screening(data, config or dict(ANALYSIS.BASE), detailed=detailed)

    def test_inclusive_ties_are_never_broken_by_section_order(self):
        values=np.r_[np.zeros(38), np.ones(2)]
        upper=ANALYSIS.upper_counts(values)
        np.testing.assert_array_equal(upper[-2:], [2,2])
        np.testing.assert_array_equal(upper[:-2], np.full(38,40))
        self.assertEqual(int((upper*20<=40).sum()),2)
        # Three tied maxima would overfill the 5% tail: reject all three.
        values=np.r_[np.zeros(37), np.ones(3)]
        self.assertFalse((ANALYSIS.upper_counts(values)*20<=40).any())
        self.assertFalse((ANALYSIS.upper_counts(np.zeros(40))*20<=40).any())
        # Reordering rows changes no section's rank or tail membership.
        order=np.random.default_rng(812).permutation(40)
        np.testing.assert_array_equal(ANALYSIS.upper_counts(values[order]),
                                      ANALYSIS.upper_counts(values)[order])

    def test_zero_candidate_and_unanimous_other_candidate_have_no_tails(self):
        data=fixture()
        data['turnout'][:]=np.arange(121,161)
        data['nominal'][:]=data['turnout']
        data['abstentions'][:]=data['aptos']-data['turnout']
        data['candidate_votes'][:,0]=0
        data['candidate_votes'][:,1]=data['nominal']
        screen=self.screen(data)
        for result in screen['candidates']:
            self.assertEqual(result['joint_count'],0)
            self.assertEqual(result['expected_joint'],0)
            self.assertEqual(result['variance'],0)
            self.assertEqual(result['strata'][0]['candidate_tail_count'],0)
        with tempfile.TemporaryDirectory() as temporary:
            tests,_=ANALYSIS.association([(data,screen)],Path(temporary),simulations=99,workers=1)
        self.assertTrue(all(row['status']=='not_applicable' and row['p_raw']=='' for row in tests))

    def test_insufficient_peers_are_unsupported_not_negative_evidence(self):
        data=fixture(29)
        primary=self.screen(data)
        coverage=next(row for row in primary['coverage'] if row['uf']=='BR')
        self.assertEqual((coverage['eligible'],coverage['covered'],coverage['no_peer_support']),(29,0,29))
        self.assertEqual(candidate(primary)['strata'],[])
        relaxed=self.screen(data,dict(ANALYSIS.BASE,min_sections=20))
        self.assertEqual(int(relaxed['covered_mask'].sum()),29)
        self.assertEqual(len(candidate(relaxed)['strata']),1)
        data30=fixture(30)
        self.assertEqual(int(self.screen(data30)['covered_mask'].sum()),30)
        with tempfile.TemporaryDirectory() as temporary:
            tests,_=ANALYSIS.association([(data,primary)],Path(temporary),simulations=49,workers=1)
        self.assertTrue(all(row['status']=='not_applicable' for row in tests))

    def test_exclusions_are_exclusive_and_follow_the_declared_order(self):
        data=fixture(7)
        data['installed'][0]=False
        data['cancelled'][1]=True
        data['aptos'][:3]=0
        data['aptos'][2]=49
        data['turnout'][:4]=0
        data['nominal'][:5]=0
        eligible,reasons=ANALYSIS.eligibility(data)
        np.testing.assert_array_equal(reasons,[1,1,2,3,4,0,0])
        np.testing.assert_array_equal(eligible,[False]*5+[True,True])
        # Raising the nominal floor changes its own exclusion only.
        data['nominal'][5]=99
        _,higher=ANALYSIS.eligibility(data,100)
        np.testing.assert_array_equal(higher,[1,1,2,3,4,4,0])

    def test_priority_includes_exact_five_and_ten_point_boundaries(self):
        for turnout,votes,expected in [(150,90,1),(149,89,0),(150,89,0)]:
            with self.subTest(turnout=turnout,votes=votes):
                data=fixture()
                set_counts(data,0,turnout=turnout,candidate13=votes)
                result=candidate(self.screen(data))
                self.assertEqual(result['joint_count'],1)
                self.assertEqual(result['priority_count'],expected)
                if expected:
                    case=result['cases'][0]
                    self.assertAlmostEqual(case['turnout_delta_pp'],5)
                    self.assertAlmostEqual(case['share_delta_pp'],10)
                    # .6-.5 is slightly below .1 in binary floating point.
                    self.assertLess(float(data['candidate_votes'][0,0])/data['nominal'][0]-.5,.1)

    def test_local_context_excludes_target_and_respects_size_and_eligibility(self):
        data=fixture()
        set_counts(data,0,turnout=150,candidate13=90)
        data['place'][:]=2
        data['place'][:8]=1
        # Exactly four eligible size-comparable peers; endpoints are included.
        for i,a in [(1,160),(2,250),(3,200),(4,200),(5,159),(6,251),(7,200)]:
            set_counts(data,i,aptos=a,turnout=round(.7*a))
        data['cancelled'][7]=True
        screen=self.screen(data)
        ANALYSIS.local_context(data,screen)
        case=next(row for row in candidate(screen)['cases'] if row['_index']==0)
        self.assertEqual(case['local_peer_count'],4)
        self.assertEqual(case['local_status'],'persists_both')
        self.assertAlmostEqual(case['local_median_turnout'],.7)
        # Losing one peer must say insufficient, not attenuated or cleared.
        data['cancelled'][4]=True
        screen=self.screen(data)
        ANALYSIS.local_context(data,screen)
        case=next(row for row in candidate(screen)['cases'] if row['_index']==0)
        self.assertEqual(case['local_peer_count'],3)
        self.assertEqual(case['local_status'],'insufficient_peers')
        self.assertEqual(case['local_median_share'],'')

    def test_unknown_place_never_becomes_a_shared_local_context(self):
        data=fixture()
        data['place'][:]=-1
        set_counts(data,0,turnout=150,candidate13=90)
        screen=self.screen(data)
        ANALYSIS.local_context(data,screen)
        case=candidate(screen)['cases'][0]
        self.assertEqual(case['local_peer_count'],0)
        self.assertEqual(case['local_status'],'insufficient_peers')

    def test_coherent_added_votes_positive_control_is_detected(self):
        data=fixture()
        data['nominal'][:]=130
        data['blank'][:]=5
        data['null_votes'][:]=5
        data['candidate_votes'][:]=[65,65]
        self.assertEqual(candidate(self.screen(data))['joint_count'],0)
        injected=copy.deepcopy(data)
        injected['turnout'][0]+=40
        injected['abstentions'][0]-=40
        injected['nominal'][0]+=40
        injected['candidate_votes'][0,0]+=40
        np.testing.assert_array_equal(injected['aptos'],injected['turnout']+injected['abstentions'])
        np.testing.assert_array_equal(injected['nominal'],injected['candidate_votes'].sum(axis=1))
        np.testing.assert_array_equal(injected['turnout'],injected['nominal']+injected['blank']+injected['null_votes'])
        result=candidate(self.screen(injected))
        self.assertEqual(result['joint_count'],1)
        self.assertEqual(result['priority_count'],1)
        self.assertEqual(result['cases'][0]['section'],1)
        # The test must not mutate either input payload.
        self.assertEqual(data['turnout'][0],140)
        self.assertEqual(injected['turnout'][0],180)

    def test_legitimate_geographic_mixture_can_create_a_large_association(self):
        # Two synthetic communities differ legitimately; no alteration is inserted.
        data=fixture(800)
        for i in range(800):
            set_counts(data,i,turnout=160 if i<40 else 140,candidate13=112 if i<40 else 56)
        data['place'][:40]=1
        data['place'][40:]=2
        mixed=self.screen(data)
        result=candidate(mixed)
        self.assertEqual(result['joint_count'],40)
        self.assertEqual(result['expected_joint'],2)
        self.assertEqual(result['priority_count'],40)
        ANALYSIS.local_context(data,mixed)
        self.assertTrue(all(case['local_status']=='attenuated_one_or_both' for case in result['cases']))
        # Once comparison strata separate those communities, each is homogeneous.
        narrower=copy.deepcopy(data)
        narrower['zone'][40:]=2
        separate=self.screen(narrower)
        self.assertEqual(int(separate['covered_mask'].sum()),800)
        self.assertEqual(candidate(separate)['joint_count'],0)

    def test_holm_known_vector_and_monotonicity(self):
        np.testing.assert_allclose(ANALYSIS.holm([.01,.04,.03,.002]),[.03,.06,.06,.008],rtol=0,atol=1e-15)
        self.assertEqual(ANALYSIS.holm([1.0,.5]),[1.0,1.0])


class HypergeometricReferenceControls(unittest.TestCase):
    def task(self,cache):
        return dict(n=[40],a=[2],b=[2],observed=1,turno=1,candidate=13,
                    seed=20261028,simulations=4999,code_sha256=ANALYSIS.sha256(ANALYSIS.__file__),
                    numpy=np.__version__,cache=str(cache))

    def test_reference_matches_exact_small_distribution_and_plus_one_p(self):
        with tempfile.TemporaryDirectory() as temporary:
            task=self.task(Path(temporary)/'reference.npy')
            result=ANALYSIS._simulate_task(task)
            counts=np.load(task['cache'],allow_pickle=False)
            self.assertTrue(set(counts).issubset({0,1,2}))
            # Exact Hypergeom(N=40,K=2,draws=2), computed combinatorially.
            exact=[math.comb(2,k)*math.comb(38,2-k)/math.comb(40,2) for k in range(3)]
            frequencies=[float(np.mean(counts==k)) for k in range(3)]
            np.testing.assert_allclose(frequencies,exact,rtol=0,atol=.02)
            self.assertAlmostEqual(float(counts.mean()),.1,delta=.02)
            self.assertEqual(result['exceedances'],int(np.count_nonzero(counts>=1)))
            # The public association function must use the +1 convention.
            data=fixture()
            data['candidate_numbers']=np.array([13],dtype=np.int32)
            screen=dict(candidates=[dict(candidate=13,strata=[dict(n=40,turnout_tail_count=2,candidate_tail_count=2)],
                                         joint_count=1,expected_joint=.1,variance=2*2*38*38/(40*40*39),priority_count=0)])
            tests,_=ANALYSIS.association([(data,screen)],Path(temporary)/'public',simulations=4999,workers=1)
            row=tests[0]
            self.assertEqual(row['p_raw'],(row['exceedances']+1)/5000)
            self.assertGreater(row['p_raw'],0)

    def test_cache_is_reproducible_immutable_and_rejects_changed_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache=Path(temporary)/'reference.npy'
            task=self.task(cache)
            first=ANALYSIS._simulate_task(task)
            before=(cache.read_bytes(),cache.with_suffix('.json').read_bytes(),cache.stat().st_mtime_ns)
            self.assertEqual(first,ANALYSIS._simulate_task(task))
            self.assertEqual(before,(cache.read_bytes(),cache.with_suffix('.json').read_bytes(),cache.stat().st_mtime_ns))
            replica=dict(task,cache=str(Path(temporary)/'replica.npy'))
            ANALYSIS._simulate_task(replica)
            self.assertEqual(cache.read_bytes(),Path(replica['cache']).read_bytes())
            for changed in [dict(task,seed=1),dict(task,observed=2),dict(task,n=[41])]:
                with self.subTest(changed=changed),self.assertRaisesRegex(ValueError,'fingerprint mismatch'):
                    ANALYSIS._simulate_task(changed)
            with cache.open('ab') as stream:
                stream.write(b'corruption')
            with self.assertRaisesRegex(ValueError,'fingerprint mismatch'):
                ANALYSIS._simulate_task(task)


if __name__=='__main__':
    unittest.main()
