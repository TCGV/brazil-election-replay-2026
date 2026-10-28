"""Comparator regression checks using isolated copies of published H1 evidence.

The altered records below are synthetic test changes, never source observations.
No original TSE CSV is read and no published artifact is modified.
"""
from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path


CODE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('h1_comparator', CODE/'compare_validations.py')
COMPARATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPARATOR)


class EvidenceComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.evidence = self.root/'evidence'
        self.evidence.mkdir()
        published = CODE.parent/'evidence'
        shutil.copytree(published/'accounting',self.evidence/'accounting')
        shutil.copyfile(published/'independent-validation.json',self.evidence/'independent-validation.json')
        self.manifest_path = self.evidence/'accounting/manifest.json'
        self.checks_path = self.evidence/'accounting/checks.csv'

    def mutate_checks_with_consistent_hash(self, mutate):
        with self.checks_path.open(encoding='utf-8',newline='') as stream:
            reader=csv.DictReader(stream)
            columns=reader.fieldnames
            rows=list(reader)
        mutate(rows)
        with self.checks_path.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns,lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        manifest=json.loads(self.manifest_path.read_text())
        manifest['artifact_sha256']['checks.csv']=COMPARATOR.digest(self.checks_path)
        self.manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def compare(self):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return COMPARATOR.compare(self.evidence,self.root/'comparison.json')

    def assert_failure_category(self, result, category):
        self.assertEqual(result['status'],'failed')
        self.assertGreater(result['mismatches'],0)
        self.assertIn(category,{row['category'] for row in result['failures']})

    def test_current_published_evidence_passes(self):
        result=self.compare()
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['mismatches'],0)
        self.assertGreater(result['comparisons']['section_check'],0)

    def test_missing_primary_check_fails_inventory_even_with_consistent_manifest(self):
        def remove_one(rows):
            index=next(i for i,row in enumerate(rows) if row['check']=='reconcile_blank')
            rows.pop(index)
        self.mutate_checks_with_consistent_hash(remove_one)
        result=self.compare()
        self.assert_failure_category(result,'inventory')
        self.assertNotIn('artifact_hash',{row['category'] for row in result['failures']},'The inventory guard must catch a semantically incomplete, coherently hashed artifact')

    def test_duplicate_primary_check_fails_inventory_even_with_consistent_manifest(self):
        self.mutate_checks_with_consistent_hash(lambda rows:rows.append(dict(rows[0])))
        result=self.compare()
        self.assert_failure_category(result,'inventory')
        self.assertNotIn('artifact_hash',{row['category'] for row in result['failures']})

    def test_changed_numeric_result_fails_independent_section_comparison(self):
        def alter_count(rows):
            row=next(row for row in rows if row['check']=='reconcile_nominal' and row['uf']=='BR')
            row['violations']=str(int(row['violations'])+1)
        self.mutate_checks_with_consistent_hash(alter_count)
        result=self.compare()
        self.assert_failure_category(result,'section_check')
        self.assertNotIn('artifact_hash',{row['category'] for row in result['failures']})

    def test_running_manifest_is_rejected_before_comparison(self):
        manifest=json.loads(self.manifest_path.read_text())
        manifest['status']='running'
        self.manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'completed'):
            self.compare()
        self.assertFalse((self.root/'comparison.json').exists())


if __name__=='__main__':
    unittest.main()
