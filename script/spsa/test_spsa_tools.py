#!/usr/bin/env python3
"""gen_params.py / apply_params.py の回帰テスト。"""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from apply_params import apply_parameters  # noqa: E402
from gen_params import generate  # noqa: E402
from spsa_common import (  # noqa: E402
    EXPECTED_PARAMETER_COUNT,
    NOT_USED_MARKER,
    SpsaError,
    TARGET_FILES,
    load_source_contract,
    parse_params_file,
    publish_new_file,
)


class TemporaryRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temporary_directory.name)
        for relative_path, _expected_count in TARGET_FILES:
            destination = self.repo_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(REPO_ROOT / relative_path), str(destination))

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_params(self, text):
        path = self.repo_root / "input.params"
        path.write_text(text, encoding="utf-8")
        return path

    def source_bytes(self):
        return {
            relative_path: (self.repo_root / relative_path).read_bytes()
            for relative_path, _expected_count in TARGET_FILES
        }


class SourceContractTests(unittest.TestCase):
    def test_real_repository_has_exactly_139_plus_9_unique_parameters(self):
        documents, parameters = load_source_contract(REPO_ROOT)
        names = {parameter.name for parameter in parameters}
        self.assertEqual([len(document.parameters) for document in documents], [139, 9])
        self.assertEqual(len(parameters), EXPECTED_PARAMETER_COUNT)
        self.assertEqual(len(names), EXPECTED_PARAMETER_COUNT)
        self.assertTrue(
            {
                "YaneuraOuWorker_clear1_1",
                "YaneuraOuWorker_clear1_2",
                "YaneuraOuWorker_clear1_3",
                "update_all_stats_1c_6",
            }.issubset(names)
        )
        self.assertTrue(
            names.isdisjoint(
                {
                    "Search_Decrease_reduction_for_PvNodes_6_1",
                    "Search_Decrease_reduction_for_PvNodes_6_2",
                    "Search_nullmove_1",
                    "Search_nullmove_2",
                }
            )
        )

    def test_divisor_parameter_ranges_exclude_zero(self):
        _documents, parameters = load_source_contract(REPO_ROOT)
        parameters_by_name = {parameter.name: parameter for parameter in parameters}
        divisor_names = {
            "aspiration_window_2",
            "Search_futility_1_5",
            "Search_Continuation_history_based_pruning1_3",
            "Search_Extensions1_3",
            "Search_Extensions2_1",
            "Search_Decrease_reduction_for_PvNodes_3_2",
            "Search_fail_low_quiet_bonus_2",
            "MovePicker_good_capture_see_1",
        }
        self.assertTrue(divisor_names.issubset(parameters_by_name))
        for name in divisor_names:
            with self.subTest(name=name):
                self.assertGreater(parameters_by_name[name].minimum, 0)

    def test_generated_params_have_exact_format_and_no_not_used(self):
        output = generate(REPO_ROOT)
        lines = output.splitlines()
        self.assertTrue(output.endswith("\n"))
        self.assertEqual(len(lines), EXPECTED_PARAMETER_COUNT)
        self.assertNotIn(NOT_USED_MARKER, output)
        self.assertEqual(lines[0], "QSearch_SEE_pruning_1,int,-73,-146,0,7.3,0.002")
        self.assertIn("Search_fail_low_quiet_bonus_13,int,1400,0,2800,140,0.002", lines)
        self.assertEqual(lines[-1], "MovePicker_capture_score_1,int,7,0,14,0.7,0.002")

    def test_cli_is_independent_of_current_working_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "gen_params.py")],
                cwd=temporary_directory,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), EXPECTED_PARAMETER_COUNT)

    def test_apply_cli_is_independent_of_current_working_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            params_path = Path(temporary_directory) / "generated.params"
            params_path.write_text(generate(REPO_ROOT), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "apply_params.py"),
                    str(params_path),
                    "--dry-run",
                ],
                cwd=temporary_directory,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry-run完了", result.stdout)


