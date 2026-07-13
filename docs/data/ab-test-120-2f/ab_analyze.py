#!/usr/bin/env python3
"""A/B集計: 120+2F早期Ponderライブリプレイの対比と、B側のtimeman理論値適合判定。"""
import json, statistics

SC = "/tmp/claude-0/-home-user-YaneuraOu/c8161a19-7e1e-5666-a157-98924d98dbd6/scratchpad"
A = {json.loads(l)['ply']: json.loads(l) for l in open(f"{SC}/ab_A_tunedanbo2.jsonl")}
B = {json.loads(l)['ply']: json.loads(l) for l in open(f"{SC}/ab_B_testdanbo2.jsonl")}

# timeman.cpp理論値 (フィッシャー inc=2000, byoyomi=0, 既定オプション)
def theory(ply, time_ms):
    remain = time_ms + 2000 - 1120
    horizon = 180 - min(ply, 80)
    MTG = min(512 - ply + 2, horizon) // 2
    if MTG <= 0:
        return 500, 500, 500
    minimum = max(2000 - 120, 1000)
    est = max(time_ms + 2000 * MTG - (MTG + 1) * 1000, 0)
    t1 = minimum + est // MTG
    opt = min(t1, remain)
    t2 = min(minimum + est * 5 // MTG, int(est * 0.3))
    mx = min(t2, remain)
    ru = lambda t: -(-t // 1000) * 1000 - 120
    return min(ru(minimum), remain), opt, min(ru(mx), remain)

def summarize(name, D):
    lat = [d['latency_ms'] for d in D.values()]
    normal = [d for d in D.values() if d['score_type'] != 'mate' and (d['legal_count'] or 2) > 1]
    sub1 = [d for d in normal if d['latency_ms'] < 1000]
    dup = [d for d in D.values() if d['bestmove_count'] != 1]
    illegal = [d for d in D.values() if not d['bestmove_legal']]
    to = [d for d in D.values() if d.get('timeout_flag')]
    warn = [d for d in D.values() if d['warnings']]
    last = D[max(D)]
    print(f"[{name}] {len(D)}手  実測ms min/med/max = {min(lat)}/{round(statistics.median(lat))}/{max(lat)}")
    print(f"  非mate・複数合法手 {len(normal)}手中 1秒未満 = {len(sub1)}手"
          f" ({round(100*len(sub1)/max(1,len(normal)))}%)")
    print(f"  時間切れ={len(to)} 警告={len(warn)} 二重bestmove={len(dup)} 非合法={len(illegal)}")
    print(f"  最終白時計 = {last['wclock_after']/1000:.1f}s (開始120.0s)")
    return normal, sub1

print("== A: tune/danbo2 (ponderhit修正なし・対照) ==")
a_normal, a_sub1 = summarize("A", A)
print()
print("== B: test/danbo-tuned2-ponderhit (修正あり・実験) ==")
b_normal, b_sub1 = summarize("B", B)

# B: 理論値適合(自時計基準)
print()
print("== B の timeman理論値適合 (非mate・複数合法手) ==")
viol = []
for d in b_normal:
    mn, opt, mx = theory(d['ply'], d['wclock_before'])
    if d['latency_ms'] < mn - 60 or d['latency_ms'] > mx + 1500:
        viol.append((d['ply'], d['latency_ms'], mn, opt, mx))
print(f"帯域逸脱: {len(viol)}件" + (f" {viol}" if viol else " (全手 min-60ms〜max+1500ms 内)"))

# 対比サンプル(序盤/中盤/終盤 + A系のT0感覚)
print()
print("== 対比サンプル (同一局面・同一Ponder窓) ==")
print(" ply | opp睡眠 | A: 時計→実測 | B: 時計→実測 | B理論min/opt/max")
for ply in sorted(B):
    if ply in (24, 44, 62, 80, 96, 110, 120, 128) and ply in A:
        a, b = A[ply], B[ply]
        mn, opt, mx = theory(ply, b['wclock_before'])
        print(f"{ply:4d} | {b['opp_sleep']:4.1f}s | "
              f"{a['wclock_before']/1000:6.1f}s→{a['latency_ms']/1000:6.2f}s | "
              f"{b['wclock_before']/1000:6.1f}s→{b['latency_ms']/1000:6.2f}s | "
              f"{mn}/{opt}/{mx}")

# A側の分布の裏取り: 全手が即指しか
a_lat = sorted(d['latency_ms'] for d in a_normal)
print()
print(f"A 非mate実測分布: 最頻帯 {a_lat[0]}〜{a_lat[-1]}ms, "
      f"90パーセンタイル {a_lat[int(len(a_lat)*0.9)]}ms")
b_lat = sorted(d['latency_ms'] for d in b_normal)
print(f"B 非mate実測分布: {b_lat[0]}〜{b_lat[-1]}ms, "
      f"中央値 {b_lat[len(b_lat)//2]}ms")
