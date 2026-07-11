# Stochastic Ponder 有効時の「残り時間に関わらず即指し」調査ログ

## 2026-07-11: 調査のまとめ

### 症状

Stochastic_Ponder を有効にして対局していると、残り時間が十分あるのに
bestmove がほぼ即座に返ることがある。本fork の改造
(OpeningTarget / ponder miss 検出 / ProgressSlowMover / ProgressMtg /
SlowMover_black・white / 定跡 repetition 処理 / uciScore 変更) が原因かを調査した。

### 結論

- **fork の改造の中に即指しを引き起こす欠陥は見つからなかった。**
  コード監査に加えて、下記のUSI対局シミュレーション 4 構成 + 定跡構成
  (計 11 局・被験側の計測手 652 手、うち ponderhit 経由 417 手、
  go ponder 603 回で ponder 中の bestmove 漏れ 0 件) で、
  持ち時間が残っている状態での非詰みスコアの即指しは **0 件**。
  非詰み局面の最短思考時間は常に 1880ms
  (= MinimumThinkingTime 2000 − NetworkDelay 120。設計どおりの下限) だった。
- 観測された「即指し」は全件 (42/42) **score が mate ±N の局面**で発生していた。
  これは本家 V9.60 の `iterative_deepening()` にある
  **詰み読み切り時の早期打ち切り** (`yaneuraou-search.cpp` 2212〜2227行付近、
  「mateを読みきったとき、そのmateの2.5倍以上、iterationを回しても仕方ない」)
  が原因で、`rootDepth > 詰み手数×2.5` になった時点で反復深化を break する。
  この経路は MinimumThinkingTime / optimumTime / search_end を経由しないため、
  **TTが温まっている連続局面では bestmove が数ms で返る**。
  勝ち詰みだけでなく **詰まされる側 (mate −N) でも同様に即指しになる**。
- この挙動は **Stochastic_Ponder とは無関係**。ponder を完全に無効化しても再現した
  (下記デモ)。Stochastic Ponder 有効時は ponderhit 直後の再探索が
  ホットTTから瞬時に詰みを再証明するため、「相手が指した瞬間に即応する」形で
  体感されやすくなるだけである。

### 改造点ごとの監査結果

| 改造 | 即指しへの影響 |
| --- | --- |
| Stochastic Ponder の ponderhit 処理 (usi.cpp: bestmove抑制→stop→再position→再go) | 問題なし。抑制リスナーは参照経由で探索中も有効。再goで tm.init が startTime/ponderhitTime/search_end を初期化、start_thinking が stop をリセット。go ponder→即ponderhit のレース(プリムーブ相当)も多数試行して健全 |
| ponder miss 検出 (`consume_ponder_miss` / `remember_bestmove`) | 時間への作用は PonderMissMaximumScale による maximumTime の**延長**のみで、短縮はしない |
| OpeningTarget (penalty / TT salt / ponder出力抑制 / ignoreOpeningTarget) | penalty は decisive 値を除外して clamp しており偽の mate スコアは作れない。target 有効中は ponder 自体が出ないので ponder 経路にも影響なし |
| ProgressSlowMover / ProgressMtg / SlowMover_black・white | optimum/maximum を係数で増減するだけで、minimumTime の下限 (≈1880ms) は割れない。ただし scale を 100 未満にすると下限近くまで思考が短くなるので「早指しに見える」要因にはなり得る |
| 定跡 repetition 処理 (BookRepetitionPly / BookIgnoreRepeatedRoot) | 既定オフ。オンでも定跡候補の除外/実効値置換のみ。定跡ヒット自体の即指しは従来仕様 |
| uciScore を α/β clamp しない変更 | 表示と ResignValue 判定に影響し得るが、探索停止条件には不使用 |

### 再現テスト構成

被験エンジン: sojotsec7 配布物 (V9.60DEV AVX512VNNI TOURNAMENT + nn.bin +
progress.bin、engine_options.txt は LS_BUCKET_MODE=progress8kpabs /
LS_PROGRESS_COEFF / FV_SCALE=28)。
`script/ponder_stress_test.py` が GUI (将棋所相当) として被験側A
(USI_Ponder + Stochastic_Ponder オン) と相手側B (`go rtime`) を対局させ、
go / ponderhit → bestmove のレイテンシを全数記録する。

