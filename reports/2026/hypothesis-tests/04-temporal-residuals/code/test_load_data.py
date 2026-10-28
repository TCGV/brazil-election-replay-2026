"""Small synthetic fixtures for source pinning, reconciliation and H4 caches."""
import contextlib
import csv
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np


SPEC = importlib.util.spec_from_file_location('h4_loader_test', Path(__file__).with_name('load_data.py'))
LOADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOADER)


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root/'cache'
        self.details = [self.detail(1, 2), self.detail(2, installed='Não', aptos=20,
                       turnout=0, abstentions=0, nominal=0, blank=0, null_votes=0, separate=0), self.detail(1)]
        self.votes = []
        for d in self.details:
            if d['QT_COMPARECIMENTO']=='0':
                continue
            for number, quantity in ((13,40),(22,34),(14,0),(95,2),(96,3),(97,1)):
                self.votes.append({**{k:d[k] for k in [*LOADER.KEY_FIELDS,'ANO_ELEICAO','DS_CARGO','SG_UE']},
                                   'NR_VOTAVEL':str(number),'NM_VOTAVEL':f'Candidate {number}','QT_VOTOS':str(quantity)})
        self.write_sources()
        self.pin_sources()

    @staticmethod
    def detail(section, turn=1, installed='Sim', **changes):
        quantities=dict(aptos=100,turnout=80,abstentions=20,nominal=74,blank=2,null_votes=3,legend=0,separate=1)
        quantities.update(changes)
        return dict(ANO_ELEICAO='2026',CD_ELEICAO=str(6256+turn),NR_TURNO=str(turn),SG_UF='SP',
                    CD_MUNICIPIO='71072',NR_ZONA='2',NR_SECAO=str(section),CD_CARGO='1',
                    DS_CARGO='Presidente',SG_UE='BR',NR_LOCAL_VOTACAO='01031',NM_MUNICIPIO='SÃO PAULO',
                    ST_SECAO_INSTALADA=installed,ST_SECAO_ANULADA='Não',
                    DT_PRIM_TOT_PARCIAL_HOR_TSE=f'{4 if turn == 1 else 25:02d}/10/2026 17:08:30',
                    DT_RECEBIMENTO_BU_HOR_TSE=f'{4 if turn == 1 else 25:02d}/10/2026 17:07:20',
                    CD_MODELO_URNA='2022',
                    **{source:str(quantities[field]) for field,source in LOADER.METRICS.items()})

    def write_sources(self):
        for kind, rows in [('details',self.details),('votes',self.votes)]:
            path=self.root/LOADER.SOURCE_PATHS[kind]
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('w',encoding='latin1',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter=';')
                writer.writeheader();writer.writerows(rows)

    def pin_sources(self):
        sources={name:dict(path=relative,size_bytes=(self.root/relative).stat().st_size,
                          sha256=LOADER.sha256(self.root/relative)) for name,relative in LOADER.SOURCE_PATHS.items()}
        stage1=self.root/'reports/2026/input-manifest.json'
        stage1.parent.mkdir(parents=True,exist_ok=True)
        stage1.write_text(json.dumps(dict(status='completed',inputs=sources)))
        h1=stage1.parent/'hypothesis-tests/01-accounting-integrity/evidence/accounting'
        h1.mkdir(parents=True,exist_ok=True)
        scopes=sorted({(int(r['CD_ELEICAO']),int(r['NR_TURNO'])) for r in self.details})
        with (h1/'checks.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['election_code','turno','uf','check','violations','not_comparable'])
            writer.writerows((e,t,'BR',c,0,0) for e,t in scopes for c in LOADER.H1_ESSENTIAL_CHECKS)
        with (h1/'totals.csv').open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['election_code','turno','uf','section_records',*LOADER.METRICS])
            for e,t in scopes:
                rows=[r for r in self.details if int(r['CD_ELEICAO'])==e and int(r['NR_TURNO'])==t]
                writer.writerow([e,t,'BR',len(rows),*(sum(int(r[source]) for r in rows) for source in LOADER.METRICS.values())])
        manifest=dict(status='completed',hypothesis='H1',inputs=sources,
                      artifact_sha256={name:LOADER.sha256(h1/name) for name in ['checks.csv','totals.csv']})
        (h1/'manifest.json').write_text(json.dumps(manifest))

    def load(self):
        with contextlib.redirect_stderr(io.StringIO()):
            return LOADER.load_data(self.root,self.cache)

    def test_sorted_arrays_zero_vote_categories_and_uninstalled_rows_survive_cache(self):
        original={k:(self.root/p).read_bytes() for k,p in LOADER.SOURCE_PATHS.items()}
        data=self.load()
        self.assertFalse(data['cache_reused'])
        self.assertEqual([r['turno'] for r in data['rounds']],[1,2])
        r=data['rounds'][0]
        self.assertEqual(r['section'].tolist(),[1,2])
        self.assertEqual(r['source_line'].tolist(),[4,3])
        self.assertEqual(r['installed'].tolist(),[True,False])
        self.assertEqual(r['candidate_numbers'],[13,14,22])
        self.assertEqual(r['candidate_votes'].tolist(),[[40,0,34],[0,0,0]])
        self.assertEqual(r['candidate_votes'].dtype,np.dtype('int32'))
        self.assertEqual(r['uf'].dtype,np.dtype('U2'))
        self.assertEqual(r['place'].tolist(),[1031,1031])
        self.assertEqual(r['separate'].tolist(),[1,0])
        expected = int((datetime(2026,10,4,17,8,30)-datetime(1970,1,1)).total_seconds())
        self.assertEqual(r['first_time'].tolist(),[expected,expected])
        self.assertEqual(r['bu_time'].tolist(),[expected-70,expected-70])
        self.assertEqual(r['first_time'].dtype,np.dtype('int64'))
        self.assertEqual(r['bu_time'].dtype,np.dtype('int64'))
        self.assertEqual(r['model_urna'].dtype,np.dtype('int32'))
        self.assertEqual(r['model_urna'].tolist(),[2022,2022])
        timing = data['source_counts']['rounds'][0]['timing']['first_time']
        self.assertEqual(timing, dict(valid=2,missing=0,min_seconds=expected,max_seconds=expected,
                                    min_local='2026-10-04 17:08:30',max_local='2026-10-04 17:08:30'))
        self.assertEqual(data['names']['SP:71072'],'SÃO PAULO')
        cached=self.load()
        self.assertTrue(cached['cache_reused'])
        for a,b in zip(data['rounds'],cached['rounds']):
            for field in ['candidate_votes','first_time','bu_time','model_urna']:
                np.testing.assert_array_equal(a[field],b[field])
        self.assertEqual(original,{k:(self.root/p).read_bytes() for k,p in LOADER.SOURCE_PATHS.items()})

    def test_changed_source_cannot_reuse_pinned_cache(self):
        self.load()
        previous=(self.cache/'metadata.json').read_bytes()
        path=self.root/LOADER.SOURCE_PATHS['votes']
        path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'source does not match'):
            self.load()
        self.assertEqual(previous,(self.cache/'metadata.json').read_bytes())

    def test_modified_h1_artifact_is_rejected(self):
        path=self.root/'reports/2026/hypothesis-tests/01-accounting-integrity/evidence/accounting/checks.csv'
        path.write_text(path.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'artifact hash mismatch'):
            self.load()

    def test_duplicate_detail_key_is_detected_even_if_fixture_claims_h1_passed(self):
        self.details.append(dict(self.details[-1]))
        self.write_sources();self.pin_sources()
        with self.assertRaisesRegex(ValueError,'Duplicate normalized detail key'):
            self.load()
        self.assertEqual(json.loads((self.cache/'metadata.json').read_text())['status'],'failed')

    def test_category_error_cannot_hide_behind_correct_nominal_totals(self):
        next(r for r in self.votes if r['NR_VOTAVEL']=='95')['QT_VOTOS']='1'
        self.write_sources();self.pin_sources()
        with self.assertRaisesRegex(ValueError,'category mismatch for blank'):
            self.load()

    def test_unknown_or_tampered_cache_is_preserved_and_refused(self):
        self.cache.mkdir();marker=self.cache/'notes.txt';marker.write_text('keep')
        with self.assertRaisesRegex(ValueError,'unknown/non-completed'):
            self.load()
        self.assertEqual(marker.read_text(),'keep')
        marker.unlink();self.cache.rmdir()
        self.load()
        arrays=self.cache/'arrays.npz';arrays.write_bytes(arrays.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'array hash mismatch'):
            self.load()

    def test_lfs_pointer_is_not_treated_as_an_empty_source(self):
        path=self.root/LOADER.SOURCE_PATHS['votes']
        path.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:123\nsize 1\n')
        with self.assertRaisesRegex(ValueError,'Git LFS pointer'):
            self.load()

    def test_timestamp_day_first_iso_and_post_int32_epoch_are_exact(self):
        expected = int((datetime(2050,12,31,23,59,59)-datetime(1970,1,1)).total_seconds())
        for value in ['31/12/2050 23:59:59','2050-12-31 23:59:59','2050-12-31T23:59:59']:
            with self.subTest(value=value):
                self.assertEqual(LOADER._timestamp(value,'time'),expected)
        self.details[-1]['DT_PRIM_TOT_PARCIAL_HOR_TSE']='31/12/2050 23:59:59'
        self.write_sources(); self.pin_sources()
        r = self.load()['rounds'][0]
        self.assertEqual(int(r['first_time'][0]),expected)
        self.assertGreater(expected,np.iinfo(np.int32).max)

    def test_timestamp_missing_tokens_remain_missing(self):
        for value in ['', ' ', '#NULO', '#NE', '-1', '-3', '#nulo']:
            with self.subTest(value=value):
                self.assertEqual(LOADER._timestamp(value,'time'),-1)

    def test_timestamp_invalid_dates_offsets_precision_and_formats_fail(self):
        for value in ['31/02/2026 17:00:00','10/25/2026 17:00:00','2026-10-25T17:00:00Z',
                      '2026-10-25T17:00:00-03:00','2026-10-25T17:00:00.500',
                      '25/10/2026 17:00','5/10/2026 17:00:00','25/10/2026 24:00:00',
                      'not-a-time','1969-12-31 23:59:59']:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError,'time:'):
                    LOADER._timestamp(value,'time')

    def test_missing_times_and_model_are_reported_without_excluding_rows(self):
        self.details[1]['DT_PRIM_TOT_PARCIAL_HOR_TSE']='#NULO'
        self.details[1]['DT_RECEBIMENTO_BU_HOR_TSE']=''
        self.details[1]['CD_MODELO_URNA']='#NE'
        self.write_sources(); self.pin_sources()
        data=self.load()
        r=data['rounds'][0]
        self.assertEqual(r['first_time'].tolist()[1],-1)
        self.assertEqual(r['bu_time'].tolist()[1],-1)
        self.assertEqual(r['model_urna'].tolist(),[2022,-1])
        self.assertEqual(len(r['aptos']),2)
        counts=data['source_counts']['rounds'][0]
        self.assertEqual(counts['timing']['first_time']['missing'],1)
        self.assertEqual(counts['timing']['first_time']['valid'],1)
        self.assertEqual(counts['missing_model_urna'],1)

    def test_optional_model_column_may_be_absent_but_time_columns_are_required(self):
        for row in self.details:
            del row['CD_MODELO_URNA']
        self.write_sources(); self.pin_sources()
        data=self.load()
        self.assertTrue(all((r['model_urna']==-1).all() for r in data['rounds']))
        self.assertEqual(data['source_counts']['details']['missing_model_urna'],3)
        for row in self.details:
            del row['DT_RECEBIMENTO_BU_HOR_TSE']
        self.write_sources(); self.pin_sources()
        self.cache=self.root/'other-cache'
        with self.assertRaisesRegex(ValueError,'missing columns.*DT_RECEBIMENTO_BU_HOR_TSE'):
            self.load()

    def test_invalid_source_timestamp_does_not_silently_become_missing(self):
        self.details[-1]['DT_PRIM_TOT_PARCIAL_HOR_TSE']='31/02/2026 17:08:30'
        self.write_sources(); self.pin_sources()
        with self.assertRaisesRegex(ValueError,'invalid local timestamp'):
            self.load()
        self.assertEqual(json.loads((self.cache/'metadata.json').read_text())['status'],'failed')

    def test_loader_fingerprint_change_refuses_cache_without_overwrite(self):
        self.load()
        path=self.cache/'metadata.json'
        metadata=json.loads(path.read_text())
        metadata['fingerprint']['loader_code_sha256']='changed-loader'
        path.write_text(json.dumps(metadata))
        before=path.read_bytes()
        with self.assertRaisesRegex(ValueError,'fingerprint differs'):
            self.load()
        self.assertEqual(path.read_bytes(),before)

    def test_timing_summary_retains_all_missing_as_none_range(self):
        self.assertEqual(LOADER._timing_summary(np.array([-1,-1],dtype=np.int64)),
                         dict(valid=0,missing=2,min_seconds=None,max_seconds=None,min_local=None,max_local=None))


if __name__=='__main__':
    unittest.main()
