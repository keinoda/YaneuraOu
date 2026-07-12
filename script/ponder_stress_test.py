#!/usr/bin/env python3
"""
Stochastic Ponder immediate-move reproduction harness.

Simulates a USI GUI (like Shogidokoro/ShogiGUI) driving:
  - Engine A (subject): USI_Ponder=true, Stochastic_Ponder=true
  - Engine B (opponent): fast mover via `go rtime N`

Flow per A-move:
  position + go  ->  bestmove M ponder P
  (if P) position(+M+P) + go ponder ; ask B for reply R
     R == P -> ponderhit           -> measure elapsed to bestmove
     R != P -> stop (drain) -> position(+M+R) + go -> measure
Anomaly: elapsed < ANOM_MS while remaining time before the move > REMAIN_MIN.
"""
import subprocess, threading, queue, time, sys, os, json, random, argparse

ENGINE_DIR = "."  # --engine-dir で上書き
ENGINE_BIN = "./YaneuraOu-by-gcc"  # --engine-bin で上書き

ANOM_MS = 1200        # bestmove faster than this is suspicious...
REMAIN_MIN = 20000    # ...when at least this much time remains

class Engine:
    def __init__(self, name, logf):
        self.name = name
        self.logf = logf
        self.p = subprocess.Popen([ENGINE_BIN], cwd=ENGINE_DIR,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.q = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.p.stdout:
            t = time.monotonic()
            line = line.rstrip("\n")
            self.q.put((t, line))
            self.logf.write(f"{t:.3f} <{self.name} {line}\n")
        self.q.put((time.monotonic(), None))

    def send(self, cmd):
        t = time.monotonic()
        self.logf.write(f"{t:.3f} >{self.name} {cmd}\n")
        self.logf.flush()
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()
        return t

    def wait_for(self, pred, timeout=180.0):
        """Wait for a line satisfying pred(line). Returns (timestamp, line, all_lines_seen)."""
        seen = []
        end = time.monotonic() + timeout
        while True:
            remain = end - time.monotonic()
            if remain <= 0:
                raise TimeoutError(f"{self.name}: timeout waiting; last lines: {seen[-5:]}")
            try:
                t, line = self.q.get(timeout=remain)
            except queue.Empty:
                raise TimeoutError(f"{self.name}: timeout waiting; last lines: {seen[-5:]}")
            if line is None:
                raise RuntimeError(f"{self.name}: engine died; last: {seen[-5:]}")
            seen.append(line)
            if pred(line):
                return t, line, seen

    def drain(self):
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                return

def parse_bestmove(line):
    tok = line.split()
    bm = tok[1]
    pd = tok[3] if len(tok) >= 4 and tok[2] == "ponder" else None
    return bm, pd

def last_info(seen):
    depth = score = None
    for l in seen:
        if l.startswith("info") and " score " in l:
            t = l.split()
            if "depth" in t:
                depth = t[t.index("depth")+1]
            if "score" in t:
                i = t.index("score")
                score = t[i+1] + " " + t[i+2]
    return depth, score

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=4)
    ap.add_argument("--main-time", type=int, default=180000)
    ap.add_argument("--byoyomi", type=int, default=0)
    ap.add_argument("--max-ply", type=int, default=220)
    ap.add_argument("--tag", default="run1")
    ap.add_argument("--b-rtime", type=int, default=150)
    ap.add_argument("--slow-ponder-prob", type=float, default=0.15,
                    help="prob of extra GUI-side delay before ponderhit/stop")
    ap.add_argument("--instant-hit-prob", type=float, default=0.0,
                    help="prob of sending ponderhit immediately after go ponder "
                         "(premove-style: opponent plays the predicted move instantly)")
    ap.add_argument("--opt", action="append", default=[],
                    help="extra setoption for engine A, e.g. --opt PonderMissMaximumScale=200")
    ap.add_argument("--engine-dir", default=".",
                    help="engine working directory (eval/, book/, engine_options.txt here)")
    ap.add_argument("--engine-bin", default="./YaneuraOu-by-gcc",
                    help="engine binary (relative to --engine-dir or absolute)")
    ap.add_argument("--out-dir", default=".", help="where to write logs/records")
    args = ap.parse_args()

    globals()["ENGINE_DIR"] = args.engine_dir
    globals()["ENGINE_BIN"] = args.engine_bin

    outdir = args.out_dir
    logf = open(os.path.join(outdir, f"engine_io_{args.tag}.log"), "w")
    recf = open(os.path.join(outdir, f"records_{args.tag}.jsonl"), "w")
    random.seed(1234)

    A = Engine("A", logf)
    B = Engine("B", logf)

    for e, th, hash_ in ((A, 2, 512), (B, 1, 128)):
        e.send("usi"); e.wait_for(lambda l: l == "usiok")
        e.send(f"setoption name Threads value {th}")
        e.send(f"setoption name USI_Hash value {hash_}")
    A.send("setoption name USI_Ponder value true")
    A.send("setoption name Stochastic_Ponder value true")
    for kv in args.opt:
        k, v = kv.split("=", 1)
        A.send(f"setoption name {k} value {v}")
    for e in (A, B):
        e.send("isready"); e.wait_for(lambda l: l == "readyok", timeout=120)

    anomalies = []
    move_no = 0

    def record(game, ply, kind, remain, elapsed_ms, bm, pd, seen, extra=None):
        nonlocal anomalies
        depth, score = last_info(seen)
        rec = dict(game=game, ply=ply, kind=kind, remain_before=remain,
                   elapsed_ms=round(elapsed_ms), bestmove=bm, ponder=pd,
                   depth=depth, score=score)
        if extra: rec.update(extra)
        book_hit = any(("%)" in l or "book" in l) for l in seen if l.startswith("info"))
        rec["book"] = book_hit
        time_available = remain > REMAIN_MIN or args.byoyomi >= 2500
        is_anom = (elapsed_ms < ANOM_MS and time_available
                   and bm not in ("resign", "win")
                   and not book_hit
                   and not (score or "").startswith("mate"))
        rec["anomaly"] = is_anom
        recf.write(json.dumps(rec, ensure_ascii=False) + "\n"); recf.flush()
        if is_anom:
            anomalies.append(rec)
            print(f"*** ANOMALY g{game} ply{ply} {kind} remain={remain} "
                  f"elapsed={elapsed_ms:.0f}ms bm={bm} score={score}", flush=True)

    for game in range(1, args.games + 1):
        a_is_black = (game % 2 == 1)
        moves = []
        a_time = args.main_time
        b_time = args.main_time
        for e in (A, B):
            e.drain()
            e.send("usinewgame")
        print(f"=== game {game}: A is {'BLACK' if a_is_black else 'WHITE'} ===", flush=True)

        def clocks():
            bt = a_time if a_is_black else b_time
            wt = b_time if a_is_black else a_time
            s = f"btime {bt} wtime {wt}"
            if args.byoyomi: s += f" byoyomi {args.byoyomi}"
            return s

        def pos(mv):
            return "position startpos" + (" moves " + " ".join(mv) if mv else "")

        def b_move():
            nonlocal b_time
            B.send(pos(moves))
            t0 = B.send(f"go rtime {args.b_rtime}")
            t1, line, seen = B.wait_for(lambda l: l.startswith("bestmove"))
            b_time = max(1000, b_time - int((t1 - t0) * 1000))
            return parse_bestmove(line)[0]

        # If A is white, B moves first.
        if not a_is_black:
            r = b_move()
            if r in ("resign", "win"): continue
            moves.append(r)

        game_over = False
        pondering = None  # predicted move P if A is pondering
        while not game_over and len(moves) < args.max_ply:
            # --- A's turn ---
            remain = a_time
            if pondering is None:
                A.send(pos(moves))
                t0 = A.send("go " + clocks())
                kind = "go"
            else:
                # opponent's actual move == pondering (already appended)
                t0 = A.send("ponderhit")
                kind = "ponderhit"
            t1, line, seen = A.wait_for(lambda l: l.startswith("bestmove"))
            elapsed_ms = (t1 - t0) * 1000
            a_time = max(0, a_time - int(elapsed_ms))
            bm, pd = parse_bestmove(line)
            record(game, len(moves) + 1, kind, remain, elapsed_ms, bm, pd, seen)
            pondering = None
            if bm in ("resign", "win"):
                break
            moves.append(bm)
            if a_time < 8000 and not args.byoyomi:
                print(f"  (game {game}: A clock low, ending game at ply {len(moves)})", flush=True)
                break

            # --- opponent's turn; A may ponder ---
            if pd and random.random() < args.instant_hit_prob:
                # Premove: opponent instantly plays the predicted move.
                # go ponder and ponderhit arrive nearly back-to-back.
                A.send(pos(moves + [pd]))
                A.send("go ponder " + clocks())
                moves.append(pd)
                pondering = pd
                continue
            if pd:
                A.send(pos(moves + [pd]))
                A.send("go ponder " + clocks())
            r = b_move()
            if r in ("resign", "win"):
                if pd:
                    A.send("stop")
                    A.wait_for(lambda l: l.startswith("bestmove"))
                game_over = True
                break
            if random.random() < args.slow_ponder_prob:
                time.sleep(random.uniform(0.5, 3.0))
            if pd:
                if r == pd:
                    moves.append(r)
                    pondering = pd
                else:
                    A.send("stop")
                    A.wait_for(lambda l: l.startswith("bestmove"))
                    moves.append(r)
            else:
                moves.append(r)

        print(f"=== game {game} done, plies={len(moves)}, A time left={a_time} ===", flush=True)

    print(f"\n==== SUMMARY: {len(anomalies)} anomalies ====")
    for a in anomalies:
        print(json.dumps(a, ensure_ascii=False))
    for e in (A, B):
        try:
            e.send("quit")
        except Exception:
            pass
    logf.close(); recf.close()

if __name__ == "__main__":
    main()
