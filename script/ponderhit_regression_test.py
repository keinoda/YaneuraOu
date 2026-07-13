#!/usr/bin/env python3
"""ponderhit時間制御拡張のPTY回帰テスト。

失敗時はAssertionErrorにより非0で終了する。
定跡を無効化し、詰みでなく合法手が複数ある固定局面を使用する。

必要: pip install pexpect python-shogi

usage:
  python3 script/ponderhit_regression_test.py \
      --engine-dir /path/to/engine --engine-bin ./YaneuraOu-by-gcc
"""

import argparse
import os
import time

try:
    import pexpect
    import shogi
except ImportError as exc:
    raise SystemExit("pexpectとpython-shogiが必要です: pip install pexpect python-shogi") from exc


parser = argparse.ArgumentParser()
parser.add_argument("--engine-dir", required=True)
parser.add_argument("--engine-bin", default="./YaneuraOu-by-gcc")
parser.add_argument("--ponder-sleep", type=float, default=0.3)
parser.add_argument("--tolerance-ms", type=float, default=450.0)
parser.add_argument("--quiet-seconds", type=float, default=0.5)
args = parser.parse_args()

engine_bin = args.engine_bin
if not os.path.isabs(engine_bin):
    engine_bin = os.path.join(args.engine_dir, engine_bin)
if not os.path.isfile(engine_bin):
    raise SystemExit(f"エンジンが見つかりません: {engine_bin}")

position_moves = ["2g2f", "8c8d", "7g7f"]
position_cmd = "position startpos moves " + " ".join(position_moves)

board = shogi.Board()
for move in position_moves:
    board.push_usi(move)
legal_moves = {move.usi() for move in board.legal_moves}
assert "8d8e" in legal_moves

ponder_board = shogi.Board()
for move in position_moves[:-1]:
    ponder_board.push_usi(move)
stochastic_ponder_legal_moves = {move.usi() for move in ponder_board.legal_moves}
assert legal_moves.isdisjoint(stochastic_ponder_legal_moves)

byo_long = "btime 0 wtime 0 byoyomi 3000"
byo_mid = "btime 0 wtime 0 byoyomi 2500"
byo_short = "btime 0 wtime 0 byoyomi 2000"
fischer_low = "btime 1100 wtime 1100 binc 2000 winc 2000"
asymmetric_clock = "btime 1100 wtime 3000"

engine = pexpect.spawn(
    engine_bin,
    cwd=args.engine_dir,
    encoding="utf-8",
    echo=False,
    timeout=30,
)


def send(command):
    engine.sendline(command)


def drain(seconds=0.15):
    output = ""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            output += engine.read_nonblocking(size=65536, timeout=0.03)
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            break
    return output


def assert_no_bestmove(label, seconds):
    output = drain(seconds)
    assert "bestmove" not in output, f"{label}: 予期しないbestmoveを検出した"
    return output


def extract_pv_root_moves(output):
    root_moves = []
    for line in output.replace("\r", "").splitlines():
        fields = line.split()
        if not fields or fields[0] != "info" or "pv" not in fields:
            continue
        pv_index = fields.index("pv")
        if pv_index + 1 < len(fields):
            root_moves.append(fields[pv_index + 1])
    return root_moves


def extract_search_samples(output):
    samples = []
    for line in output.replace("\r", "").splitlines():
        fields = line.split()
        if not fields or fields[0] != "info" or "depth" not in fields or "nodes" not in fields:
            continue
        try:
            depth = int(fields[fields.index("depth") + 1])
            nodes = int(fields[fields.index("nodes") + 1])
        except (ValueError, IndexError):
            continue
        samples.append((depth, nodes))
    return samples


def expect_bestmove(timeout=30):
    engine.expect(r"bestmove [^\r\n]+", timeout=timeout)
    line = engine.after.strip()
    return line.split()[1], engine.before + line


def assert_legal_bestmove(label, bestmove):
    assert bestmove in legal_moves, f"{label}: 非合法bestmove: {bestmove}"


def set_stochastic_ponder(label, enabled):
    assert_no_bestmove(f"{label}: オプション設定前", 0.05)
    expected = "true" if enabled else "false"
    send(f"setoption name Stochastic_Ponder value {expected}")
    send("getoption Stochastic_Ponder")
    engine.expect(r"(true|false)", timeout=5)
    actual = engine.match.group(1)
    assert actual == expected, f"{label}: Stochastic_Ponder={actual}, 期待={expected}"
    assert_no_bestmove(f"{label}: オプション設定後", 0.05)


def assert_reference_latency(label, elapsed_ms, reference_ms):
    difference = abs(elapsed_ms - reference_ms)
    assert difference <= args.tolerance_ms, (
        f"{label}: {elapsed_ms:.0f}ms, 基準{reference_ms:.0f}msと{difference:.0f}ms差"
    )


def run_go(label, go_args):
    assert_no_bestmove(f"{label}: 開始前", 0.05)
    send(position_cmd)
    started = time.monotonic()
    send("go " + go_args)
    bestmove, output = expect_bestmove()
    elapsed_ms = (time.monotonic() - started) * 1000
    tail = assert_no_bestmove(f"{label}: 応答後", args.quiet_seconds)
    assert_legal_bestmove(label, bestmove)
    print(f"PASS {label:52s} {elapsed_ms:7.0f}ms bestmove={bestmove}", flush=True)
    return elapsed_ms, output + tail


def run_ponder_case(
    label,
    stochastic,
    go_args,
    hit_args,
    reference_ms=None,
    expected_warning=False,
    expected_bestmoves=None,
    maximum_ms=None,
    expected_ponder_legal_moves=None,
    expect_continuity=False,
):
    set_stochastic_ponder(label, stochastic)
    send(position_cmd)
    send(("go ponder " + go_args).strip())
    time.sleep(args.ponder_sleep)
    before_hit = drain() if args.ponder_sleep > 0 else ""
    assert "bestmove" not in before_hit, f"{label}: ponderhit前にbestmoveを出力した"
    if expected_ponder_legal_moves is not None and args.ponder_sleep > 0:
        pv_root_moves = extract_pv_root_moves(before_hit)
        assert pv_root_moves, f"{label}: Ponder中のPVを観測できなかった"
        unexpected = set(pv_root_moves) - expected_ponder_legal_moves
        assert not unexpected, (
            f"{label}: 想定外のPonderルート手={sorted(unexpected)}, "
            f"観測={pv_root_moves}"
        )

    started = time.monotonic()
    send(("ponderhit " + hit_args).strip())
    bestmove, output = expect_bestmove()
    elapsed_ms = (time.monotonic() - started) * 1000
    tail = assert_no_bestmove(f"{label}: 応答後", args.quiet_seconds)
    combined_output = before_hit + output + tail

    if expect_continuity and args.ponder_sleep > 0:
        before_samples = extract_search_samples(before_hit)
        after_samples = extract_search_samples(output)
        assert before_samples, f"{label}: ponderhit前のdepth/nodesを観測できなかった"
        assert after_samples, f"{label}: ponderhit後のdepth/nodesを観測できなかった"

        before_depth = max(depth for depth, _ in before_samples)
        before_nodes = max(nodes for _, nodes in before_samples)
        after_depth = max(depth for depth, _ in after_samples)
        after_nodes = min(nodes for _, nodes in after_samples)
        assert after_depth >= before_depth, (
            f"{label}: depthが{before_depth}から{after_depth}へリセットされた"
        )
        assert after_nodes >= before_nodes, (
            f"{label}: hit後の最小nodes={after_nodes}がhit前の最大nodes={before_nodes}を下回った"
        )

    assert_legal_bestmove(label, bestmove)
    if expected_bestmoves is not None:
        assert bestmove in expected_bestmoves, (
            f"{label}: searchmoves外のbestmove: {bestmove}, 期待={sorted(expected_bestmoves)}"
        )
    warned = "Warning!" in combined_output
    assert warned == expected_warning, (
        f"{label}: warning={warned}, 期待={expected_warning}"
    )
    if reference_ms is not None:
        assert_reference_latency(label, elapsed_ms, reference_ms)
    if maximum_ms is not None:
        assert elapsed_ms <= maximum_ms, (
            f"{label}: {elapsed_ms:.0f}ms, 上限{maximum_ms:.0f}msを超過"
        )

    print(f"PASS {label:52s} {elapsed_ms:7.0f}ms bestmove={bestmove}", flush=True)
    return elapsed_ms


