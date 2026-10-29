"""Artificial controls for the independent H7 implementation."""
import csv
from fractions import Fraction
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np

SPEC=importlib.util.spec_from_file_location('h7_independent',Path(__file__).with_name('validate_independently.py'))
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


def municipal_fixture():
    rounds=artificial((304,308,312,316),(152,160,168,176),places=(1,1,1,1))
    for rd in rounds:
        rd['municipality']=np.array([1,1,2,2])
        rd['section']=np.array([1,2,1,2])
    return rounds


class IndependentMetricTests(unittest.TestCase):
    def test_exited_candidates_create_nominal_advantage_without_preference_change(self):
        m=I.fraction_metrics(dict(v13_1=14,v22_1=6,nominal_1=25,v13_2=21,v22_2=9,nominal_2=30))
        self.assertEqual(m['delta_q_pp'],0)
        self.assertEqual(m['growth_sign'],0)
        self.assertEqual(m['count_sign'],1)
        self.assertEqual(m['nominal_sign'],1)
        self.assertEqual(m['nominal_difference_pp'],8)

    def test_gain_definition_can_reverse_which_direction_is_larger(self):
        m=I.fraction_metrics(dict(v13_1=10,v22_1=90,nominal_1=200,v13_2=40,v22_2=160,nominal_2=200))
        self.assertEqual(m['count_sign'],-1)
        self.assertEqual(m['nominal_sign'],-1)
        self.assertEqual(m['growth_sign'],1)
        self.assertEqual(m['conditional_sign'],1)

    def test_zero_initial_candidate_is_undefined_for_relative_growth(self):
        m=I.fraction_metrics(dict(v13_1=0,v22_1=100,nominal_1=100,v13_2=20,v22_2=80,nominal_2=100))
        self.assertIsNone(m['growth13_pct'])
        self.assertIsNone(m['growth_difference_pct'])
        self.assertIsNone(m['growth_sign'])
        self.assertEqual(m['conditional_sign'],1)

    def test_zero_nominal_denominators_are_not_pseudocounted(self):
        m=I.fraction_metrics(dict(v13_1=0,v22_1=0,nominal_1=0,v13_2=0,v22_2=0,nominal_2=0))
        self.assertIsNone(m['nominal_difference_pp'])
        self.assertIsNone(m['delta_q_pp'])
        self.assertEqual(m['count_sign'],0)

    def test_python_integer_products_do_not_overflow(self):
        n=10**12
        m=I.fraction_metrics(dict(v13_1=3*n,v22_1=2*n,nominal_1=6*n,v13_2=4*n,v22_2=2*n,nominal_2=6*n))
        self.assertEqual(m['conditional_sign'],1)
        self.assertEqual(m['delta_q_pp'],Fraction(20,3))


class IndependentPairTests(unittest.TestCase):
    def test_physical_join_handles_reversed_source_order(self):
        rounds=municipal_fixture()
        rounds[1]={k:v[::-1] if isinstance(v,np.ndarray) else v for k,v in rounds[1].items()}
        p=I.pair_reference(rounds)
        self.assertEqual(p['keys'],[('SP',1,1,1),('SP',1,1,2),('SP',2,1,1),('SP',2,1,2)])
        np.testing.assert_array_equal(p['v13_2'],[152,160,168,176])

    def test_duplicate_physical_key_and_electorate_inconsistency_raise(self):
        rounds=municipal_fixture();rounds[0]['section'][1]=1
        with self.assertRaisesRegex(ValueError,'Duplicate physical'):
            I.pair_reference(rounds)
        rounds=municipal_fixture();rounds[1]['abstentions'][0]+=1
        with self.assertRaisesRegex(ValueError,'identity fails'):
            I.pair_reference(rounds)

    def test_domestic_scope_and_exclusive_exclusions(self):
        rounds=municipal_fixture()
        for rd in rounds:rd['uf'][0]='ZZ'
        rounds[0]['installed'][1]=False;rounds[0]['aptos'][1]=10
        p=I.pair_reference(rounds,domestic_only=True)
        self.assertEqual(sum(p['reasons']=='exterior'),1)
        self.assertEqual(sum(p['reasons']=='section_status'),1)
        self.assertEqual(len(p['selected']),2)