class SourceContractValidationTests(TemporaryRepositoryTestCase):
    def replace_in_search_source(self, old, new):
        relative_path = TARGET_FILES[0][0]
        path = self.repo_root / relative_path
        with path.open("r", encoding="utf-8", newline="") as source_file:
            text = source_file.read()
        self.assertIn(old, text)
        with path.open("w", encoding="utf-8", newline="") as source_file:
            source_file.write(text.replace(old, new, 1))

    def test_rejects_non_integer_macro_value(self):
        self.replace_in_search_source(
            "TUNABLE_PARAM(QSearch_SEE_pruning_1, -73, -146, 0)",
            "TUNABLE_PARAM(QSearch_SEE_pruning_1, -73.5, -146, 0)",
        )
        with self.assertRaisesRegex(SpsaError, "構文を解釈できません"):
            load_source_contract(self.repo_root)

    def test_rejects_invalid_range_and_out_of_range_default(self):
        self.replace_in_search_source(
            "TUNABLE_PARAM(QSearch_SEE_pruning_1, -73, -146, 0)",
            "TUNABLE_PARAM(QSearch_SEE_pruning_1, -73, 0, -146)",
        )
        with self.assertRaisesRegex(SpsaError, "範囲が不正"):
            load_source_contract(self.repo_root)

        # 最初の異常を戻してから、既定値だけを範囲外にする。
        self.replace_in_search_source(
            "TUNABLE_PARAM(QSearch_SEE_pruning_1, -73, 0, -146)",
            "TUNABLE_PARAM(QSearch_SEE_pruning_1, 1, -146, 0)",
        )
        with self.assertRaisesRegex(SpsaError, "既定値が範囲外"):
            load_source_contract(self.repo_root)

    def test_rejects_duplicate_source_name(self):
        self.replace_in_search_source(
            "TUNABLE_PARAM(QSearch_move_count_pruning_1, 2, 0, 4)",
            "TUNABLE_PARAM(QSearch_SEE_pruning_1, 2, 0, 4)",
        )
        with self.assertRaisesRegex(SpsaError, "重複"):
            load_source_contract(self.repo_root)


class GenerateOutputTests(unittest.TestCase):
    def test_existing_output_requires_force_and_force_replaces_atomically(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "generated.params"
            output_path.write_text("既存\n", encoding="utf-8")
            original_inode = output_path.stat().st_ino

            with self.assertRaisesRegex(SpsaError, "--force"):
                publish_new_file(output_path, "新規\n", force=False)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "既存\n")

            publish_new_file(output_path, "新規\n", force=True)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "新規\n")
            self.assertNotEqual(output_path.stat().st_ino, original_inode)


