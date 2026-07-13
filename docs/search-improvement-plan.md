# やねうら王 探索部改善計画 (Search Improvement Ultraplan)

作成日: 2026-07-13
対象: このリポジトリ (V9.60git ベース + fork独自機能) の探索部
`source/engine/yaneuraou-engine/yaneuraou-search.cpp` / `source/movepick.cpp` / `source/history.h` ほか

---

## 1. 現状分析

### 1.1 探索部の素性

- V9.60 の探索部は **2025年中頃の Stockfish master (SF17.1以降のdev) をほぼ忠実に移植**したもの。
  以下の最新機構がすでに導入済みであることをコード精読で確認した。
  - Correction History 一式 (pawn / minor piece / non-pawn(先後) / continuation)。
    NUMAノード内スレッド共有 (`SharedHistories`, atomic) + `UnifiedCorrectionHistory` (キャッシュライン最適化のバンドル化)
  - Pawn History (スレッド共有・atomic)、Low Ply History、TTMoveHistory
  - priorReduction による事後的 depth 調整 (hindsight adjustment)
  - cutoffCnt ベースの reduction、doDeeperSearch / doShallowerSearch
  - singular拡張の double/triple margin、negative extension、multicut
  - `is_shuffling` (手待ち往復手の検出。将棋向けに駒打ち除外の適応済み)
  - 10バイトTTエントリ (key16/depth8/move16/value16/eval16 + gen5/pv1/bound2)
  - 時間管理: fallingEval / timeReduction / bestMoveInstability / nodesEffort (highBestMoveEffort)
- したがって「古いSFとの差分を取り込む」型の改善余地はほぼ枯れており、残る改善余地は主に:
  1. **チェス用定数・チェス用ロジックの将棋への適応不足** (捕獲価値、王手の扱い等)
  2. **やねうらお氏自身がコード中コメントで「要検証」と残している箇所** (🤔/TODO/OLD_CODE)
  3. **V9.60 で入った未検証の独自実験** (followPV ゲーティング)
  4. 将棋固有の指し手性質 (駒打ち・王手の多さ) を突いた独自ヒューリスティック

### 1.2 fork独自機能と探索部の接点 (改変時の保全ポイント)

このforkには OpeningTarget / 進行度SFNN(LS_PROGRESS) / Tatara NNUEヘッダ対応が入っている。
探索部を変更する際に**壊してはならない**接点は次の3系統:

| 接点 | 場所 | 内容 |
|---|---|---|
| TTソルト | search() L2953-2956, qsearch() L4993-4996 | `posKey ^= opening_target_tt_salt(...)` を probe/write 両方に適用 |
| 評価値ペナルティ | search() L3408/L3436, qsearch() L5088/L5153 | `apply_opening_target_penalty()` が staticEval 代入を包む |
| スタック伝播 | iterative_deepening L1788, do_move L2419, NMP L3615 | `ss->openingTargetReached/Hidden` を (ss+1) へ伝播 |

本計画の各パッチはいずれもこれらの行を変更しない (Step 14/15/17、NMPのR、IIR、statScore、
qsearch futility、aspiration delta のみを触る)。

### 1.3 ビルド・検証手段

- ビルド: `cd source && make -j4 tournament YANEURAOU_EDITION=YANEURAOU_ENGINE_NNUE TARGET_CPU=AVX2 COMPILER=clang++`
  (スモークには `YANEURAOU_ENGINE_MATERIAL` + `COMPILER=g++` が評価ファイル不要で手軽)
- 動作確認: `bench [TT_MB] [threads] [limit] default nodes` / `unittest`
- 自己対局: 従来は `script/engine_invoker5.py` (古い)。**本計画で SPRT 付きの新ハーネス `script/ab/` を追加**。

---

## 2. 改善候補の全リスト

精読で洗い出した候補を「採用(A/Bブランチ化)」「見送り(理由付き)」「将来課題」に分類する。
期待効果は根拠の強さとSFでの類似パッチの実績からの目安であり、**最終判定はすべてA/Bテストで行う**。

