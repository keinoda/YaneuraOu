#!/usr/bin/env python3
"""CSA棋譜をエンジンでリプレイし、ponderhit(または通常go)からbestmoveまでの
実測レイテンシを全数計測するツール。

実際の対局のT値から各局面の時計残量を復元し、GUI相当のUSIポンダー手順
(always-hit: 棋譜の実際の応手を予測手として go ponder → 相手考慮時間をsleep →
ponderhit) を再現する。Stochastic_Ponder の ON/OFF で挙動差
(ONは毎回現局面を再探索するため最低でも MinimumThinkingTime−NetworkDelay 程度かかる /
OFFは相手考慮中に思考が完了していれば即指しになる) を実測比較できる。

必要: pip install python-shogi

usage:
  python3 script/csa_ponder_replay.py kifu.csa --engine-dir /path/to/engine \
      --mode stochastic --side w --main-time 600000 --inc 2000
"""
import subprocess, threading, queue, time, json, argparse

import shogi
import shogi.CSA

ap = argparse.ArgumentParser()
ap.add_argument("csa")
ap.add_argument("--engine-dir", required=True)
ap.add_argument("--engine-bin", default="./YaneuraOu-by-gcc")
ap.add_argument("--mode", choices=["stochastic", "normal", "noponder", "earlyponder"],
                default="stochastic",
                help="earlyponder = ShogiHomeの早期Ponder形式 "
                     "(時計なし go ponder + 時計付き ponderhit, Stochastic_Ponder=true)")
ap.add_argument("--side", choices=["b", "w"], default="w", help="which side the engine replays")
ap.add_argument("--main-time", type=int, default=600000)
ap.add_argument("--inc", type=int, default=2000)
ap.add_argument("--byoyomi", type=int, default=0)
ap.add_argument("--max-opp-sleep", type=float, default=6.0,
                help="cap for simulated opponent thinking time [s]")
ap.add_argument("--threads", type=int, default=2)
ap.add_argument("--hash", type=int, default=1024)
ap.add_argument("--out", default="csa_replay_result.jsonl")
args = ap.parse_args()

parsed = shogi.CSA.Parser.parse_file(args.csa)[0]
moves = parsed["moves"]

# CSAからT値(消費秒)を拾う
times = []
for line in open(args.csa):
    line = line.strip()
    if line.startswith("T") and line[1:].isdigit():
        times.append(int(line[1:]))
assert len(times) == len(moves), (len(times), len(moves))

my_parity = 0 if args.side == "b" else 1

p = subprocess.Popen([args.engine_bin], cwd=args.engine_dir, stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
q = queue.Queue()
def reader():
    for l in p.stdout:
        q.put((time.monotonic(), l.rstrip()))
    q.put((time.monotonic(), None))
threading.Thread(target=reader, daemon=True).start()

def send(c):
    p.stdin.write(c + "\n"); p.stdin.flush()
    return time.monotonic()

def wait(pred, timeout=300):
    seen = []
    end = time.monotonic() + timeout
    while True:
        remain = end - time.monotonic()
        if remain <= 0:
            raise TimeoutError(str(seen[-3:]))
        try:
            t, l = q.get(timeout=remain)
        except queue.Empty:
            continue
        if l is None:
            raise RuntimeError("engine died: " + str(seen[-3:]))
        seen.append(l)
        if pred(l):
            return t, l, seen

def drain():
    while True:
        try: q.get_nowait()
        except queue.Empty: return

def clocks_str(i):
    # 手番i(0-based)の直前時点の時計(フィッシャー: 各手のあとinc加算)
    b = w = args.main_time
    for j in range(i):
        if j % 2 == 0: b = b - times[j] * 1000 + args.inc
        else:          w = w - times[j] * 1000 + args.inc
    s = f"btime {max(0, b)} wtime {max(0, w)} binc {args.inc} winc {args.inc}"
    if args.byoyomi: s += f" byoyomi {args.byoyomi}"
    return s

send("usi"); wait(lambda l: l == "usiok")
send(f"setoption name Threads value {args.threads}")
send(f"setoption name USI_Hash value {args.hash}")
send("setoption name USI_Ponder value true")
stochastic = args.mode in ("stochastic", "earlyponder")
send(f"setoption name Stochastic_Ponder value {'true' if stochastic else 'false'}")
send("isready"); wait(lambda l: l == "readyok", 180)
send("usinewgame")

out = open(args.out, "w")

for i in range(len(moves)):
    if i % 2 != my_parity:
        continue
    prefix = moves[:i]
    opp_t = times[i - 1] if i - 1 >= 0 else 0

    drain()
    if args.mode in ("stochastic", "normal", "earlyponder") and i >= 1:
        send("position startpos moves " + " ".join(prefix))
        if args.mode == "earlyponder":
            # ShogiHomeの早期Ponder: go ponderには時計を付けず、ponderhitに付ける。
            send("go ponder")
        else:
            send("go ponder " + clocks_str(i))
        time.sleep(min(opp_t, args.max_opp_sleep) + 0.2)
        if args.mode == "earlyponder":
            t0 = send("ponderhit " + clocks_str(i))
        else:
            t0 = send("ponderhit")
        kind = "ponderhit"
    else:
        send("position startpos moves " + " ".join(prefix))
        t0 = send("go " + clocks_str(i))
        kind = "go"
    t1, line, seen = wait(lambda l: l.startswith("bestmove"))
    lat = (t1 - t0) * 1000
    score = depth = None
    for l in seen:
        if l.startswith("info") and " score " in l:
            tk = l.split()
            if "depth" in tk: depth = tk[tk.index("depth") + 1]
            si = tk.index("score"); score = tk[si + 1] + " " + tk[si + 2]
    rec = dict(mode=args.mode, ply=i + 1, kifu_move=moves[i], kifu_t=times[i],
               opp_think=opp_t, kind=kind, latency_ms=round(lat), score=score,
               depth=depth, bestmove=line.split()[1])
    out.write(json.dumps(rec) + "\n"); out.flush()
    print(f"ply {i+1:3d} kifuT={times[i]:3d} oppT={opp_t:3d} -> {lat/1000:7.2f}s "
          f"score={score} bm={rec['bestmove']}", flush=True)

send("quit")
print("DONE", args.mode)
