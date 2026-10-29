"""Small synthetic fixtures for source pinning, reconciliation and H5 caches."""
import contextlib
import csv
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np


SPEC = importlib.util.spec_from_file_location('h5_loader_test', Path(__file__).with_name('load_data.py'))
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
        self.assertEqual(data['names']['SP:71072'],'SÃO PAULO')
        cached=self.load()
        self.assertTrue(cached['cache_reused'])
        for a,b in zip(data['rounds'],cached['rounds']):
            np.testing.assert_array_equal(a['candidate_votes'],b['candidate_votes'])
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

    def test_same_physical_section_stays_separate_by_round_and_election(self):
        data=self.load()
        first,second=data['rounds']
        self.assertEqual((first['election_code'],first['turno']),(6257,1))
        self.assertEqual((second['election_code'],second['turno']),(6258,2))
        for field in ('uf','municipality','zone','section'):
            self.assertEqual(first[field][0],second[field][0])
        self.assertEqual(len(first['aptos']),2)
        self.assertEqual(len(second['aptos']),1)
        self.assertNotEqual(first['source_line'][0],second['source_line'][0])
        self.assertEqual(data['cache_fingerprint']['hypothesis'],'H5')

    def test_polling_place_and_electorate_changes_are_preserved_without_pairing(self):
        second=next(row for row in self.details if row['NR_TURNO']=='2')
        second.update(NR_LOCAL_VOTACAO='02031',QT_APTOS='110',QT_ABSTENCOES='30')
        self.write_sources();self.pin_sources()
        data=self.load()
        first,second=data['rounds']
        self.assertEqual(first['place'][0],1031)
        self.assertEqual(second['place'][0],2031)
        self.assertEqual((first['aptos'][0],second['aptos'][0]),(100,110))
        self.assertEqual((first['abstentions'][0],second['abstentions'][0]),(20,30))

    def test_missing_polling_place_is_not_borrowed_from_the_other_round(self):
        next(row for row in self.details if row['NR_TURNO']=='2')['NR_LOCAL_VOTACAO']='#NULO'
        self.write_sources();self.pin_sources()
        data=self.load()
        self.assertEqual(data['rounds'][0]['place'][0],1031)
        self.assertEqual(data['rounds'][1]['place'][0],-1)
        self.assertEqual(data['source_counts']['details']['missing_place_ids'],1)

    def test_loader_code_fingerprint_change_cannot_reuse_cache(self):
        self.load()
        metadata=self.cache/'metadata.json'
        value=json.loads(metadata.read_text())
        value['fingerprint']['loader_code_sha256']='0'*64
        metadata.write_text(json.dumps(value))
        original=(self.cache/'arrays.npz').read_bytes()
        with self.assertRaisesRegex(ValueError,'fingerprint differs'):
            self.load()
        self.assertEqual(original,(self.cache/'arrays.npz').read_bytes())


if __name__=='__main__':
    unittest.main()
