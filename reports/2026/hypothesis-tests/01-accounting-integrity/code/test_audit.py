"""Synthetic corruption fixtures for H1; these are not election observations.

Run from the repository root with:
python3 -m unittest discover -s reports/2026/hypothesis-tests/01-accounting-integrity/code -p 'test_*.py' -v
"""
from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location('h1_primary_audit', Path(__file__).with_name('run_audit.py'))
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def detail(section=1, turno=1, **changes):
    row = dict(ANO_ELEICAO='2026', CD_ELEICAO=str(6256 + turno), NR_TURNO=str(turno),
               SG_UF='SP', CD_MUNICIPIO='71072', NR_ZONA='1', NR_SECAO=str(section),
               CD_CARGO='1', DS_CARGO='Presidente', SG_UE='BR', QT_APTOS='10',
               QT_COMPARECIMENTO='8', QT_ABSTENCOES='2', QT_VOTOS_NOMINAIS='6',
               QT_VOTOS_BRANCOS='1', QT_VOTOS_NULOS='1', QT_VOTOS_LEGENDA='0',
               QT_VOTOS_ANULADOS_APU_SEP='0', ST_SECAO_INSTALADA='Sim',
               ST_SECAO_ANULADA='Não', DS_ORIGEM_VOTO='Urna Eletrônica')
    row.update({name: str(value) for name, value in changes.items()})
    return row


def votes_for(row, amounts=None):
    base = {name: row[name] for name in [*AUDIT.SOURCE_KEY, 'ANO_ELEICAO', 'DS_CARGO', 'SG_UE']}
    return [dict(base, NR_VOTAVEL=str(number), QT_VOTOS=str(count))
            for number, count in (amounts or {13: 3, 22: 3, 95: 1, 96: 1}).items()]


class AccountingAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write_source(self, name, rows, columns=None):
        path = self.root / name
        fields = columns or list(rows[0])
        with path.open('w', encoding='latin1', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter=';', lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        return path

    def run_fixture(self, details, votes, output='results'):
        dpath = self.write_source('details.csv', details)
        vcolumns = [*AUDIT.SOURCE_KEY, 'ANO_ELEICAO', 'DS_CARGO', 'SG_UE', 'NR_VOTAVEL', 'QT_VOTOS']
        vpath = self.write_source('votes.csv', votes, vcolumns)
        original = dpath.read_bytes(), vpath.read_bytes()
        out = self.root / output
        with contextlib.redirect_stderr(io.StringIO()):
            summary = AUDIT.run(vpath, dpath, out)
        self.assertEqual(original, (dpath.read_bytes(), vpath.read_bytes()), 'Audit must not change source files')
        self.assertEqual(json.loads((out/'manifest.json').read_text())['status'], 'completed')
        checks = {(r['turno'], r['check']): r for r in summary['national_checks']}
        return checks, out, summary

    def read_csv(self, out, name):
        with (out/name).open(encoding='utf-8', newline='') as stream:
            return list(csv.DictReader(stream))

    def test_both_rounds_normalized_keys_and_separate_votes_are_not_duplicates(self):
        d1 = detail(7)
        d2 = detail(7, 2, QT_VOTOS_NOMINAIS=5, QT_VOTOS_ANULADOS_APU_SEP=1)
        v1 = votes_for(d1)
        for row in v1:
            row.update(NR_SECAO='0007', NR_ZONA='0001', SG_UF='sp')
        v2 = votes_for(d2, {13: 2, 22: 3, 95: 1, 96: 1, 97: 1})
        checks, out, summary = self.run_fixture([d1, d2], v1+v2)
        self.assertTrue(all(r['violations']==0 and r['not_comparable']==0 for r in checks.values()))
        self.assertEqual([(r['turno'], r['v_total']) for r in summary['national_totals']], [(1, 8), (2, 8)])
        self.assertEqual(summary['national_totals'][1]['v_separate'], 1)
        self.assertEqual(len(self.read_csv(out, 'violations.csv')), 0)

    def test_opposite_section_errors_do_not_cancel_in_national_totals(self):
        d1, d2 = detail(1), detail(2)
        votes = votes_for(d1)+votes_for(d2)
        d1['QT_VOTOS_NOMINAIS']='7'
        d2['QT_VOTOS_NOMINAIS']='5'
        checks, out, summary = self.run_fixture([d1, d2], votes)
        self.assertEqual(summary['national_totals'][0]['nominal'], summary['national_totals'][0]['v_nominal'])
        self.assertEqual(checks[1,'detail_votes_equal_turnout']['violations'], 2)
        self.assertEqual(checks[1,'reconcile_nominal']['violations'], 2)
        residuals = [int(r['difference']) for r in self.read_csv(out,'violations.csv') if r['check']=='reconcile_nominal']
        self.assertEqual(sorted(residuals), [-1, 1])

    def test_overflow_of_electorate_and_source_votes_is_detected(self):
        d1=detail(1, QT_APTOS=5, QT_ABSTENCOES=0)
        d2=detail(2)
        votes=votes_for(d1)+votes_for(d2, {13: 4,22:3,95:1,96:1})
        checks, _, _ = self.run_fixture([d1,d2], votes)
        self.assertEqual(checks[1,'turnout_le_electorate']['violations'],1)
        self.assertEqual(checks[1,'electorate_identity']['violations'],1)
        self.assertEqual(checks[1,'source_votes_le_turnout']['violations'],1)
        self.assertEqual(checks[1,'source_votes_equal_turnout']['violations'],1)
        self.assertEqual(checks[1,'reconcile_nominal']['violations'],1)

    def test_duplicate_keys_are_detected_before_aggregation(self):
        original=[detail(i) for i in range(1,5)]
        # One identical and one conflicting detail duplicate; likewise for vote keys.
        details=[*original, dict(original[0]),dict(original[1],QT_APTOS='11',QT_ABSTENCOES='3')]
        votes=[row for d in original for row in votes_for(d)]
        votes += [dict(votes[8]),dict(votes[12],QT_VOTOS='4')]
        checks,out,_=self.run_fixture(details,votes)
        self.assertEqual(checks[1,'unique_detail_key']['violations'],2)
        self.assertEqual(checks[1,'unique_vote_key']['violations'],2)
        self.assertEqual(checks[1,'vote_section_has_unique_detail']['violations'],2)
        self.assertEqual(checks[1,'reconcile_nominal']['eligible'],2,'Ambiguous detail keys must not be chosen arbitrarily')
        for filename in ['duplicate-details.csv','duplicate-votes.csv']:
            rows=self.read_csv(out,filename)
            self.assertEqual(len(rows),4)
            by_section={}
            for row in rows:
                by_section.setdefault(row['section'],set()).add(row['fingerprint'])
            self.assertEqual(sorted(map(len,by_section.values())),[1,2])

    def test_missing_quantities_are_not_silently_replaced_with_zero(self):
        details=[detail(i) for i in range(1,5)]
        votes=[row for d in details for row in votes_for(d)]
        details[0]['QT_VOTOS_NOMINAIS']='#NULO'
        details[1]['QT_COMPARECIMENTO']='-1'
        details[2]['QT_ABSTENCOES']='-3'
        votes[-4]['QT_VOTOS']='bad-number'
        checks,out,_=self.run_fixture(details,votes)
        self.assertEqual(checks[1,'detail_quantities_complete']['violations'],3)
        self.assertEqual(checks[1,'vote_quantities_complete']['violations'],1)
        self.assertEqual(checks[1,'reconcile_nominal']['not_comparable'],2)
        self.assertEqual(checks[1,'source_votes_equal_turnout']['not_comparable'],2)
        self.assertEqual(checks[1,'electorate_identity']['not_comparable'],2)
        issues=self.read_csv(out,'input-issues.csv')
        self.assertEqual(len(issues),4)
        self.assertEqual({r['reason'] for r in issues},{'missing','invalid'})

    def test_coverage_separates_zero_details_positive_missing_votes_and_votes_only(self):
        zero=detail(1, QT_APTOS=5,QT_COMPARECIMENTO=0,QT_ABSTENCOES=5,QT_VOTOS_NOMINAIS=0,QT_VOTOS_BRANCOS=0,QT_VOTOS_NULOS=0)
        uninstalled=dict(zero,NR_SECAO='2',QT_ABSTENCOES='0',ST_SECAO_INSTALADA='Não',DS_ORIGEM_VOTO='Totalização')
        positive=detail(3)
        matched=detail(4)
        votes_only=detail(5)
        checks,out,_=self.run_fixture([zero,uninstalled,positive,matched],votes_for(matched)+votes_for(votes_only))
        self.assertEqual(checks[1,'positive_detail_has_votes']['violations'],1)
        self.assertEqual(checks[1,'vote_section_has_unique_detail']['violations'],1)
        self.assertEqual(checks[1,'electorate_identity']['violations'],1)
        self.assertEqual(checks[1,'electorate_identity_installed']['violations'],0)
        self.assertEqual(checks[1,'electorate_identity_not_installed']['violations'],1)
        self.assertEqual(len(self.read_csv(out,'zero-vote-details-only.csv')),2)
        self.assertEqual(checks[1,'reconcile_nominal']['compared'],4,'Absent vote rows are explicitly reconciled only with existing unique details')

    def test_negative_votes_and_legend_are_reported_not_absorbed(self):
        d1=detail(1,QT_COMPARECIMENTO=9,QT_ABSTENCOES=1,QT_VOTOS_LEGENDA=1)
        d2=detail(2)
        votes=votes_for(d1)+votes_for(d2,{13:-2,22:8,95:1,96:1})
        checks,out,_=self.run_fixture([d1,d2],votes)
        self.assertEqual(checks[1,'presidential_legend_zero']['violations'],1)
        self.assertEqual(checks[1,'detail_votes_equal_turnout']['violations'],0,'Legend contributes exactly once to the five-category identity')
        self.assertEqual(checks[1,'vote_quantities_nonnegative']['violations'],1)
        self.assertEqual(checks[1,'source_votes_equal_turnout']['not_comparable'],1)
        self.assertIn('negative',{r['reason'] for r in self.read_csv(out,'input-issues.csv')})

    def test_existing_empty_output_is_allowed_nonempty_output_is_preserved(self):
        out=self.root/'results'
        out.mkdir()
        d=detail()
        self.run_fixture([d],votes_for(d))
        marker=(out/'manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'nonempty output'):
            AUDIT.run(self.root/'votes.csv',self.root/'details.csv',out)
        self.assertEqual((out/'manifest.json').read_bytes(),marker)

    def test_malformed_source_key_fails_instead_of_dropping_record(self):
        d=detail(NR_SECAO='not-a-section')
        dpath=self.write_source('details.csv',[d])
        vpath=self.write_source('votes.csv',votes_for(detail()))
        out=self.root/'results'
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaisesRegex(ValueError,'Invalid key NR_SECAO'):
            AUDIT.run(vpath,dpath,out)
        self.assertEqual(json.loads((out/'manifest.json').read_text())['status'],'failed')

    def test_empty_or_out_of_scope_sources_fail_instead_of_completing_empty_audit(self):
        valid=detail()
        other_office=detail(CD_CARGO=2,DS_CARGO='Governador')
        other_year=detail(ANO_ELEICAO=2022)
        vote_columns=list(votes_for(valid)[0])
        scenarios=[
            ('empty-details',[],votes_for(valid)),
            ('other-office-details',[other_office],votes_for(valid)),
            ('other-year-details',[other_year],votes_for(valid)),
            ('empty-votes',[valid],[]),
            ('other-office-votes',[valid],votes_for(other_office)),
            ('other-year-votes',[valid],votes_for(other_year)),
        ]
        for name,details,votes in scenarios:
            with self.subTest(source=name):
                dpath=self.write_source('details.csv',details,list(valid))
                vpath=self.write_source('votes.csv',votes,vote_columns)
                out=self.root/name
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaisesRegex(ValueError,'no presidential records selected'):
                    AUDIT.run(vpath,dpath,out)
                manifest=json.loads((out/'manifest.json').read_text())
                self.assertEqual(manifest['status'],'failed')
                self.assertIn('no presidential records selected',manifest['error'])
                self.assertFalse((out/'summary.json').exists(),'An empty selection must not yield a completed summary')


if __name__=='__main__':
    unittest.main()
