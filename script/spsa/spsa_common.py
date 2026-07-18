#!/usr/bin/env python3
"""探索パラメーター用SPSAツールの共通処理。"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Dict, List, Mapping, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# パラメーター定義を探す対象は、この2ファイルだけに固定する。
TARGET_FILES: Tuple[Tuple[Path, int], ...] = (
    (Path("source/engine/yaneuraou-engine/yaneuraou-search.cpp"), 137),
    (Path("source/movepick.cpp"), 9),
)
EXPECTED_PARAMETER_COUNT = 146
NOT_USED_MARKER = "[[NOT USED]]"

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ACTIVE_MACRO_RE = re.compile(r"(?m)^[ \t]*TUNABLE_PARAM[ \t]*\(")
_TUNABLE_RE = re.compile(
    r"(?m)^[ \t]*TUNABLE_PARAM[ \t]*\("
    r"[ \t\r\n]*(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"[ \t\r\n]*,[ \t\r\n]*(?P<default>[+-]?\d+)"
    r"[ \t\r\n]*,[ \t\r\n]*(?P<minimum>[+-]?\d+)"
    r"[ \t\r\n]*,[ \t\r\n]*(?P<maximum>[+-]?\d+)"
    r"[ \t\r\n]*\)"
)


class SpsaError(Exception):
    """入力やソースの契約違反を、原因付きで通知する例外。"""


@dataclass(frozen=True)
class TunableParameter:
    name: str
    default: int
    minimum: int
    maximum: int
    relative_path: Path
    default_span: Tuple[int, int]


@dataclass(frozen=True)
class SourceDocument:
    path: Path
    relative_path: Path
    text: str
    mode: int
    parameters: Tuple[TunableParameter, ...]


@dataclass(frozen=True)
class ParamsEntry:
    name: str
    value: int
    was_rounded: bool
    minimum: Decimal
    maximum: Decimal
    c_end: Decimal
    r_end: Decimal
    not_used: bool
    line_number: int


def _read_text_preserving_newlines(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", newline="") as source_file:
            return source_file.read()
    except OSError as exc:
        raise SpsaError("ソースを読み込めません: {}: {}".format(path, exc)) from exc
    except UnicodeError as exc:
        raise SpsaError("ソースがUTF-8ではありません: {}: {}".format(path, exc)) from exc


def _parse_source_document(repo_root: Path, relative_path: Path, expected_count: int) -> SourceDocument:
    path = repo_root / relative_path
    text = _read_text_preserving_newlines(path)
    active_macro_count = len(_ACTIVE_MACRO_RE.findall(text))
    matches = list(_TUNABLE_RE.finditer(text))

    if active_macro_count != len(matches):
        raise SpsaError(
            "{} のTUNABLE_PARAM構文を解釈できません: 宣言{}件、正常な定義{}件".format(
                relative_path, active_macro_count, len(matches)
            )
        )
    if len(matches) != expected_count:
        raise SpsaError(
            "{} のパラメーター数が不正です: 期待{}件、実際{}件".format(
                relative_path, expected_count, len(matches)
            )
        )

    parameters: List[TunableParameter] = []
    names: Dict[str, int] = {}
    for match in matches:
        name = match.group("name")
        default = int(match.group("default"))
        minimum = int(match.group("minimum"))
        maximum = int(match.group("maximum"))
        line_number = text.count("\n", 0, match.start()) + 1

        if name in names:
            raise SpsaError(
                "{}:{} のパラメーター名が重複しています: {}（初出{}行）".format(
                    relative_path, line_number, name, names[name]
                )
            )
        if minimum >= maximum:
            raise SpsaError(
                "{}:{} の範囲が不正です: {} は min={}、max={}".format(
                    relative_path, line_number, name, minimum, maximum
                )
            )
        if not minimum <= default <= maximum:
            raise SpsaError(
                "{}:{} の既定値が範囲外です: {} は def={}、範囲=[{}, {}]".format(
                    relative_path, line_number, name, default, minimum, maximum
                )
            )

        names[name] = line_number
        parameters.append(
            TunableParameter(
                name=name,
                default=default,
                minimum=minimum,
                maximum=maximum,
                relative_path=relative_path,
                default_span=match.span("default"),
            )
        )

    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise SpsaError("ソースの属性を取得できません: {}: {}".format(path, exc)) from exc

    return SourceDocument(
        path=path,
        relative_path=relative_path,
        text=text,
        mode=mode,
        parameters=tuple(parameters),
    )


def load_source_contract(repo_root: Path = PROJECT_ROOT) -> Tuple[Tuple[SourceDocument, ...], Tuple[TunableParameter, ...]]:
    """固定2ファイルから全有効パラメーターの契約を読み込む。"""

    documents = tuple(
        _parse_source_document(repo_root, relative_path, expected_count)
        for relative_path, expected_count in TARGET_FILES
    )
    parameters = tuple(parameter for document in documents for parameter in document.parameters)
    if len(parameters) != EXPECTED_PARAMETER_COUNT:
        raise SpsaError(
            "全パラメーター数が不正です: 期待{}件、実際{}件".format(
                EXPECTED_PARAMETER_COUNT, len(parameters)
            )
        )

    first_locations: Dict[str, Path] = {}
    duplicates: List[str] = []
    for parameter in parameters:
        if parameter.name in first_locations:
            duplicates.append(
                "{} ({} / {})".format(
                    parameter.name, first_locations[parameter.name], parameter.relative_path
                )
            )
        else:
            first_locations[parameter.name] = parameter.relative_path
    if duplicates:
        raise SpsaError("対象2ファイル間でパラメーター名が重複しています: {}".format(", ".join(duplicates)))

    return documents, parameters


def decimal_text(value: Decimal) -> str:
    """指数表記を使わず、不要な末尾ゼロを除去する。"""

    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def render_params(parameters: Sequence[TunableParameter]) -> str:
    lines = []
    for parameter in parameters:
        c_end = Decimal(parameter.maximum - parameter.minimum) / Decimal(20)
        lines.append(
            "{},{},{},{},{},{},{}".format(
                parameter.name,
                "int",
                parameter.default,
                parameter.minimum,
                parameter.maximum,
                decimal_text(c_end),
                "0.002",
            )
        )
    return "\n".join(lines) + "\n"


def _parse_decimal(raw_value: str, field_name: str, path: Path, line_number: int) -> Decimal:
    try:
        value = Decimal(raw_value)
    except (InvalidOperation, ValueError) as exc:
        raise SpsaError(
            "{}:{} の{}が数値ではありません: {!r}".format(path, line_number, field_name, raw_value)
        ) from exc
    if not value.is_finite():
        raise SpsaError(
            "{}:{} の{}は有限値でなければなりません: {!r}".format(
                path, line_number, field_name, raw_value
            )
        )
    return value


def parse_params_file(path: Path) -> Tuple[ParamsEntry, ...]:
    """params全体を検証してから、重複のないエントリー列を返す。"""

    try:
        with path.open("r", encoding="utf-8") as params_file:
            lines = params_file.readlines()
    except OSError as exc:
        raise SpsaError("paramsファイルを読み込めません: {}: {}".format(path, exc)) from exc
    except UnicodeError as exc:
        raise SpsaError("paramsファイルがUTF-8ではありません: {}: {}".format(path, exc)) from exc

    entries: List[ParamsEntry] = []
    first_lines: Dict[str, int] = {}
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            continue

        marker_count = line.count(NOT_USED_MARKER)
        if marker_count > 1:
            raise SpsaError(
                "{}:{} に{}が複数あります".format(path, line_number, NOT_USED_MARKER)
            )
        not_used = marker_count == 1
        value_part = line.replace(NOT_USED_MARKER, "")
        if "//" in value_part:
            value_part = value_part.split("//", 1)[0]

        fields = [field.strip() for field in value_part.split(",")]
        if len(fields) != 7:
            raise SpsaError(
                "{}:{} の列数が不正です: 期待7列、実際{}列".format(
                    path, line_number, len(fields)
                )
            )
        name, parameter_type, raw_current, raw_minimum, raw_maximum, raw_c_end, raw_r_end = fields
        if not _IDENTIFIER_RE.fullmatch(name):
            raise SpsaError("{}:{} の名前が不正です: {!r}".format(path, line_number, name))
        if name in first_lines:
            raise SpsaError(
                "{}:{} の名前が重複しています: {}（初出{}行）".format(
                    path, line_number, name, first_lines[name]
                )
            )
        if parameter_type != "int":
            raise SpsaError(
                "{}:{} の型が不正です: {} は int でなければなりません".format(
                    path, line_number, name
                )
            )

        current_decimal = _parse_decimal(raw_current, "現在値", path, line_number)
        minimum = _parse_decimal(raw_minimum, "min", path, line_number)
        maximum = _parse_decimal(raw_maximum, "max", path, line_number)
        c_end = _parse_decimal(raw_c_end, "c_end", path, line_number)
        r_end = _parse_decimal(raw_r_end, "r_end", path, line_number)
        if minimum >= maximum:
            raise SpsaError(
                "{}:{} の範囲が不正です: {} は min={}、max={}".format(
                    path, line_number, name, raw_minimum, raw_maximum
                )
            )
        if not minimum <= current_decimal <= maximum:
            raise SpsaError(
                "{}:{} の現在値が範囲外です: {}={}、範囲=[{}, {}]".format(
                    path, line_number, name, raw_current, raw_minimum, raw_maximum
                )
            )
        if c_end <= 0:
            raise SpsaError("{}:{} のc_endは正でなければなりません: {}".format(path, line_number, raw_c_end))
        if r_end <= 0:
            raise SpsaError("{}:{} のr_endは正でなければなりません: {}".format(path, line_number, raw_r_end))

        # rshogiはint型パラメーターもSPSA内部のθを小数のまま保存する。
        # 焼き込み時だけC++のround()と同じく、0.5を0から遠い側へ丸める。
        rounded_decimal = current_decimal.to_integral_value(rounding=ROUND_HALF_UP)

        first_lines[name] = line_number
        entries.append(
            ParamsEntry(
                name=name,
                value=int(rounded_decimal),
                was_rounded=current_decimal != rounded_decimal,
                minimum=minimum,
                maximum=maximum,
                c_end=c_end,
                r_end=r_end,
                not_used=not_used,
                line_number=line_number,
            )
        )

    if not entries:
        raise SpsaError("paramsファイルにパラメーターがありません: {}".format(path))
    return tuple(entries)


def replace_defaults(document: SourceDocument, values: Mapping[str, int]) -> Tuple[str, int]:
    """各マクロのdefトークンだけを置換する。"""

    replacements: List[Tuple[int, int, str]] = []
    changed_count = 0
    for parameter in document.parameters:
        new_value = values[parameter.name]
        if parameter.default != new_value:
            changed_count += 1
        replacements.append((parameter.default_span[0], parameter.default_span[1], str(new_value)))

    text = document.text
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text, changed_count


def stage_atomic_text(path: Path, text: str, mode: int) -> Path:
    """同じディレクトリにfsync済み一時ファイルを作る。"""

    try:
        file_descriptor, temporary_name = tempfile.mkstemp(prefix=".{}-".format(path.name), dir=str(path.parent))
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as temporary_file:
                temporary_file.write(text)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.chmod(str(temporary_path), mode)
            return temporary_path
        except Exception:
            try:
                temporary_path.unlink()
            except OSError:
                pass
            raise
    except OSError as exc:
        raise SpsaError("一時ファイルを作成できません: {}: {}".format(path.parent, exc)) from exc


def publish_new_file(path: Path, text: str, force: bool) -> None:
    """新規作成は競合を拒否し、--force時だけatomicに置換する。"""

    if path.exists() and not force:
        raise SpsaError("出力先は既に存在します（置換するには --force が必要です）: {}".format(path))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SpsaError("出力先ディレクトリを作成できません: {}: {}".format(path.parent, exc)) from exc

    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    temporary_path = stage_atomic_text(path, text, mode)
    try:
        if force:
            os.replace(str(temporary_path), str(path))
        else:
            # hard linkなら、出力先が同時に作成されても既存ファイルを上書きしない。
            os.link(str(temporary_path), str(path))
            temporary_path.unlink()
    except FileExistsError as exc:
        raise SpsaError("出力先は既に存在します（置換するには --force が必要です）: {}".format(path)) from exc
    except OSError as exc:
        raise SpsaError("出力ファイルをatomicに確定できません: {}: {}".format(path, exc)) from exc
    finally:
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass
