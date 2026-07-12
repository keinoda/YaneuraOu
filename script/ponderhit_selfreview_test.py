#!/usr/bin/env python3
"""ponderhit時間制御拡張のセルフレビュー用テストマトリクス (PTY/pexpect)。

docs/ponderhit-extension-selfreview.md の検証結果を再現する。

- 定跡無効・詰みなし・合法手2手以上の固定局面を使用
- 各ケースで以下を検査する:
    * ponderhit前にbestmoveが出ないこと
    * hit後のbestmoveが1回だけであること
    * bestmoveが局面の合法手であること (python-shogi)
    * レイテンシ(時間管理の帯域。byoyomi系はmin=opt=maxが確定するので
      公式値と直接比較できる)
    * 警告の有無

必要: pip install pexpect python-shogi

usage:
  python3 script/ponderhit_selfreview_test.py --engine-dir /path/to/engine \
      [--engine-bin ./YaneuraOu-by-gcc]
"""
import time, argparse
import pexpect
import shogi

ap = argparse.ArgumentParser()
ap.add_argument("--engine-dir", required=True)
ap.add_argument("--engine-bin", default="./YaneuraOu-by-gcc",
                help="engine binary (relative to --engine-dir or absolute)")
ap.add_argument("--ponder-sleep", type=float, default=2.0)
args = ap.parse_args()

import os
BIN = args.engine_bin
if not os.path.isabs(BIN):
    BIN = os.path.join(args.engine_dir, BIN)

POS_MOVES = ["2g2f", "8c8d", "7g7f"]  # 後手番、合法手30以上、詰みなし
POS_CMD = "position startpos moves " + " ".join(POS_MOVES)

FISCHER300 = "btime 300000 wtime 300000 binc 2000 winc 2000"
FISCHER50  = "btime 50000 wtime 50000 binc 2000 winc 2000"
BYO10      = "btime 0 wtime 0 byoyomi 10000"
BYO9       = "btime 0 wtime 0 byoyomi 9000"
BYO2       = "btime 0 wtime 0 byoyomi 2000"

board = shogi.Board()
for m in POS_MOVES:
    board.push_usi(m)
LEGAL = {m.usi() for m in board.legal_moves}

sp = pexpect.spawn(BIN, cwd=args.engine_dir, encoding="utf-8", echo=False, timeout=240)

def send(s): sp.sendline(s)

def drain(seconds=0.3):
    buf = ""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            buf += sp.read_nonblocking(size=65536, timeout=0.05)
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            break
    return buf

send("usi"); sp.expect("usiok")
for o in ["Threads value 2", "USI_Hash value 256", "USI_Ponder value true",
          "USI_OwnBook value false"]:
    send("setoption name " + o)
send("isready"); sp.expect("readyok", timeout=180)
send("usinewgame")

def run_go(label, go_args):
    drain(0.2)
    send(POS_CMD)
    t0 = time.monotonic()
    send("go " + go_args)
    sp.expect(r"bestmove [^\r\n]+", timeout=200)
    ms = (time.monotonic() - t0) * 1000
    bm = sp.after.strip().split()[1]
    dup = "bestmove" in drain(0.3)
    print(f"{label:62s} {ms:8.0f}ms bm={bm:6s} dup={dup}", flush=True)
    return ms

def run_case(label, stochastic, go_args, hit_args):
    send(f"setoption name Stochastic_Ponder value {'true' if stochastic else 'false'}")
    drain(0.2)
    send(POS_CMD)
    send(("go ponder " + go_args).strip())
    time.sleep(args.ponder_sleep)
    pre = drain(0.1)
    premature = "bestmove" in pre
    t0 = time.monotonic()
    send(("ponderhit " + hit_args).strip())
    sp.expect(r"bestmove [^\r\n]+", timeout=200)
    ms = (time.monotonic() - t0) * 1000
    bm = sp.after.strip().split()[1]
    tail = drain(0.4)
    dup = "bestmove" in tail
    warned = ("Warning" in pre) or ("Warning" in sp.before) or ("Warning" in tail)
    legal = bm in LEGAL or bm in ("resign", "win")
    print(f"{label:62s} {ms:8.0f}ms bm={bm:6s} premature={premature} dup={dup} "
          f"warn={warned} legal={legal}", flush=True)
    return ms

print("== baselines (direct go) ==")
r1 = run_go("R1 base: go fischer300k", FISCHER300)
r2 = run_go("R2 base: go byoyomi10000", BYO10)
r3 = run_go("R3 base: go fischer50k", FISCHER50)

print("== matrix ==")
run_case("A_f OFF gp(fischer300k) + hit(bare)", False, FISCHER300, "")
run_case("A_b OFF gp(byo10000) + hit(bare)", False, BYO10, "")
run_case("B_f ON  gp(fischer300k) + hit(bare)", True, FISCHER300, "")
b_b = run_case("B_b ON  gp(byo10000) + hit(bare)", True, BYO10, "")
run_case("C_f OFF gp(bare) + hit(fischer300k)  [spec:recalc]", False, "", FISCHER300)
run_case("D_f ON  gp(bare) + hit(fischer300k)", True, "", FISCHER300)
d_b = run_case("D_b ON  gp(bare) + hit(byo10000)", True, "", BYO10)
run_case("P1  ON  gp(byo2000) + hit(byo10000)  [hit priority]", True, BYO2, BYO10)
run_case("P1r ON  gp(byo10000) + hit(byo2000)  [hit priority]", True, BYO10, BYO2)
run_case("P3  ON  gp(byo9000) + hit(btime/wtimeのみ) [維持確認]", True, BYO9,
         "btime 0 wtime 0")
run_case("P3r ON  gp(fischer300k) + hit(byoyomi9000のみ)", True, FISCHER300,
         "byoyomi 9000")
run_case("N   ON  gp(bare) + hit(bare)  [floor+warn]", True, "", "")

print("== ponder miss flow (ON: stop -> position -> go) ==")
send("setoption name Stochastic_Ponder value true")
drain(0.2)
send(POS_CMD)
send("go ponder " + FISCHER300)
time.sleep(1.5)
pre = drain(0.1)
assert "bestmove" not in pre, "premature bestmove in miss flow"
send("stop")
sp.expect(r"bestmove [^\r\n]+", timeout=60)
stop_bm = sp.after.strip()
dup1 = "bestmove" in drain(0.4)
send("position startpos moves 2g2f 8c8d 2f2e")   # 予測と異なる実際の応手
t0 = time.monotonic()
send("go " + FISCHER300)
sp.expect(r"bestmove [^\r\n]+", timeout=200)
miss_ms = (time.monotonic() - t0) * 1000
miss_bm = sp.after.strip()
dup2 = "bestmove" in drain(0.4)
print(f"miss: stop->'{stop_bm}' dup={dup1}; re-go {miss_ms:.0f}ms '{miss_bm}' dup={dup2}")

send("quit")
print("\n== summary ==")
print(f"R1={r1:.0f}ms R2={r2:.0f}ms R3={r3:.0f}ms | B_b/D_b vs R2: {b_b:.0f}/{d_b:.0f}ms")
