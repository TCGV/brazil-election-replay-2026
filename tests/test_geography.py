"""Geographic arithmetic on synthetic section events, never real election output."""

import csv
from datetime import datetime
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from election_replay.geography import analyze


FIELDS = [
    "election_code", "turno", "uf", "municipality", "municipality_name", "zone",
    "section", "region", "is_capital", "size_band", "municipality_electorate", "aptos",
    "nominal_votes", "lula_votes", "flavio_votes", "first_time", "bu_time",
]


def event(section, nominal, lula, time, municipality="1", capital=1, uf="SP",
          region="Sudeste", band=">1m", election="100", turn="1", bu=None):
    return dict(zip(FIELDS, [election, turn, uf, municipality,
        "Município Sintético " + municipality, "1", str(section), region, capital,
        band, 2000000 if capital else 9000, nominal + 10, nominal, lula,
        nominal - lula, time, time if bu is None else bu]))


class GeographicAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "events.sqlite"
        self.output = self.root / "analysis"

    def execute(self, events):
        with sqlite3.connect(self.database) as db:
            text_fields = {"election_code", "turno", "uf", "municipality", "municipality_name",
                           "zone", "section", "region", "size_band", "first_time", "bu_time"}
            db.execute("CREATE TABLE section_events (" + ",".join(
                field + (" TEXT" if field in text_fields else " INTEGER") for field in FIELDS
            ) + ")")
            db.executemany("INSERT INTO section_events VALUES (" + ",".join("?" for _ in FIELDS) + ")",
                           [tuple(row[field] for field in FIELDS) for row in events])
        before = hashlib.sha256(self.database.read_bytes()).hexdigest()
        result = analyze(self.database, self.output)
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), before,
                         "Analysis must leave its source database unchanged")
        return result

    @staticmethod
    def fixture():
        # SP final: 60 nominal / 30 Lula; national including ZZ: 100 / 30.
        # Three tied-inclusive events have arrived at 17:30:30: 70 / 30.
        return [
            event(1, 10, 10, "2026-10-04 17:00:00.000000"),
            event(2, 30, 0, "2026-10-04 18:00:00.000000"),
            event(3, 20, 20, "2026-10-04 17:30:30.000000", municipality="2",
                  capital=0, band="<=10k"),
            event(4, 40, 0, "2026-10-04 17:30:30.000000", municipality="99",
                  capital=None, uf="ZZ", region="Exterior", band="exterior"),
        ]

    def rows(self, filename, **matches):
        with (self.output / filename).open(encoding="utf-8", newline="") as stream:
            return [row for row in csv.DictReader(stream)
                    if all(row[key] == str(value) for key, value in matches.items())]

    def test_milestones_include_all_ties_and_weight_shares_by_nominal_votes(self):
        self.execute(self.fixture())
        [half] = self.rows("national-milestones.csv", source_timestamp="first_partial_totalization",
                           scope="BR", requested_sections_percentage="50")
        self.assertEqual(datetime.fromisoformat(half["cutoff_timestamp"]),
                         datetime(2026, 10, 4, 17, 30, 30))
        self.assertEqual(int(half["target_reached"]), 1)
        self.assertEqual(int(half["cumulative_sections"]), 3)
        self.assertEqual(float(half["actual_sections_percentage"]), 75)
        self.assertEqual(int(half["cumulative_nominal_votes"]), 70)
        self.assertEqual(float(half["nominal_completion_percentage"]), 70)
        self.assertAlmostEqual(float(half["lula_percentage"]), 300 / 7)
        self.assertEqual(float(half["lula_final_percentage"]), 30)
        [timing] = self.rows("timing-summary.csv", source_timestamp="first_partial_totalization",
                             dimension="uf", group="SP")
        self.assertEqual(datetime.fromisoformat(timing["t50"]), datetime(2026, 10, 4, 17, 30, 30))
        self.assertAlmostEqual(float(timing["t50_minutes"]), 30.5)

    def test_decomposition_is_exact_for_regions_ufs_and_sp_municipalities(self):
        self.execute(self.fixture())
        for row in self.rows("composition-decomposition.csv"):
            self.assertAlmostEqual(float(row["composition_effect_pp"]) +
                                   float(row["within_group_effect_pp"]), float(row["total_gap_pp"]))
            self.assertAlmostEqual(float(row["current_lula_percentage"]) -
                                   float(row["final_lula_percentage"]), float(row["total_gap_pp"]))
        [national] = self.rows("composition-decomposition.csv",
                               source_timestamp="first_partial_totalization", scope="BR",
                               requested_sections_percentage="25", dimension="region")
        self.assertAlmostEqual(float(national["composition_effect_pp"]), 20)
        self.assertAlmostEqual(float(national["within_group_effect_pp"]), 50)
        self.assertAlmostEqual(float(national["total_gap_pp"]), 70)
        [sp] = self.rows("composition-decomposition.csv",
                         source_timestamp="first_partial_totalization", scope="SP",
                         requested_sections_percentage="25", dimension="municipality")
        self.assertAlmostEqual(float(sp["composition_effect_pp"]), -25)
        self.assertAlmostEqual(float(sp["within_group_effect_pp"]), 75)
        self.assertAlmostEqual(float(sp["total_gap_pp"]), 50)
        contributions = self.rows("sp-municipality-contributions.csv",
                                  source_timestamp="first_partial_totalization",
                                  requested_sections_percentage="25")
        self.assertEqual(len(contributions), 2)
        self.assertAlmostEqual(sum(float(r["composition_contribution_pp"]) for r in contributions), -25)
        self.assertAlmostEqual(sum(float(r["within_contribution_pp"]) for r in contributions), 75)

    def test_domestic_capital_and_size_groups_exclude_exterior_national_includes_it(self):
        self.execute(self.fixture())
        [national] = self.rows("national-milestones.csv", source_timestamp="first_partial_totalization",
                               scope="BR", requested_sections_percentage="100")
        [sp] = self.rows("national-milestones.csv", source_timestamp="first_partial_totalization",
                         scope="SP", requested_sections_percentage="100")
        self.assertEqual(int(national["cumulative_sections"]), 4)
        self.assertEqual(int(national["cumulative_nominal_votes"]), 100)
        self.assertEqual(float(national["lula_percentage"]), 30)
        self.assertEqual(int(sp["cumulative_nominal_votes"]), 60)
        self.assertEqual(float(sp["lula_percentage"]), 50)
        for dimension in ("capital_status", "size_band"):
            rows = self.rows("timing-summary.csv", source_timestamp="first_partial_totalization",
                             dimension=dimension)
            [exterior] = [row for row in rows if row["group"] == "exterior"]
            domestic = [row for row in rows if row["group"] != "exterior"]
            self.assertEqual(sum(int(row["total_sections"]) for row in domestic), 3)
            self.assertEqual(sum(int(row["total_nominal_votes"]) for row in domestic), 60)
            self.assertEqual(int(exterior["total_nominal_votes"]), 40)

    def test_exact_clock_excludes_later_seconds_while_minute_curve_includes_them(self):
        self.execute(self.fixture())
        [clock] = self.rows("clock-completion.csv", source_timestamp="first_partial_totalization",
                            dimension="uf", group="SP", clock="17:30")
        [minute] = self.rows("geographic-minute.csv", source_timestamp="first_partial_totalization",
                             dimension="uf", group="SP", minute="2026-10-04 17:30:00")
        self.assertEqual(int(clock["cumulative_sections"]), 1)
        self.assertEqual(int(clock["cumulative_nominal_votes"]), 10)
        self.assertEqual(int(minute["cumulative_sections"]), 2)
        self.assertEqual(int(minute["cumulative_nominal_votes"]), 30)
        [progress] = self.rows("national-milestones.csv", source_timestamp="first_partial_totalization",
                               scope="SP", requested_sections_percentage="50")
        self.assertNotEqual(datetime.fromisoformat(clock["cutoff_timestamp"]),
                            datetime.fromisoformat(progress["cutoff_timestamp"]))
        self.assertNotEqual(float(clock["section_completion_percentage"]),
                            float(progress["actual_sections_percentage"]))

    def test_missing_timing_does_not_turn_partial_coverage_into_100_percent(self):
        events = self.fixture()
        events[-1]["first_time"] = None
        events[-1]["bu_time"] = None
        self.execute(events)
        [last] = self.rows("national-milestones.csv", source_timestamp="first_partial_totalization",
                           scope="BR", requested_sections_percentage="100")
        self.assertEqual(int(last["target_reached"]), 0)
        self.assertEqual(float(last["actual_sections_percentage"]), 75)
        self.assertEqual(float(last["nominal_completion_percentage"]), 60)

    def test_sources_rounds_and_zero_nominal_groups_are_kept_separate(self):
        events = [event(1, 10, 10, "2026-10-04 17:00:00.000000",
                        bu="2026-10-04 16:00:00.000000"),
                  event(1, 20, 0, "2026-10-25 18:00:00.000000", election="101", turn="2",
                        bu="2026-10-25 17:00:00.000000"),
                  event(2, 0, 0, "2026-10-25 18:00:00.000000", municipality="2", capital=0,
                        election="101", turn="2", band="<=10k")]
        self.execute(events)
        [first] = self.rows("national-milestones.csv", source_timestamp="first_partial_totalization",
                            election_code="100", requested_sections_percentage="100", scope="BR")
        [second] = self.rows("national-milestones.csv", source_timestamp="first_partial_totalization",
                             election_code="101", requested_sections_percentage="100", scope="BR")
        self.assertEqual(float(first["lula_percentage"]), 100)
        self.assertEqual(float(second["lula_percentage"]), 0)
        [bu] = self.rows("national-milestones.csv", source_timestamp="bu_received",
                         election_code="100", requested_sections_percentage="100", scope="BR")
        self.assertEqual(datetime.fromisoformat(bu["cutoff_timestamp"]), datetime(2026, 10, 4, 16))
        empty = self.rows("timing-summary.csv", source_timestamp="first_partial_totalization",
                          election_code="101", dimension="capital_status", group="non_capital")
        self.assertEqual(empty[0]["lula_final_percentage"], "")

    def test_flavio_geographic_fields_use_votes_not_lula_complement(self):
        first = event(1, 100, 30, "2026-10-04 17:00:00.000000")
        second = event(2, 200, 80, "2026-10-04 18:00:00.000000",
                       municipality="2", capital=0, band="<=10k")
        # The rest belong to other first-round candidates.
        first["flavio_votes"], second["flavio_votes"] = 20, 60
        self.execute([first, second])
        [timing] = self.rows("timing-summary.csv", source_timestamp="first_partial_totalization",
                             dimension="uf", group="SP")
        self.assertAlmostEqual(float(timing["flavio_final_percentage"]), 100 * 80 / 300)
        self.assertNotAlmostEqual(float(timing["flavio_final_percentage"]),
                                  100 - float(timing["lula_final_percentage"]))
        [clock] = self.rows("clock-completion.csv", source_timestamp="first_partial_totalization",
                            dimension="uf", group="SP", clock="17:30")
        self.assertEqual(float(clock["flavio_percentage"]), 20)
        [minute] = self.rows("geographic-minute.csv", source_timestamp="first_partial_totalization",
                             dimension="uf", group="SP", minute="2026-10-04 17:00:00")
        self.assertEqual(int(minute["flavio_votes_in_minute"]), 20)
        self.assertEqual(int(minute["cumulative_flavio_votes"]), 20)
        self.assertEqual(float(minute["flavio_percentage"]), 20)
        self.assertEqual(float(minute["incoming_flavio_percentage"]), 20)
        [composition] = self.rows("milestone-composition.csv",
                                  source_timestamp="first_partial_totalization", scope="BR",
                                  dimension="uf", group="SP", requested_sections_percentage="50")
        self.assertEqual(float(composition["flavio_percentage"]), 20)
        self.assertAlmostEqual(float(composition["flavio_final_percentage"]), 100 * 80 / 300)

    def test_uf_milestones_use_own_progress_include_ties_and_keep_zz_separate(self):
        events = self.fixture() + [
            event(5, 40, 10, "2026-10-04 17:30:30.000000", municipality="3", capital=0),
            event(1, 50, 5, "2026-10-04 18:10:00.000000", municipality="4",
                  uf="BA", region="Nordeste"),
        ]
        self.execute(events)
        primary = self.rows("uf-milestones.csv", source_timestamp="first_partial_totalization")
        self.assertEqual({r["scope"] for r in primary}, {"SP", "BA", "ZZ"})
        self.assertEqual(len(primary), 3 * 8)
        [half] = self.rows("uf-milestones.csv", source_timestamp="first_partial_totalization",
                           scope="SP", requested_sections_percentage="50")
        self.assertEqual(datetime.fromisoformat(half["cutoff_timestamp"]),
                         datetime(2026, 10, 4, 17, 30, 30))
        self.assertEqual(int(half["total_sections"]), 4)
        self.assertEqual(int(half["cumulative_sections"]), 3)
        self.assertEqual(float(half["actual_sections_percentage"]), 75)
        self.assertEqual(int(half["cumulative_nominal_votes"]), 70)
        self.assertEqual(int(half["total_nominal_votes"]), 100)
        self.assertAlmostEqual(float(half["lula_percentage"]), 400 / 7)
        self.assertAlmostEqual(float(half["flavio_percentage"]), 300 / 7)
        for row in self.rows("uf-milestones.csv", requested_sections_percentage="100"):
            self.assertEqual(int(row["target_reached"]), 1)
            self.assertEqual(float(row["actual_sections_percentage"]), 100)
            self.assertEqual(int(row["cumulative_nominal_votes"]), int(row["total_nominal_votes"]))


if __name__ == "__main__":
    unittest.main()
