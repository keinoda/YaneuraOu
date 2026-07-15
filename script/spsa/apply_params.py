#!/usr/bin/env python3
"""rshogi SPSA用paramsの整数値をTUNABLE_PARAMのdefへ適用する。"""

import argparse
from decimal import Decimal
import os
from pathlib import Path
import sys
from typing import Dict, List, Optional, Sequence, Tuple

from spsa_common import (
    PROJECT_ROOT,
    SourceDocument,
    SpsaError,
    load_source_contract,
    parse_params_file,
    replace_defaults,
    stage_atomic_text,
)


def prepare_application(params_path: Path, repo_root: Path = PROJECT_ROOT) -> Tuple[
    Tuple[SourceDocument, ...], Dict[Path, str], int, Tuple[str, ...]
]:
    """全入力を検証し、書き込み前の新しい内容をメモリ上で組み立てる。"""

    documents, parameters = load_source_contract(repo_root)
    entries = parse_params_file(params_path)
    parameters_by_name = {parameter.name: parameter for parameter in parameters}
    known_names = set(parameters_by_name)

    active_values: Dict[str, int] = {}
    known_not_used: List[str] = []
    warnings: List[str] = []
    for entry in entries:
        if entry.name not in known_names:
            suffix = "（NOT USED）" if entry.not_used else ""
            warnings.append("未知のパラメーターを無視します: {}{}".format(entry.name, suffix))
        elif entry.not_used:
            known_not_used.append(entry.name)
        else:
            parameter = parameters_by_name[entry.name]
            if (
                entry.minimum != Decimal(parameter.minimum)
                or entry.maximum != Decimal(parameter.maximum)
            ):
                raise SpsaError(
                    "{}:{} の範囲がソース定義と一致しません: {} は params=[{}, {}]、"
                    "source=[{}, {}]".format(
                        params_path,
                        entry.line_number,
                        entry.name,
                        entry.minimum,
                        entry.maximum,
                        parameter.minimum,
                        parameter.maximum,
                    )
                )
            active_values[entry.name] = entry.value

    missing_names = sorted(known_names - set(active_values))
    if missing_names:
        details = []
        if known_not_used:
            details.append("既知名がNOT USED: {}".format(", ".join(sorted(known_not_used))))
        details.append("不足: {}".format(", ".join(missing_names)))
        raise SpsaError(
            "有効な既知パラメーター148件が揃っていないため適用しません（{}）".format(
                "、".join(details)
            )
        )

    new_texts: Dict[Path, str] = {}
    changed_count = 0
    for document in documents:
        new_text, document_changed_count = replace_defaults(document, active_values)
        new_texts[document.path] = new_text
        changed_count += document_changed_count
    return documents, new_texts, changed_count, tuple(warnings)


def apply_parameters(params_path: Path, repo_root: Path = PROJECT_ROOT, dry_run: bool = False) -> Tuple[int, int, Tuple[str, ...]]:
    documents, new_texts, changed_count, warnings = prepare_application(params_path, repo_root)
    changed_documents = [document for document in documents if new_texts[document.path] != document.text]
    if dry_run:
        return changed_count, len(changed_documents), warnings

    # 先に全ファイルをstageし、検証後の書き込みを各ファイル単位でatomicにする。
    staged: List[Tuple[Path, Path]] = []
    try:
        for document in changed_documents:
            temporary_path = stage_atomic_text(
                document.path, new_texts[document.path], document.mode
            )
            staged.append((temporary_path, document.path))
        for temporary_path, destination in staged:
            os.replace(str(temporary_path), str(destination))
    except OSError as exc:
        raise SpsaError("ソースをatomicに置換できません: {}".format(exc)) from exc
    finally:
        for temporary_path, _destination in staged:
            if temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    return changed_count, len(changed_documents), warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="paramsの有効な既知148名を、固定2ファイルのdef値へ適用します。"
    )
    parser.add_argument("params", type=Path, help="適用するparamsファイル")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="全検証と変更数の計算だけを行い、ソースを書き換えません。",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        changed_count, changed_file_count, warnings = apply_parameters(
            args.params, dry_run=args.dry_run
        )
        for warning in warnings:
            print("警告: {}".format(warning), file=sys.stderr)
        action = "dry-run完了" if args.dry_run else "適用完了"
        print(
            "{}: パラメーター{}件、ファイル{}件を変更{}".format(
                action,
                changed_count,
                changed_file_count,
                "予定" if args.dry_run else "",
            )
        )
    except SpsaError as exc:
        print("エラー: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
