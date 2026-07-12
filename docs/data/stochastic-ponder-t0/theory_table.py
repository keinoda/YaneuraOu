#!/usr/bin/env python3
"""timeman.cpp の時間配分式(600s+2s加算、既定オプション)による理論値と
棋譜の消費時間の照合表を出力する。

前提: NetworkDelay=120, NetworkDelay2=1120, MinimumThinkingTime=2000,
SlowMover=100, RoundUpToFullSecond=true, MaxMovesToDraw=512,
ProgressSlowMover/Mtg=false, USI_Ponder=true, Stochastic_Ponder=true
(ON時。OFF時は optimum が 1.25倍になるが maximum は不変)。
"""
import json, statistics

rows = [r for r in json.load(open("csa_replay_rows.json")) if r['side'] == 'W']

def expected(ply, time_ms):
    remain = time_ms + 2000 - 1120
    horizon = 180 - min(ply, 80)          # 切れ負けでない場合: MoveHorizon+20-min(ply,80)
    MTG = min(512 - ply + 2, horizon) // 2
    if MTG <= 0:
        return 0.5, 0.5
    minimum = max(2000 - 120, 1000)
    est = max(time_ms + 2000 * MTG - (MTG + 1) * 1000, 0)
    t1 = minimum + est // MTG
    opt = min(t1, remain)
    t2 = min(minimum + est * 5 // MTG, int(est * 0.3))
    mx = min(t2, remain)
    ru = lambda t: -(-t // 1000) * 1000 - 120   # 秒切り上げ - NetworkDelay
    return opt / 1000, min(ru(mx), remain) / 1000

print(" ply | kifuT | optimum | theory_max | diff(kifuT-max)")
diffs = []
for r in rows:
    if r['t'] >= 20:
        opt, mx = expected(r['ply'], r['clock_before'])
        diffs.append(r['t'] - mx)
        print(f"{r['ply']:4d} | {r['t']:4d}s | {opt:6.2f}s | {mx:8.2f}s | {r['t']-mx:+.2f}")
print(f"mean diff: {statistics.mean(diffs):+.2f}s ; |diff|<=1.0s: "
      f"{sum(1 for d in diffs if abs(d) <= 1.0)}/{len(diffs)}")