### 2.1 採用 — A/Bテストブランチ (1ブランチ = 1改善)

ブランチはすべてベースブランチ `claude/yaneuraou-search-optimization-qxvzz0`
(= master + 本ドキュメント + A/Bテスト基盤。エンジンコードはmasterと同一) から分岐。
**エンジンコードの差分が「その改善1つだけ」**になるよう構成している。

#### AB-01 `claude/search-ab/01-capture-futility` — 捕獲futilityに将棋の交換値(盤上+手駒+成り)を使用

- **場所**: search() Step 14 (捕獲手のfutility)、qsearch() Step 6 (futility)
- **現状**: `PieceValue[捕獲される駒]` (盤上の駒価値のみ) を加算している。
- **問題**: 将棋の捕獲は「相手の盤上駒が消える + 自分の手駒が増える」ので実質の評価値変動は
  約2倍 (`CapturePieceValue = PieceValue[pc] + PieceValue[raw(pc)]`)。さらに成りを伴う指し手は
  成り差分 (`ProDiffPieceValue`) も上乗せされる。現状は捕獲による上昇分を大幅に過小評価しており、
  **有望な捕獲手・歩成りが futility で刈られすぎる**。歩の成り(非捕獲)は現状加算0点扱い。
- **変更**: 両箇所を `Eval::CapturePieceValuePlusPromote(pos, move)` に置換。
- **根拠**: やねうらお氏自身のコメント (search L3966-3971「CapturePieceValuePlusPromote()のほうが
  より正確な評価ではないか？」、qsearch L5298-5302 計測資料14)。
- **リスク**: 枝刈り減少によるNPS低下。効果とのトレードオフをA/Bで判定。

#### AB-02 `claude/search-ab/02-check-extension` — 王手延長の復活 (限定条件)

- **場所**: search() Step 15 (singular延長のelse-ifチェーン末尾)
- **現状**: SFがRemove check extensionで削除したのに追随し、王手延長なし。
- **変更**: `else if (givesCheck && depth > 9 && pos.see_ge(move, 0)) extension = 1;`
  SEE≥0 条件で「駒を捨てない王手」に限定し、将棋特有の王手ラッシュによる組み合わせ爆発を防ぐ。
- **根拠**: やねうらお氏のコメント (L4207-4213)「将棋では王手はわりと続くので(SFのまま持ってくると)
  やりすぎ」「王手延長自体は何らかあった方が良い可能性はあるので条件を調整してはどうか」。
  将棋は王手絡みの読み抜けが勝敗に直結しやすい。
- **リスク**: 延長による探索肥大。depth>9 で影響を深いノードに限定。

#### AB-03 `claude/search-ab/03-iir-old-style` — IIR(内部反復リダクション)を旧方式へ

- **場所**: search() Step 10
- **現状**: `if (!ss->followPV && !allNode && depth >= 6 && !ttData.move && priorReduction <= 3) depth--;`
- **変更**: コード中に `#if OLD_CODE` として残されている旧方式を有効化 (現行方式は削除):
  ```cpp
  if (PvNode && !ttData.move) depth -= 3;
  if (depth <= 0) return qsearch<PV>(pos, ss, alpha, beta);
  if (cutNode && depth >= 7 && (!ttData.move || ttData.bound == BOUND_UPPER)) depth -= 1 + !ttData.move;
  ```
- **根拠**: やねうらお氏のコメント (L3677-3678)「🌈 以前のコードのほうが強い可能性がある」。
  作者自身が未決着とマークしている分岐点であり、A/Bで白黒つける価値が高い。
- **リスク**: PvNodeでの-3は大きい。旧SFで長年実績のある形ではある。

#### AB-04 `claude/search-ab/04-no-followpv` — followPVゲーティングの除去 (純SF挙動)

