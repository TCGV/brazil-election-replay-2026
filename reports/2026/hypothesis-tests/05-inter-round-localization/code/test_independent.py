"""Independent H5 controls; every example is explicitly artificial."""
import csv
from fractions import Fraction
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

SPEC=importlib.util.spec_from_file_location('h5_independent',Path(__file__).with_name('validate_independently.py'))
I=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(I)


def artificial(first_votes,second_votes,places=None,aptos=None,minor=None):
    n=len(first_votes)
    if places is None: places=np.ones(n,dtype=np.int64)
    if aptos is None: aptos=np.full(n,200,dtype=np.int64)
    result=[]
    for turn,votes in ((1,first_votes),(2,second_votes)):
        m=np.zeros(n,dtype=np.int64) if minor is None or turn==2 else np.asarray(minor)
        matrix=np.column_stack([votes,m,100-np.asarray(votes)]) if turn==1 else np.column_stack([votes,100-np.asarray(votes)])
        nominal=matrix.sum(axis=1)
        result.append(dict(election_code=6256+turn,turno=turn,candidate_numbers=[13,14,22] if turn==1 else [13,22],
            candidate_votes=matrix,aptos=np.asarray(aptos).copy(),turnout=nominal.copy(),
            nominal=nominal.copy(),abstentions=np.asarray(aptos)-nominal,place=np.asarray(places).copy(),
            source_line=np.arange(2,n+2),installed=np.ones(n,dtype=bool),cancelled=np.zeros(n,dtype=bool),
            uf=np.full(n,'SP'),municipality=np.full(n,71072),zone=np.ones(n,dtype=np.int64),
            section=np.arange(1,n+1)))
    return result


class IndependentPairControls(unittest.TestCase):
    def test_same_physical_key_matches_different_election_codes(self):
        rounds=artificial([40,50],[45,60])
        rounds[1]={name:values[::-1] if isinstance(values,np.ndarray) else values for name,values in rounds[1].items()}
        pairs=I.pair_reference(rounds)
        self.assertEqual(pairs['keys'],[('SP',71072,1,1),('SP',71072,1,2)])
        np.testing.assert_allclose(pairs['delta'],[5,10])
        self.assertEqual(pairs['selected'].tolist(),[0,1])

    def test_missing_counterpart_is_recorded_without_invented_change(self):
        rounds=artificial([40,50],[45,60]); rounds[1]['section'][1]=3
        pairs=I.pair_reference(rounds)
        self.assertEqual(len(pairs['keys']),1)
        self.assertEqual(pairs['only_first'],[('SP',71072,1,2)])
        self.assertEqual(pairs['only_second'],[('SP',71072,1,3)])
        rounds[1]['section'][1]=1
        with self.assertRaisesRegex(ValueError,'Duplicate physical'):
            I.pair_reference(rounds)

    def test_exit_of_minor_candidates_can_raise_nominal_share_without_finalist_shift(self):
        pairs=I.pair_reference(artificial([50],[50],minor=[100]))
        self.assertEqual(pairs['delta'].tolist(),[0])
        self.assertEqual(pairs['delta_p13'].tolist(),[25])
        self.assertEqual(pairs['delta_p22'].tolist(),[25])
        self.assertEqual(100*((1-pairs['q2'][0])-(1-pairs['q1'][0])),-pairs['delta'][0])

    def test_exclusions_are_exclusive_and_cadastral_tolerance_is_symmetric(self):
        rounds=artificial([40]*8,[50]*8)
        rounds[0]['installed'][0]=False;rounds[0]['aptos'][0]=1
        rounds[0]['aptos'][1]=49
        rounds[1]['turnout'][2]=0
        rounds[0]['nominal'][3]=49
        rounds[0]['candidate_votes'][4]=[20,60,20]
        rounds[0]['place'][5]=-1
        rounds[1]['place'][6]=2
        rounds[0]['aptos'][7]=100;rounds[1]['aptos'][7]=126
        pairs=I.pair_reference(rounds)
        self.assertEqual(pairs['reasons'].tolist(),['section_status','aptos_below_50','nonpositive_turnout',
            'nominal_below_50','finalists_below_floor','missing_place','changed_place','electorate_ratio'])
        rounds=artificial([40,40],[50,50]);rounds[0]['aptos'][:]=[100,125];rounds[1]['aptos'][:]=[125,100]
        self.assertEqual(len(I.pair_reference(rounds)['selected']),2)

    def test_preference_bins_use_integer_rationals_and_closed_upper_endpoint(self):
        self.assertEqual(I.initial_band(0,100),0)
        self.assertEqual(I.initial_band(5,100),1)
        self.assertEqual(I.initial_band(499,1000),9)
        self.assertEqual(I.initial_band(50,100),10)
        self.assertEqual(I.initial_band(100,100),19)

    def test_own_section_is_excluded_from_peer_median(self):
        pairs=I.pair_reference(artificial([50]*5,[50,50,50,50,90]))
        context=I.peer_reference(pairs)
        self.assertEqual(context[4]['strict'],dict(other_count=4,median=0.,difference=40.,priority=True))
        self.assertFalse(context[0]['strict']['priority'])
        pairs=I.pair_reference(artificial([50]*4,[50,50,50,90]))
        self.assertIsNone(I.peer_reference(pairs)[3]['strict']['median'])

    def test_initial_preference_context_is_distinct_from_broader_place_context(self):
        pairs=I.pair_reference(artificial([20]*5+[80]*5,[30]*5+[70]*5))
        rows=I.peer_reference(pairs)
        self.assertEqual(rows[0]['strict']['difference'],0)
        self.assertEqual(rows[0]['broad']['difference'],20)