| run | 構成 | 計測手 | 非詰み即指し |
| --- | --- | --- | --- |
| run1 | 3分切れ負け、通常進行 | 135 | 0 |
| run3 | 高速相手 + 35% プリムーブ即時 ponderhit (レース誘発) | 210 | 0 |
| run4 | 90秒+秒読み3秒、OpeningTarget両側 + PonderMissMaximumScale=200 + ProgressSlowMover/Mtg + SlowMover_black/white | 189 | 0 |
| run5 | run1 + 定跡 (標準定跡形式 78局面、定跡ヒット/離脱境界の確認。ヒット10手を book と識別) | 118 | 0 |

`info string PonderMiss maximumTime=...` の発火 (run4 で 10回)、
OpeningTarget 有効中の ponder 出力抑制、定跡ヒットの busy-wait
(go ponder 中は stop/ponderhit まで bestmove を返さない) も期待どおり動作。

### ponder 無効でも再現するデモ (詰み読み切り早期終了)

`script/mate_instant_move_demo.py` : 詰みが見えはじめる局面から
USI_Ponder=false / Stochastic_Ponder=false / 5分+秒読み10秒 で連続して指させる。

観測例 (run4 game1 の139手目局面から):

```text
move 139: elapsed=   3635ms score=mate 15  bestmove=3f2f  (コールドTT: 読み切りに時間を使う)
move 141: elapsed=     27ms score=mate 13  bestmove=2f1e
move 143: elapsed=     12ms score=mate 11  bestmove=2g2f
move 145: elapsed=     22ms score=mate 9   bestmove=2e3c+
move 147: elapsed=     31ms score=mate 7   bestmove=1b2c+
move 149: elapsed=      8ms score=mate 5   bestmove=S*2d
```

ponder なしでも2手目以降は数ms。よって Stochastic_Ponder は原因ではない。

### 切り分けの目安

- 即指しの瞬間の `info ... score` が `mate ±N` (GUI表示は「詰み」) なら本件
  = 本家仕様。挙動を変えたい場合は `yaneuraou-search.cpp` の
  当該 break に MinimumThinkingTime 相当の待ちを足す改造になる (本家仕様変更)。
- `score cp` のまま即指きが観測されたら本調査で未再現の別事象。
  DebugLogFile オプションで USI ログを取り、GUI名 (将棋所/ShogiGUI/自作ランナー等)
  と合わせて解析する。特に「stop 後の bestmove を読み捨てずに次の go を送る」
  タイプのランナーは、ponder miss 時に**古い ponder 探索の bestmove を
  新しい go への応答と誤認**し、即指し (Stochastic Ponder では非合法手) に見える。

### 副次的発見

1. **`isready` 前に `position` を送ると segfault する** (配布バイナリ・
   本リポジトリからの再ビルドの両方で確認。`position startpos` のみで再現)。
   GUI は必ず isready を先に送るため実対局への影響はないが、手動デバッグ時に注意。
2. GUI が stop 後の bestmove を待たずに次の go を送ると、ponder 探索の
   bestmove が `remember_bestmove` に記録され、ponder miss 検出
   (PonderMissMaximumScale) が誤動作し得る (時間が延びないだけで実害は軽微)。
3. `MaxMovesToDraw` を設定した対局で手数が上限を超過すると
   MTG≦0 の保険経路 (timeman.cpp「MaxMovesToDraw is too small」) に入り
   1手500ms固定になる。上限到達後もGUIが対局を打ち切らない場合のみ発生。

### 使い方

```bash
# 対局シミュレーション (エンジン配置ディレクトリを指定)
python3 script/ponder_stress_test.py --engine-dir /path/to/engine \
  --games 4 --main-time 180000 --tag run1
# 秒読み・レース・追加オプションの例
python3 script/ponder_stress_test.py --engine-dir /path/to/engine \
  --byoyomi 3000 --main-time 90000 --instant-hit-prob 0.35 \
  --opt PonderMissMaximumScale=200 --tag run4

# 詰み読み切り早期終了のデモ (pos.txt: "startpos moves ..." 1行)
python3 script/mate_instant_move_demo.py pos.txt /path/to/engine
```

records_<tag>.jsonl に 1手1行 (kind=go/ponderhit, remain_before, elapsed_ms,
score, book, anomaly) で記録される。非詰み・持ち時間ありで elapsed<1.2s の手が
anomaly=true になる。
