# Stochastic Ponder T0調査の計測生データ

`docs/stochastic-ponder-immediate-move-test.md` の
「2026-07-12: 実対局CSA棋譜の0秒指し検証」の全数データ。
独立検証(集計の再現)用。

対象棋譜: `dr7tsec+buoy_blackbid600_tsec7p2-3-top_4_suishoo_sojo-600-2F+suishoo+sojo+20260711212454.csa`
(600秒+2秒加算、sojo=後手=本エンジン)。
エンジン: sojotsec7配布物 (V9.60DEV AVX512VNNI TOURNAMENT + nn.bin +
progress.bin、定跡ファイルなし)。ホスト: 4コア、Threads=2, USI_Hash=1024。

## ファイル

- `csa_replay_rows.json` : CSAから復元した1手ごとのデータ。
  ply / side / usi(指し手) / t(消費秒) / clock_before(手番側の残りms) /
  legal(白番局面の合法手数) / check(王手か)。
  時計復元は 600_000ms 開始、各手で `-T*1000 +2000`(加算)。
- `csa_replay_stochastic.jsonl` : Stochastic_Ponder=ON、時計付き
  always-hitポンダー手順での全白番104手の実測。
  latency_ms = ponderhit送信からbestmove受信まで。
  black_thinkは実消費(sleepは min(t, 6s))。
- `csa_replay_normal_full.jsonl` : 同、Stochastic_Ponder=OFF(通常ponder)。
- `csa_replay_normal_rerun12s.jsonl` : OFFの追試。黒考慮sleep上限を12秒に
  拡大し、ply82〜146の29手を再計測(min=1880ms、1秒未満0件)。
- `csa_replay_earlyponder_before.jsonl` : ShogiHome早期Ponder形式
  (時計なしgo ponder + 時計付きponderhit)、修正前バイナリ、ply82〜92。
  全手約0.10秒(=棋譜のT0を再現)。
- `csa_replay_earlyponder_after.jsonl` : 同、ponderhit時刻反映パッチ
  適用後ビルド。3.88〜17.88秒(正常な時間管理)。

## 集計の再現例

```bash
# ON: 非詰み・合法手2手以上の最短レイテンシ (=2880ms, <1.8s は 0件)
python3 - <<'EOF'
import json
rows=[json.loads(l) for l in open('csa_replay_stochastic.jsonl')]
x=[r['latency_ms'] for r in rows
   if not (r['score'] or '').startswith('mate') and (r['legal'] or 99)>1]
print(len(x), min(x), sum(1 for v in x if v<1800))
EOF

# 長考(T>=20秒)と理論maximumTimeの照合 (13/15が-0.88s差)
python3 theory_table.py
```

- 計測ツール: `script/csa_ponder_replay.py`(モード:
  stochastic / normal / noponder / earlyponder)。
- 理論値: `theory_table.py`(timeman.cpp の式をそのまま移植)。