class IndependentAllocationTests(unittest.TestCase):
    def test_aggregation_and_whole_block_membership(self):
        p=I.pair_reference(municipal_fixture(),domestic_only=True)
        section=I.reference_prepare(p,'section',min_target=1)
        block=I.reference_prepare(p,'place_block',min_target=1)
        self.assertEqual(len(section['unit_keys']),4)
        self.assertEqual(block['unit']['ns'].tolist(),[2,2])
        self.assertEqual(block['unit_members'],[[0,1],[2,3]])
        self.assertEqual(len(block['buckets']),1)
        np.testing.assert_array_equal(I.reference_aggregate(section)['v13_2'],[312,344])
        np.testing.assert_allclose(I.reference_scores(section)[:3],I.reference_scores(block)[:3])

    def test_all_twentyfour_section_allocations_match_exact_fraction_scores(self):
        p=I.pair_reference(municipal_fixture(),domestic_only=True)
        ref=I.reference_prepare(p,'section',min_target=1)
        count=0
        for assignment in I.finite_assignments(ref):
            actual=I.reference_scores(ref,assignment)
            exact=I.exact_score_squares(ref,assignment)
            expected=[float(v) if i<3 else float(v)**.5 for i,v in enumerate(exact)]
            np.testing.assert_allclose(actual,expected,atol=1e-12)
            count+=1
        self.assertEqual(count,24)

    def test_rng_stream_hash_reproducible_and_group_slots_preserved(self):
        p=I.pair_reference(municipal_fixture(),domestic_only=True)
        ref=I.reference_prepare(p,'section',min_target=1)
        a=I.independent_assignment(ref,20261029,0,1)
        np.testing.assert_array_equal(a,I.independent_assignment(ref,20261029,0,1))
        for row in ref['group_rows']:
            self.assertEqual(sorted(a[row['members']].tolist()),row['members'])
        with self.assertRaises(ValueError):I.independent_assignment(ref,20261029,1,1)

    def test_fixed_targets_do_not_change_on_block_reassignment(self):
        p=I.pair_reference(municipal_fixture(),domestic_only=True)
        ref=I.reference_prepare(p,'place_block',min_target=2)
        before=ref['targets'].copy()
        assignment=np.array([1,0])
        I.reference_scores(ref,assignment)
        np.testing.assert_array_equal(ref['targets'],before)

    def test_no_cross_municipality_mobility_is_proven_not_applicable(self):
        rounds=artificial();p=I.pair_reference(rounds,domestic_only=True)
        ref=I.reference_prepare(p,'section',min_target=1)
        score=I.reference_scores(ref)
        flags,reasons=I.score_applicability(ref,np.tile(score,(3,1)),score)
        self.assertFalse(any(flags))
        self.assertEqual(reasons[:4],['no_cross_target_municipality_mobility']*4)
        self.assertEqual(reasons[4],'no_adjacent_target_municipality_pairs')

    def test_small_orbit_constancy_uses_exact_values(self):
        p=I.pair_reference(municipal_fixture(),domestic_only=True)
        ref=I.reference_prepare(p,'place_block',min_target=1)
        observed=I.reference_scores(ref)
        flags,reasons=I.score_applicability(ref,np.tile(observed,(2,1)),observed)
        self.assertEqual(len(flags),5)
        self.assertTrue(all(reason.startswith('exact_enumeration_') for reason in reasons))

    def test_unwitnessed_large_orbit_is_unresolved_instead_of_nondetection(self):
        p=I.pair_reference(municipal_fixture(),domestic_only=True)
        ref=I.reference_prepare(p,'section',min_target=1);score=I.reference_scores(ref)
        flags,reasons=I.score_applicability(ref,np.tile(score,(2,1)),score,max_exact=1)
        self.assertFalse(any(flags))
        self.assertEqual(reasons,['unresolved_large_orbit']*5)

    def test_holm_family_includes_na_as_one(self):
        result=I.holm_reference({'a':.0002,'b':.02,'na':1.})
        self.assertAlmostEqual(result['a'],.0006)
        self.assertAlmostEqual(result['b'],.04)
        self.assertEqual(result['na'],1.)


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
    def test_streamed_checks_detect_changed_count_and_missing_row(self):
        rows=[dict(key='a',count=2,measure=1.5,supported=True),dict(key='b',count=3,measure=None,supported=False)]
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'example.csv'
            def write(values):
                with path.open('w',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=rows[0]);writer.writeheader();writer.writerows(values)
            write(rows);audit=I.Comparisons()
            I.compare_ordered_table(path,iter(rows),audit,'fixture')
            self.assertEqual(audit.counts['mismatches'],0)
            write([dict(rows[0],count=9)]);audit=I.Comparisons()
            I.compare_ordered_table(path,iter(rows),audit,'fixture')
            self.assertEqual(audit.counts['mismatches'],2)


if __name__=='__main__':
    unittest.main()