class IndependentConcentrationControls(unittest.TestCase):
    def test_cluster_scores_match_hand_computed_finite_reference(self):
        pairs=I.pair_reference(artificial([50]*4,[30,30,70,70],places=[1,1,2,2]))
        reference=I.localization_reference(pairs,'zone_size_baseline',min_place=2)
        observed,_=I.localization_scores(reference)
        np.testing.assert_allclose(observed,[20,20*math.sqrt(2)])
        exact=I.exact_localization(reference)
        self.assertEqual(len(exact),24)
        self.assertEqual(np.count_nonzero(exact[:,0]>=observed[0]-1e-12),8)
        self.assertEqual(np.count_nonzero(exact[:,1]>=observed[1]-1e-12),8)

    def test_one_large_section_shift_does_not_become_a_marginal_extremeness_test(self):
        pairs=I.pair_reference(artificial([50]*6,[90,50,50,50,50,50],places=[1]*3+[2]*3))
        reference=I.localization_reference(pairs,'zone_size_baseline',min_place=3)
        exact=I.exact_localization(reference)
        # The same single outlier moves, but each target receives one of two
        # symmetric allocations, making both magnitudes constant.
        np.testing.assert_allclose(np.ptp(exact,axis=0),[0,0],atol=1e-12)
        self.assertEqual(float(pairs['delta'].max()),40)

    def test_homogeneous_movement_and_constant_rational_changes_have_zero_residual(self):
        pairs=I.pair_reference(artificial([50]*10,[60]*10,places=[1]*5+[2]*5))
        reference=I.localization_reference(pairs,'zone_size_baseline')
        np.testing.assert_array_equal(reference['residual'],np.zeros(10))
        np.testing.assert_array_equal(I.localization_scores(reference)[0],np.zeros(2))
        self.assertFalse(reference['group_rows'][0]['variable'])

    def test_initial_heterogeneity_can_generate_legitimate_between_place_changes(self):
        pairs=I.pair_reference(artificial([20]*5+[80]*5,[30]*5+[70]*5,places=[1]*5+[2]*5))
        broad=I.localization_reference(pairs,'zone_size');strict=I.localization_reference(pairs,'zone_size_baseline')
        self.assertGreater(I.localization_scores(broad)[0][0],0)
        np.testing.assert_array_equal(I.localization_scores(strict)[0],np.zeros(2))

    def test_assignments_preserve_whole_pairs_and_groups(self):
        pairs=I.pair_reference(artificial([20,21,50,51,80,81],[30,32,55,57,70,72],places=[1,1,2,2,3,3]))
        reference=I.localization_reference(pairs,'zone_size_baseline',min_place=2)
        assignment=I.independent_assignment(reference,20261029,1,0)
        self.assertEqual(sorted(assignment.tolist()),list(range(6)))
        for members in reference['groups'].values():
            self.assertEqual(sorted(assignment[members].tolist()),sorted(members))
        moved=pairs['delta'][reference['selected']][assignment]
        np.testing.assert_allclose(np.sort(moved),np.sort(pairs['delta'][reference['selected']]))
        for field in ('votes13_1','votes22_1','votes13_2','votes22_2','finalists1','finalists2'):
            original=pairs[field][reference['selected']]
            self.assertEqual(int(original.sum()),int(original[assignment].sum()))

    def test_fixed_holm_family_and_plus_one_never_publish_zero(self):
        self.assertEqual(I.holm_reference({'a':.01,'b':.03,'c':1.,'d':.2}),{'a':.04,'b':.09,'d':.4,'c':1.})
        self.assertEqual(I.monte_carlo_p(10,[1,2,3]),.25)
        self.assertEqual(I.monte_carlo_p(2,[1,2,2]),.75)

    def test_absolute_score_constancy_requires_enumeration_not_a_constant_sample(self):
        pairs=I.pair_reference(artificial([50]*6,[90,50,50,50,50,50],places=[1]*3+[2]*3))
        ref=I.localization_reference(pairs,'zone_size_baseline',min_place=3)
        obs=I.localization_scores(ref)[0]
        flags,reasons=I.score_applicability(ref,np.vstack([obs,obs]),obs)
        self.assertEqual(flags.tolist(),[False,False])
        self.assertEqual(reasons,['exact_enumeration_constant']*2)
        pairs=I.pair_reference(artificial([50]*4,[30,30,70,70],places=[1,1,2,2]))
        ref=I.localization_reference(pairs,'zone_size_baseline',min_place=2)
        obs=I.localization_scores(ref)[0]
        flags,reasons=I.score_applicability(ref,np.vstack([obs,obs]),obs)
        self.assertEqual(flags.tolist(),[True,True])
        self.assertEqual(reasons,['exact_enumeration_variable']*2)

    def test_no_targets_and_unresolved_large_orbit_never_become_nondetection(self):
        pairs=I.pair_reference(artificial([50]*4,[30,30,70,70],places=[1,1,2,2]))
        ref=I.localization_reference(pairs,'zone_size_baseline')
        obs=I.localization_scores(ref)[0]
        flags,reasons=I.score_applicability(ref,np.vstack([obs,obs]),obs)
        self.assertEqual(flags.tolist(),[False,False]);self.assertEqual(reasons,['no_targets']*2)
        pairs=I.pair_reference(artificial([50]*10,[30]*5+[70]*5,places=[1]*5+[2]*5))
        ref=I.localization_reference(pairs,'zone_size_baseline')
        obs=I.localization_scores(ref)[0]
        with self.assertRaisesRegex(ArithmeticError,'Unresolved concentration'):
            I.score_applicability(ref,np.vstack([obs,obs]),obs,max_exact=100)


