"""H5 CLI controls on explicitly artificial, original-format source snapshots.

Each fixture has an isolated temporary Git repository for provenance. Its empty
commit never changes the user's repository or real election observations.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

import test_load_data as fixtures

SCRIPT=Path(__file__).with_name('run_analysis.py')
HERE=SCRIPT.parent.parent
CANDIDATES={1:[13,14,16,21,22,27,28,29,30,35,55,70,80],2:[13,22]}
SECOND_VOTES=[110,112,108,109,111,113,107,150,92,95,98,100,102,104,106,108]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    opener=gzip.open if Path(path).suffix=='.gz' else open
    with opener(path,'rt',encoding='utf-8',newline='') as stream:
        return list(csv.DictReader(stream))


class AnalysisCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.LoaderTests('test_sorted_arrays_zero_vote_categories_and_uninstalled_rows_survive_cache')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        self.fixture.details=[];self.fixture.votes=[]
        self.second_votes=list(SECOND_VOTES)
        self.place_width=8
        self.rebuild()
        subprocess.run(['git','init','--quiet',str(self.root)],check=True,capture_output=True)
        subprocess.run(['git','-c','user.name=H5 synthetic fixture',
            '-c','user.email=h5-fixture@example.invalid','-c','commit.gpgsign=false',
            '-c','core.hooksPath=/dev/null','commit','--quiet','--allow-empty',
            '-m','Synthetic H5 CLI fixture'],cwd=self.root,check=True,capture_output=True)

    def add_section(self,section,turn,v13,place):
        detail=self.fixture.detail(section,turn,aptos=300,turnout=205,abstentions=95,
                                   nominal=200,blank=2,null_votes=3,separate=0)
        detail['NR_LOCAL_VOTACAO']=str(place)
        self.fixture.details.append(detail)
        choices={13:v13,22:180-v13 if turn==1 else 200-v13,14:20 if turn==1 else 0,95:2,96:3,97:0}
        for number in [*CANDIDATES[turn],95,96,97]:
            self.fixture.votes.append({
                **{key:detail[key] for key in [*fixtures.LOADER.KEY_FIELDS,'ANO_ELEICAO','DS_CARGO','SG_UE']},
                'NR_VOTAVEL':str(number),'NM_VOTAVEL':f'Synthetic candidate {number}',
                'QT_VOTOS':str(choices.get(number,0)),
            })

    def rebuild(self):
        self.fixture.details=[];self.fixture.votes=[]
        for turn in (1,2):
            # Reverse round 2 input order: a positional zip must not pass as a
            # physical-key match, and source-line provenance must remain usable.
            indices=range(16) if turn==1 else reversed(range(16))
            for index in indices:
                self.add_section(index+1,turn,90 if turn==1 else self.second_votes[index],
                                 1001+index//self.place_width)
        self.pin()

    def pin(self):
        self.fixture.write_sources();self.fixture.pin_sources()
        self.original={kind:(self.root/relative).read_bytes()
                       for kind,relative in fixtures.LOADER.SOURCE_PATHS.items()}

    def cli(self,name,*,workers=1,simulations=19,simulation_cache=None,expect=0):
        output=self.root/name
        cache=self.root/'simulation-cache' if simulation_cache is None else simulation_cache
        result=subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),
            '--output',str(output),'--cache',str(self.root/'data-cache'),
            '--simulation-cache',str(cache),'--simulations',str(simulations),
            '--seed','20261029','--workers',str(workers)],capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,expect,msg=result.stdout+'\n'+result.stderr)
        return output,result

    def assert_sources_preserved(self):
        self.assertEqual(self.original,{kind:(self.root/relative).read_bytes()
                                       for kind,relative in fixtures.LOADER.SOURCE_PATHS.items()})

    def expected_assignment(self,model_id,repetition):
        rng=np.random.default_rng(np.random.SeedSequence([20261029,model_id],spawn_key=(repetition,)))
        return rng.permuted(np.arange(16,dtype=np.int32)[None,:],axis=1).ravel()

    def test_original_pair_trace_leave_one_out_and_fixed_four_test_family(self):
        output,_=self.cli('analysis')
        manifest=json.loads((output/'manifest.json').read_text())
        summary=json.loads((output/'summary.json').read_text())
        self.assertEqual(manifest['status'],'completed')
        self.assertEqual(manifest['method_sha256'],digest(HERE/'METHOD.pt-BR.md'))
        self.assertEqual(manifest['parameters']['family_size'],4)
        self.assertEqual(manifest['parameters']['simulations'],19)
        self.assertEqual(summary['matched_pairs'],16)
        self.assertEqual(summary['cohort_pairs'],16)
        self.assertEqual(summary['paired_elections'],[6257,6258])
        self.assertEqual(summary['primary_not_applicable'],0)
        expected_git=subprocess.check_output(['git','rev-parse','HEAD'],cwd=self.root,text=True).strip()
        self.assertEqual(manifest['git_base'],expected_git)
        for name,expected in manifest['implementation_sha256'].items():
            self.assertEqual(expected,digest(SCRIPT.parent/name))
        for name,expected in manifest['artifacts'].items():
            self.assertEqual(expected['sha256'],digest(output/name))
            self.assertEqual(expected['size_bytes'],(output/name).stat().st_size)

        pairs=rows(output/'paired-sections.csv.gz')
        self.assertEqual(len(pairs),16)
        self.assertEqual([int(row['section']) for row in pairs],list(range(1,17)))
        for i,row in enumerate(pairs):
            self.assertEqual(int(row['source_line_1']),i+2)
            self.assertEqual(int(row['source_line_2']),33-i)
            self.assertEqual(int(row['v13_2']),SECOND_VOTES[i])
            self.assertEqual(int(row['other_nominal_1']),20)
            self.assertEqual(int(row['f_1']),180)
            self.assertEqual(int(row['f_2']),200)
            self.assertEqual(row['eligible'],'True')
            self.assertAlmostEqual(float(row['delta_pp']),SECOND_VOTES[i]/2-50,places=11)
            self.assertAlmostEqual(float(row['dp13_pp'])-float(row['dp22_pp']),
                                   2*float(row['delta_pp']),places=11)
        section_rows=rows(output/'section-screening.csv.gz')
        self.assertEqual(len(section_rows),16)
        target=next(row for row in section_rows if row['section']=='8')
        expected_delta=np.asarray(SECOND_VOTES,dtype=float)/2-50
        expected_other_median=float(np.median(expected_delta[:7]))
        self.assertEqual(int(target['strict_peer_count']),7)
        self.assertEqual(float(target['strict_median']),expected_other_median)
        self.assertEqual(float(target['strict_contrast']),25-expected_other_median)
        self.assertEqual(target['strict_priority'],'True')
        self.assertEqual(target['priority_candidate'],'13')
        self.assertNotEqual(float(target['strict_median']),float(np.median(expected_delta[:8])))
        self.assertEqual(sum(int(row['sections']) for row in rows(output/'transition-grid.csv')),16)

        tests=rows(output/'tests.csv')
        self.assertEqual({(row['model'],row['statistic']) for row in tests},
                         {(model,stat) for model in ['zone_size','zone_size_baseline'] for stat in ['RMS','MAX']})
        self.assertTrue(all(row['status'] in {'detected','not_detected'} for row in tests))
        p=np.asarray([float(row['p_raw']) for row in tests]);order=np.argsort(p,kind='stable')
        adjusted=np.minimum(1,np.maximum.accumulate(p[order]*np.arange(4,0,-1)))
        for rank,index in enumerate(order):
            row=tests[index]
            self.assertEqual(float(row['p_raw']),(1+int(row['exceedances']))/20)
            self.assertEqual(float(row['p_holm']),adjusted[rank])
        for entry in manifest['simulation_caches']:
            directory=self.root/entry['path'];metadata=entry['metadata']
            self.assertEqual(entry['metadata_sha256'],digest(directory/'metadata.json'))
            self.assertEqual(metadata['scores_sha256'],digest(directory/'scores.npy'))
            scores=np.load(directory/'scores.npy',allow_pickle=False)
            self.assertEqual(scores.shape,(19,2))
            residual=expected_delta-expected_delta.mean()
            for rep in (0,1):
                assigned=self.expected_assignment(metadata['model_id'],rep)
                self.assertEqual(metadata['assignment_prefix'][str(rep)],
                                 hashlib.sha256(assigned.astype('<i4').tobytes()).hexdigest())
                self.assertEqual(sorted(assigned.tolist()),list(range(16)))
                sums=np.array([residual[assigned[:8]].sum(),residual[assigned[8:]].sum()])
                oracle=np.array([np.sqrt(np.sum(sums*sums/8)/16),np.max(abs(sums)/np.sqrt(8))])
                np.testing.assert_allclose(scores[rep],oracle,atol=1e-12,rtol=1e-12)
        self.assert_sources_preserved()

    def test_workers_and_cache_reuse_keep_all_numerical_evidence_identical(self):
        first,_=self.cli('serial',workers=1,simulations=53)
        second,_=self.cli('parallel',workers=2,simulations=53,simulation_cache=self.root/'parallel-cache')
        numerical=sorted(path.name for path in first.iterdir() if path.name!='manifest.json')
        for name in numerical:
            if name.endswith('.json'):
                self.assertEqual(json.loads((first/name).read_text()),json.loads((second/name).read_text()),name)
            else:
                self.assertEqual((first/name).read_bytes(),(second/name).read_bytes(),name)
        cached=sorted((self.root/'simulation-cache').rglob('*.npy'))
        before={str(path):(path.stat().st_mtime_ns,path.read_bytes()) for path in cached}
        third,result=self.cli('reused',workers=2,simulations=53)
        self.assertNotIn('53/53',result.stdout)
        self.assertEqual(before,{str(path):(path.stat().st_mtime_ns,path.read_bytes()) for path in cached})
        for name in numerical:
            if name.endswith('.json'):
                self.assertEqual(json.loads((first/name).read_text()),json.loads((third/name).read_text()),name)
            else:
                self.assertEqual((first/name).read_bytes(),(third/name).read_bytes(),name)
        self.assert_sources_preserved()

    def test_constant_paired_change_is_na_without_dividing_by_zero(self):
        self.second_votes=[100]*16;self.rebuild()
        output,_=self.cli('constant')
        summary=json.loads((output/'summary.json').read_text())
        self.assertEqual(summary['primary_not_applicable'],4)
        self.assertEqual(summary['primary_detected'],0)
        self.assertEqual(summary['primary_not_detected'],0)
        for row in rows(output/'tests.csv'):
            self.assertEqual(row['status'],'not_applicable')
            self.assertEqual(row['applicability_reason'],'no_movable_variable_groups')
            self.assertEqual(row['p_raw'],'');self.assertEqual(row['p_holm'],'')
            self.assertEqual(float(row['observed']),0.0)
        for row in rows(output/'section-screening.csv.gz'):
            self.assertEqual(float(row['delta_pp']),0.0)
            self.assertEqual(float(row['strict_contrast']),0.0)
            self.assertEqual(row['strict_priority'],'False')
        self.assert_sources_preserved()

    def test_places_without_target_size_are_na_and_have_empty_peer_references(self):
        self.place_width=4;self.rebuild()
        output,_=self.cli('no-targets')
        summary=json.loads((output/'summary.json').read_text())
        self.assertEqual(summary['cohort_pairs'],16)
        self.assertEqual(summary['primary_not_applicable'],4)
        for row in rows(output/'tests.csv'):
            self.assertEqual(row['status'],'not_applicable')
            self.assertEqual(row['applicability_reason'],'no_targets')
            self.assertEqual(row['p_raw'],'');self.assertEqual(row['p_holm'],'')
        for row in rows(output/'section-screening.csv.gz'):
            self.assertEqual(int(row['strict_peer_count']),3)
            self.assertEqual(row['strict_median'],'')
            self.assertEqual(row['strict_contrast'],'')
            self.assertEqual(row['strict_priority'],'False')
        self.assert_sources_preserved()

    def test_unmatched_keys_are_reported_without_fabricated_changes(self):
        self.add_section(99,1,90,1999)
        self.add_section(98,2,100,1998)
        self.pin()
        output,_=self.cli('unmatched')
        overall=next(row for row in rows(output/'pairing.csv') if row['uf']=='BR')
        self.assertEqual(int(overall['round1_records']),17)
        self.assertEqual(int(overall['round2_records']),17)
        self.assertEqual(int(overall['matched_pairs']),16)
        self.assertEqual((int(overall['only_round1']),int(overall['only_round2'])),(1,1))
        self.assertEqual({(row['present_in_round'],row['section']) for row in rows(output/'unmatched.csv')},
                         {('1','99'),('2','98')})
        self.assertEqual(len(rows(output/'paired-sections.csv.gz')),16)
        self.assertEqual(len(rows(output/'section-screening.csv.gz')),16)
        self.assert_sources_preserved()

    def test_existing_outputs_and_invalid_cli_parameters_are_preserved(self):
        folder=self.root/'existing';folder.mkdir()
        marker=folder/'keep.txt';marker.write_text('Existing evidence stays intact.\n')
        before=marker.read_bytes()
        _,result=self.cli('existing',expect=2)
        self.assertIn('Refusing a nonempty output directory',result.stderr)
        self.assertEqual(marker.read_bytes(),before)
        self.assertEqual(list(folder.iterdir()),[marker])
        for name,kwargs in [('zero-simulations',dict(simulations=0)),('worker-limit',dict(workers=5))]:
            _,result=self.cli(name,expect=2,**kwargs)
            self.assertIn('Use positive simulations and 1–4 workers',result.stderr)
            self.assertFalse((self.root/name).exists())
        self.assert_sources_preserved()


if __name__=='__main__':
    unittest.main()
