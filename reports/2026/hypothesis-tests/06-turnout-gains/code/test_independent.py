"""Artificial controls for the independent H6 implementation."""
import csv
from fractions import Fraction
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np

SPEC=importlib.util.spec_from_file_location('h6_independent',Path(__file__).with_name('validate_independently.py'))
I=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(I)


def artificial(turnout2=(304,308,312), votes2=(152,160,168), places=None):
    n=len(turnout2)
    result=[]
    for turn in (1,2):
        turnout=np.full(n,300,dtype=np.int64) if turn==1 else np.array(turnout2,dtype=np.int64)
        votes=np.full(n,150,dtype=np.int64) if turn==1 else np.array(votes2,dtype=np.int64)
        result.append(dict(election_code=6256+turn,turno=turn,candidate_numbers=[13,22],
            candidate_votes=np.column_stack([votes,turnout-votes]),aptos=np.full(n,400),turnout=turnout,
            abstentions=400-turnout,nominal=turnout.copy(),blank=np.zeros(n,dtype=np.int64),
            null_votes=np.zeros(n,dtype=np.int64),legend=np.zeros(n,dtype=np.int64),separate=np.zeros(n,dtype=np.int64),
            place=np.ones(n,dtype=np.int64) if places is None else np.array(places),source_line=np.arange(n)+2,
            installed=np.ones(n,dtype=bool),cancelled=np.zeros(n,dtype=bool),uf=np.full(n,'SP'),
            municipality=np.full(n,71072),zone=np.ones(n,dtype=np.int64),section=np.arange(n)+1))
    return result


class IndependentPairTests(unittest.TestCase):
    def test_join_uses_physical_key_not_row_order_or_election(self):
        rounds=artificial()
        rounds[1]={key:value[::-1] if isinstance(value,np.ndarray) else value for key,value in rounds[1].items()}
        pair=I.pair_reference(rounds)
        self.assertEqual(pair['keys'],[('SP',71072,1,j) for j in (1,2,3)])
        np.testing.assert_array_equal(pair['v13_2'],[152,160,168])

    def test_missing_and_ambiguous_physical_keys(self):
        rounds=artificial();rounds[1]['section'][2]=4
        pair=I.pair_reference(rounds)
        self.assertEqual(pair['only_first'],[('SP',71072,1,3)])
        self.assertEqual(pair['only_second'],[('SP',71072,1,4)])
        rounds[1]['section'][2]=1
        with self.assertRaisesRegex(ValueError,'Duplicate physical'):
            I.pair_reference(rounds)

    def test_abstention_identity_failure_is_not_silently_excluded(self):
        rounds=artificial();rounds[0]['abstentions'][0]+=1
        with self.assertRaisesRegex(ValueError,'identity fails'):
            I.pair_reference(rounds)

    def test_simultaneous_cadastral_criteria_have_exclusive_priority(self):
        rounds=artificial();rounds[0]['installed'][0]=False;rounds[0]['aptos'][0]=10
        rounds[1]['place'][1]=3
        pair=I.pair_reference(rounds)
        self.assertEqual(pair['reasons'].tolist(),['section_status','changed_place','eligible'])

    def test_rates_prevent_electorate_growth_becoming_turnout_growth(self):
        rounds=artificial((300,300,300),(150,150,150))
        rounds[1]['aptos'][:]=400
        rounds[1]['aptos'][0]=420;rounds[1]['abstentions'][0]=120
        pair=I.pair_reference(rounds)
        measure=I.measurements(pair)
        self.assertLess(measure['x'][0],0)
        self.assertEqual(pair['turnout_2'][0]-pair['turnout_1'][0],0)
        self.assertEqual(len(I.pair_reference(rounds,unchanged_electorate=True)['selected']),2)


