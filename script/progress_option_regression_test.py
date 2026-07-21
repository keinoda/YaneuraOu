#!/usr/bin/env python3
"""進行度係数パスのUSIオプション名を検証する回帰テスト。"""

import argparse
import os
import re
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-bin", required=True)
    parser.add_argument("--engine-dir")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    engine_bin = os.path.abspath(args.engine_bin)
    engine_dir = os.path.abspath(args.engine_dir or os.path.dirname(engine_bin))
    if not os.path.isfile(engine_bin):
        raise SystemExit(f"エンジンが見つかりません: {engine_bin}")

    try:
        completed = subprocess.run(
            [engine_bin],
            input="usi\nquit\n",
            cwd=engine_dir,
            text=True,
            capture_output=True,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"USIオプション取得が{args.timeout}秒でタイムアウトしました") from exc
    except OSError as exc:
        raise SystemExit(f"エンジンを起動できません: {exc}") from exc

    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise SystemExit(
            f"エンジンが終了コード{completed.returncode}で失敗しました:\n{output}"
        )
    if "usiok" not in output:
        raise SystemExit(f"usiokを確認できませんでした:\n{output}")

    current_option = re.findall(
        r"^option name LS_PROGRESS_COEFF(?:\s|$)", output, flags=re.MULTILINE
    )
    if len(current_option) != 1:
        raise SystemExit(
            f"LS_PROGRESS_COEFFの登録数が1ではありません: {len(current_option)}"
        )
    if re.search(r"^option name ProgressFilePath(?:\s|$)", output, flags=re.MULTILINE):
        raise SystemExit("削除対象のProgressFilePathがUSIオプションに残っています")

    print("PASS: LS_PROGRESS_COEFFのみがUSIオプションとして登録されています")


if __name__ == "__main__":
    main()
