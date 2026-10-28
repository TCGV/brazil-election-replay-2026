"""Small source-to-publication controls for H3; fixtures are artificial."""
from contextlib import redirect_stderr, redirect_stdout
import csv
from fractions import Fraction
import gzip
import importlib.util
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('h3_primary_runner', HERE/'run_analysis.py')
RUN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN)
FIXTURE_SPEC = importlib.util.spec_from_file_location('h3_source_fixture_helpers', HERE/'test_load_data.py')
FIXTURES = importlib.util.module_from_spec(FIXTURE_SPEC)
FIXTURE_SPEC.loader.exec_module(FIXTURES)


def read_rows(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


class RunnerControls(unittest.TestCase):
    def test_labeled_fastpaths_match_direct_matrix_counts_on_selected_rows(self):
        from collision_statistics import stratum_statistics
        fixtures = [
            ([0], [0]),
            ([0,0], [0,0]),
            ([0,1], [0,0]),
            ([0,0], [0,1]),
            ([0,0,1], [0,1,0]),
            ([0,0,1], [0,0,1]),
            ([0,0,1,1], [0,0,1,1]),
            (list(range(40)), [i//4 for i in range(40)]),
            ([0]*40, [i//4 for i in range(40)]),
            ([i//4 for i in range(40)], [0]*40),
            ([0]*10+list(range(1,91)), [0]*10+list(range(1,91))),
        ]
        for a_values, b_values in fixtures:
            with self.subTest(a=a_values, b=b_values):
                n = len(a_values)
                # Interleaved outside rows ensure global labels and restricted
                # IDs work even when labels are nonconsecutive in the stratum.
                ids = np.arange(0, 2*n, 2)
                a = np.column_stack([np.arange(2*n+1)+1000, np.zeros(2*n+1, dtype=int)])
                b = np.column_stack([np.arange(2*n+1)+2000, np.zeros(2*n+1, dtype=int)])
                a[ids, 0] = a_values
                b[ids, 0] = b_values
                a_labels = np.unique(a, axis=0, return_inverse=True)[1]
                b_labels = np.unique(b, axis=0, return_inverse=True)[1]
                full_labels = np.unique(np.column_stack((a,b)), axis=0, return_inverse=True)[1]
                actual = RUN.labeled_statistics(a_labels, b_labels, full_labels, ids)
                expected = stratum_statistics(a[ids], b[ids])
                for field in ('n','a_unique','b_unique','a_pairs','b_pairs','observed_pairs'):
                    self.assertEqual(actual[field], expected[field], field)
                self.assertEqual(actual['mean'], expected['expected_pairs'])
                self.assertEqual(actual['var'], expected['variance'])
                self.assertIsInstance(actual['mean'], Fraction)
                self.assertIsInstance(actual['var'], Fraction)

    def test_original_csv_run_exports_every_view_signature_and_round(self):
        fixture = FIXTURES.LoaderTests('test_lfs_pointer_is_not_treated_as_an_empty_source')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.details = []
        for turn in (1, 2):
            fixture.details.extend([
                fixture.detail(1, turn), fixture.detail(2, turn),
                fixture.detail(3, turn, installed='Não', aptos=20, turnout=0, abstentions=0,
                               nominal=0, blank=0, null_votes=0, separate=0),
                fixture.detail(4, turn, installed='Não', aptos=30, turnout=0, abstentions=0,
                               nominal=0, blank=0, null_votes=0, separate=0),
                fixture.detail(5, turn, aptos=20, turnout=8, abstentions=12,
                               nominal=6, blank=1, null_votes=1, separate=0),
                fixture.detail(6, turn, aptos=20, turnout=8, abstentions=12,
                               nominal=6, blank=1, null_votes=1, separate=0),
                fixture.detail(7, turn, installed='Não'), fixture.detail(8, turn, installed='Não'),
            ])
        fixture.votes = []
        for detail in fixture.details:
            nominal = int(detail['QT_VOTOS_NOMINAIS'])
            if not int(detail['QT_COMPARECIMENTO']):
                continue
            shares = [(13,40),(14,0),(22,34)] if nominal == 74 else [(13,4),(14,0),(22,2)]
            amounts = shares+[(95,int(detail['QT_VOTOS_BRANCOS'])),
                             (96,int(detail['QT_VOTOS_NULOS'])),
                             (97,int(detail['QT_VOTOS_ANULADOS_APU_SEP']))]
            for number, quantity in amounts:
                fixture.votes.append({**{key: detail[key] for key in [*FIXTURES.LOADER.KEY_FIELDS,'ANO_ELEICAO','DS_CARGO','SG_UE']},
                                      'NR_VOTAVEL':str(number), 'NM_VOTAVEL':f'Candidate {number}', 'QT_VOTOS':str(quantity)})
        fixture.write_sources()
        fixture.pin_sources()
        originals = {name:(fixture.root/path).read_bytes() for name,path in FIXTURES.LOADER.SOURCE_PATHS.items()}
        output = fixture.root/'analysis'
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            summary = RUN.run(fixture.root, output, fixture.cache)
        self.assertEqual(originals, {name:(fixture.root/path).read_bytes() for name,path in FIXTURES.LOADER.SOURCE_PATHS.items()})
        manifest = json.loads((output/'manifest.json').read_text())
        self.assertEqual(manifest['status'], 'completed')
        self.assertEqual(manifest['primary_family_size'], 2)
        for filename, expected in manifest['artifact_sha256'].items():
            self.assertEqual(RUN.digest(output/filename), expected)
        rows = read_rows(output/'inventory.csv')
        views = {'all_details','eligible','small_positive','zero_activity','other_excluded_positive'}
        self.assertEqual({(int(row['turno']),row['view'],row['signature_type']) for row in rows},
                         {(turn,view,kind) for turn in (1,2) for view in views for kind in ('full','extended')})
        self.assertEqual(len(rows), 20)
        for row in rows:
            expected_pairs = (8 if row['signature_type']=='full' else 7) if row['view']=='all_details' else (
                0 if row['view']=='zero_activity' and row['signature_type']=='extended' else 1)
            self.assertEqual(int(row['collision_pairs']), expected_pairs)
        clusters = read_rows(output/'clusters.csv.gz')
        members = read_rows(output/'cluster-members.csv.gz')
        strata = read_rows(output/'strata.csv.gz')
        self.assertEqual((len(clusters), len(members), len(strata)), (24,56,2))
        self.assertEqual({row['municipality_name'] for row in members}, {'SÃO PAULO'})
        for row in strata:
            self.assertEqual((int(row['n']),int(row['observed_pairs'])), (2,1))
            self.assertEqual(Fraction(int(row['expected_numerator']),int(row['expected_denominator'])), 1)
            self.assertEqual(Fraction(int(row['variance_numerator']),int(row['variance_denominator'])), 0)
        self.assertTrue(all(row['status']=='not_applicable' and row['p_bound']=='' and row['p_holm']=='' for row in summary['conditional_tests']))
        self.assertEqual(len(summary['conditional_tests']), 2)
        for name in ('clusters.csv.gz','cluster-members.csv.gz','strata.csv.gz'):
            self.assertEqual((output/name).read_bytes()[4:8], b'\0\0\0\0', 'Compressed evidence has a deterministic gzip timestamp')

    def test_nonempty_output_is_rejected_before_any_source_access_or_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root/'analysis'
            output.mkdir()
            marker = output/'keep.txt'
            marker.write_text('Existing evidence must survive.')
            before = marker.read_bytes()
            with self.assertRaisesRegex(ValueError, 'nonempty output'):
                RUN.run(root, output, root/'cache')
            self.assertEqual(marker.read_bytes(), before)
            self.assertEqual(list(output.iterdir()), [marker])


if __name__ == '__main__':
    unittest.main()
