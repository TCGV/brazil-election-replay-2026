"""Integration checks using tiny, explicitly synthetic TSE-style CSVs.

These fixtures exercise arithmetic and exclusions; they are not election results.
Run from the repository root: PYTHONPATH=src python3 -m unittest discover -s tests -v
"""

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from election_replay.pipeline import run


COMMON = [
    "ANO_ELEICAO", "CD_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO",
    "NR_ZONA", "NR_SECAO", "CD_CARGO", "DS_CARGO", "SG_UE",
]
VOTE_FIELDS = COMMON + ["NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS"]
DETAIL_FIELDS = COMMON + [
    "DT_RECEBIMENTO_BU_HOR_TSE", "DT_PRIM_TOT_PARCIAL_HOR_TSE",
    "QT_VOTOS_NOMINAIS", "QT_VOTOS_BRANCOS", "QT_VOTOS_NULOS",
    "QT_VOTOS_ANULADOS_APU_SEP", "QT_APTOS", "QT_COMPARECIMENTO",
    "QT_ABSTENCOES", "ST_SECAO_INSTALADA", "ST_SECAO_ANULADA", "DS_ORIGEM_VOTO",
]


def common(section, election="100", round_="1", uf="AC"):
    return dict(zip(COMMON, ["2026", election, round_, uf, "123", "1", str(section),
                             "1", "Presidente", "BR"]))


def vote(section, candidate="10", count=10, **scope):
    row = common(section, **scope)
    row.update(NR_VOTAVEL=str(candidate), NM_VOTAVEL={
        "10": "Ana Teste", "20": "Beto Teste", "95": "Branco", "96": "Nulo",
        "97": "Anulado e apurado em separado",
    }.get(str(candidate), "Outro Teste"), QT_VOTOS=str(count))
    return row


