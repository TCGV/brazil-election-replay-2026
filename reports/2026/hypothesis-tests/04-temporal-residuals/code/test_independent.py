"""Independent H4 controls; all fixtures here are artificial, not election results."""
from collections import Counter
import csv
from datetime import datetime
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

SPEC = importlib.util.spec_from_file_location('h4_independent', Path(__file__).with_name('validate_independently.py'))
INDEPENDENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INDEPENDENT)


def artificial(votes, times=None, places=None, nominal=None):
    values = np.asarray(votes, dtype=np.int64)
    if values.ndim == 1:
        values = np.column_stack([values, 100 - values])
    n = len(values)
    if nominal is None:
        nominal = values.sum(axis=1)
    if times is None:
        times = np.arange(n) * 60
    return dict(election_code=6257, turno=1, candidate_numbers=[13,22] if values.shape[1]==2 else [13,14,22],
        candidate_votes=values, aptos=np.full(n, 120, dtype=np.int64), turnout=np.asarray(nominal),
        nominal=np.asarray(nominal), installed=np.ones(n, dtype=bool), cancelled=np.zeros(n, dtype=bool),
        first_time=np.asarray(times), bu_time=np.asarray(times)-1,
        uf=np.full(n, 'SP'), municipality=np.ones(n, dtype=np.int64), zone=np.ones(n, dtype=np.int64),
        section=np.arange(1,n+1), place=np.ones(n,dtype=np.int64) if places is None else np.asarray(places))


