"""Focused independent-validator guard checks on small synthetic CSV fixtures."""
import csv
import importlib.util
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    'h1_independent_validator', Path(__file__).with_name('validate_independently.py'))
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class IndependentGuardTests(unittest.TestCase):
    def make_root(self, detail_rows, vote_rows):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        details = root / 'data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv'
        votes = root / 'data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv'
        details.parent.mkdir(parents=True)
        votes.parent.mkdir(parents=True)
        for path, header, rows in (
            (details, ['ANO_ELEICAO', *AUDIT.KEY_FIELDS, *AUDIT.DETAIL_FIELDS,
                       'ST_SECAO_INSTALADA', 'ST_SECAO_ANULADA', 'DS_ORIGEM_VOTO'], detail_rows),
            (votes, ['ANO_ELEICAO', *AUDIT.KEY_FIELDS, 'NR_VOTAVEL', 'QT_VOTOS'], vote_rows),
        ):
            with path.open('w', encoding='latin1', newline='') as stream:
                writer = csv.writer(stream, delimiter=';')
                writer.writerow(header)
                writer.writerows(rows)
        return root

    @staticmethod
    def detail(section=1, aptos=100, turnout=80, abstentions=20,
               nominal=70, blank=5, null=5, installed='S'):
        return ['2026', 6257, 1, 'SP', 71072, 1, section, 1,
                aptos, turnout, abstentions, nominal, blank, null, 0, 0,
                installed, 'N', 'U']

    @staticmethod
    def vote(number, quantity, section=1):
        return ['2026', 6257, 1, 'SP', 71072, 1, section, 1, number, quantity]

    def run_validation(self, root):
        with redirect_stdout(StringIO()):
            result = AUDIT.validate(root)
        checks = {row['check']: row for row in result['checks'] if row['uf'] == 'BR'}
        totals = next(row for row in result['group_totals'] if row['uf'] == 'BR')
        return result, checks, totals

    def test_duplicate_and_zero_activity_detail_denominators(self):
        root = self.make_root(
            [self.detail(), self.detail(section=2, aptos=10, turnout=0,
                                       abstentions=0, nominal=0, blank=0, null=0, installed='N')],
            [self.vote(13, 40), self.vote(22, 30), self.vote(95, 5),
             self.vote(96, 5), self.vote(13, 40)],
        )
        _, checks, totals = self.run_validation(root)
        self.assertEqual(totals['duplicate_vote_key_groups'], 1)
        self.assertEqual(totals['vote_duplicate_rows_exact_to_first'], 1)
        self.assertEqual(totals['detail_only_keys'], 1)
        self.assertEqual(checks['vote_detail_nominal_equality']['opportunities'], 1)
        self.assertEqual(checks['vote_detail_all_unique_nominal_equality']['opportunities'], 2)
        self.assertEqual(checks['electorate_equals_turnout_plus_abstentions']['mismatches'], 1)
        self.assertEqual(checks['electorate_equals_turnout_plus_abstentions_installed']['mismatches'], 0)

    def test_negative_votes_fail_domain_and_are_not_comparable(self):
        root = self.make_root(
            [self.detail(aptos=20, turnout=0, abstentions=20, nominal=0, blank=0, null=0)],
            [self.vote(13, -2)],
        )
        _, checks, _ = self.run_validation(root)
        self.assertEqual(checks['vote_count_complete_nonnegative']['mismatches'], 1)
        for name in ('vote_detail_nominal_equality', 'vote_detail_all_unique_nominal_equality',
                     'vote_file_all_categories_equal_turnout', 'vote_file_all_unique_categories_equal_turnout'):
            self.assertEqual(checks[name]['evaluated'], 0)
            self.assertEqual(checks[name]['non_comparable'], 1)

    def test_unknown_installation_is_not_treated_as_no(self):
        root = self.make_root([self.detail(installed='#NULO')], [self.vote(13, 70)])
        _, checks, _ = self.run_validation(root)
        self.assertEqual(checks['installation_status_known']['mismatches'], 1)
        self.assertEqual(checks['electorate_equals_turnout_plus_abstentions_unknown_installation']['evaluated'], 1)
        self.assertNotIn('electorate_equals_turnout_plus_abstentions_not_installed', checks)
        self.assertNotIn('electorate_equals_turnout_plus_abstentions_installed', checks)

    def test_empty_detail_scope_rejected(self):
        root = self.make_root([], [self.vote(13, 70)])
        with redirect_stdout(StringIO()), self.assertRaisesRegex(ValueError, 'Detail CSV has no selected'):
            AUDIT.validate(root)

    def test_empty_vote_scope_rejected(self):
        root = self.make_root([self.detail()], [])
        with redirect_stdout(StringIO()), self.assertRaisesRegex(ValueError, 'Vote CSV has no selected'):
            AUDIT.validate(root)


if __name__ == '__main__':
    unittest.main()