class ApplyTests(TemporaryRepositoryTestCase):
    def test_applies_only_default_numeric_spans(self):
        documents, parameters = load_source_contract(self.repo_root)
        lines = generate(self.repo_root).splitlines()
        replacements = {
            parameters[0].name: parameters[0].default + 1,
            parameters[-1].name: parameters[-1].default + 1,
        }
        for index, line in enumerate(lines):
            fields = line.split(",")
            if fields[0] in replacements:
                fields[2] = "{}.0".format(replacements[fields[0]])
                lines[index] = ",".join(fields)
        params_path = self.write_params("\n".join(lines) + "\n")

        expected_texts = {}
        for document in documents:
            expected = document.text
            spans = []
            for parameter in document.parameters:
                value = replacements.get(parameter.name, parameter.default)
                spans.append((parameter.default_span[0], parameter.default_span[1], str(value)))
            for start, end, value in reversed(spans):
                expected = expected[:start] + value + expected[end:]
            expected_texts[document.relative_path] = expected

        changed_count, changed_file_count, warnings = apply_parameters(
            params_path, repo_root=self.repo_root
        )
        self.assertEqual(changed_count, 2)
        self.assertEqual(changed_file_count, 2)
        self.assertEqual(warnings, ())
        for relative_path, expected in expected_texts.items():
            with (self.repo_root / relative_path).open("r", encoding="utf-8", newline="") as source_file:
                self.assertEqual(source_file.read(), expected)

    def test_unknown_active_and_not_used_entries_warn_and_are_skipped(self):
        params_text = generate(self.repo_root)
        params_text += "FutureParam,int,1,0,2,0.1,0.002\n"
        params_text += "OldParam,int,1,0,2,0.1,0.002 [[NOT USED]]\n"
        params_path = self.write_params(params_text)

        changed_count, changed_file_count, warnings = apply_parameters(
            params_path, repo_root=self.repo_root, dry_run=True
        )
        self.assertEqual(changed_count, 0)
        self.assertEqual(changed_file_count, 0)
        self.assertEqual(len(warnings), 2)
        self.assertIn("FutureParam", warnings[0])
        self.assertIn("OldParam", warnings[1])

    def test_known_not_used_is_reported_as_required_name_missing(self):
        lines = generate(self.repo_root).splitlines()
        known_name = lines[0].split(",", 1)[0]
        lines[0] += " [[NOT USED]]"
        params_path = self.write_params("\n".join(lines) + "\n")
        before = self.source_bytes()

        with self.assertRaisesRegex(SpsaError, "既知名がNOT USED.*{}".format(known_name)):
            apply_parameters(params_path, repo_root=self.repo_root)
        self.assertEqual(self.source_bytes(), before)

    def test_any_duplicate_name_is_an_error_before_writing(self):
        params_text = generate(self.repo_root)
        params_text += "UnknownParam,int,1,0,2,0.1,0.002\n"
        params_text += "UnknownParam,int,1,0,2,0.1,0.002 [[NOT USED]]\n"
        params_path = self.write_params(params_text)
        before = self.source_bytes()

        with self.assertRaisesRegex(SpsaError, "重複"):
            apply_parameters(params_path, repo_root=self.repo_root)
        self.assertEqual(self.source_bytes(), before)

    def test_missing_known_name_is_an_error_before_writing(self):
        lines = generate(self.repo_root).splitlines()
        missing_name = lines.pop(10).split(",", 1)[0]
        params_path = self.write_params("\n".join(lines) + "\n")
        before = self.source_bytes()

        with self.assertRaisesRegex(SpsaError, "不足: .*{}".format(missing_name)):
            apply_parameters(params_path, repo_root=self.repo_root)
        self.assertEqual(self.source_bytes(), before)

    def test_known_range_mismatch_is_an_error_before_writing(self):
        lines = generate(self.repo_root).splitlines()
        fields = lines[0].split(",")
        fields[3] = str(int(fields[3]) - 1)
        lines[0] = ",".join(fields)
        params_path = self.write_params("\n".join(lines) + "\n")
        before = self.source_bytes()

        with self.assertRaisesRegex(SpsaError, "範囲がソース定義と一致しません"):
            apply_parameters(params_path, repo_root=self.repo_root)
        self.assertEqual(self.source_bytes(), before)

    def test_dry_run_never_writes_sources(self):
        lines = generate(self.repo_root).splitlines()
        fields = lines[0].split(",")
        fields[2] = str(int(fields[2]) + 1)
        lines[0] = ",".join(fields)
        params_path = self.write_params("\n".join(lines) + "\n")
        before = self.source_bytes()

        changed_count, changed_file_count, warnings = apply_parameters(
            params_path, repo_root=self.repo_root, dry_run=True
        )
        self.assertEqual((changed_count, changed_file_count, warnings), (1, 1, ()))
        self.assertEqual(self.source_bytes(), before)


class ParamsValidationTests(unittest.TestCase):
    def assert_invalid(self, text, message_pattern):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "invalid.params"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(SpsaError, message_pattern):
                parse_params_file(path)

    def test_rejects_malformed_columns(self):
        self.assert_invalid("A,int,1,0,2,0.1\n", "列数")

    def test_rejects_non_integral_current_value_without_rounding(self):
        self.assert_invalid("A,int,1.5,0,2,0.1,0.002\n", "整数相当")

    def test_rejects_nan_and_infinity(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                self.assert_invalid("A,int,{},0,2,0.1,0.002\n".format(value), "有限値")

    def test_rejects_non_int_type(self):
        self.assert_invalid("A,float,1,0,2,0.1,0.002\n", "int")

    def test_rejects_out_of_range_current_value(self):
        self.assert_invalid("A,int,3,0,2,0.1,0.002\n", "範囲外")

    def test_rejects_invalid_range_and_schedule(self):
        self.assert_invalid("A,int,1,1,1,0.1,0.002\n", "範囲が不正")
        self.assert_invalid("A,int,1,0,2,0,0.002\n", "c_endは正")
        self.assert_invalid("A,int,1,0,2,0.1,0\n", "r_endは正")


if __name__ == "__main__":
    unittest.main()