def detail(section, first="04/10/2026 17:00:59", received="04/10/2026 16:59:30",
           nominal=10, blank=0, null=0, separate=0, **scope):
    row = common(section, **scope)
    attendance = nominal + blank + null + separate
    row.update(
        DT_PRIM_TOT_PARCIAL_HOR_TSE=first, DT_RECEBIMENTO_BU_HOR_TSE=received,
        QT_VOTOS_NOMINAIS=str(nominal), QT_VOTOS_BRANCOS=str(blank),
        QT_VOTOS_NULOS=str(null), QT_VOTOS_ANULADOS_APU_SEP=str(separate),
        QT_APTOS=str(attendance + 10), QT_COMPARECIMENTO=str(attendance),
        QT_ABSTENCOES="10", ST_SECAO_INSTALADA="S", ST_SECAO_ANULADA="N",
        DS_ORIGEM_VOTO="Urna eletrônica",
    )
    return row


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.votes = self.root / "votes.csv"
        self.details = self.root / "details.csv"
        self.output = self.root / "output"

    def write_csv(self, path, rows, fields):
        with path.open("w", encoding="latin1", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";",
                                    quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(rows)

    def execute(self, votes, details, output=None):
        self.write_csv(self.votes, votes, VOTE_FIELDS)
        self.write_csv(self.details, details, DETAIL_FIELDS)
        return run(self.votes, self.details, output or self.output)

    def rows(self, name, output=None):
        with ((output or self.output) / name).open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    @staticmethod
    def time(row):
        return datetime.fromisoformat(row["minute"])

    def primary(self):
        return self.rows("replay-first-totalization-minute.csv")

    def test_minute_boundaries_gap_and_nominal_percentage(self):
        self.execute(
            [vote(1, "10", 10), vote(1, "20", 20), vote(1, "95", 5),
             vote(1, "96", 2), vote(1, "97", 1), vote(2, "10", 30), vote(2, "20", 10)],
            [detail(1, nominal=30, blank=5, null=2, separate=1),
             detail(2, first="04/10/2026 17:02:00", received="04/10/2026 17:01:59",
                    nominal=40)],
        )
        ana = sorted([r for r in self.primary() if r["nr_votavel"] == "10"], key=self.time)
        self.assertEqual([self.time(r).minute for r in ana], [0, 1, 2])
        self.assertEqual([int(r["votes_in_minute"]) for r in ana], [10, 0, 30])
        self.assertEqual([int(r["cumulative_votes"]) for r in ana], [10, 10, 40])
        self.assertEqual([int(r["sections_in_minute"]) for r in ana], [1, 0, 1])
        self.assertEqual([int(r["cumulative_sections"]) for r in ana], [1, 1, 2])
        self.assertAlmostEqual(float(ana[0]["percentage_valid_votes"]), 100 / 3, places=4)
        self.assertAlmostEqual(float(ana[-1]["percentage_valid_votes"]), 400 / 7, places=4)
        specials = [r for r in self.primary() if r["nr_votavel"] in {"95", "96", "97"}]
        self.assertTrue(specials)
        self.assertTrue(all(not r["percentage_valid_votes"] for r in specials))
        bu = [r for r in self.rows("replay-bu-received-minute.csv") if r["nr_votavel"] == "10"]
        self.assertEqual(min(self.time(r) for r in bu), datetime(2026, 10, 4, 16, 59))
        self.assertEqual(max(int(r["cumulative_votes"]) for r in bu), 40)
        finals = {r["nr_votavel"]: int(r["votes"]) for r in self.rows("final-results.csv")}
        self.assertEqual(finals, {"10": 40, "20": 30, "95": 5, "96": 2, "97": 1})

    def test_missing_invalid_and_duplicate_details_conserve_votes(self):
        duplicate = detail(3)
        self.execute(
            [vote(i) for i in range(1, 6)],
            [detail(1), duplicate, dict(duplicate),
             detail(4, first="invalid"),
             detail(5, first="#NULO", received="invalid"), detail(99)],
        )
        finals = self.rows("final-results.csv")
        self.assertEqual(sum(int(r["votes"]) for r in finals), 50)
        untimed = self.rows("untimed-votes.csv")
        sources = {
            "first_partial_totalization": "replay-first-totalization-minute.csv",
            "bu_received": "replay-bu-received-minute.csv",
        }
        for source, filename in sources.items():
            series = self.rows(filename)
            timed = max(int(r["cumulative_votes"]) for r in series)
            excluded = sum(int(r["votes"]) for r in untimed if r["source_timestamp"] == source)
            self.assertEqual(timed + excluded, 50)
        reasons = {r["reason"] for r in untimed}
        self.assertEqual(reasons, {"detail_missing", "detail_duplicate", "timestamp_missing",
                                  "timestamp_invalid"})
        first = [r for r in self.primary() if r["nr_votavel"] == "10"]
        self.assertEqual(max(int(r["cumulative_votes"]) for r in first), 10)

    def test_rounds_elections_and_overseas_are_not_mixed(self):
        self.execute(
            [vote(1, count=10), vote(1, count=20, election="101", round_="2", uf="ZZ"),
             vote(1, count=30, election="102", round_="2")],
            [detail(1), detail(1, nominal=20, election="101", round_="2", uf="ZZ"),
             detail(1, nominal=30, election="102", round_="2")],
        )
        finals = {(r["election_code"], r["turno"]): int(r["votes"])
                  for r in self.rows("final-results.csv")}
        self.assertEqual(finals, {("100", "1"): 10, ("101", "2"): 20, ("102", "2"): 30})
        self.assertEqual(len(self.primary()), 3)

    def test_single_round_and_non_presidential_rows(self):
        other_vote, other_detail = vote(2, count=999), detail(2, nominal=999)
        for row in (other_vote, other_detail):
            row.update(CD_CARGO="3", DS_CARGO="Governador")
        self.execute([vote(1), other_vote], [detail(1), other_detail])
        self.assertEqual({r["turno"] for r in self.primary()}, {"1"})
        self.assertEqual(sum(int(r["votes"]) for r in self.rows("final-results.csv")), 10)

    def test_repeated_vote_rows_aggregate_without_join_multiplication(self):
        self.execute([vote(1, count=10), vote(1, count=2), vote(2, count=3)],
                     [detail(1, nominal=12), detail(2, nominal=3)])
        final = self.rows("final-results.csv")
        self.assertEqual(len(final), 1)
        self.assertEqual(int(final[0]["votes"]), 15)
        self.assertEqual(max(int(r["cumulative_votes"]) for r in self.primary()), 15)

    def test_shuffle_does_not_change_results(self):
        votes = [vote(1, "10", 10), vote(1, "20", 5), vote(2, "10", 7), vote(2, "20", 6)]
        details = [detail(1, nominal=15), detail(2, first="04/10/2026 17:01:01", nominal=13)]
        self.execute(votes, details)
        other = self.root / "reversed-output"
        self.execute(list(reversed(votes)), list(reversed(details)), other)
        for name in ["final-results.csv", "replay-first-totalization-minute.csv",
                     "replay-bu-received-minute.csv", "untimed-votes.csv"]:
            self.assertEqual(self.rows(name), self.rows(name, other), name)

    def test_mismatch_is_reported_without_rewriting_vote_totals(self):
        self.execute([vote(1, count=10)], [detail(1, nominal=12)])
        self.assertEqual(int(self.rows("final-results.csv")[0]["votes"]), 10)
        mismatch = self.rows("reconciliation.csv")
        self.assertEqual(len(mismatch), 1)
        self.assertEqual(mismatch[0]["category"], "nominal")
        self.assertEqual(int(mismatch[0]["difference"]), -2)

    def test_lfs_pointer_is_rejected(self):
        self.votes.write_text("version https://git-lfs.github.com/spec/v1\n"
                              "oid sha256:" + "a" * 64 + "\nsize 123\n", encoding="ascii")
        self.write_csv(self.details, [detail(1)], DETAIL_FIELDS)
        with self.assertRaises(ValueError):
            run(self.votes, self.details, self.output)

    def test_missing_schema_and_negative_vote_are_rejected(self):
        self.write_csv(self.votes, [{"QT_VOTOS": "10"}], ["QT_VOTOS"])
        self.write_csv(self.details, [detail(1)], DETAIL_FIELDS)
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            run(self.votes, self.details, self.output)
        with self.assertRaisesRegex(ValueError, "QT_VOTOS"):
            self.execute([vote(1, count=-1)], [detail(1)], self.root / "negative-output")

    def test_date_boundary_keeps_full_date(self):
        self.execute([vote(1, count=10), vote(2, count=20)],
                     [detail(1, first="04/10/2026 23:59:59"),
                      detail(2, first="05/10/2026 00:00:00", nominal=20)])
        times = sorted(self.time(r) for r in self.primary())
        self.assertEqual(times, [datetime(2026, 10, 4, 23, 59), datetime(2026, 10, 5, 0, 0)])
        self.assertEqual(max(int(r["cumulative_votes"]) for r in self.primary()), 30)

    def test_all_timestamps_missing_produces_empty_timelines_and_accounting(self):
        summary = self.execute([vote(1, count=17)], [detail(1, first="#NE", received="-3", nominal=17)])
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(self.primary(), [])
        self.assertEqual(self.rows("replay-bu-received-minute.csv"), [])
        excluded = self.rows("untimed-votes.csv")
        self.assertEqual(len(excluded), 2)
        self.assertTrue(all(r["reason"] == "timestamp_missing" and int(r["votes"]) == 17
                            for r in excluded))

    def test_no_nominal_votes_does_not_divide_by_zero(self):
        self.execute([vote(1, "95", 5), vote(1, "96", 2)],
                     [detail(1, nominal=0, blank=5, null=2)])
        self.assertTrue(self.primary())
        self.assertTrue(all(r["percentage_valid_votes"] == "" for r in self.primary()))

    def test_zero_padded_keys_and_latin1_names_join(self):
        original = vote(1, count=13)
        original.update(NM_VOTAVEL="Candidata Ágata", NR_SECAO="0001", NR_ZONA="001",
                        CD_MUNICIPIO="00123", CD_ELEICAO="00100", NR_VOTAVEL="010")
        self.execute([original], [detail(1, nominal=13)])
        rows = self.primary()
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["cumulative_votes"]), 13)
        self.assertEqual(rows[0]["nm_votavel"], "Candidata Ágata")
        self.assertEqual(self.rows("untimed-votes.csv"), [])

    def test_input_integrity_manifest_and_preserve_previous_output(self):
        self.write_csv(self.votes, [vote(1)], VOTE_FIELDS)
        self.write_csv(self.details, [detail(1)], DETAIL_FIELDS)
        expected = {"votes": hashlib.sha256(self.votes.read_bytes()).hexdigest(),
                    "details": hashlib.sha256(self.details.read_bytes()).hexdigest()}
        run(self.votes, self.details, self.output)
        manifest = json.loads((self.output / "input-manifest.json").read_text(encoding="utf-8"))
        for kind, path in [("votes", self.votes), ("details", self.details)]:
            self.assertEqual(manifest["inputs"][kind]["sha256"], expected[kind])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected[kind])
        before = (self.output / "final-results.csv").read_bytes()
        with self.assertRaisesRegex(ValueError, "empty"):
            run(self.votes, self.details, self.output)
        self.assertEqual((self.output / "final-results.csv").read_bytes(), before)

    def test_minute_limit_failure_is_explicit_in_manifest(self):
        self.write_csv(self.votes, [vote(1), vote(2)], VOTE_FIELDS)
        self.write_csv(self.details, [detail(1), detail(2, first="05/10/2026 17:00:00")],
                       DETAIL_FIELDS)
        with self.assertRaisesRegex(ValueError, "max-minutes"):
            run(self.votes, self.details, self.output, max_minutes=60)
        manifest = json.loads((self.output / "input-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "failed")

    def test_conflicting_candidate_names_are_preserved_before_aggregation(self):
        first, second = vote(1, count=4), vote(1, count=6)
        first["NM_VOTAVEL"] = "Ana Nome Original"
        second["NM_VOTAVEL"] = "Ana Outro Nome"
        self.execute([first, second], [detail(1, nominal=10)])
        names = {r["nm_votavel"]: (int(r["input_rows"]), int(r["votes"]))
                 for r in self.rows("candidate-names.csv")}
        self.assertEqual(names, {"Ana Nome Original": (1, 4), "Ana Outro Nome": (1, 6)})
        self.assertEqual(int(self.rows("final-results.csv")[0]["votes"]), 10)

    def test_missing_detail_metrics_are_not_claimed_as_compared(self):
        missing = detail(1)
        for field in ["QT_VOTOS_NOMINAIS", "QT_VOTOS_BRANCOS", "QT_VOTOS_NULOS",
                      "QT_VOTOS_ANULADOS_APU_SEP"]:
            missing[field] = "#NULO"
        summary = self.execute([vote(1)], [missing])
        nominal = summary["quality"]["reconciliation_comparability"]["nominal"]
        self.assertEqual(nominal["compared_sections"], 0)
        self.assertEqual(nominal["missing_metric_sections"], 1)
        self.assertEqual(self.rows("reconciliation.csv"), [])

    def test_presidential_description_cannot_have_another_office_code(self):
        conflicting = vote(1)
        conflicting["CD_CARGO"] = "3"
        with self.assertRaisesRegex(ValueError, "DS_CARGO=Presidente"):
            self.execute([conflicting], [detail(1)])

    def test_normal_descriptive_section_flags_are_not_exceptions(self):
        normal = detail(1)
        normal.update(ST_SECAO_INSTALADA="Sim", ST_SECAO_ANULADA="Não",
                      DS_ORIGEM_VOTO="Urna Eletrônica")
        self.execute([vote(1)], [normal])
        self.assertEqual(self.rows("section-exceptions.csv"), [])


if __name__ == "__main__":
    unittest.main()
