"""H6 CLI tests with artificial original-format inputs and isolated Git metadata.

Fixture/provenance scaffolding adapted from H5 test_run_analysis.py at commit
 a3362b3ec72c0c567fcf80c5b6761b6cc1cc52c2. Fixture commits are temporary only.
"""
from __future__ import annotations

import csv
from fractions import Fraction
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

import test_load_data as fixtures

SCRIPT = Path(__file__).with_name('run_analysis.py')
HERE = SCRIPT.parent.parent
CANDIDATES = {1:[13,14,16,21,22,27,28,29,30,35,55,70,80],2:[13,22]}
SECOND_VOTES = [160,164,158,170,169,180,175,190,150,155,159,165,161,175,173,180]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    opener = gzip.open if Path(path).suffix=='.gz' else open
    with opener(path,'rt',encoding='utf-8',newline='') as stream:
        return list(csv.DictReader(stream))


class AnalysisCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LoaderTests('test_sorted_arrays_zero_vote_categories_and_uninstalled_rows_survive_cache')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.place_width = 8
        self.constant = False
        self.rebuild()
        subprocess.run(['git','init','--quiet',str(self.root)],check=True,capture_output=True)
        subprocess.run(['git','-c','user.name=H6 synthetic fixture','-c','user.email=h6-fixture@example.invalid',
            '-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null','commit','--quiet','--allow-empty',
            '-m','Artificial H6 CLI fixture'],cwd=self.root,check=True,capture_output=True)

    def add_section(self,section,turn,index=0):
        turnout = 300 if turn==1 else 325 if self.constant else 310+2*index
        nominal = turnout-5
        v13 = 135 if turn==1 else 160 if self.constant else SECOND_VOTES[index%16]
        other = 25 if turn==1 else 0
        detail = self.fixture.detail(section,turn,aptos=400,turnout=turnout,abstentions=400-turnout,
            nominal=nominal,blank=2,null_votes=3,separate=0)
        detail['NR_LOCAL_VOTACAO'] = str(1001+index//self.place_width)
        self.fixture.details.append(detail)
        choices = {13:v13,22:nominal-other-v13,14:other,95:2,96:3,97:0}
        for number in [*CANDIDATES[turn],95,96,97]:
            self.fixture.votes.append({**{key:detail[key] for key in [*fixtures.LOADER.KEY_FIELDS,'ANO_ELEICAO','DS_CARGO','SG_UE']},
                'NR_VOTAVEL':str(number),'NM_VOTAVEL':f'Artificial candidate {number}','QT_VOTOS':str(choices.get(number,0))})

    def rebuild(self):
        self.fixture.details = [];self.fixture.votes = []
        for turn in (1,2):
            for index in range(16) if turn==1 else reversed(range(16)):
                self.add_section(index+1,turn,index)
        self.pin()

    def pin(self):
        self.fixture.write_sources();self.fixture.pin_sources()
        self.original = {kind:(self.root/relative).read_bytes() for kind,relative in fixtures.LOADER.SOURCE_PATHS.items()}

    def cli(self,name,*,workers=1,simulations=19,simulation_cache=None,expect=0):
        output = self.root/name
        cache = self.root/'simulation-cache' if simulation_cache is None else simulation_cache
        environment = dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        result = subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),'--output',str(output),
            '--cache',str(self.root/'data-cache'),'--simulation-cache',str(cache),'--simulations',str(simulations),
            '--seed','20261029','--workers',str(workers)],capture_output=True,text=True,timeout=90,env=environment)
        self.assertEqual(result.returncode,expect,msg=result.stdout+'\n'+result.stderr)
        return output,result

    def assert_sources_preserved(self):
        self.assertEqual(self.original,{kind:(self.root/relative).read_bytes() for kind,relative in fixtures.LOADER.SOURCE_PATHS.items()})

    def expected_assignment(self,model_id,repetition):
        rng = np.random.default_rng(np.random.SeedSequence([20261029,6,model_id],spawn_key=(repetition,)))
        bucket = np.arange(16,dtype=np.int32).reshape(1,16) if model_id==0 else np.arange(16,dtype=np.int32).reshape(2,8)
        return rng.permuted(bucket,axis=1).ravel()

    @staticmethod
    def ranks(values):
        order = sorted(range(len(values)),key=values.__getitem__)
        result = np.empty(len(values),dtype=float)
        left = 0
        while left<len(order):
            right = left+1
            while right<len(order) and values[order[left]]==values[order[right]]:
                right += 1
            result[order[left:right]] = (left+right-1)/2
            left = right
        return result-result.mean()

    def oracle(self,model_id,assigned):
        xs = [Fraction(310+2*i-300,400)*100 for i in range(16)]
        ys = [100*(Fraction(SECOND_VOTES[i],305+2*i)-Fraction(1,2)) for i in range(16)]
        chunks = [list(range(16))] if model_id==0 else [list(range(8)),list(range(8,16))]
        rx,ry,rank_x,rank_y = [np.zeros(16) for _ in range(4)]
        for members in chunks:
            xx = [xs[i] for i in members];yy = [ys[i] for i in members]
            mx,my = sum(xx)/len(xx),sum(yy)/len(yy)
            rx[members] = [float(x-mx) for x in xx]
            ry[members] = [float(y-my) for y in yy]
            rank_x[members] = self.ranks(xx);rank_y[members] = self.ranks(yy)
        return np.array([np.dot(rx,ry[assigned])/np.sqrt(np.dot(rx,rx)*np.dot(ry,ry)),
            np.dot(rank_x,rank_y[assigned])/np.sqrt(np.dot(rank_x,rank_x)*np.dot(rank_y,rank_y))])

    def test_complete_original_pairing_accounting_decomposition_and_four_test_family(self):
        output,_ = self.cli('analysis')
        manifest = json.loads((output/'manifest.json').read_text())
        summary = json.loads((output/'summary.json').read_text())
        self.assertEqual(manifest['status'],'completed')
        self.assertEqual(manifest['method_sha256'],digest(HERE/'METHOD.pt-BR.md'))
        self.assertEqual(manifest['parameters']['family_size'],4)
        self.assertEqual(summary['matched_pairs'],16);self.assertEqual(summary['cohort_pairs'],16)
        self.assertEqual(summary['paired_elections'],[6257,6258])
        self.assertEqual(summary['primary_not_applicable'],0)
        self.assertEqual(manifest['git_base'],subprocess.check_output(['git','rev-parse','HEAD'],cwd=self.root,text=True).strip())
        for name,expected in manifest['implementation_sha256'].items():
            self.assertEqual(expected,digest(SCRIPT.parent/name))
        for name,expected in manifest['artifacts'].items():
            self.assertEqual(expected['sha256'],digest(output/name))
            self.assertEqual(expected['size_bytes'],(output/name).stat().st_size)
        pairs = rows(output/'paired-sections.csv.gz')
        self.assertEqual([int(row['section']) for row in pairs],list(range(1,17)))
        measured = rows(output/'section-measures.csv.gz')
        for i,(pair,m) in enumerate(zip(pairs,measured)):
            self.assertEqual(int(pair['source_line_1']),i+2)
            self.assertEqual(int(pair['source_line_2']),33-i)
            self.assertEqual(int(pair['v13_2']),SECOND_VOTES[i])
            self.assertEqual(int(pair['f_1']),270)
            self.assertEqual(int(pair['f_2']),305+2*i)
            self.assertEqual(pair['eligible'],'True')
            self.assertAlmostEqual(float(m['x']),2.5+i/2,places=12)
            self.assertAlmostEqual(float(m['y']),100*(SECOND_VOTES[i]/(305+2*i)-.5),places=12)
            for c in (13,22):
                self.assertAlmostEqual(float(m[f'gain{c}_aptos_pp']),float(m[f'turnout{c}_component_pp'])+float(m[f'composition{c}_component_pp']),places=11)
                self.assertAlmostEqual(float(m[f'gain{c}_count']),float(m[f'gain{c}_equiv_votes']),places=11)
            self.assertEqual(m['support_zone_baseline'],'True');self.assertEqual(m['support_place_baseline'],'True')
        national = next(row for row in rows(output/'totals.csv') if row['scope_type']=='BR')
        self.assertEqual(int(national['identity_residual']),0)
        self.assertEqual(int(national['finalist_gain']),int(national['turnout_change'])-int(national['other_and_special_change']))
        self.assertEqual(sum(int(row['sections']) for row in rows(output/'heatmap.csv')),16)
        for scope in ('BR','UF','region'):
            self.assertEqual(sum(int(row['sections']) for row in rows(output/'x-bins.csv') if row['scope_type']==scope),16)
        tests = rows(output/'tests.csv')
        self.assertEqual({(row['model'],row['statistic']) for row in tests},{(m,s) for m in ('zone_baseline','place_baseline') for s in ('linear','rank')})
        ps = np.asarray([float(row['p_raw']) for row in tests]);order = np.argsort(ps,kind='stable')
        adjusted = np.minimum(1,np.maximum.accumulate(ps[order]*np.arange(4,0,-1)))
        for rank,index in enumerate(order):
            self.assertEqual(float(tests[index]['p_raw']),(1+int(tests[index]['exceedances']))/20)
            self.assertEqual(float(tests[index]['p_holm']),adjusted[rank])
        for entry in manifest['simulation_caches']:
            directory = self.root/entry['path'];metadata = entry['metadata']
            self.assertEqual(entry['metadata_sha256'],digest(directory/'metadata.json'))
            self.assertEqual(metadata['scores_sha256'],digest(directory/'scores.npy'))
            scores = np.load(directory/'scores.npy',allow_pickle=False)
            self.assertEqual(scores.shape,(19,2))
            for rep in (0,1):
                assigned = self.expected_assignment(metadata['model_id'],rep)
                self.assertEqual(metadata['assignment_prefix'][str(rep)],hashlib.sha256(assigned.astype('<i4').tobytes()).hexdigest())
                np.testing.assert_allclose(scores[rep],self.oracle(metadata['model_id'],assigned),atol=1e-12,rtol=1e-12)
        published_scores = rows(output/'permutation-scores.csv.gz')
        self.assertEqual(len(published_scores),38)
        for entry in manifest['simulation_caches']:
            cached_scores = np.load(self.root/entry['path']/'scores.npy',allow_pickle=False)
            selected = [row for row in published_scores if row['model']==entry['metadata']['model']]
            self.assertEqual([int(row['repetition']) for row in selected],list(range(19)))
            np.testing.assert_array_equal([[float(row['rho_linear']),float(row['rho_rank'])] for row in selected],cached_scores)
        self.assertEqual(len(rows(output/'sensitivity.csv')),14)
        self.assert_sources_preserved()

    def test_workers_and_cache_reuse_preserve_every_numerical_artifact(self):
        first,_ = self.cli('serial',workers=1,simulations=53)
        second,_ = self.cli('parallel',workers=2,simulations=53,simulation_cache=self.root/'parallel-cache')
        numerical = sorted(path.name for path in first.iterdir() if path.name!='manifest.json')
        for name in numerical:
            self.assertEqual((first/name).read_bytes(),(second/name).read_bytes(),name)
        paths = sorted((self.root/'simulation-cache').rglob('*.npy'))
        before = {str(path):(path.stat().st_mtime_ns,path.read_bytes()) for path in paths}
        third,result = self.cli('reused',workers=2,simulations=53)
        self.assertNotIn('53/53',result.stdout)
        self.assertEqual(before,{str(path):(path.stat().st_mtime_ns,path.read_bytes()) for path in paths})
        for name in numerical:
            self.assertEqual((first/name).read_bytes(),(third/name).read_bytes(),name)
        self.assert_sources_preserved()

    def test_constant_marginal_measures_are_not_applicable_not_negative_findings(self):
        self.constant = True;self.rebuild()
        output,_ = self.cli('constant')
        summary = json.loads((output/'summary.json').read_text())
        self.assertEqual(summary['primary_not_applicable'],4)
        self.assertEqual(summary['primary_detected'],0);self.assertEqual(summary['primary_not_detected'],0)
        for row in rows(output/'tests.csv'):
            self.assertEqual(row['status'],'not_applicable')
            self.assertEqual(row['applicability_reason'],'no_informative_groups')
            self.assertEqual(row['p_raw'],'');self.assertEqual(row['p_holm'],'')
        for row in rows(output/'section-measures.csv.gz'):
            self.assertEqual(float(row['y']),0.)
            self.assertEqual(row['support_zone_baseline'],'False');self.assertEqual(row['support_place_baseline'],'False')
        self.assert_sources_preserved()

    def test_singleton_places_do_not_borrow_support_from_the_zone_reference(self):
        self.place_width = 1;self.rebuild()
        output,_ = self.cli('singletons')
        result = rows(output/'tests.csv')
        self.assertTrue(all(row['status']=='not_applicable' for row in result if row['model']=='place_baseline'))
        self.assertTrue(all(row['status']!='not_applicable' for row in result if row['model']=='zone_baseline'))
        for row in rows(output/'section-measures.csv.gz'):
            self.assertEqual(row['support_zone_baseline'],'True');self.assertEqual(row['support_place_baseline'],'False')
        self.assert_sources_preserved()

    def test_unmatched_sections_are_counted_in_raw_totals_but_not_the_cohort(self):
        self.add_section(99,1);self.add_section(98,2);self.pin()
        output,_ = self.cli('unmatched')
        overall = next(row for row in rows(output/'pairing.csv') if row['uf']=='BR')
        self.assertEqual((int(overall['round1_records']),int(overall['round2_records']),int(overall['matched_pairs'])),(17,17,16))
        self.assertEqual({(row['present_in_round'],row['section']) for row in rows(output/'unmatched.csv')},{('1','99'),('2','98')})
        totals = next(row for row in rows(output/'totals.csv') if row['scope_type']=='BR')
        self.assertEqual(int(totals['sections_1']),17);self.assertEqual(int(totals['sections_2']),17)
        self.assertEqual(len(rows(output/'section-measures.csv.gz')),16)
        self.assert_sources_preserved()

    def test_existing_outputs_bad_cli_and_corrupted_simulation_cache_are_preserved(self):
        folder = self.root/'existing';folder.mkdir()
        marker = folder/'keep.txt';marker.write_text('Preserve existing evidence.\n');before = marker.read_bytes()
        _,result = self.cli('existing',expect=2)
        self.assertIn('Refusing a nonempty output directory',result.stderr)
        self.assertEqual(marker.read_bytes(),before);self.assertEqual(list(folder.iterdir()),[marker])
        for name,kwargs in [('zero',dict(simulations=0)),('workers',dict(workers=5))]:
            _,result = self.cli(name,expect=2,**kwargs)
            self.assertIn('Use positive simulations and 1–4 workers',result.stderr)
            self.assertFalse((self.root/name).exists())
        self.cli('valid')
        path = self.root/'simulation-cache/zone_baseline/scores.npy'
        changed = path.read_bytes()+b'preserve tamper marker';path.write_bytes(changed)
        _,result = self.cli('must-fail',expect=1)
        self.assertIn('Incomplete, different or corrupted simulation cache',result.stderr)
        self.assertEqual(path.read_bytes(),changed)
        self.assert_sources_preserved()


if __name__=='__main__':
    unittest.main()
