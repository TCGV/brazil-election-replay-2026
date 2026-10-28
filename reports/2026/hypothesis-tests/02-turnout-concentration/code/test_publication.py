"""Publication consistency controls; mutations affect temporary evidence copies only."""
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('h2_publication_validator',Path(__file__).with_name('validate_publication.py'))
PUBLICATION=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLICATION)
HERE=Path(__file__).resolve().parents[1]


class PublicationControls(unittest.TestCase):
    def copy_evidence(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        evidence=Path(temporary.name)/'evidence'
        evidence.mkdir()
        shutil.copytree(HERE/'evidence/analysis',evidence/'analysis')
        shutil.copy2(HERE/'evidence/independent-validation.json',evidence/'independent-validation.json')
        return evidence/'analysis'

    def test_current_publication_matches_audited_primary_tables(self):
        result=PUBLICATION.validate(self.copy_evidence())
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['mismatches'],0)
        self.assertEqual(result['derived_counts']['uf_summary_rows'],420)
        self.assertEqual(result['derived_counts']['distinct_joint_section_rounds'],7867)
        self.assertEqual(result['derived_counts']['distinct_priority_section_rounds'],2046)

    def test_coherent_uf_and_json_tampering_is_detected_beyond_hash_checks(self):
        analysis=self.copy_evidence()
        path=analysis/'uf-summary.csv'
        with path.open(newline='') as stream:
            reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
        rows[0]['priority_count']=str(int(rows[0]['priority_count'])+1)
        with path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n')
            writer.writeheader();writer.writerows(rows)
        summary_path=analysis/'summary.json'
        summary=json.loads(summary_path.read_text())
        summary['total_priority_cases']+=1
        summary_path.write_text(json.dumps(summary)+'\n')
        manifest_path=analysis/'manifest.json'
        manifest=json.loads(manifest_path.read_text())
        for filename in ('uf-summary.csv','summary.json'):
            manifest['artifact_sha256'][filename]=PUBLICATION.digest(analysis/filename)
        manifest_path.write_text(json.dumps(manifest)+'\n')
        result=PUBLICATION.validate(analysis)
        self.assertEqual(result['status'],'failed')
        categories={row['category'] for row in result['failures']}
        self.assertIn('uf_summary',categories)
        self.assertIn('summary_counts',categories)
        self.assertNotIn('artifact_integrity',categories,'Hashes alone must not be the reason this fails')


if __name__=='__main__':
    unittest.main()