class IndependentTemporalControls(unittest.TestCase):
    def test_local_wall_clock_day_first_iso_and_invalid_offsets(self):
        value = INDEPENDENT.wall_clock('04/10/2026 17:08:57')
        expected = datetime(2026,10,4,17,8,57) - datetime(1970,1,1)
        self.assertEqual(value, expected.days*86400+expected.seconds)
        self.assertEqual(value, INDEPENDENT.wall_clock('2026-10-04T17:08:57'))
        self.assertEqual(value, INDEPENDENT.wall_clock('2026-10-04 17:08:57'))
        for raw in ['', '#NULO', '#NE', '-1', '-3']:
            self.assertEqual(INDEPENDENT.wall_clock(raw), -1)
        for raw in ['2026-10-04T17:08:57Z', '2026-10-04T17:08:57-03:00',
                    '31/02/2026 00:00:00', '2026-10-04 17:08', '01/01/1960 00:00:00']:
            with self.assertRaises(ValueError, msg=raw):
                INDEPENDENT.wall_clock(raw)

    def test_exclusive_eligibility_preserves_missing_and_status_distinctions(self):
        data = artificial([40]*8, times=np.arange(8)*60+600)
        data['installed'][0]=False
        data['aptos'][0]=1
        data['aptos'][1]=1
        data['turnout'][2]=0
        data['nominal'][3]=49
        data['first_time'][4]=-1
        data['bu_time'][5]=-1
        data['place'][6]=-1
        selected, reasons=INDEPENDENT.eligibility(data)
        self.assertEqual(np.flatnonzero(selected).tolist(), [7])
        self.assertEqual(reasons.tolist(), ['section_status','aptos_below_50','nonpositive_turnout',
            'nominal_below_floor','missing_time','missing_time','missing_place','eligible'])

    def test_slow_gradual_artificial_signal_has_small_exhaustive_tail(self):
        votes=[47,48,49,51,52,53]
        data=artificial(votes, times=np.arange(6)*60+600)
        reference=INDEPENDENT.model_reference(data,'zone_size')
        result=INDEPENDENT.minute_reference(reference,'first_time')
        permutations=INDEPENDENT.exact_permutation_statistics([100]*6,votes,list(range(6)),[list(range(6))])
        self.assertEqual(len(permutations),math.factorial(6))
        observed=result['statistics'][0,0]
        exact=sum(row[0]>=observed-1e-12 for row in permutations)/len(permutations)
        self.assertAlmostEqual(exact,2/720)
        self.assertGreater(result['signed_gradual'][0],0)
        self.assertAlmostEqual(result['signed_gradual'][0],-result['signed_gradual'][1])
        self.assertAlmostEqual(result['cumulative_residual'][-1,0],0)

    def test_geographic_composition_can_change_raw_curve_with_no_local_residual(self):
        data=artificial([20,20,80,80], times=np.arange(4)*60+600, places=[1,1,2,2])
        place=INDEPENDENT.model_reference(data,'place_size')
        zone=INDEPENDENT.model_reference(data,'zone_size')
        local=INDEPENDENT.minute_reference(place,'first_time')
        broad=INDEPENDENT.minute_reference(zone,'first_time')
        self.assertLess(local['cumulative_votes'][0,0]/local['cumulative_nominal'][0],
                        local['cumulative_votes'][-1,0]/local['cumulative_nominal'][-1])
        np.testing.assert_array_equal(local['statistics'],np.zeros((2,3)))
        self.assertGreater(broad['statistics'][0,0],0)
        self.assertGreater(broad['statistics'][0,1],0)

    def test_complete_minute_ties_have_no_temporal_information(self):
        data=artificial([10,30,70,90],times=[600]*4)
        reference=INDEPENDENT.model_reference(data,'place_size')
        result=INDEPENDENT.minute_reference(reference,'first_time')
        np.testing.assert_array_equal(result['statistics'],np.zeros((2,3)))
        self.assertEqual(result['sections'].tolist(),[4])
        self.assertEqual(result['checkpoints'].tolist(),[-1]+[0]*100)

    def test_empty_minutes_are_retained_and_candidate_counts_not_rounded(self):
        data=artificial([[20,1,79],[21,0,79]],times=[600,720])
        reference=INDEPENDENT.model_reference(data,'place_size')
        result=INDEPENDENT.minute_reference(reference,'first_time')
        self.assertEqual(result['sections'].tolist(),[1,0,1])
        self.assertEqual(result['statistics'].shape,(3,3))
        self.assertGreater(result['statistics'][1,0],0)
        self.assertEqual(result['statistics'][2,0],0)

    def test_group_weighted_share_not_mean_of_percentages(self):
        data=artificial([[10,40],[90,10]],times=[600,660],nominal=[50,100])
        reference=INDEPENDENT.model_reference(data,'place_size')
        # p=(10+90)/(50+100)=2/3, not mean(1/5,9/10)=.55
        self.assertAlmostEqual(reference['residual'][0,0],10-50*2/3)
        self.assertAlmostEqual(reference['residual'][1,0],90-100*2/3)
        self.assertAlmostEqual(reference['residual'][:,0].sum(),0)

    def test_constant_absolute_scores_are_not_informative_despite_signed_variance(self):
        data=artificial([20,80],times=[600,660])
        reference=INDEPENDENT.model_reference(data,'place_size')
        minute=INDEPENDENT.minute_reference(reference,'first_time')
        for j in range(3):
            observed=float(minute['statistics'][0,j])
            applicable,reason=INDEPENDENT.score_applicability(reference,'first_time',minute,0,j,observed,[observed]*4,2)
            self.assertFalse(applicable)
            self.assertEqual(reason,'exact_enumeration_constant')
        self.assertGreater(np.var(reference['residual'][:,0]),0)

    def test_fixed_family_holm_and_plus_one_never_zero(self):
        values={'a':.0002,'b':.02,'c':1.}
        adjusted=INDEPENDENT.holm_reference(values)
        for key, expected in {'a':.0006,'b':.04,'c':1.}.items():
            self.assertAlmostEqual(adjusted[key],expected)
        self.assertEqual(INDEPENDENT.monte_carlo_p(10,[1,2,3]),.25)
        self.assertEqual(INDEPENDENT.monte_carlo_p(1,[1,1,1]),1.)
        self.assertEqual(INDEPENDENT.monte_carlo_p(1,[1-5e-13,0,0]),.5)

    def test_small_exhaustive_reference_keeps_strata_and_whole_residual_pairs(self):
        values=INDEPENDENT.exact_permutation_statistics([100]*4,[20,40,60,80],[0,1,2,3],[[0,1],[2,3]])
        self.assertEqual(len(values),4)
        # Two possible sign orientations per group, no exchange between groups.
        self.assertEqual(len(set(round(row[0],12) for row in values)),2)
        self.assertTrue(all(row[2]==2.5 for row in values))