- **場所**: search() Step 10 (IIR) と Step 14 (quiet枝刈りブロック)
- **現状**: V9.60独自の `ss->followPV` (前回iterationのPVを辿っているフラグ) が
  IIR (`!ss->followPV &&`) と quiet系枝刈り一式 (`else if (!ss->followPV || !PvNode)`) を抑制している。
  これは公開された計測根拠が見当たらない実験的機構。
- **変更**: 両条件から followPV を外す (IIR: `!allNode && ...`、quiet枝刈り: `else`)。
  followPV の計算自体は残す(最小差分)。
- **根拠**: 前回PV上で枝刈りを甘くするのは fail low 時の復元力を上げる一方、探索効率は下がる。
  SFに存在しない機構であり、効果検証が必要。
- **リスク**: これが実は効いていた場合は負けるだけ。どちらに転んでも知見になる。

#### AB-05 `claude/search-ab/05-nmp-eval-r` — null move探索のRにeval-beta項を追加

- **場所**: search() Step 9
- **現状**: `Depth R = 7 + depth / 3;` (深さのみ依存)
- **変更**: `Depth R = std::min(int(eval - beta) / 232, 6) + depth / 3 + 5;`
  (SF16〜17.1で長年使われた形。evalがbetaを大きく超えるほど深く削減)
- **根拠**: 将棋は終盤の評価値スイングがチェスより大きく、eval≫beta の局面では null move の
  検証を粗くしても安全という仮説。逆に eval≈beta では R が小さくなり検証が丁寧になる。
- **リスク**: SF最新が固定Rに簡素化したのには理由がある(チェスでは等価以上だった)。将棋で
  どちらが良いかは自明でない。

#### AB-06 `claude/search-ab/06-drop-lmr` — 王手にならない駒打ちのreduction増加 (将棋固有・独自案)

- **場所**: search() Step 16-17 のreduction計算
- **変更**: `if (move.is_drop() && !givesCheck) r += 768;` (≈0.75手分reduction増)
- **根拠**: 将棋の合法手の多さ(平均~100手、最大593手)の主因は駒打ちで、その大半は無意味な手。
  history群は学習に時間がかかるため、構造的な事前確率として「王手でない駒打ちは薄く読む」を
  reductionに直接与える。王手になる駒打ち(詰み絡みで重要)は除外。
- **リスク**: 受けの中合いや攻めの拠点打ちなど重要なquiet打ちも遅れて発見される。
  失敗した場合は逆符号 (`r -= X`、駒打ちを優遇) のテストも検討価値あり。

#### AB-07 `claude/search-ab/07-statscore-conthist` — statScoreに4手前・6手前の継続手履歴を追加

- **場所**: search() Step 16 (quiet手のstatScore計算)
- **現状**: `2*mainHistory + contHist[0] + contHist[1]`
- **変更**: `+ contHist[3]/2 + contHist[5]/2` を追加 (4手前・6手前の継続手 = 自分の手の流れ)
- **根拠**: やねうらお氏のコメント (L4283-4284)「contHist[5]も/2とかで入れたほうが良いのでは…。
  誤差か…？」+ 計測資料11 (contHist[3]の再検証)。MovePickerのオーダリングでは既に
  contHist[0..3],[5] を使っており、reduction側との整合を取る意味もある。
- **リスク**: 小さい変更なので必要対局数が多い(効果が小さい)可能性。

#### AB-08 `claude/search-ab/08-aspiration-delta` — aspiration windowの初期幅を将棋向けに拡大

- **場所**: iterative_deepening() のaspiration search初期化
- **現状**: `delta = 5 + threadIdx % 8 + |meanSquaredScore| / 9000;` (base 5 はSF17の値)
- **変更**: base を 5 → 9 に拡大。
- **根拠**: コード中の解説コメント (L1977)「💡 将棋ではStockfishより少し高めが良さそう」。
  KPP時代は35-40が最適だった歴史があり、NNUEでも評価値の揺れはチェスより大きい。
  fail high/lowの再探索コスト削減とのトレードオフ。
