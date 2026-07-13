#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ab_match.py : USIエンジン同士のA/B自己対局ハーネス (SPRT判定付き)

やねうら王の探索部改善のA/Bテスト用。外部ライブラリ不要 (cshogiがあれば
千日手・連続王手千日手・詰みの厳密判定に自動で利用する)。

例:
    python3 script/ab/ab_match.py \
        --engine1 build/ab/base.bin --engine2 build/ab/ab01.bin \
        --eval-dir /path/to/eval \
        --byoyomi 1000 --concurrency 2 \
        --openings script/ab/openings.sfen \
        --sprt 0 5 --max-games 20000 \
        --option USI_Hash=256 --option MaxMovesToDraw=320

結果は engine2 (テスト側) 視点で集計する。
LLR >= 2.94 → H1受理 (engine2が elo1 以上強い)
LLR <= -2.94 → H0受理 (改善なし)
"""

import argparse
import json
import math
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time

# ---------------------------------------------------------------------------
# cshogi (任意)
# ---------------------------------------------------------------------------
try:
    import cshogi  # type: ignore
    HAS_CSHOGI = True
except ImportError:
    cshogi = None
    HAS_CSHOGI = False


# ---------------------------------------------------------------------------
# SPRT (GSPRT近似 / トリノミアル)
# ---------------------------------------------------------------------------
def elo_to_score(elo: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-elo / 400.0))


def sprt_llr(wins: int, draws: int, losses: int, elo0: float, elo1: float) -> float:
    """fastchess/cutechess系のGSPRT近似によるLLR。"""
    if wins + draws + losses == 0:
        return 0.0
    # 正則化 (0分散を避ける)
    W, D, L = max(wins, 0.5), max(draws, 0.5), max(losses, 0.5)
    n = W + D + L
    w, d, l = W / n, D / n, L / n
    s = w + d / 2.0
    m2 = w + d / 4.0
    var = m2 - s * s
    if var <= 0:
        return 0.0
    var_s = var / n
    s0 = elo_to_score(elo0)
    s1 = elo_to_score(elo1)
    return (s1 - s0) * (2.0 * s - s0 - s1) / (2.0 * var_s)


def elo_estimate(wins: int, draws: int, losses: int):
    """(elo, 95%誤差) を返す。"""
    n = wins + draws + losses
    if n == 0:
        return 0.0, float("inf")
    score = (wins + 0.5 * draws) / n
    score = min(max(score, 1e-6), 1.0 - 1e-6)
    elo = -400.0 * math.log10(1.0 / score - 1.0)
    # 分散 (トリノミアル)
    w, d, l = wins / n, draws / n, losses / n
    var = w * (1 - score) ** 2 + d * (0.5 - score) ** 2 + l * (0 - score) ** 2
    se = math.sqrt(max(var, 1e-12) / n)
    lo = min(max(score - 1.96 * se, 1e-6), 1 - 1e-6)
    hi = min(max(score + 1.96 * se, 1e-6), 1 - 1e-6)
    elo_lo = -400.0 * math.log10(1.0 / lo - 1.0)
    elo_hi = -400.0 * math.log10(1.0 / hi - 1.0)
    return elo, (elo_hi - elo_lo) / 2.0


# ---------------------------------------------------------------------------
# USIエンジンラッパ
# ---------------------------------------------------------------------------
class EngineError(Exception):
    pass


class USIEngine:
    def __init__(self, path: str, options: dict, name: str):
        self.path = os.path.abspath(path)
        self.options = options
        self.name = name
        self.proc = None
        self.lines = queue.Queue()
        self.reader = None

    def start(self):
        self.proc = subprocess.Popen(
            [self.path],
            cwd=os.path.dirname(self.path) or ".",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()
        self.send("usi")
        self.wait_for("usiok", timeout=30)
        for k, v in self.options.items():
            self.send(f"setoption name {k} value {v}")
        self.send("isready")
        self.wait_for("readyok", timeout=180)  # eval読み込みがあるので長め

    def _read_loop(self):
        try:
            for line in self.proc.stdout:
                self.lines.put(line.rstrip("\n"))
        except Exception:
            pass
        self.lines.put(None)  # EOF marker

    def send(self, cmd: str):
        if self.proc is None or self.proc.poll() is not None:
            raise EngineError(f"{self.name}: engine died (send '{cmd}')")
        try:
            self.proc.stdin.write(cmd + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise EngineError(f"{self.name}: pipe broken: {e}")

    def wait_for(self, token: str, timeout: float):
        deadline = time.monotonic() + timeout
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                raise EngineError(f"{self.name}: timeout waiting '{token}'")
            try:
                line = self.lines.get(timeout=remain)
            except queue.Empty:
                raise EngineError(f"{self.name}: timeout waiting '{token}'")
            if line is None:
                raise EngineError(f"{self.name}: EOF waiting '{token}'")
            if line.startswith(token):
                return line

    def new_game(self):
        self.send("isready")
        self.wait_for("readyok", timeout=180)
        self.send("usinewgame")

    def go(self, position_cmd: str, go_cmd: str, timeout: float):
        """(bestmove, ponder, last_score_cp, is_mate_score) を返す。"""
        # 古い出力を捨てる
        while True:
            try:
                self.lines.get_nowait()
            except queue.Empty:
                break
        self.send(position_cmd)
        self.send(go_cmd)
        last_cp = None
        is_mate = False
        deadline = time.monotonic() + timeout
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                raise EngineError(f"{self.name}: bestmove timeout ({go_cmd})")
            try:
                line = self.lines.get(timeout=remain)
            except queue.Empty:
                raise EngineError(f"{self.name}: bestmove timeout ({go_cmd})")
            if line is None:
                raise EngineError(f"{self.name}: EOF during search")
            if line.startswith("info ") and " score " in line:
                m = re.search(r"score cp (-?\d+)", line)
                if m:
                    last_cp = int(m.group(1))
                    is_mate = False
                else:
                    m = re.search(r"score mate (-?\d+)", line)
                    if m:
                        v = int(m.group(1))
                        last_cp = 100000 if v > 0 else -100000
                        is_mate = True
            elif line.startswith("bestmove"):
                parts = line.split()
                best = parts[1] if len(parts) > 1 else "resign"
                ponder = parts[3] if len(parts) > 3 and parts[2] == "ponder" else None
                return best, ponder, last_cp, is_mate

    def quit(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.send("quit")
                self.proc.wait(timeout=5)
        except Exception:
            pass
        finally:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()


# ---------------------------------------------------------------------------
# 1対局
# ---------------------------------------------------------------------------
class GameResult:
    def __init__(self, score2: float, reason: str, moves, opening: str, e2_is_sente: bool):
        self.score2 = score2  # engine2視点: 1=勝ち, 0.5=分, 0=負け
        self.reason = reason
        self.moves = moves
        self.opening = opening
        self.e2_is_sente = e2_is_sente


def make_go_cmd(args, clocks, stm_idx):
    if args.nodes:
        return f"go nodes {args.nodes}", 3600.0
    if args.movetime:
        return f"go movetime {args.movetime}", args.movetime / 1000.0 + args.move_margin
    # 時計制 (btime/wtime は先手/後手)
    b, w = clocks
    cmd = f"go btime {b} wtime {w}"
    if args.inc:
        cmd += f" binc {args.inc} winc {args.inc}"
    if args.byoyomi:
        cmd += f" byoyomi {args.byoyomi}"
    budget = (b if stm_idx == 0 else w) + args.byoyomi + args.inc
    return cmd, budget / 1000.0 + args.move_margin


def play_game(args, e_sente: USIEngine, e_gote: USIEngine, opening_moves, e2_is_sente: bool):
    """1局対局する。resultはengine2視点。"""
    for e in (e_sente, e_gote):
        e.new_game()

    board = cshogi.Board() if HAS_CSHOGI else None
    moves = []
    if board is not None:
        for mv in opening_moves:
            m = board.move_from_usi(mv)
            if m == 0 or not board.is_legal(m):
                raise EngineError(f"opening move illegal: {mv} after {moves}")
            board.push(m)
            moves.append(mv)
    else:
        moves = list(opening_moves)

    clocks = [args.time, args.time]  # [先手btime, 後手wtime] (ms)
    bad_count = [0, 0]  # 連続で resign 閾値を下回った回数 (先手,後手)
    max_plies = args.draw_moves

    def result_for_e2(sente_score: float, reason: str) -> GameResult:
        s2 = sente_score if e2_is_sente else 1.0 - sente_score
        return GameResult(s2, reason, moves, " ".join(opening_moves), e2_is_sente)

    while True:
        ply = len(moves)
        if ply >= max_plies:
            return result_for_e2(0.5, "max_moves")

        # cshogiによる厳密な終局判定
        if board is not None:
            if board.is_game_over():  # 合法手なし = 詰み (手番側の負け)
                sente_win = 1.0 if board.turn == cshogi.WHITE else 0.0
                return result_for_e2(sente_win, "mate")
            rep = board.is_draw()
            if rep == cshogi.REPETITION_DRAW:
                return result_for_e2(0.5, "sennichite")
            if rep == cshogi.REPETITION_WIN:  # 手番側の勝ち(相手の連続王手千日手)
                sente_win = 1.0 if board.turn == cshogi.BLACK else 0.0
                return result_for_e2(sente_win, "perpetual_check")
            if rep == cshogi.REPETITION_LOSE:
                sente_win = 0.0 if board.turn == cshogi.BLACK else 1.0
                return result_for_e2(sente_win, "perpetual_check")

        stm_idx = ply % 2  # 0=先手番
        engine = e_sente if stm_idx == 0 else e_gote
        pos_cmd = "position startpos" + (" moves " + " ".join(moves) if moves else "")
        go_cmd, budget = make_go_cmd(args, clocks, stm_idx)

        t0 = time.monotonic()
        try:
            best, _, cp, _ = engine.go(pos_cmd, go_cmd, budget)
        except EngineError as e:
            sys.stderr.write(f"[warn] {e}\n")
            sente_win = 0.0 if stm_idx == 0 else 1.0
            return result_for_e2(sente_win, "engine_error")
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        # 時計更新 (時計制のときのみ)
        if not args.nodes and not args.movetime and args.time:
            used = max(0, elapsed_ms - args.byoyomi)
            clocks[stm_idx] = max(0, clocks[stm_idx] - used + args.inc)

        if best in ("resign", "none", "0000"):
            sente_win = 0.0 if stm_idx == 0 else 1.0
            return result_for_e2(sente_win, "resign")
        if best == "win":
            sente_win = 1.0 if stm_idx == 0 else 0.0
            return result_for_e2(sente_win, "declaration")

        # 投了スコア判定 (エンジン自身の評価値ベース)
        if cp is not None and args.resign_score > 0:
            if cp <= -args.resign_score:
                bad_count[stm_idx] += 1
                if bad_count[stm_idx] >= args.resign_count:
                    sente_win = 0.0 if stm_idx == 0 else 1.0
                    return result_for_e2(sente_win, "adjudication")
            else:
                bad_count[stm_idx] = 0

        if board is not None:
            m = board.move_from_usi(best)
            if m == 0 or not board.is_legal(m):
                sys.stderr.write(f"[warn] {engine.name}: illegal move {best}\n")
                sente_win = 0.0 if stm_idx == 0 else 1.0
                return result_for_e2(sente_win, "illegal_move")
            board.push(m)
        moves.append(best)


# ---------------------------------------------------------------------------
# ワーカー (1ワーカー = エンジン2プロセスを保持して対局を回す)
# ---------------------------------------------------------------------------
class Shared:
    def __init__(self):
        self.lock = threading.Lock()
        self.w = self.d = self.l = 0  # engine2視点
        self.games = 0
        self.stop = False
        self.results_f = None


def worker_main(wid, args, shared: Shared, openings, opts1, opts2):
    e1 = USIEngine(args.engine1, opts1, f"E1#{wid}")
    e2 = USIEngine(args.engine2, opts2, f"E2#{wid}")
    try:
        e1.start()
        e2.start()
    except EngineError as e:
        sys.stderr.write(f"[fatal] worker{wid}: {e}\n")
        with shared.lock:
            shared.stop = True
        return

    def restart_engines():
        nonlocal e1, e2
        for e in (e1, e2):
            e.quit()
        e1 = USIEngine(args.engine1, opts1, f"E1#{wid}")
        e2 = USIEngine(args.engine2, opts2, f"E2#{wid}")
        e1.start()
        e2.start()

    rng = random.Random(args.seed + wid * 9973)
    try:
        while True:
            with shared.lock:
                if shared.stop or shared.games >= args.max_games:
                    break
            opening = rng.choice(openings) if openings else []
            # 同一開始局面で先後入替のペア対局
            for e2_is_sente in (True, False):
                with shared.lock:
                    if shared.stop or shared.games >= args.max_games:
                        break
                es = e2 if e2_is_sente else e1
                eg = e1 if e2_is_sente else e2
                try:
                    r = play_game(args, es, eg, opening, e2_is_sente)
                except EngineError as e:
                    sys.stderr.write(f"[warn] worker{wid}: {e} -> restart engines\n")
                    try:
                        restart_engines()
                    except EngineError as e2rr:
                        sys.stderr.write(f"[fatal] worker{wid}: restart failed: {e2rr}\n")
                        return
                    continue
                if r.reason == "engine_error":
                    # ハング/クラッシュ後はエンジンを作り直して継続する
                    try:
                        restart_engines()
                    except EngineError as e2rr:
                        sys.stderr.write(f"[fatal] worker{wid}: restart failed: {e2rr}\n")
                        return
                with shared.lock:
                    shared.games += 1
                    if r.score2 == 1.0:
                        shared.w += 1
                    elif r.score2 == 0.0:
                        shared.l += 1
                    else:
                        shared.d += 1
                    n = shared.games
                    w, d, l = shared.w, shared.d, shared.l
                    if shared.results_f:
                        shared.results_f.write(json.dumps({
                            "game": n, "e2_sente": r.e2_is_sente,
                            "score2": r.score2, "reason": r.reason,
                            "opening": r.opening, "plies": len(r.moves),
                            "moves": " ".join(r.moves),
                        }, ensure_ascii=False) + "\n")
                        shared.results_f.flush()
                    llr = sprt_llr(w, d, l, args.sprt[0], args.sprt[1])
                    elo, err = elo_estimate(w, d, l)
                    print(f"[{n:5d}] E2: {w}-{l}-{d} (W-L-D)  "
                          f"elo {elo:+6.1f} ±{err:5.1f}  LLR {llr:+.2f} "
                          f"[{args.llr_lower:.2f},{args.llr_upper:.2f}]  ({r.reason})",
                          flush=True)
                    if llr >= args.llr_upper or llr <= args.llr_lower:
                        shared.stop = True
    finally:
        e1.quit()
        e2.quit()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="USI A/B match harness with SPRT")
    p.add_argument("--engine1", required=True, help="基準側エンジン (base)")
    p.add_argument("--engine2", required=True, help="テスト側エンジン (改善パッチ)")
    p.add_argument("--eval-dir", default=None, help="両エンジン共通のEvalDir")
    p.add_argument("--eval-dir1", default=None)
    p.add_argument("--eval-dir2", default=None)
    p.add_argument("--option", action="append", default=[], metavar="K=V",
                   help="両エンジンに設定するUSIオプション (複数可)")
    p.add_argument("--option1", action="append", default=[], metavar="K=V")
    p.add_argument("--option2", action="append", default=[], metavar="K=V")
    p.add_argument("--byoyomi", type=int, default=1000, help="秒読み[ms] (default 1000)")
    p.add_argument("--time", type=int, default=0, help="持ち時間[ms] (default 0)")
    p.add_argument("--inc", type=int, default=0, help="加算[ms]")
    p.add_argument("--movetime", type=int, default=0, help="1手固定時間[ms] (指定時は時計無視)")
    p.add_argument("--nodes", type=int, default=0, help="固定ノード数 (NPSに影響する変更の測定には非推奨)")
    p.add_argument("--move-margin", type=float, default=5.0, help="1手のタイムアウト余裕[s]")
    p.add_argument("--openings", default=None, help="開始局面ファイル ('startpos moves ...' 形式)")
    p.add_argument("--draw-moves", type=int, default=320, help="この手数で引き分け")
    p.add_argument("--resign-score", type=int, default=3000, help="自己申告評価値がこれ以下なら投了扱い(0で無効)")
    p.add_argument("--resign-count", type=int, default=3, help="連続手数")
    p.add_argument("--sprt", nargs=2, type=float, default=[0.0, 5.0], metavar=("ELO0", "ELO1"))
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--beta", type=float, default=0.05)
    p.add_argument("--max-games", type=int, default=20000)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--threads", type=int, default=1, help="各エンジンのThreads")
    p.add_argument("--hash", type=int, default=256, help="USI_Hash [MB]")
    p.add_argument("--seed", type=int, default=20260713)
    p.add_argument("--log", default="ab_results.jsonl", help="対局ログ(JSONL)")
    return p.parse_args(argv)


def build_options(args, side: int) -> dict:
    opts = {
        "USI_Ponder": "false",
        "Threads": str(args.threads),
        "USI_Hash": str(args.hash),
        "MaxMovesToDraw": str(args.draw_moves),
        "NetworkDelay": "0",
        "NetworkDelay2": "0",
        "USI_OwnBook": "false",
        "BookFile": "no_book",
    }
    ev = args.eval_dir1 if side == 1 else args.eval_dir2
    ev = ev or args.eval_dir
    if ev:
        opts["EvalDir"] = os.path.abspath(ev)
    for kv in args.option + (args.option1 if side == 1 else args.option2):
        k, _, v = kv.partition("=")
        opts[k] = v
    return opts


def load_openings(path):
    openings = []
    if not path:
        return [[]]
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("startpos"):
                toks = line.split()
                openings.append(toks[2:] if len(toks) > 2 and toks[1] == "moves" else [])
            else:
                openings.append(line.split())
    return openings or [[]]


def main(argv=None):
    args = parse_args(argv)
    args.llr_upper = math.log((1 - args.beta) / args.alpha)
    args.llr_lower = math.log(args.beta / (1 - args.alpha))

    if not HAS_CSHOGI:
        print("[info] cshogi未検出: 千日手/連続王手千日手/詰みの厳密判定なしで実行します。\n"
              "       (`pip install cshogi` で厳密判定が有効になります。終局は投了/宣言/最大手数で判定)")

    openings = load_openings(args.openings)
    print(f"[info] openings: {len(openings)}種  concurrency: {args.concurrency}  "
          f"SPRT elo0={args.sprt[0]} elo1={args.sprt[1]} bounds=({args.llr_lower:.2f},{args.llr_upper:.2f})")

    opts1 = build_options(args, 1)
    opts2 = build_options(args, 2)

    shared = Shared()
    shared.results_f = open(args.log, "a", encoding="utf-8")

    workers = []
    for wid in range(args.concurrency):
        t = threading.Thread(target=worker_main,
                             args=(wid, args, shared, openings, opts1, opts2), daemon=True)
        t.start()
        workers.append(t)
        time.sleep(0.3)  # 起動をずらす
    try:
        for t in workers:
            t.join()
    except KeyboardInterrupt:
        with shared.lock:
            shared.stop = True
        for t in workers:
            t.join(timeout=30)

    w, d, l = shared.w, shared.d, shared.l
    llr = sprt_llr(w, d, l, args.sprt[0], args.sprt[1])
    elo, err = elo_estimate(w, d, l)
    print("\n================ 結果 (engine2視点) ================")
    print(f"games {shared.games}  W-L-D {w}-{l}-{d}  elo {elo:+.1f} ±{err:.1f}  LLR {llr:+.2f}")
    if llr >= args.llr_upper:
        print(f"判定: H1受理 — engine2 は engine1 より強い (elo1={args.sprt[1]}基準)")
    elif llr <= args.llr_lower:
        print(f"判定: H0受理 — 有意な改善なし")
    else:
        print("判定: 打ち切り (境界未達)。対局数を増やすこと。")
    shared.results_f.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
