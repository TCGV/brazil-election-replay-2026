"""End-to-end CLI controls on original-format, explicitly synthetic CSVs.

The temporary fixture has its own Git repository. Its empty commit supplies
provenance to the CLI and never changes the user's repository or election data.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

import test_load_data as fixtures


SCRIPT = Path(__file__).with_name('run_analysis.py')
HERE = SCRIPT.parent.parent
CANDIDATES = {1: [13,14,16,21,22,27,28,29,30,35,55,70,80], 2: [13,22]}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_rows(path):
    path = Path(path)
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


class AnalysisCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LoaderTests('test_sorted_arrays_zero_vote_categories_and_uninstalled_rows_survive_cache')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.fixture.details = []
        self.fixture.votes = []
        for turn in (1,2):
            base = datetime(2026,10,4 if turn == 1 else 25,17,0)
            for index in range(8):
                row = self.fixture.detail(index+1,turn,aptos=200,turnout=155,abstentions=45,
                                          nominal=150,blank=2,null_votes=3,separate=0)
                row['NR_LOCAL_VOTACAO'] = str(1001+index//4)
                row['DT_PRIM_TOT_PARCIAL_HOR_TSE'] = (base+timedelta(minutes=index//2,seconds=30)).strftime('%d/%m/%Y %H:%M:%S')
                row['DT_RECEBIMENTO_BU_HOR_TSE'] = (base+timedelta(minutes=(7-index)//2,seconds=10)).strftime('%d/%m/%Y %H:%M:%S')
                self.fixture.details.append(row)
                choices = {13:40+10*index,22:110-10*index,95:2,96:3,97:0}
                for number in [*CANDIDATES[turn],95,96,97]:
                    self.fixture.votes.append({
                        **{key:row[key] for key in [*fixtures.LOADER.KEY_FIELDS,'ANO_ELEICAO','DS_CARGO','SG_UE']},
                        'NR_VOTAVEL':str(number),'NM_VOTAVEL':f'Synthetic candidate {number}',
                        'QT_VOTOS':str(choices.get(number,0)),
                    })
        self.fixture.write_sources()
        self.fixture.pin_sources()
        self.original = {name:(self.root/relative).read_bytes()
                         for name,relative in fixtures.LOADER.SOURCE_PATHS.items()}
        subprocess.run(['git','init','--quiet',str(self.root)],check=True,capture_output=True)
        subprocess.run(['git','-c','user.name=H4 synthetic fixture',
                        '-c','user.email=h4-fixture@example.invalid','-c','commit.gpgsign=false',
                        '-c','core.hooksPath=/dev/null','commit','--quiet','--allow-empty',
                        '-m','Synthetic H4 integration fixture'],cwd=self.root,check=True,capture_output=True)

    def run_cli(self, name, *, workers=1, simulations=7, simulation_cache=None, expect=0):
        output = self.root/name
        cache = self.root/'simulation-cache' if simulation_cache is None else simulation_cache
        result = subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),
            '--output',str(output),'--cache',str(self.root/'data-cache'),
            '--simulation-cache',str(cache),'--simulations',str(simulations),'--seed','20261028',
            '--workers',str(workers)],capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,expect,msg=result.stdout+'\n'+result.stderr)
        return output,result

    def assert_sources_preserved(self):
        self.assertEqual(self.original,{name:(self.root/relative).read_bytes()
                                       for name,relative in fixtures.LOADER.SOURCE_PATHS.items()})

    def test_cli_publishes_fixed_family_reconciled_gzip_and_provenance(self):
        output,_ = self.run_cli('analysis')
        manifest = json.loads((output/'manifest.json').read_text())
        summary = json.loads((output/'summary.json').read_text())
        self.assertEqual(manifest['status'],'completed')
        self.assertEqual(manifest['method_sha256'],digest(HERE/'METHOD.pt-BR.md'))
        self.assertEqual(manifest['parameters']['family_size'],90)
        self.assertEqual(manifest['parameters']['simulations'],7)
        self.assertEqual(manifest['parameters']['workers'],1)
        expected_git = subprocess.check_output(['git','rev-parse','HEAD'],cwd=self.root,text=True).strip()
        self.assertEqual(manifest['git_base'],expected_git)
        for name,expected in manifest['implementation_sha256'].items():
            self.assertEqual(expected,digest(SCRIPT.parent/name))
        for name,expected in manifest['artifacts'].items():
            self.assertEqual(expected['sha256'],digest(output/name))
            self.assertEqual(expected['size_bytes'],(output/name).stat().st_size)
        for name,relative in fixtures.LOADER.SOURCE_PATHS.items():
            self.assertEqual(manifest['source_inputs'][name]['sha256'],digest(self.root/relative))
        self.assertEqual(summary['candidate_numbers'],{str(k):v for k,v in CANDIDATES.items()})
        self.assertEqual(summary['family_size'],90)
        self.assertEqual(summary['primary_not_applicable'],66)
        self.assertEqual(summary['primary_detected'],0)
        self.assertEqual(summary['primary_not_detected'],24)

        tests = read_rows(output/'tests.csv')
        self.assertEqual(len(tests),90)
        keys = {(r['model'],r['turno'],r['candidate'],r['statistic']) for r in tests}
        self.assertEqual(len(keys),90)
        for row in tests:
            self.assertEqual(int(row['simulations']),7)
            if row['candidate'] not in {'13','22'}:
                self.assertEqual(row['status'],'not_applicable')
                self.assertEqual(row['p_raw'],'')
                self.assertEqual(row['p_holm'],'')
                self.assertEqual(row['detected'],'')
                self.assertEqual(float(row['observed']),0.0)
                self.assertEqual(int(row['informative_sections']),0)
            else:
                self.assertEqual(float(row['p_raw']),(int(row['exceedances'])+1)/8)
                self.assertGreaterEqual(float(row['p_holm']),float(row['p_raw']))
                self.assertEqual(int(row['informative_sections']),8)

        curves = read_rows(output/'curves.csv.gz')
        self.assertEqual(len(curves),240)
        for row in curves:
            self.assertAlmostEqual(float(row['share'])-float(row['composition_share']),
                                   float(row['residual_current_pp']),places=11)
            if int(row['sections_cumulative']) == 8:
                self.assertEqual(int(row['nominal_cumulative']),1200)
                self.assertAlmostEqual(float(row['residual_cumulative']),0.0,places=10)
        groups = read_rows(output/'group-totals.csv.gz')
        self.assertEqual(len(groups),6)
        self.assertEqual(sum(int(r['n']) for r in groups),32)
        self.assertEqual(sum(int(r['nominal_total']) for r in groups),4800)
        self.assertEqual(len(read_rows(output/'bands.csv')),6060)
        for entry in manifest['simulation_caches']:
            directory = self.root/entry['path']
            self.assertEqual(entry['metadata_sha256'],digest(directory/'metadata.json'))
            self.assertEqual(entry['metadata']['status'],'completed')
            for name,expected in entry['metadata']['sha256'].items():
                self.assertEqual(expected,digest(directory/name))
            scores = np.load(directory/'scores.npy',allow_pickle=False)
            turn = int(entry['metadata']['turno'])
            self.assertEqual(scores.shape,(7,2,len(CANDIDATES[turn]),3))
        self.assert_sources_preserved()

    def test_cli_worker_count_and_completed_cache_reuse_preserve_numeric_evidence(self):
        first,_ = self.run_cli('serial',workers=1)
        cache_parallel = self.root/'parallel-simulations'
        second,_ = self.run_cli('parallel',workers=2,simulation_cache=cache_parallel)
        numeric = sorted(path.name for path in first.iterdir() if path.name != 'manifest.json')
        self.assertEqual(numeric,sorted(path.name for path in second.iterdir() if path.name != 'manifest.json'))
        for name in numeric:
            if name.endswith('.json'):
                # The loader's canonical cache may reorder mapping keys; the
                # decoded numerical/provenance content must remain identical.
                self.assertEqual(json.loads((first/name).read_text()),json.loads((second/name).read_text()),msg=name)
            else:
                self.assertEqual((first/name).read_bytes(),(second/name).read_bytes(),msg=name)
        simulation_files = sorted((self.root/'simulation-cache').rglob('*.npy'))
        before = {str(path):(path.stat().st_mtime_ns,path.read_bytes()) for path in simulation_files}
        third,result = self.run_cli('cached',workers=2)
        self.assertNotIn('7/7',result.stdout)
        self.assertEqual(before,{str(path):(path.stat().st_mtime_ns,path.read_bytes()) for path in simulation_files})
        for name in numeric:
            if name.endswith('.json'):
                self.assertEqual(json.loads((first/name).read_text()),json.loads((third/name).read_text()),msg=name)
            else:
                self.assertEqual((first/name).read_bytes(),(third/name).read_bytes(),msg=name)
        self.assert_sources_preserved()

    def test_cli_refuses_nonempty_output_and_invalid_parameters(self):
        output = self.root/'keep-existing'
        output.mkdir()
        marker = output/'keep.txt'
        marker.write_text('This existing evidence must survive.\n')
        before = marker.read_bytes()
        _,result = self.run_cli('keep-existing',expect=2)
        self.assertIn('Refusing a nonempty output directory',result.stderr)
        self.assertEqual(marker.read_bytes(),before)
        self.assertEqual(list(output.iterdir()),[marker])
        for name,arguments in [('zero-simulations',dict(simulations=0)),('too-many-workers',dict(workers=5))]:
            _,result = self.run_cli(name,expect=2,**arguments)
            self.assertIn('Use positive simulations and 1–4 workers',result.stderr)
            self.assertFalse((self.root/name).exists())
        self.assert_sources_preserved()

    def test_all_singleton_strata_are_reported_as_noninformative(self):
        for row in self.fixture.details:
            row['NR_ZONA'] = row['NR_SECAO']
        for row in self.fixture.votes:
            row['NR_ZONA'] = row['NR_SECAO']
        self.fixture.write_sources()
        self.fixture.pin_sources()
        self.original = {name:(self.root/relative).read_bytes()
                         for name,relative in fixtures.LOADER.SOURCE_PATHS.items()}
        output,_ = self.run_cli('singletons')
        summary = json.loads((output/'summary.json').read_text())
        self.assertEqual(summary['primary_not_applicable'],90)
        self.assertEqual(summary['primary_detected'],0)
        self.assertEqual(summary['primary_not_detected'],0)
        tests = read_rows(output/'tests.csv')
        self.assertTrue(all(row['status']=='not_applicable' and row['p_raw']=='' for row in tests))
        spans = read_rows(output/'span-summary.csv')
        self.assertEqual(len(spans),8)
        for row in spans:
            self.assertEqual(int(row['nonsingleton_groups']),0)
            self.assertTrue(all(row[key]=='' for key in ('span_min','span_q25','span_median','span_q75','span_q95','span_max')))
        self.assert_sources_preserved()


if __name__ == '__main__':
    unittest.main()