- **リスク**: 窓が広いと1回の探索コストが増える。単スレッドテストで判定しやすい(threadIdx項が0)。

#### AB-ALL `claude/search-ab/all` — 全部乗せ (相互作用確認用)

AB-01〜08をすべて適用したブランチ。個別テスト完了前の参考値、および「勝った改善同士を
足したときに相互作用で消えないか」の確認に使う。AB-03とAB-04はIIR部分が競合するため、
「旧方式IIR(followPVゲートなし)」として解決してある。

### 2.2 検討したが今回見送り (理由付き)

| 候補 | 見送り理由 |
|---|---|
| SEE (`see_ge`) 自体を CapturePieceValue スケールに変更 | 探索中の全SEE閾値(-25*lmrDepth², 167*depth, -73, GOOD_CAPTUREの/18等)の再調整が必要になり、1改善=1ブランチの原則に収まらない。効果は大きい可能性があるが、SPSA一括調整とセットでやるべき大工事。 |
| upcoming_repetition (千日手が近い時の早期打ち切り) | 作者が既に計測済み(効果なしと明記, L2601)。 |
| threat-based quiet ordering (安い駒の当たりからの逃げ) | 作者が2022年に簡易版を計測済みで不採用 (movepick L297-308)。将棋では利き計算コストが高い。LONG_EFFECT_LIBRARY常設化とセットの将来課題。 |
| qsearchでの王手生成の復活 | 手駒のある将棋では組み合わせ爆発リスクが高い(ファイル冒頭の設計コメント参照)。mate_1plyが1手詰めは拾えている。 |
| rule50/TT graph history interaction対策 | 作者計測でR10悪化と明記 (L3099-3100)。 |
| 時間管理 (timeman.cpp) の調整 | やねうら王独自の秒読み/切り上げロジックと fork独自のProgressSlowMover/ProgressMtgが絡み、退行リスクが高い。fallingEval等の定数はSPSA枠で。 |
| TT置換ポリシー・エントリ構造 | 最新SF相当が移植済みで、明確な改善案がない。 |
| aspiration の threadIdx % 8 項 (Lazy SMP多様化) | 検証にはマルチスレッドの大規模対局が必要でコストが高い。単スレ性能に影響なし。 |
| mate_1ply呼び出し条件の変更 (`!ttHit`→`!ttData.move`等) | 期待効果が小さく、置換表の状態に依存して再現性の低い変化。 |
| 宣言勝ち判定の呼び出し頻度削減 | 既に `!ttData.move \|\| PvNode` に限定されており軽量。 |
| Skill Level / MultiPV 周り | 棋力に無関係。 |

### 2.3 将来課題 (このA/Bラウンドの後に)

