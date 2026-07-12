#!/usr/bin/env python3
"""Demonstrate mate-early-break instant moves WITHOUT any ponder.

iterative_deepening() には「詰みを読み切ったら rootDepth > 詰み手数の2.5倍で
探索を打ち切る」処理(本家やねうら王由来)があり、これは時間管理
(MinimumThinkingTime等)より優先される。TTが温まっている連続局面では
数ms で bestmove が返る。これが「残り時間に関わらず即指し」の正体である
ことを、ponder を完全に無効化した状態で実証するスクリプト。

usage: mate_instant_move_demo.py <pos_file> [engine_dir] [engine_bin]
  pos_file: "startpos moves ..." 形式1行 (詰みが見えはじめる10数手前の局面)
"""
import subprocess, threading, queue, time, sys

POS = open(sys.argv[1]).read().strip()
ENGINE_DIR = sys.argv[2] if len(sys.argv) > 2 else "."
ENGINE_BIN = sys.argv[3] if len(sys.argv) > 3 else "./YaneuraOu-by-gcc"

p = subprocess.Popen([ENGINE_BIN], cwd=ENGINE_DIR, stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
q = queue.Queue()
threading.Thread(target=lambda: [q.put(l.rstrip()) for l in p.stdout], daemon=True).start()

def send(c): p.stdin.write(c + "\n"); p.stdin.flush()
def wait(pred, timeout=180):
    end = time.monotonic() + timeout; seen = []
    while time.monotonic() < end:
        try: l = q.get(timeout=0.5)
        except queue.Empty: continue
        seen.append(l)
        if pred(l): return l, seen
    raise TimeoutError(seen[-5:])

send("usi"); wait(lambda l: l == "usiok")
send("setoption name Threads value 2")
send("setoption name USI_Hash value 512")
send("setoption name USI_Ponder value false")
send("setoption name Stochastic_Ponder value false")
send("isready"); wait(lambda l: l == "readyok", 120)
send("usinewgame")

moves = POS.split()[2:]  # after "startpos moves"
for step in range(6):
    send("position startpos moves " + " ".join(moves))
    t0 = time.monotonic()
    send("go btime 300000 wtime 300000 byoyomi 10000")
    line, seen = wait(lambda l: l.startswith("bestmove"))
    ms = (time.monotonic() - t0) * 1000
    score = ""
    for l in seen:
        if l.startswith("info") and " score " in l:
            t = l.split(); score = t[t.index("score")+1] + " " + t[t.index("score")+2]
    tok = line.split()
    bm = tok[1]
    pd = tok[3] if len(tok) >= 4 else None
    print(f"move {len(moves)+1}: elapsed={ms:7.0f}ms score={score:10s} bestmove={bm} ponder={pd}", flush=True)
    if bm in ("resign", "win") or not pd:
        break
    moves += [bm, pd]  # opponent plays our predicted reply
send("quit")