class IndependentParserControls(unittest.TestCase):
    def write_fixture(self,root,duplicate=False,bad_vote=False):
        details=[]
        votes=[]
        for turn in (1,2):
            base=dict(ANO_ELEICAO='2026',CD_ELEICAO=str(6256+turn),NR_TURNO=str(turn),SG_UF='SP',
                CD_MUNICIPIO='71072',NR_ZONA='1',NR_SECAO='1',CD_CARGO='1',SG_UE='BR',DS_CARGO='Presidente')
            details.append(dict(base,NR_LOCAL_VOTACAO='001',ST_SECAO_INSTALADA='Sim',ST_SECAO_ANULADA='Não',
                QT_APTOS='100',QT_COMPARECIMENTO='80',QT_ABSTENCOES='20',QT_VOTOS_NOMINAIS='75',
                QT_VOTOS_BRANCOS='2',QT_VOTOS_NULOS='3',QT_VOTOS_LEGENDA='0',QT_VOTOS_ANULADOS_APU_SEP='0',
                DT_RECEBIMENTO_BU_HOR_TSE='04/10/2026 17:00:00',DT_PRIM_TOT_PARCIAL_HOR_TSE='04/10/2026 17:00:59'))
            for candidate,quantity in [(13,40),(22,35),(95,2),(96,3)]:
                votes.append(dict(base,NR_VOTAVEL=str(candidate),QT_VOTOS=str(quantity+int(bad_vote and candidate==13))))
        if duplicate:
            details.append(dict(details[0]))
        for kind,rows in [('details',details),('votes',votes)]:
            path=root/INDEPENDENT.SOURCE_PATHS[kind]
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('w',encoding='latin1',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter=';')
                writer.writeheader();writer.writerows(rows)

    def test_independent_csv_parser_reconciles_each_source_and_round(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            self.write_fixture(root)
            rounds,statistics=INDEPENDENT.read_sources(root)
            self.assertEqual(statistics,dict(detail_rows_read=2,detail_rows_selected=2,vote_rows_read=8,vote_rows_selected=8))
            self.assertEqual([data['turno'] for data in rounds],[1,2])
            self.assertEqual(rounds[0]['candidate_votes'].tolist(),[[40,35]])
            self.assertEqual(rounds[0]['place'].tolist(),[1])
            self.assertEqual((rounds[0]['first_time']-rounds[0]['bu_time']).tolist(),[59])

    def test_independent_parser_rejects_duplicate_details_and_discordant_votes(self):
        for changes in [dict(duplicate=True),dict(bad_vote=True)]:
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                self.write_fixture(root,**changes)
                with self.assertRaises(ValueError):
                    INDEPENDENT.read_sources(root)


class PublicationComparatorControls(unittest.TestCase):
    def write_rows(self, path, rows):
        with path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=['id','count','score'])
            writer.writeheader();writer.writerows(rows)

    def test_missing_or_duplicate_rows_are_detected_after_any_manifest_rehash(self):
        expected=[dict(id='a',count=2,score=.25),dict(id='b',count=3,score=.5)]
        for actual in [expected[:1],expected+[expected[0]]]:
            with tempfile.TemporaryDirectory() as temporary:
                path=Path(temporary)/'example.csv'
                self.write_rows(path,actual)
                result=INDEPENDENT.Comparisons()
                INDEPENDENT.compare_table(path,expected,('id',),result,'synthetic')
                self.assertGreater(result.counts['mismatches'],0)

    def test_recomputed_values_are_checked_beyond_file_fingerprints(self):
        expected=[dict(id='a',count=2,score=.25)]
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'example.csv'
            self.write_rows(path,[dict(id='a',count=3,score=.25)])
            result=INDEPENDENT.Comparisons()
            INDEPENDENT.compare_table(path,expected,('id',),result,'synthetic')
            self.assertEqual(result.counts['mismatches'],1)
            self.write_rows(path,expected)
            result=INDEPENDENT.Comparisons()
            INDEPENDENT.compare_table(path,expected,('id',),result,'synthetic')
            self.assertEqual(result.counts['mismatches'],0)

    def test_independent_assignments_preserve_group_and_complete_section_identity(self):
        data=artificial([10,20,30,60,70,80],times=np.arange(6)*60+600,places=[1,1,1,2,2,2])
        reference=INDEPENDENT.model_reference(data,'place_size')
        for repetition in range(4):
            assignment=INDEPENDENT.independent_assignment(reference,20261028,1,repetition)
            self.assertEqual(sorted(assignment.tolist()),list(range(6)))
            self.assertTrue(np.array_equal(data['place'][assignment],data['place']))
            moved=data['candidate_votes'][assignment]
            self.assertTrue(np.array_equal(moved.sum(axis=1),data['nominal'][assignment]))
            self.assertTrue(np.array_equal(moved.sum(axis=0),data['candidate_votes'].sum(axis=0)))
        assignment=INDEPENDENT.independent_assignment(reference,20261028,1,2)
        np.testing.assert_array_equal(assignment,INDEPENDENT.independent_assignment(reference,20261028,1,2))


if __name__=='__main__':
    unittest.main()