1. **SPSAによる一括パラメータ調整**: コードには `%%TUNE_DECLARATION%%` 等のマーカーと `Tune::init()`
   が既にあり、[YaneuraOu-ScriptCollection/SPSA](https://github.com/yaneurao/YaneuraOu-ScriptCollection) の
   tune.py が使える。今回のA/Bで生き残った構造変更を入れた上で、futility/razoring/LMR系の定数
   (razoring 502+306d²、futilityMult 76、singularBeta係数60/55、reduction定数2763/585/206/1133 等)
   を将棋の評価値スケールで再調整するのが本命。数万局規模の計算資源が必要。
2. **今回負けた仮説の逆方向テスト** (例: AB-06が負けたら駒打ちreduction減を試す)。
3. **勝った改善のmaster統合とリベース再テスト** (§4.4)。
4. **fishtest的な常設テスト基盤** (script/ab をワーカー並列化・結果集約サーバ化)。

---

## 3. A/Bテスト方法論

### 3.1 統計的判定 — SPRT

- 帰無仮説 H0: elo差 = 0 / 対立仮説 H1: elo差 = +5 (デフォルト。微小改善を狙うならelo1=3)
- α = β = 0.05 → LLR境界 ±log((1-β)/α) ≈ ±2.94
- 判定はGSPRT近似 (fishtest/fastchess系のトリノミアルMLE) を `script/ab/ab_match.py` に実装済み。
- 目安: 真の差が+5eloなら数千局、差が0なら平均~数千局でH0受理。**数百局で「勝ってそう」と
  判断しない**こと (それは±20elo級の差しか検出できない)。

### 3.2 対局条件 (推奨デフォルト)

| 項目 | 推奨値 | 理由 |
|---|---|---|
| スレッド | 各エンジン1 | 分散を減らす。SMP相互作用の検証は勝った改善のみ後で実施 |
| 持ち時間 | 秒読み1秒 (`--byoyomi 1000`) or 10分切れ負け相当の短縮版 | 短すぎるとNPS差・オーバーヘッドに支配される。時間の許す限り長いTCでの追試を推奨 (LTC で逆転する改善は多い) |
| USI_Hash | 256MB/エンジン | 短TCなら十分 |
| 開始局面 | `script/ab/openings.sfen` からランダム抽出、**同一局面で先後入替のペア対局** | 互角性の担保と分散低減 |
| 引き分け | 320手 or 千日手 (cshogi導入時は正確判定) | MaxMovesToDraw=320 をエンジン側にも設定 |
| 投了 | 評価値-3000が3手連続 (`--resign-score 3000 --resign-count 3`) | 対局高速化。宣言勝ち(`bestmove win`)対応済み |
| DrawValue | 両者 -2 (デフォルトのまま) | 対称性維持 |
| 評価関数 | 両ブランチで**完全に同一** の eval を使用 | 探索部のみの差を測るため |

### 3.3 実行手順 (詳細は `script/ab/README.md`)

```bash
# 1) 全ブランチのバイナリを一括ビルド (git worktree 使用)
script/ab/build_branches.sh -e YANEURAOU_ENGINE_NNUE -a AVX2 \
    claude/yaneuraou-search-optimization-qxvzz0 claude/search-ab/01-capture-futility

# 2) SPRT対局 (base vs ab01)
python3 script/ab/ab_match.py \
    --engine1 build/ab/claude_yaneuraou-search-optimization-qxvzz0.bin \
    --engine2 build/ab/claude_search-ab_01-capture-futility.bin \
    --eval-dir /path/to/eval --byoyomi 1000 --concurrency 2 \
    --openings script/ab/openings.sfen --sprt 0 5 --max-games 20000 \
    --option USI_Hash=256 --option MaxMovesToDraw=320
```

- engine2 (テスト側) が **H1受理 → 採用候補**。LTCで追試してからmaster統合。
- H0受理 → 不採用 (ブランチは記録として残す)。
- max-games 到達 → 実質差なし。簡素化を伴うなら採用可、複雑化なら不採用。

### 3.4 注意事項

- **openings.sfen は同梱のものは駒得エンジン生成の暫定版**。本測定の前に
  `python3 script/ab/make_openings.py --engine <強いエンジン> --eval-dir <eval>` で作り直すか、
  たややん互角局面集などの実績ある互角局面集を使うことを推奨。
- NPSに影響する変更 (AB-01等) は固定ノード対局 (`--nodes`) では正しく測れない。必ず時間制御で。
- ブランチ間の直接対決は不要。**常に base (または master) を対照群にする**。

---

## 4. ブランチ構成と運用

### 4.1 構成

```
master
 └─ claude/yaneuraou-search-optimization-qxvzz0   ← ベース: 本計画書 + script/ab (エンジンコードはmaster同一)
     ├─ claude/search-ab/01-capture-futility      ← ベース + AB-01のみ
     ├─ claude/search-ab/02-check-extension       ← ベース + AB-02のみ
     ├─ claude/search-ab/03-iir-old-style         ← ベース + AB-03のみ
     ├─ claude/search-ab/04-no-followpv           ← ベース + AB-04のみ
     ├─ claude/search-ab/05-nmp-eval-r            ← ベース + AB-05のみ
     ├─ claude/search-ab/06-drop-lmr              ← ベース + AB-06のみ
     ├─ claude/search-ab/07-statscore-conthist    ← ベース + AB-07のみ
     ├─ claude/search-ab/08-aspiration-delta      ← ベース + AB-08のみ
     └─ claude/search-ab/all                      ← ベース + AB-01..08 全部
```

- 各ABブランチの「エンジンコード diff」はベース比で1改善のみ:
  `git diff claude/yaneuraou-search-optimization-qxvzz0 claude/search-ab/01-capture-futility -- source/`
- ベースブランチのエンジンコードはmasterと同一なので、**対照群のバイナリはベースブランチから
  ビルドすればよい** (スクリプト込みで扱いやすい)。

### 4.2 検証済み事項 (このリポジトリ上で実施)

- 全ブランチ: `YANEURAOU_ENGINE_MATERIAL` (g++ / AVX2) でビルド成功 + `bench` 完走 (結果は§5)
- `claude/search-ab/all`: 加えて `YANEURAOU_ENGINE_NNUE` でビルド成功 (全パッチのNNUE互換確認)
- ベース: `unittest` 全パス、`ab_match.py` のスモーク対局完走

### 4.3 A/Bテストの優先順位 (推奨)

根拠の強さと期待効果から: **AB-01 → AB-03 → AB-04 → AB-02 → AB-05 → AB-08 → AB-06 → AB-07**

### 4.4 勝った改善の統合手順

1. LTC (長い持ち時間) で追試 → 再度H1なら確定。
2. masterへcherry-pick (`git cherry-pick <ABブランチの先頭コミット>`)。
3. 複数採用時は統合後のmaster vs 統合前masterで最終確認 (相互作用チェック。AB-ALLの結果が参考になる)。
4. 採用改善に含まれる定数 (AB-02のdepth>9、AB-06の768等) は次のSPSAラウンドの調整対象に加える。

---

## 5. ビルド・スモーク検証結果 (2026-07-13実施)

環境: このリポジトリのコンテナ (4コア, g++ 13.3, AVX2)。
bench は `bench 16 1 13 default depth` (固定depth13・シングルスレッドなのでノード数は決定的)。
エディションは MATERIAL (評価ファイル不要のため)。NPSは共有VMのため±10%程度の揺れあり。

**ノード数は「探索木の形が意図した方向に変わったか」の確認用**であり、増減の善し悪しは
対局テストでしか判定できない点に注意。

| ブランチ | ビルド | depth13 nodes | NPS | 傾向の解釈 |
|---|---|---|---|---|
| base | ✅ (+unittest 84/84) | 2,675,037 | ~800k | 基準 |
| ab/01-capture-futility | ✅ | 1,009,597 | ~796k | futility見積り精緻化で木が大きく変形 (MATERIAL評価では捕獲価値=評価値変動そのものなので効果が誇張される) |
| ab/02-check-extension | ✅ | 7,809,834 | ~759k | 王手延長で木が拡大 (bench局面は王手の多い終盤なので誇張あり) |
| ab/03-iir-old-style | ✅ | 2,205,896 | ~800k | IIR強化で木が縮小 |
| ab/04-no-followpv | ✅ | 2,015,457 | ~763k | PV上の枝刈り解禁で木が縮小 |
| ab/05-nmp-eval-r | ✅ | 4,677,343 | ~756k | eval≈betaでのnull move検証が丁寧になり木が拡大 |
| ab/06-drop-lmr | ✅ | 1,267,977 | ~966k | 駒打ちreductionで木が縮小・NPS向上 |
| ab/07-statscore-conthist | ✅ | 2,814,843 | ~844k | 微増 (小さな変更) |
| ab/08-aspiration-delta | ✅ | 2,408,994 | ~793k | 再探索減で微減 |
| ab/all (全部乗せ) | ✅ MATERIAL + **NNUEクリーンビルドも成功** | 1,493,180 | ~755k | 8パッチの合成 |

- `claude/search-ab/all` で NNUE エディション (`YANEURAOU_ENGINE_NNUE`) のクリーンビルドが
  通ることを確認済み → 全パッチはNNUE互換。
- ⚠ エディションを切り替えてビルドする際は `obj/` を削除すること (フラグ違いの
  オブジェクト混在でリンクエラーになる。`make clean` でも可)。
- MATERIAL評価・秒読み100msでの粗いサニティ対局 (各ブランチ vs base、30局) も実施した。
  結果は結論を出せる規模ではない (±100elo級の検出力) が、壊滅的退行 (ハング・クラッシュ・
  全敗) がないことの確認として `script/ab/sanity-results.md` に記録した。
  **本判定は必ずNNUE評価+1秒以上の秒読みでSPRTを回すこと。**

---

## 付録A: 精読で確認した主要な既存機構の所在

| 機構 | 場所 (yaneuraou-search.cpp) |
|---|---|
| correction_value / 補正eval | L999-1046, 使用 L3349, L3413, L3441, L5067 |
| 1手詰め (search/qsearch) | L3235-3297 / L5113-5147 |
| 宣言勝ち | L3305-3339 (search), pre_start L1206-1224 |
| Razoring | L3540-3541 |
| Futility (child) | L3562-3577 |
| NMP | L3585-3657 |
| IIR (+OLD_CODE) | L3674-3698 |
| ProbCut / small ProbCut | L3714-3780 / L3790-3793 |
| 浅い深さの枝刈り (Step14) | L3941-4055 |
| Singular延長ほか (Step15) | L4102-4214 |
| LMR (Step17) | L4309-4365 |
| statScore | L4279-4292 |
| update_all_stats ほか | L5660-5789 |
| followPV | L2706-2708 (計算), L3674, L3999 (使用) |
| 王手延長への言及 | L4207-4213 |

## 付録B: 参考 — 主要定数の現在値 (SPSA将来課題の対象)

- razoring: `alpha - 502 - 306*depth*depth`
- futilityMult: `76 - 21*!ttHit`, improving/opponentWorsening補正 `(2686*i + 362*ow)*mult/1024`
- NMP: 発動 `staticEval >= beta - 16*depth - 53*improving + 378`, `R = 7 + depth/3`, 検証 `depth >= 16`
- probCutBeta: `beta + 224 - 61*improving` / small: `beta + 416`
- moveCountPruning: `(3 + depth*depth) / (2 - improving)`
- 捕獲futility: `staticEval + 218 + 223*lmrDepth + PieceValue[捕獲駒] + 131*captHist/1024`
- quiet futility: `staticEval + 42 + 151*!bestMove + 120*lmrDepth + 86*(staticEval>alpha)`, lmrDepth<13
- 継続手枝刈り: `history < -4097*depth`, SEE枝刈り: `-25*lmrDepth*lmrDepth`
- singularBeta: `ttValue - (60 + 66*(ttPv&&!PvNode))*depth/55`, singularDepth: `newDepth/2`
- reduction(): `reductions[d]*reductions[mn] - delta*585/rootDelta + !i*scale*206/512 + 1133`,
  `reductions[i] = 2763/128 * log(i)`
- LMR補正: ttPv `+1013/-2819...`, cutNode `+3611+985*!ttMove`, ttCapture `+1054`,
  cutoffCnt `+251+1124+1042*allNode`, ttMove `-2239`, statScore `*428/4096`, allNode scale `273/(256d+260)`
- qsearch: futilityBase `staticEval + 328`, SEE打ち切り `-73`, moveCount `> 2`
- aspiration: `delta = 5 + threadIdx%8 + |msq|/9000`, 拡大 `delta += delta/3`
