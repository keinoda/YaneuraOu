#!/usr/bin/env python3
"""TUNABLE_PARAM定義からrshogi SPSA用paramsを生成する。"""

import argparse
from pathlib import Path
import sys
from typing import Optional, Sequence

from spsa_common import (
    EXPECTED_PARAMETER_COUNT,
    PROJECT_ROOT,
    SpsaError,
    load_source_contract,
    publish_new_file,
    render_params,
)


def generate(repo_root: Path = PROJECT_ROOT) -> str:
    _documents, parameters = load_source_contract(repo_root)
    return render_params(parameters)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="固定2ファイルの{}個のTUNABLE_PARAMからparamsを生成します。".format(
            EXPECTED_PARAMETER_COUNT
        )
    )
    parser.add_argument("-o", "--output", type=Path, help="出力先。省略時は標準出力へ出力します。")
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存の出力ファイルをatomicに置換します。",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.force and args.output is None:
        parser.error("--force は -o/--output と同時に指定してください")

    try:
        output = generate()
        if args.output is None:
            sys.stdout.write(output)
        else:
            publish_new_file(args.output, output, args.force)
            print("生成完了: {}（{}件）".format(args.output, EXPECTED_PARAMETER_COUNT))
    except SpsaError as exc:
        print("エラー: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