try:
    send("usi")
    engine.expect("usiok")
    send("getoption PonderMissMaximumScale")
    engine.expect(r"100\r?\n", timeout=5)
    print("PASS PonderMissMaximumScale default is 100", flush=True)
    for option in (
        "Threads value 2",
        "USI_Hash value 64",
        "USI_Ponder value true",
        "USI_OwnBook value false",
        "BookFile value no_book",
        "PvInterval value 0",
        "MinimumThinkingTime value 2000",
        "NetworkDelay value 120",
        "NetworkDelay2 value 1120",
        "RoundUpToFullSecond value true",
    ):
        send("setoption name " + option)
    send("isready")
    engine.expect("readyok", timeout=60)
    send("usinewgame")

    print("== direct go baselines ==")
    long_ms, _ = run_go("R-long: direct byoyomi 3000", byo_long)
    mid_ms, _ = run_go("R-mid: direct byoyomi 2500", byo_mid)
    short_ms, _ = run_go("R-short: direct byoyomi 2000", byo_short)
    asymmetric_ms, _ = run_go("R-asymmetric: direct uses White clock", asymmetric_clock)

    print("== Fischer current-move limit ==")
    fischer_ms, _ = run_go(
        "F-direct: direct go does not add increment", fischer_low
    )
    assert fischer_ms <= 700, (
        f"F-direct: {fischer_ms:.0f}ms, 残り1100msへincrementを先取りしている"
    )

    run_ponder_case(
        "F-normal: OFF bare go + clocked hit",
        False,
        "",
        fischer_low,
        maximum_ms=700,
        expected_ponder_legal_moves=legal_moves,
    )
    run_ponder_case(
        "F-stochastic: ON bare go + clocked hit",
        True,
        "",
        fischer_low,
        maximum_ms=700,
        expected_ponder_legal_moves=stochastic_ponder_legal_moves,
    )

    print("== standard/early ponder matrix ==")
    run_ponder_case(
        "A: OFF clocked go + bare hit",
        False,
        byo_long,
        "",
        long_ms,
        expected_ponder_legal_moves=legal_moves,
        expect_continuity=True,
    )
    run_ponder_case(
        "B: ON clocked go + bare hit",
        True,
        byo_long,
        "",
        long_ms,
        expected_ponder_legal_moves=stochastic_ponder_legal_moves,
    )
    run_ponder_case(
        "C: OFF bare go + clocked hit",
        False,
        "",
        byo_long,
        long_ms,
        expected_ponder_legal_moves=legal_moves,
        expect_continuity=True,
    )
    run_ponder_case(
        "D: ON bare go + clocked hit",
        True,
        "",
        byo_long,
        long_ms,
        expected_ponder_legal_moves=stochastic_ponder_legal_moves,
    )
    run_ponder_case(
        "E: OFF bare go + asymmetric clocked hit",
        False,
        "",
        asymmetric_clock,
        asymmetric_ms,
        expected_ponder_legal_moves=legal_moves,
        expect_continuity=True,
    )

    print("== merge semantics ==")
    run_ponder_case("P1: hit overrides byoyomi upward", True, byo_short, byo_long, long_ms)
    run_ponder_case("P1-normal: OFF hit overrides upward", False, byo_short, byo_long, long_ms)
    run_ponder_case("P2: hit overrides byoyomi downward", True, byo_long, byo_short, short_ms)
    run_ponder_case(
        "P3: unspecified byoyomi is retained",
        True,
        byo_mid,
        "btime 0 wtime 0",
        mid_ms,
    )
    run_ponder_case(
        "P4: searchmoves does not consume hit clocks",
        True,
        "searchmoves 8d8e",
        byo_long,
        long_ms,
        expected_bestmoves={"8d8e"},
    )
    run_ponder_case(
        "P5: unsupported nodes is not injected",
        True,
        "",
        "nodes 1 " + byo_long,
        long_ms,
    )

    print("== fallback ==")
    run_ponder_case(
        "N: no clocks keeps immediate fallback",
        True,
        "",
        "",
        expected_warning=True,
        maximum_ms=700,
    )

    print("== ponder miss ==")
    set_stochastic_ponder("miss", True)
    send(position_cmd)
    send("go ponder " + byo_long)
    time.sleep(args.ponder_sleep)
    assert_no_bestmove("miss: stop前", 0.15)
    send("stop")
    expect_bestmove()
    assert_no_bestmove("miss: stop後", args.quiet_seconds)

    miss_moves = ["2g2f", "8c8d", "2f2e"]
    miss_board = shogi.Board()
    for move in miss_moves:
        miss_board.push_usi(move)
    miss_legal = {move.usi() for move in miss_board.legal_moves}
    send("position startpos moves " + " ".join(miss_moves))
    started = time.monotonic()
    send("go " + byo_long)
    bestmove, _ = expect_bestmove()
    miss_ms = (time.monotonic() - started) * 1000
    tail = assert_no_bestmove("miss: 再go応答後", args.quiet_seconds)
    assert bestmove in miss_legal, f"miss: 非合法bestmove: {bestmove}"
    assert_reference_latency("miss: normal re-go", miss_ms, long_ms)
    print(f"PASS {'miss: stop -> position -> go':52s} {miss_ms:7.0f}ms bestmove={bestmove}")

    send("quit")
    engine.expect(pexpect.EOF, timeout=10)
except BaseException:
    if engine.isalive():
        engine.close(force=True)
    raise

print("\nAll ponderhit regression cases passed.")