class IndependentMeasurementTests(unittest.TestCase):
    def test_symmetric_decomposition_is_exact_with_distinct_denominators(self):
        rounds=artificial();rounds[1]['aptos'][0]=410;rounds[1]['abstentions'][0]=106
        pair=I.pair_reference(rounds);measure=I.measurements(pair)
        for c in (13,22):
            np.testing.assert_allclose(measure[f'component_turnout{c}']+measure[f'component_composition{c}'],
                                       measure[f'delta_per_aptos{c}'],atol=1e-12)
            i=0
            t1=Fraction(300,400);t2=Fraction(304,410)
            s1=Fraction(150,300);s2=Fraction(pair[f'v{c}_2'][i],304)
            expected=100*((s1+s2)/2)*(t2-t1)
            self.assertAlmostEqual(measure[f'component_turnout{c}'][i],float(expected),places=12)

    def test_constant_conditional_preference_despite_more_votes(self):
        pair=I.pair_reference(artificial((304,308,312),(152,154,156)))
        measure=I.measurements(pair)
        np.testing.assert_array_equal(measure['y'],[0,0,0])
        self.assertTrue(np.all(measure['gain13']>0))
        ref=I.grouping_reference(pair,'zone_baseline')
        self.assertEqual(ref['group_rows'][0]['status'],'constant_y')
        self.assertTrue(np.all(np.isnan(I.association_scores(ref))))

    def test_exact_rational_ties_and_mid_ranks(self):
        values=[Fraction(1,3),Fraction(2,6),Fraction(1,2),Fraction(-1,3)]
        np.testing.assert_array_equal(I.average_ranks(values),[2.5,2.5,4,1])
        # Distinct rationals that round to the same floating point value still
        # receive distinct ranks; ties are not defined by float approximation.
        a,b=Fraction(2**55,2**55),Fraction(2**55+1,2**55)
        self.assertEqual(float(a),float(b))
        np.testing.assert_array_equal(I.average_ranks([a,b]),[1,2])

    def test_integer_proportion_bands_at_edges(self):
        self.assertEqual(I.initial_band(0,100),0)
        self.assertEqual(I.initial_band(5,100),1)
        self.assertEqual(I.initial_band(499,1000),9)
        self.assertEqual(I.initial_band(100,100),19)
        with self.assertRaises(ValueError):
            I.initial_band(1,0)


class IndependentAssociationTests(unittest.TestCase):
    def test_linear_and_rank_associations_have_direction(self):
        ref=I.grouping_reference(I.pair_reference(artificial()),'zone_baseline')
        scores=I.association_scores(ref)
        self.assertGreater(scores[0],.999)
        self.assertEqual(scores[1],1)
        self.assertGreater(I.slope_reference(ref),1)
        negative=I.grouping_reference(I.pair_reference(artificial((304,308,312),(152,148,144))),'zone_baseline')
        self.assertLess(I.association_scores(negative)[0],-.999)
        self.assertEqual(I.association_scores(negative)[1],-1)

    def test_place_control_changes_support_without_calling_unsupported_normal(self):
        pair=I.pair_reference(artificial(places=[1,2,3]))
        zone=I.grouping_reference(pair,'zone_baseline')
        place=I.grouping_reference(pair,'place_baseline')
        self.assertTrue(np.all(zone['informative']))
        self.assertFalse(np.any(place['informative']))
        self.assertTrue(all(row['status']=='singleton' for row in place['group_rows']))

    def test_all_six_assignments_and_trajectory_preservation(self):
        ref=I.grouping_reference(I.pair_reference(artificial()),'zone_baseline')
        draws=list(I.exact_assignments(ref))
        self.assertEqual(len(draws),6)
        results=np.array([I.association_scores(ref,a) for a in draws])
        self.assertAlmostEqual(float(results[:,1].mean()),0)
        self.assertEqual(sorted(results[:,1].tolist()),[-1,-.5,-.5,.5,.5,1])
        assignment=I.independent_assignment(ref,20261029,0,0)
        self.assertEqual(sorted(assignment.tolist()),[0,1,2])
        for name in ('v13_1','f_1','v13_2','f_2'):
            values=ref['pair'][name][ref['selected']]
            self.assertEqual(int(values.sum()),int(values[assignment].sum()))

    def test_two_member_signed_variation_has_constant_magnitude(self):
        ref=I.grouping_reference(I.pair_reference(artificial((304,308),(152,160))),'zone_baseline')
        observed=I.association_scores(ref)
        simulated=np.array([observed,-observed])
        applicable,reasons=I.score_applicability(ref,simulated,observed)
        self.assertEqual(applicable.tolist(),[False,False])
        self.assertEqual(reasons,['exact_enumeration_constant']*2)

    def test_unwitnessed_large_orbit_never_becomes_nondetection(self):
        ref=I.grouping_reference(I.pair_reference(artificial()),'zone_baseline')
        observed=I.association_scores(ref)
        with self.assertRaisesRegex(ArithmeticError,'Unresolved magnitude'):
            I.score_applicability(ref,np.array([observed]),observed,max_exact=2)

    def test_holm_and_plus_one_reference(self):
        self.assertEqual(I.holm_reference({'a':.01,'b':.03,'c':.2,'d':1}),{'a':.04,'b':.09,'c':.4,'d':1})
        self.assertEqual(I.monte_carlo_p(10,[1,2,3]),.25)
        self.assertEqual(I.monte_carlo_p(2,[1,2,2]),.75)


