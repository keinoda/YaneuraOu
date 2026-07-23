import unittest
from pathlib import Path

from script.ordo_from_markdown import (
    MarkdownResultError,
    analyze_group,
    analyze_table,
    format_markdown,
    group_result_tables,
    parse_result_tables,
)


FIXTURE = """\
# NAGISA_V3 棋力比較

## 参考

### 1手1秒，1Thread

| 対戦相手 | 対局数 | NAGISA_V3成績（勝–敗–引分） | Ptnml |
|---|---:|---:|---:|
| 水匠5 | 1,024 | 802–173–49 | [12, 8, 143, 37, 312] |
| AobaNNUE | 1,026 | 531–434–61 | [87, 31, 234, 20, 141] |
"""

PAIR_FIXTURE = """\
# NAGISA_V3 棋力比較

## 参考

### 40s+0.4s，1Thread

| A vs B | 対局数 | A目線成績（勝–敗–引分） | Ptnml（A目線） |
|---|---:|---:|---:|
| AobaNNUE vs 水匠11β | 1,026 | 443–539–44 | [131, 25, 253, 17, 87] |
"""

FOLDED_FIXTURE = """\
# NGSv3 棋力比較

<details>
<summary><strong>参考(v9.60gitパラメータに統一)</strong></summary>

### 40s+0.4s，1Thread

| 対戦相手 | 対局数 | NGSv3成績（勝–敗–引分） | Ptnml |
|---|---:|---:|---:|
| 水匠11 | 1,054 | 474–458–122 | [85, 69, 224, 43, 106] |

</details>
"""


class MarkdownOrdoTests(unittest.TestCase):

    def test_parses_win_loss_draw_order_and_ptnml(self):
        table = parse_result_tables(FIXTURE)[0]

        self.assertEqual(table.subject, "NAGISA_V3")
        self.assertEqual(table.section, "参考")
        self.assertEqual(table.condition, "1手1秒，1Thread")
        self.assertEqual(
            (table.matches[0].wins, table.matches[0].losses,
             table.matches[0].draws),
            (802, 173, 49),
        )
        self.assertEqual(table.matches[0].ptnml, (12, 8, 143, 37, 312))
        self.assertEqual(table.matches[0].subject, "NAGISA_V3")

    def test_parses_individual_a_vs_b_rows_from_a_perspective(self):
        table = parse_result_tables(PAIR_FIXTURE)[0]
        match = table.matches[0]

        self.assertEqual(table.subject, "")
        self.assertEqual(match.subject, "AobaNNUE")
        self.assertEqual(match.opponent, "水匠11β")
        self.assertEqual(
            (match.wins, match.losses, match.draws),
            (443, 539, 44),
        )
        self.assertEqual(match.ptnml, (131, 25, 253, 17, 87))

    def test_parses_folded_summary_as_section(self):
        table = parse_result_tables(FOLDED_FIXTURE)[0]

        self.assertEqual(
            table.section, "参考(v9.60gitパラメータに統一)"
        )
        self.assertEqual(table.condition, "40s+0.4s，1Thread")
        self.assertEqual(table.subject, "NGSv3")

    def test_rejects_inconsistent_ptnml(self):
        broken = FIXTURE.replace(
            "[12, 8, 143, 37, 312]", "[13, 8, 143, 37, 312]"
        )

        with self.assertRaisesRegex(MarkdownResultError, "対局数とPtnml"):
            parse_result_tables(broken)

    def test_rejects_a_different_wdl_column_order(self):
        broken = FIXTURE.replace("勝–敗–引分", "勝–引分–敗")

        with self.assertRaisesRegex(MarkdownResultError, "勝–敗–引分の順"):
            parse_result_tables(broken)

    def test_point_ratings_are_centered(self):
        table = parse_result_tables(FIXTURE)[0]
        analysis = analyze_table(table, bootstrap_samples=0)

        self.assertAlmostEqual(
            sum(player.rating for player in analysis.players), 0.0, places=10
        )
        ratings = {player.name: player.rating for player in analysis.players}
        self.assertGreater(ratings["NAGISA_V3"], ratings["AobaNNUE"])
        self.assertGreater(ratings["AobaNNUE"], ratings["水匠5"])

    def test_bootstrap_is_deterministic(self):
        table = parse_result_tables(FIXTURE)[0]

        first = analyze_table(table, bootstrap_samples=100, seed=42)
        second = analyze_table(table, bootstrap_samples=100, seed=42)

        self.assertEqual(first, second)
        self.assertTrue(all(player.lower is not None for player in first.players))

    def test_missing_ptnml_keeps_point_estimate(self):
        text = FIXTURE.replace(
            "[12, 8, 143, 37, 312]", "—"
        ).replace(
            "[87, 31, 234, 20, 141]", "—"
        )
        table = parse_result_tables(text)[0]
        analysis = analyze_table(table, bootstrap_samples=100)

        self.assertIn("点推定のみ", analysis.warning)
        self.assertTrue(all(player.lower is None for player in analysis.players))

    def test_formats_pasteable_markdown(self):
        table = parse_result_tables(FIXTURE)[0]
        analysis = analyze_table(table, bootstrap_samples=20, seed=7)
        output = format_markdown([analysis])

        self.assertIn("## 参考 / 1手1秒，1Thread", output)
        self.assertIn("| 順位 | AI | Rating | 95%区間 |", output)
        self.assertIn("| NAGISA_V3 |", output)

    def test_current_release_document_is_readable(self):
        repository = Path(__file__).resolve().parents[1]
        document = repository / "docs" / "nagisa-v3-elo-v2.md"

        tables = parse_result_tables(document.read_text(encoding="utf-8"))
        groups = group_result_tables(tables)

        self.assertEqual(len(tables), 6)
        self.assertEqual(
            [group.condition for group in groups],
            [
                "1手1秒，1Thread（SPSA条件）",
                "40s+0.4s，1Thread",
                "8s+0.08s，1Thread",
                "1手1秒，1Thread",
                "40s+0.4s，1Thread",
            ],
        )
        self.assertEqual(len(groups[-1].tables), 2)
        self.assertEqual(
            sum(len(table.matches) for table in groups[-1].tables),
            6,
        )
        analysis = analyze_group(groups[-1], bootstrap_samples=0)
        self.assertEqual(
            {player.name for player in analysis.players},
            {
                "NGSv3",
                "AobaNNUE",
                "奏乗（TSEC7版）",
                "水匠11β",
                "水匠11",
            },
        )


if __name__ == "__main__":
    unittest.main()