class IndependentSourceControls(unittest.TestCase):
    def fixture(self, root):
        details=[]; votes=[]
        for turn in (1,2):
            detail=dict(CD_ELEICAO=6256+turn,NR_TURNO=turn,SG_UF='SP',CD_MUNICIPIO=71072,
                NR_ZONA=1,NR_SECAO=1,CD_CARGO=1,ANO_ELEICAO=2026,DS_CARGO='Presidente',SG_UE='BR',
                NR_LOCAL_VOTACAO=123,ST_SECAO_INSTALADA='Sim',ST_SECAO_ANULADA='Não',
                QT_APTOS=120,QT_COMPARECIMENTO=100,QT_ABSTENCOES=20,QT_VOTOS_NOMINAIS=100,
                QT_VOTOS_BRANCOS=0,QT_VOTOS_NULOS=0,QT_VOTOS_LEGENDA=0,QT_VOTOS_ANULADOS_APU_SEP=0)
            details.append(detail)
            for candidate,quantity in ((13,30+10*turn),(22,70-10*turn),(95,0),(96,0),(97,0)):
                votes.append({**{field:detail[field] for field in I.KEY_FIELDS},
                    'ANO_ELEICAO':2026,'NR_VOTAVEL':candidate,'QT_VOTOS':quantity})
        return details,votes

    def write(self, root, details, votes):
        for kind,rows in [('details',details),('votes',votes)]:
            path=root/I.SOURCE_PATHS[kind];path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('w',encoding='latin1',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter=';')
                writer.writeheader();writer.writerows(rows)

    def test_own_original_parser_preserves_rounds_and_reconciles_categories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); details,votes=self.fixture(root);self.write(root,details,votes)
            rounds,counts=I.read_sources(root)
            self.assertEqual(counts,dict(detail_rows_read=2,detail_rows_selected=2,vote_rows_read=10,vote_rows_selected=10))
            self.assertEqual([data['turno'] for data in rounds],[1,2])
            self.assertEqual(I.pair_reference(rounds)['delta'].tolist(),[10.])
            self.assertEqual(rounds[0]['source_line'].tolist(),[2])

    def test_own_original_parser_rejects_duplicate_details_and_wrong_candidate_totals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); details,votes=self.fixture(root)
            self.write(root,[*details,details[0]],votes)
            with self.assertRaisesRegex(ValueError,'Duplicate normalized'):
                I.read_sources(root)
            votes[0]['QT_VOTOS']+=1;self.write(root,details,votes)
            with self.assertRaisesRegex(ValueError,'nominal reconciliation'):
                I.read_sources(root)


class IndependentComparatorControls(unittest.TestCase):
    def write(self,path,rows):
        with path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=['key','count','score','priority','missing'])
            writer.writeheader();writer.writerows(rows)

    def test_changed_values_and_missing_rows_are_detected_without_trusting_hashes(self):
        expected=[dict(key='a',count=1,score=1.5,priority=True,missing=None),
                  dict(key='b',count=2,score=2.5,priority=False,missing=None)]
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'table.csv'
            self.write(path,expected);audit=I.Comparisons()
            I.compare_table(path,expected,['key'],audit,'table')
            self.assertEqual(audit.counts['mismatches'],0)
            self.write(path,[dict(expected[0],score=9)])
            audit=I.Comparisons();I.compare_table(path,expected,['key'],audit,'table')
            self.assertEqual(audit.counts['mismatches'],2)


if __name__=='__main__':
    unittest.main()
