#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_openings.py : A/Bテスト用の互角開始局面集を生成する

エンジン自身にMultiPVで候補手を出させ、最善と評価が近い手からランダムに
選んで数手進めることで、多様かつ概ね互角な開始局面 (指し手列) を作る。

例:
    python3 script/ab/make_openings.py \
        --engine source/YaneuraOu-by-gcc --eval-dir /path/to/eval \
        --count 50 --plies 12 --nodes 100000 --margin 40 \
        --out script/ab/openings.sfen

強い評価関数で生成し直すほど開始局面の質は上がる。
出力形式: 1行 = "startpos moves 7g7f 3c3d ..." (ab_match.py --openings で使用)
"""

import argparse
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time


class Engine:
    def __init__(self, path, options):
        self.proc = subprocess.Popen(
            [os.path.abspath(path)],
            cwd=os.path.dirname(os.path.abspath(path)) or ".",
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            errors="replace", bufsize=1)
        self.q = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.send("usi")
        self.wait("usiok")
        for k, v in options.items():
            self.send(f"setoption name {k} value {v}")
        self.send("isready")
        self.wait("readyok", 180)

    def _read(self):
        for line in self.proc.stdout:
            self.q.put(line.rstrip("\n"))
        self.q.put(None)

    def send(self, s):
        self.proc.stdin.write(s + "\n")
        self.proc.stdin.flush()

    def wait(self, tok, timeout=30):
        t = time.monotonic() + timeout
        while True:
            line = self.q.get(timeout=max(0.01, t - time.monotonic()))
            if line is None:
                raise RuntimeError("engine EOF")
            if line.startswith(tok):
                return line

    def candidates(self, moves, nodes, multipv):
        """(move, cp) のリストを返す (multipv順)。"""
        while not self.q.empty():
            self.q.get_nowait()
        pos = "position startpos" + (" moves " + " ".join(moves) if moves else "")
        self.send(pos)
        self.send(f"go nodes {nodes}")
        cands = {}
        while True:
            line = self.q.get(timeout=600)
            if line is None:
                raise RuntimeError("engine EOF during go")
            if line.startswith("info ") and " pv " in line and " score " in line:
                mpv = re.search(r"multipv (\d+)", line)
                idx = int(mpv.group(1)) if mpv else 1
                mcp = re.search(r"score cp (-?\d+)", line)
                mmate = re.search(r"score mate (-?\d+)", line)
                cp = int(mcp.group(1)) if mcp else (
                    100000 if mmate and int(mmate.group(1)) > 0 else -100000)
                mv = line.split(" pv ", 1)[1].split()[0]
                cands[idx] = (mv, cp)
            elif line.startswith("bestmove"):
                break
        return [cands[i] for i in sorted(cands)]

    def quit(self):
        try:
            self.send("quit")
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--eval-dir", default=None)
    ap.add_argument("--option", action="append", default=[], metavar="K=V")
    ap.add_argument("--count", type=int, default=50, help="生成する局面数")
    ap.add_argument("--plies", type=int, default=12, help="進める手数")
    ap.add_argument("--nodes", type=int, default=100000, help="1手あたりの思考ノード数")
    ap.add_argument("--multipv", type=int, default=4)
    ap.add_argument("--margin", type=int, default=40, help="最善からこのcp差以内の手を候補にする")
    ap.add_argument("--balance", type=int, default=150, help="この評価値を超えて偏った局面は捨てる")
    ap.add_argument("--seed", type=int, default=20260713)
    ap.add_argument("--out", default="script/ab/openings.sfen")
    args = ap.parse_args()

    opts = {"Threads": 1, "USI_Hash": 128, "MultiPV": args.multipv,
            "USI_OwnBook": "false", "BookFile": "no_book", "NetworkDelay": 0,
            "NetworkDelay2": 0}
    if args.eval_dir:
        opts["EvalDir"] = os.path.abspath(args.eval_dir)
    for kv in args.option:
        k, _, v = kv.partition("=")
        opts[k] = v

    rng = random.Random(args.seed)
    eng = Engine(args.engine, opts)

    lines = set()
    tries = 0
    while len(lines) < args.count and tries < args.count * 10:
        tries += 1
        moves = []
        ok = True
        for _ in range(args.plies):
            cands = eng.candidates(moves, args.nodes, args.multipv)
            if not cands:
                ok = False
                break
            best_cp = cands[0][1]
            if abs(best_cp) > args.balance:
                ok = False
                break
            pool = [mv for mv, cp in cands if best_cp - cp <= args.margin]
            moves.append(rng.choice(pool))
        if ok and moves:
            line = "startpos moves " + " ".join(moves)
            if line not in lines:
                lines.add(line)
                print(f"[{len(lines):3d}/{args.count}] {line}")
    eng.quit()

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("# A/B test openings (generated by make_openings.py)\n")
        f.write(f"# engine={os.path.basename(args.engine)} plies={args.plies} "
                f"nodes={args.nodes} margin={args.margin} seed={args.seed}\n")
        for line in sorted(lines):
            f.write(line + "\n")
    print(f"wrote {len(lines)} openings -> {args.out}")


if __name__ == "__main__":
    sys.exit(main())
