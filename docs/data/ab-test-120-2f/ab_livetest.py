#!/usr/bin/env python3
"""A/Bテスト: 実対局条件(120秒+2秒フィッシャー)・ShogiHome早期Ponder再現。

実棋譜の進行を強制ラインとして、白番(sojo側)の各手で
  position .. / go ponder(時計なし) / <相手考慮sleep> /
  ponderhit btime .. wtime .. binc 2000 winc 2000
を送り、bestmoveまでの実測時間を計測する。

時計はライブ進行: wclock(次) = wclock - 実測消費 + 2000 (フィッシャー加算)。
相手考慮は棋譜Tを3秒でキャップして再現(初手長考はcap適用)。
"""
import subprocess, threading, queue, time, json, argparse

import shogi

ap = argparse.ArgumentParser()
ap.add_argument("--engine-bin", required=True)
ap.add_argument("--engine-dir", default="/tmp/claude-0/-home-user-YaneuraOu/c8161a19-7e1e-5666-a157-98924d98dbd6/scratchpad/sojotsec7")
ap.add_argument("--rows", default="/tmp/claude-0/-home-user-YaneuraOu/c8161a19-7e1e-5666-a157-98924d98dbd6/scratchpad/csa_replay_rows.json")
ap.add_argument("--out", required=True)
ap.add_argument("--main-ms", type=int, default=120_000)
ap.add_argument("--inc-ms", type=int, default=2_000)
ap.add_argument("--opp-cap", type=float, default=3.0)
args = ap.parse_args()

rows = json.load(open(args.rows))
moves = [r['usi'] for r in rows]
times = [r['t'] for r in rows]
wrows = [r for r in rows if r['side'] == 'W']

def legal_set(prefix_moves):
    b = shogi.Board()
    for m in prefix_moves:
        b.push_usi(m)
    return {mv.usi() for mv in b.legal_moves}

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
        try:
            t, l = q.get(timeout=max(0.01, end - time.monotonic()))
        except queue.Empty:
            raise TimeoutError(str(seen[-3:]))
        if l is None:
            raise RuntimeError("engine died: " + str(seen[-3:]))
        seen.append((t, l))
        if pred(l):
            return t, l, seen

def drain(sec=0.0):
    out = []
    end = time.monotonic() + sec
    while True:
        try:
            t, l = q.get(timeout=max(0.0, end - time.monotonic()) if sec else 0.0)
            if l is not None:
                out.append((t, l))
        except queue.Empty:
            if time.monotonic() >= end:
                return out

send("usi"); wait(lambda l: l == "usiok")
send("setoption name Threads value 2")
send("setoption name USI_Hash value 1024")
send("setoption name USI_Ponder value true")
send("setoption name USI_OwnBook value false")
send("setoption name BookFile value no_book")
send("setoption name Stochastic_Ponder value true")
# 実対局のengine_options.txt相当を明示適用(両エンジン同一条件)
send(f"setoption name EvalDir value {args.engine_dir}/eval")
send("setoption name FV_SCALE value 28")
send("setoption name LS_BUCKET_MODE value progress8kpabs")
send("setoption name LS_PROGRESS_COEFF value /root/danbo/progress.bin")
send("isready"); wait(lambda l: l == "readyok", 300)
send("usinewgame")

out = open(args.out, "w")
wclock = float(args.main_ms)
bclock = float(args.main_ms)

for r in wrows:
    i = r['ply'] - 1
    prefix = moves[:i]
    opp_t = times[i-1] if i-1 >= 0 else 0
    opp_sleep = min(opp_t, args.opp_cap)
    # 黒時計は再現消費で名目進行
    bclock = bclock - opp_sleep*1000 + args.inc_ms

    drain(0.05)
    send("position startpos moves " + " ".join(prefix))
    send("go ponder")
    time.sleep(opp_sleep + 0.2)
    pre = drain(0.05)
    premature = sum(1 for _, l in pre if l.startswith("bestmove"))
    clock_before = wclock
    t0 = send(f"ponderhit btime {max(0,int(bclock))} wtime {max(0,int(wclock))} "
              f"binc {args.inc_ms} winc {args.inc_ms}")
    t1, line, seen = wait(lambda l: l.startswith("bestmove"))
    lat = (t1 - t0) * 1000
    wclock = wclock - lat + args.inc_ms
    tail = drain(0.5)
    n_best = 1 + sum(1 for _, l in tail if l.startswith("bestmove")) + premature
    warnings = [l for _, l in (pre + seen + tail) if "Warning" in l]
    score_type = score_val = depth = None
    for _, l in seen:
        if l.startswith("info") and " score " in l:
            tk = l.split()
            if "depth" in tk: depth = int(tk[tk.index("depth")+1])
            si = tk.index("score"); score_type = tk[si+1]; score_val = tk[si+2]
    bm = line.split()[1]
    legal_now = legal_set(prefix)
    rec = dict(ply=r['ply'], kifu_move=r['usi'], kifu_t=r['t'],
               opp_sleep=round(opp_sleep, 2),
               wclock_before=round(clock_before), wclock_after=round(wclock),
               btime_sent=max(0, int(bclock)),
               latency_ms=round(lat), score_type=score_type, score=score_val,
               depth=depth, legal_count=r.get('legal'),
               bestmove=bm, bestmove_count=n_best,
               bestmove_legal=(bm in legal_now or bm in ("resign", "win")),
               timeout_flag=(clock_before - lat < 0),
               warnings=warnings)
    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
    print(f"ply {r['ply']:3d} opp={opp_sleep:3.1f}s wclock={clock_before/1000:6.1f}s "
          f"-> {lat/1000:6.2f}s after={wclock/1000:6.1f}s {score_type} {score_val} "
          f"bm={bm} n={n_best} warn={len(warnings)}"
          + (" TIMEOUT" if clock_before - lat < 0 else ""), flush=True)

send("quit")
print("DONE")
