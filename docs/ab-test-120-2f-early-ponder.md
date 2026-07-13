# A/Bテスト報告: 120秒+2秒フィッシャー・早期Ponder再現 (2026-07-13)

## 目的

実対局と同じ時間条件(持ち時間120秒+1手2秒加算のフィッシャー)で、
ShogiHomeの早期Ponder(時計なし `go ponder` → `ponderhit btime .. wtime ..`)を
再現し、ponderhit時間制御修正の効果を対照実験で確認する。

- **A(対照)**: `tune/danbo2` @ 5e5f0b53 — 修正なし
- **B(実験)**: `test/danbo-tuned2-ponderhit` @ ed2d4416 — 修正あり
  (= tune/danbo2 + fix/ponderhit-time-control)

## 方法

実対局CSA棋譜(600+2、sojo後手)の全白番104手を強制ラインとして、
各手で `position` → `go ponder`(時計なし)→ 相手考慮sleep →
`ponderhit btime .. wtime .. binc 2000 winc 2000` を送りbestmoveまでを実測。

- 時計はライブ進行: `wclock(次) = wclock − 実測消費 + 2000`(GUI側計測で課金)
- 相手考慮 = 棋譜Tを3秒でキャップして再現
- 両エンジン同一設定: Threads 2 / USI_Hash 1024 / 定跡無効 /
  Stochastic_Ponder true / EvalDir(sojo 2048) / FV_SCALE 28 /
  LS_BUCKET_MODE progress8kpabs / LS_PROGRESS_COEFF /root/danbo/progress.bin
- ハーネス・生データ: `docs/data/ab-test-120-2f/`

## 結果

| 指標 | A: 修正なし | B: 修正あり |
|---|---|---|
| 非mate・複数合法手での1秒未満着手 | **95 / 95手 (100%)** | **0 / 94手 (0%)** |
| 実測 min/中央値/max | 2 / 104 / 143 ms | 3 / 1883 / 14880 ms |
| timeman理論帯域(自時計基準)からの逸脱 | ―(全手即指しで無意味) | **0件** |
| 白時計推移(開始120.0s) | **317.4sへ肥大**(時間を使わず加算だけ蓄積) | 12.1sで終局(最小1.11s @ply170) |
| 警告 / 二重bestmove / 非合法手 | 0 / 0 / 0 | 0 / 0 / 0 |

対比サンプル(同一局面・同一Ponder窓):

| ply | A: 時計→消費 | B: 時計→消費 | B理論 min/opt/max (ms) |
|---|---|---|---|
| 24 | 140.9s→0.10s | 107.3s→2.88s | 1880/4242/13880 |
| 44 | 159.8s→0.10s | 75.5s→10.88s | 1880/3975/12880 |
| 80 | 194.0s→0.11s | 45.6s→4.88s | 1880/3772/11880 |
| 110 | 222.4s→0.10s | 15.4s→1.88s | 1880/3168/8880 |
| 128 | 239.4s→0.11s | 13.5s→5.88s | 1880/3129/8880 |

**判定: 修正は120+2Fの実対局条件でも有効。** Aは全手即指し
(時計欠落→下限100ms)を再現し、Bは全手がtimeman仕様どおりの時間配分。

## 付随する発見: 終盤の増加時間への食い込み(修正とは無関係)

Bは中盤の消費で時計が減り、ply136以降は残り約1.1〜1.5秒 +
毎手2秒加算の定常状態に入った。この区間の31手で
「消費 > ponderhit時点の残り時間」となった(超過529〜889ms)。

これは `timeman.cpp:232` の設計による:

```
remain_time = time + byoyomi + inc − NetworkDelay2
```

つまり**今手のincrementを消費可能予算に含める**(超過は最大
inc − NetworkDelay2 = 880ms に一致)。Ponderなしの直接goでも
全く同じ挙動であることを両ビルドで確認した(局面=ply140、wtime=1100):

| ビルド | 直接go wtime=1100 の消費 |
|---|---|
| A(修正なし) | 1986ms |
| B(修正あり) | 1987ms |

→ **upstream由来の時間管理仕様であり、本修正の副作用ではない。**
修正前は時間を一切使わないため顕在化しなかっただけである。

### 実運用上の注意

- サーバが「増加時間を着手前に付与」(または同等の猶予)なら、
  この挙動はちょうどNetworkDelay2=1120msのマージン内で安全。
- サーバが「残り時間0で即負け・加算は着手後」の厳密仕様なら、
  120+2Fの終盤で時間切れリスクがある。その場合は
  **NetworkDelay2をinc+マージン(例: 3120)に引き上げる**と
  `remain = time − 1120` となり食い込みが消える(思考時間は短くなる)。
- 対局サーバの加算タイミング仕様の確認を推奨。

### 参考(世代差)

wtime=60000の直接goではA=13884ms、B=9884msと最大思考の伸ばし方が
異なるが、これはA(527a083a世代)とB(master 23faf0a世代)の
timeman/探索の版差によるもので、各版の仕様内の挙動である。

## 再現方法

```
python3 docs/data/ab-test-120-2f/ab_livetest.py \
  --engine-bin <binary> --engine-dir <sojo資産dir> \
  --rows docs/data/stochastic-ponder-t0/csa_replay_rows.json --out result.jsonl
python3 docs/data/ab-test-120-2f/ab_analyze.py
```

(スクリプト既定パスは検証環境のscratchpadを指すため、引数で明示すること)