class IndependentSourceTests(unittest.TestCase):
    def fixture(self,root):
        details=[];votes=[]
        for turn in (1,2):
            detail=dict(CD_ELEICAO=6256+turn,NR_TURNO=turn,SG_UF='SP',CD_MUNICIPIO=71072,NR_ZONA=1,NR_SECAO=1,
                CD_CARGO=1,ANO_ELEICAO=2026,DS_CARGO='Presidente',SG_UE='BR',NR_LOCAL_VOTACAO=123,
                ST_SECAO_INSTALADA='Sim',ST_SECAO_ANULADA='Não',QT_APTOS=400,QT_COMPARECIMENTO=300,
                QT_ABSTENCOES=100,QT_VOTOS_NOMINAIS=300,QT_VOTOS_BRANCOS=0,QT_VOTOS_NULOS=0,
                QT_VOTOS_LEGENDA=0,QT_VOTOS_ANULADOS_APU_SEP=0)
            details.append(detail)
            for candidate,quantity in ((13,150),(22,150),(95,0),(96,0),(97,0)):
                votes.append({**{field:detail[field] for field in I.KEY_FIELDS},'ANO_ELEICAO':2026,'NR_VOTAVEL':candidate,'QT_VOTOS':quantity})
        return details,votes

    def write(self,root,details,votes):
        for kind,rows in [('details',details),('votes',votes)]:
            path=root/I.SOURCE_PATHS[kind];path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('w',encoding='latin1',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter=';');writer.writeheader();writer.writerows(rows)

    def test_original_parser_and_category_reconciliation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);details,votes=self.fixture(root);self.write(root,details,votes)
            rounds,counts=I.read_sources(root)
            self.assertEqual(counts['detail_rows_read'],2)
            self.assertEqual(counts['vote_rows_read'],10)
            self.assertEqual(I.pair_reference(rounds)['selected'].tolist(),[0])
            votes[0]['QT_VOTOS']+=1;self.write(root,details,votes)
            with self.assertRaisesRegex(ValueError,'nominal reconciliation'):
                I.read_sources(root)

    def test_source_parser_rejects_duplicate_details_and_lfs_pointer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);details,votes=self.fixture(root);self.write(root,[*details,details[0]],votes)
            with self.assertRaisesRegex(ValueError,'Duplicate normalized'):
                I.read_sources(root)
            path=root/I.SOURCE_PATHS['details'];path.write_text('version https://git-lfs.github.com/spec/v1\n')
            with self.assertRaisesRegex(ValueError,'Git LFS pointer'):
                list(I.raw_rows(path))


class IndependentPublicationTests(unittest.TestCase):
    def write(self,path,rows):
        with path.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=['key','count','measure','supported'])
            writer.writeheader();writer.writerows(rows)

    def test_streaming_comparator_detects_changed_count_and_missing_row(self):
        rows=[dict(key='a',count=2,measure=1.5,supported=True),dict(key='b',count=3,measure=None,supported=False)]
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'example.csv';self.write(path,rows)
            audit=I.Comparisons();I.compare_ordered_table(path,iter(rows),audit,'fixture')
            self.assertEqual(audit.counts['mismatches'],0)
            self.write(path,[dict(rows[0],count=9)])
            audit=I.Comparisons();I.compare_ordered_table(path,iter(rows),audit,'fixture')
            self.assertEqual(audit.counts['mismatches'],2)

    def test_national_count_identity_allows_other_candidates_without_new_voters(self):
        rounds=artificial((300,300,300),(160,160,160))
        rounds[0]['candidate_numbers']=[13,14,22]
        rounds[0]['candidate_votes']=np.tile([140,20,140],(3,1))
        rows=list(I.totals_rows(rounds))
        national=rows[0]
        self.assertEqual(national['turnout_change'],0)
        self.assertEqual(national['other_nominal_change'],-60)
        self.assertEqual(national['finalist_gain'],60)
        self.assertEqual(national['identity_residual'],0)


if __name__=='__main__':
    unittest.main()
