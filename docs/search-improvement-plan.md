# やねうら王 探索部改善計画 (Search Improvement Ultraplan)

作成日: 2026-07-13 / 改訂: 2026-07-13 v2 (候補カタログを全面拡充、ブランチ命名を `test/ab-*` に統一、
効果測定はshogibenchで一括実施する方針に変更)

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
  - 10バイトTTエントリ (key16/depth8/move16/value16/eval16 + gen5/pv1/bound2)、
    置換スコア `depth8 - 8*relative_age`、save側の `+2*pv / -4` 緩衝 (最新SF相当)
  - 時間管理: fallingEval / timeReduction / bestMoveInstability / nodesEffort (highBestMoveEffort)
- したがって「古いSFとの差分を取り込む」型の改善余地はほぼ枯れており、残る改善余地は主に:
  1. **チェス用定数・チェス用ロジックの将棋への適応不足** (捕獲価値、王手の扱い、進行度等)
  2. **やねうらお氏自身がコード中コメントで「要検証」と残している箇所** (🤔/TODO/OLD_CODE/#if 0)
  3. **V9.60 で入った未検証の独自実験** (followPV ゲーティング、per-thread continuationHistory)
  4. 将棋固有の指し手性質 (駒打ち・王手の多さ・持ち駒) を突いた独自ヒューリスティック
  5. チェスのSPSA値のまま持ち込まれている定数群の将棋向け再調整 (→ §3.4)

### 1.2 fork独自機能と探索部の接点 (改変時の保全ポイント)

このforkには OpeningTarget / 進行度SFNN(LS_PROGRESS) / Tatara NNUEヘッダ対応が入っている。
探索部を変更する際に**壊してはならない**接点は次の3系統:

| 接点 | 場所 | 内容 |
|---|---|---|
| TTソルト | search() L2953-2956, qsearch() L4993-4996 | `posKey ^= opening_target_tt_salt(...)` を probe/write 両方に適用 |
| 評価値ペナルティ | search() L3408/L3436, qsearch() L5088/L5153 | `apply_opening_target_penalty()` が staticEval 代入を包む |
| スタック伝播 | iterative_deepening L1788, do_move L2419, NMP L3615 | `ss->openingTargetReached/Hidden` を (ss+1) へ伝播 |

本計画の各パッチはいずれもこれらの行を変更しない。

### 1.3 ビルド・検証手段

- ビルド: `cd source && make -j4 tournament YANEURAOU_EDITION=YANEURAOU_ENGINE_NNUE TARGET_CPU=AVX2 COMPILER=clang++`
  (スモークには `YANEURAOU_ENGINE_MATERIAL` + `COMPILER=g++` が評価ファイル不要で手軽)
- ⚠ **エディションを切り替えるときは `obj/` を削除する** (`make clean`)。フラグ違いの
  オブジェクトが混在するとリンクエラーになる。
- 動作確認: `bench [TT_MB] [threads] [limit] default [depth|nodes|movetime]` / `unittest`
- 対局測定: **shogibenchで一括実施** (→ §4)。補助として本計画で追加した
  `script/ab/ab_match.py` (SPRT付きUSI対局ハーネス) も使える。

---

## 2. 実装済み A/Bテストブランチ (test/ab-01 〜 test/ab-12, test/ab-all)

ブランチはすべてベースブランチ `claude/yaneuraou-search-optimization-qxvzz0`
(= master + 本ドキュメント + A/Bテスト基盤。**エンジンコードはmasterと同一**) から分岐。
**エンジンコードの差分が「その改善1つだけ」**になるよう構成している。対照群 (engine1) には
ベースブランチのビルドを使う。

差分の確認: `git diff claude/yaneuraou-search-optimization-qxvzz0 test/ab-01-capture-futility -- source/`

#### AB-01 `test/ab-01-capture-futility` — 捕獲futilityに将棋の交換値(盤上+手駒+成り)を使用

- **場所**: search() Step 14 (捕獲手のfutility)、qsearch() Step 6 (futility)
- **現状**: `PieceValue[捕獲される駒]` (盤上の駒価値のみ) を加算している。
- **問題**: 将棋の捕獲は「相手の盤上駒が消える + 自分の手駒が増える」ので実質の評価値変動は
  約2倍 (`CapturePieceValue = PieceValue[pc] + PieceValue[raw(pc)]`)。さらに成りを伴う指し手は
  成り差分 (`ProDiffPieceValue`) も上乗せされる。現状は捕獲による上昇分を大幅に過小評価しており、
  **有望な捕獲手・歩成りが futility で刈られすぎる**。歩の成り(非捕獲)は現状加算0点扱い。
- **変更**: 両箇所を `Eval::CapturePieceValuePlusPromote(pos, move)` に置換。
- **根拠**: やねうらお氏自身のコメント (search L3966-3971「CapturePieceValuePlusPromote()のほうが
  より正確な評価ではないか？」、qsearch L5298-5302 計測資料14)。
- **リスク**: 枝刈り減少によるNPS低下とのトレードオフ。

#### AB-02 `test/ab-02-check-extension` — 王手延長の復活 (限定条件)

- **場所**: search() Step 15 (singular延長チェーンのelse-if)
- **変更**: `else if (givesCheck && depth > 9 && pos.see_ge(move, 0)) extension = 1;`
  SEE≥0 で「駒を捨てない王手」に限定し、将棋特有の王手ラッシュによる爆発を防ぐ。
- **根拠**: 作者コメント (L4207-4213)「王手延長自体は何らかあった方が良い可能性はあるので
  条件を調整してはどうか」。将棋は王手絡みの読み抜けが勝敗に直結しやすい。
- **リスク**: 延長による探索肥大 (スモークでも木が約2.9倍)。負けたら depth>12 やPvNode限定を再試行。

#### AB-03 `test/ab-03-iir-old-style` — IIR(内部反復リダクション)を旧方式へ

- **場所**: search() Step 10
- **変更**: `#if OLD_CODE` として残されていた旧方式 (PvNode&&!ttMoveで-3 /
  cutNode&&depth>=7で-1-!ttMove) を有効化し、現行方式を削除。
- **根拠**: 作者コメント (L3677-3678)「🌈 以前のコードのほうが強い可能性がある」。
- **リスク**: PvNodeでの-3は大きい。旧SFで長年実績のある形ではある。

#### AB-04 `test/ab-04-no-followpv` — followPVゲーティングの除去 (純SF挙動)

- **場所**: search() Step 10 (IIR) と Step 14 (quiet枝刈りブロック)
- **変更**: V9.60独自の `ss->followPV` (前回iterationのPVを辿るnodeでIIRとquiet枝刈りを抑制)
  を両条件から外す。followPV の計算自体は残す(最小差分)。
- **根拠**: 公開された計測根拠が見当たらない実験的機構。探索効率とのトレードオフを検証。

#### AB-05 `test/ab-05-nmp-eval-r` — null move探索のRにeval-beta項を追加

- **場所**: search() Step 9
- **変更**: `R = 7 + depth/3` → `R = min((eval-beta)/232, 6) + depth/3 + 5`。
  あわせて発動条件に `eval >= beta` を追加 (SF17と同形。これがないと eval < beta のとき
  Rが負になり、null move探索が親より深くなる病的ケースが生じる)。
- **根拠**: 将棋は評価値スイングが大きく、eval≫betaでは粗い検証で安全という仮説 (SF16〜17.1の形)。

#### AB-06 `test/ab-06-drop-lmr` — 王手にならない駒打ちのreduction増加 (将棋固有・独自案)

- **場所**: search() Step 16-17 のreduction計算
- **変更**: `if (move.is_drop() && !givesCheck) r += 768;` (≈0.75手分)
- **根拠**: 将棋の合法手数(平均~100手、最大593手)の主因は駒打ちで、大半は有望でない。
  historyの学習を待たず構造的事前確率として薄く読む。王手になる駒打ち(詰み絡み)は除外。
- **リスク**: 中合い・拠点打ちの発見遅れ。負けたら逆符号(r -= X)も検討価値あり。

#### AB-07 `test/ab-07-statscore-conthist` — statScoreに4手前・6手前の継続手履歴を追加

- **場所**: search() Step 16 (quiet手のstatScore)
- **変更**: `+ contHist[3]/2 + contHist[5]/2` を追加。
- **根拠**: 作者コメント (L4283-4284)「contHist[5]も/2とかで入れたほうが良いのでは…。誤差か…？」
  + 計測資料11。MovePickerは既にcontHist[0..3],[5]を使っており整合も取れる。

#### AB-08 `test/ab-08-aspiration-delta` — aspiration windowの初期幅を将棋向けに拡大

- **場所**: iterative_deepening() のaspiration初期化
- **変更**: `delta = 5 + ...` → `delta = 9 + ...`
- **根拠**: コード内解説 (L1977)「💡 将棋ではStockfishより少し高めが良さそう」。
  fail high/low再探索コストとのトレードオフ。単スレッドで判定しやすい(threadIdx項が0)。

#### AB-09 `test/ab-09-gameply-futility` — futilityマージンを進行度(手数)でスケール (将棋固有)

- **場所**: search() Step 8 の futility_margin
- **変更**: `futilityMult += futilityMult * min(game_ply(), 200) / 400;` (序盤1.0倍→200手で1.5倍)
- **根拠**: 作者コメント (L3555-3556)「将棋の終盤では評価値の変動の幅は大きくなっていくので、
  進行度に応じたfutility_marginが必要となる。ここでは進行度としてgamePly()を用いる。
  このへんはあとで調整すべき」の実装。勝った場合はNNUE進行度モデル版(§3.2 S-06)へ発展。

#### AB-10 `test/ab-10-mate1ply-depth` — 通常探索の1手詰め判定に depth >= 3 を追加

- **場所**: search() の mate_1ply 呼び出し (Step 5 相当)
- **変更**: `!rootNode && !ttHit && depth >= 3 && !excludedMove` に限定。
- **根拠**: 作者コメント「depthの残りがある程度ないと、1手詰めはどうせこのあとすぐに
  見つけてしまうわけで見返りが少ない」。qsearch側の1手詰めは残るため水平線検出は保たれる。
  NPS向上狙い (スモークで+3〜6%)。

#### AB-11 `test/ab-11-goodquiet-threshold` — MovePickerのgood quiet閾値を-14000→-8000

- **場所**: movepick.cpp `goodQuietThreshold`
- **変更**: historyの悪いquietをより多くBAD_QUIET送りにし、損なcaptureを先に試す度合いを強める。
- **根拠**: 現行-14000に計測根拠コメントがなく、SF水準(≒-8000)との比較。将棋はハズレquietが
  多いためオーダリング後半の並びが効きやすい仮説。

#### AB-12 `test/ab-12-capture-statscore` — 捕獲手のstatScoreに交換値を使用

- **場所**: search() Step 16 (捕獲手のstatScore)
- **変更**: `863*PieceValue[captured]/128` → `863*CapturePieceValue[captured]/128`。
- **根拠**: AB-01のreduction側の対。大駒・成駒を取る手のreductionをより強く抑えて深く読ませる。

#### AB-ALL `test/ab-all` — 全部乗せ (相互作用確認用)

AB-01〜12をすべて適用。AB-03とAB-04はIIR部分が競合するため
「旧方式IIR(followPVゲートなし)」として解決してある。NNUEエディションのクリーンビルド確認済み。

---

## 3. 改善候補カタログ (徹底洗い出し・未実装分)

コード中の全マーカー (🤔 / TODO / #if 0 / OLD_CODE / 計測資料) の全数調査と、
補助ファイル (yaneuraou-search.h / tt.cpp / timeman.cpp / thread.cpp / movepick.h / mate/ /
evalhash.h / tune.h) の精査、およびSF系・将棋固有の一般アイデアから列挙する。

優先度: ★★★=次ラウンドでブランチ化推奨 / ★★=有望だが実装コストや前提あり / ★=検証価値はある

### 3.1 作者マーカー由来 (コード内の未決着事項)

| ID | 内容 | 場所 | 補足 | 優先度 |
|---|---|---|---|---|
| C-01 | mate_1plyの`!excludedMove`条件の除去 | search L3236 TODO「この条件必要なのか？」 | 1行の検証。excludedMove時はttHit済みのはずで実質不変の可能性 | ★★ |
| C-02 | 宣言勝ち判定の呼び出し条件を`!PvNode`基準に | L3215「!rootnodeではなく!PvNodeの方がいいかも？」 | 宣言勝ち可能局面は稀で影響小 | ★ |
| C-03 | qsearch深部の置換表手循環対策 (`depth <= -16`で引き分け扱い) | qsearch L4972 #if 0 | 稀な探索遅延の保険。qsearchにdepth引数を戻す必要あり | ★ |
| C-04 | 1手詰め・宣言勝ちが無い場合のTT save | L3338 🤔 | 現状はStep 6の`ttWriter.write(BOUND_NONE)`が実質担っており優先度低 | ★ |
| C-05 | captureHistoryのmalus表引きを`moved_piece_before()`に | update_all_stats L5725 🤔 | MovePickerの表引き(moved_piece_after)との整合ごと変える必要 | ★ |
| C-06 | value_draw()のゆらぎ(±1)の将棋向け再設計 | L1052-1060 TODO | 千日手盲点対策。優等/劣等局面・連続王手と絡む | ★ |
| C-07 | 詰み読み切り時の早期iteration打ち切り係数 (2.5倍) | L2207-2227 (独自コード) | `(VALUE_MATE-v+2)*5/2 < rootDepth` の係数検証 | ★ |
| C-08 | per-thread continuationHistory[2][2]の見直し | yaneuraou-search.h L490-493「レーティングがほぼ上がっていない。悪い改造のような気がする」 | スレッド共有化(SharedHistoriesへの移動)を再検証 | ★★ |
| C-09 | PvNodeでのLazy Evaluate二重evaluate()の原因調査 | L3383-3399「これ書かないとR70ぐらい弱くなる」「原因がよくわからない」 | evaluate_with_no_return()とevaluate()の挙動差の調査。解明できればNPS/整合性の改善余地大 | ★★★ (調査) |
| C-10 | ponder_candidate機構の効果検証 | yaneuraou-search.h L267-269 (独自) | 「Stockfish本家もこうするべき」— ponder的中率の計測 | ★ |
| C-11 | Stochastic Ponder時のスコア反転の正当性検証 | L1794-1804 | 手番が変わる場合のbestPreviousScore反転。timemanとの相互作用 | ★ |
| C-12 | 王手ラッシュ抑制のqsearch SEE閾値 (-73) | qsearch L5349-5357 🤔「歩損する指し手は延長しないほうがいいか？」 | SPSA枠 (§3.4) | ★★ |
| C-13 | qsearch futilityのPROMOTION除外条件 | L5283-5288 (SF側条件を意図的に外している) 計測済みだが再検証余地 | AB-01が勝った場合は再計測 | ★ |

### 3.2 将棋固有の適応候補 (未実装)

| ID | 内容 | 概要・根拠 | コスト | 優先度 |
|---|---|---|---|---|
| S-01 | **see_ge()の交換値スケール化** | SEE自体を`CapturePieceValue`基準にする。現在のSEEは盤上値のみで交換の実質変動を半分に見積もる。探索中の全SEE閾値 (-25*lmrDepth², 167*depth+captHist, -73, GOOD_CAPTUREの`-value/18`, ProbCut閾値) の再調整が必須で、SPSAとセットの大工事。AB-01/12が勝ったら本丸として着手 | 大 | ★★★ (条件付き) |
| S-02 | **3手詰め判定 (mate_odd_ply) のfrontier適用** | `Mate::MateSolver::mate_odd_ply()` (mate.h L177) は探索から未使用。depth<=2 && !ttHit 等の限定で呼ぶ。過去の計測では微妙だったが、correction history時代+NNUEで再検証価値 | 中 | ★★ |
| S-03 | **df-pn詰将棋ソルバの常駐並列化** | `Mate::Dfpn::MateDfpnSolver` (mate.h L256) を専用スレッドでroot局面(自玉/敵玉)に常時適用し、詰み発見でrootMovesへ注入。実戦ソフトで実績のある構成。alloc等の準備・停止同期の実装が必要 | 大 | ★★ |
| S-04 | **evasion(王手回避)オーダリングの強化** | 現状: capture=MVV+下駄、quiet=main+contHist[0]のみ (movepick score<EVASIONS>)。玉の退路確保・合駒の種類・pawnHistory等の追加次元を検証 | 中 | ★★ |
| S-05 | **駒打ち専用history次元** | 打ち駒はfrom情報がなくPieceTo系頼み。「持ち駒種×to×直前手」の専用テーブルでオーダリング改善。メモリとのトレードオフ | 中 | ★ |
| S-06 | **NNUE進行度モデルでの枝刈りスケール** | AB-09 (game_ply線形) が勝ったら、fork資産の `Tanuki::Progress` (本物の進行度) でfutility/razoring/NMPマージンをスケール。EVAL_NNUE限定 | 中 | ★★ (AB-09の結果待ち) |
| S-07 | **入玉模様の検出と探索調整** | 両玉の段・宣言点数を軽量特徴量にして、入玉形でNMP抑制・futility拡大・宣言勝ち距離のボーナス付与。入玉将棋は現代ソフト共通の弱点 | 中〜大 | ★★ |
| S-08 | **王手延長のバリエーション** | AB-02の結果を受けて: depth閾値違い / SEE条件なし / PvNode限定 / 連続王手回数でキャップ等 | 小 | ★★ (AB-02の結果待ち) |
| S-09 | 残り手数(MaxMovesToDraw)を考慮した終局間際の枝刈り | 256手ルール間際で「引き分けまでの距離」によるmate-distance-pruning類似の刈り | 小 | ★ |
| S-10 | 歩の成り(非捕獲)のqsearch生成範囲 | 現在CAPTURES_PRO_PLUSは歩成りを含む。香桂銀の成り等の追加生成の再検証 (過去計測あり: 計測資料も参照) | 小 | ★ |

### 3.3 Stockfish系・一般探索アイデア (未実装)

| ID | 内容 | 概要 | 優先度 |
|---|---|---|---|
| F-01 | threat-based quiet ordering | 「安い駒に当たられている駒を逃がす/当たりに行く手」の加点。2022年に作者が簡易版(歩の利きのみ)を計測しNG (movepick L297-308)。差分利き(LONG_EFFECT_LIBRARY)常設化とセットなら再挑戦の価値 | ★ |
| F-02 | optimism (楽観値) のNNUE移植 | `optimism[]`フィールドは存在するが未使用 (L1987 #if 0)。評価関数の学習/出力形式と絡むため評価関数側課題とセット | ★ |
| F-03 | Lazy SMPの多様化 | helper threadの先行depth (L1865-1877で作者が言及)、aspiration deltaのthreadIdx項調整、per-thread reduction揺らぎ。**マルチスレッド対局でのみ測定可能** | ★★ |
| F-04 | TT置換ポリシーの定数 | save側の`+2*pv`/`-4`、aging×8、GENERATION_BITS=5 (32世代で一周)。SPSA枠 | ★ |
| F-05 | TT_CLUSTER_SIZEの変更 (3⇔4) | やねうら王はクラスタサイズ可変対応済み (tt.cpp)。メモリ効率とヒット率のトレードオフ | ★ |
| F-06 | partial_insertion_sortの高速化 | 作者注記「全体時間の6.5〜7.5%を消費」(movepick L89-90)。ブロック化・上位k選択・SIMD化。純速度パッチとしてNPSで検証可能 | ★★ |
| F-07 | BAD_QUIETスキップの高速化 | 作者注記「AVXを使って一気に削除しておいたほうが良いのでは」(movepick L613) | ★ |
| F-08 | EVAL_HASH (評価値memo化) の有効化検証 | `USE_EVAL_HASH`は全ビルドで未定義 (プラミングはNNUE/KPPT系に現存)。NNUE差分計算下では効果限定的見込みだが計測は容易 | ★ |
| F-09 | aspiration fail-high時のdepth低下 (failedHighCnt) の調整 | `adjustedDepth = max(1, rootDepth - failedHighCnt - 3*(searchAgainCounter+1)/4)` の係数検証 | ★ |
| F-10 | 二重初期化のクリーンアップ | TT resize時の二重init (tt.cpp L309)、ThreadPool::set()の二重clear (thread.cpp L335-340)。棋力無関係の起動時間改善 | ★ |
| F-11 | qsearchでの王手生成の復活 (DEPTH_QS_CHECKS) | 手駒のある将棋では爆発リスクが高い(ファイル冒頭の設計コメント)。mate_1plyが1手詰めを拾う現構成が妥当。**非推奨のまま記録** | - |
| F-12 | upcoming_repetition | 作者計測で効果なしと明記 (L2601)。**記録のみ** | - |
| F-13 | rule50系 graph history interaction対策 | 作者計測でR10悪化 (L3099)。**記録のみ** | - |

### 3.4 SPSA一括調整の対象リスト (TUNE()化 → shogibench/tune.py)

`Tune::init()`のフック (`%%TUNE_*%%`マーカーとtune.h/tune.cpp) は組込み済みで、
**`TUNE(SetRange(a,b), var)` と書くだけで USIオプション化 + tune.py用の定義行出力**が行われる。
現状、探索定数は一切TUNE()されていない。以下は効果順の候補グループ:

1. **correction history合成重み** — `12153*pcv + 8620*micv + 12355*(wnpcv+bnpcv) + 7982*cntcv`、
   `/131072`、update側の `nonPawnWeight=187`, `153/128`, `126/128`, `63/128`、bonus `12/17/128` 系。
   **チェスのSPSA値がそのまま**入っており、将棋(持ち駒あり・歩の陣形の意味が異なる)での
   再調整期待値が最も大きい。
2. **reduction系** — `reductions[i]=2763/128*log(i)`、`reduction()`の 585 / 206/512 / 1133、
   LMR補正群 (ttPv 1013/2819/973/905/935/959、cutNode 3611/985、ttCapture 1054、
   cutoffCnt 251/1124/1042、ttMove 2239、statScore 428/4096、allNode 273/(256d+260))
3. **枝刈りマージン** — razoring 502+306d²、futilityMult 76/21、improving 2686 / opponentWorsening 362、
   quiet futility 42/151/120/86 (lmrDepth<13)、conthist枝刈り -4097d、SEE刈り -25·lmrDepth²、
   capture futility 218/223/131、SEEマージン 167d+34/1024
4. **NMP** — 16d / 53improving / 378、R=7+d/3 (or AB-05形の 232/6/5)、検証深さ16
5. **singular** — 60/66/55、doubleMargin -4/212/182/906/116517/44、tripleMargin 73/320/218/92/45、
   depth条件 6+ttPv、ttData.depth >= depth-3
6. **qsearch** — futilityBase +328、SEE -73、moveCount >2、TT置換 depth条件
7. **史料更新系** — bonus `min(128d-77,1529)+353`、malus `min(882d-204,2122)`、
   quiet/capture配分 806/1113/977/1286/1559、conthist_bonuses {1157,648,288,576,140,441}+88、
   fail-low bonusScale群 (-232/108/59/454/169/145/154/135/80/1400/221/235/290)、
   eval差分bonus (evalDiff clamp -214/171/+60, ×10/×12)
8. **history初期値** — mainHistoryDefault=0、captureHistory -678、pawnHistory -1238、
   conthist -523、contCorrHist 6、lowPlyHistory 98 (L2463 TODO「あとで調整する」)
9. **その他** — aspiration delta 5(9)/9000/threadIdx%8、delta拡大 /3、
   get_best_thread の +14、TT保存の depth+6 (1手詰め/宣言勝ち)、時間管理係数群
   (timeman: SlowMover系は「探索パラメーターとして調整すべき」と作者注記 L243)

推奨手順: グループ1→3→2の順に、shogibench/SPSA (秒読み1秒以上、数万局規模) で回す。
本ラウンドのA/B勝者を先にmasterへ統合してから行うこと。

### 3.5 検討して見送り (理由付き)

| 候補 | 見送り理由 |
|---|---|
| SEE自体の交換値化の即時実施 | 全SEE閾値の再調整が必要 (→S-01として条件付き採用) |
| upcoming_repetition | 作者計測済み・効果なし (L2601) |
| threat-based ordering即時実施 | 作者計測済みNG。利き計算コスト (→F-01) |
| qsearch王手生成 | 爆発リスク (→F-11) |
| rule50系TT対策 | 作者計測でR10悪化 (L3099) |
| 時間管理の構造変更 | fork独自のProgressSlowMover/秒切り上げと絡み退行リスク大。定数はSPSA枠 |
| Skill Level / UCI_Elo | 棋力に無関係 |
| aspirationのthreadIdx%8項の除去 | 単スレ測定に影響なし。マルチスレ検証はF-03へ |

---

## 4. shogibenchでの一括テスト設定

**効果測定はshogibenchで一括実施する** (本リポジトリでの対局測定は未実施。
ビルド・bench・unittestのスモークのみ実施済み → §5)。

### 4.1 テスト対象 (13本 + 対照群)

| # | ブランチ (engine2/test側) | 対照群 (engine1/base側) | 補足 |
|---|---|---|---|
| 1〜12 | `test/ab-01-capture-futility` 〜 `test/ab-12-capture-statscore` | `claude/yaneuraou-search-optimization-qxvzz0` (エンジンコードはmaster同一) | 1本ずつ独立にSPRT |
| 13 | `test/ab-all` | 同上 | 参考値 (相互作用確認) |

対照群はmasterのビルドでも等価 (ベースブランチのエンジンコードはmasterと同一)。

### 4.2 ビルド設定 (全ブランチ共通)

```
cd source && make -j$(nproc) tournament \
    YANEURAOU_EDITION=YANEURAOU_ENGINE_NNUE TARGET_CPU=AVX2 COMPILER=clang++
```
- エディション/ARCHは実測環境に合わせて統一 (対照群と同一コンパイラ・同一フラグであること)
- ブランチ切替時は `make clean` (obj混在防止)
- 一括ビルド補助: `script/ab/build_branches.sh -e YANEURAOU_ENGINE_NNUE -a AVX2 \
  claude/yaneuraou-search-optimization-qxvzz0 'test/ab-*'`
- ブランチ一覧の機械可読版: `script/ab/shogibench-branches.yml`

### 4.3 対局条件 (推奨)

| 項目 | 設定 | 理由 |
|---|---|---|
| 評価関数 | **両者で完全に同一**のNNUE評価 | 探索部のみの差を測る |
| Threads | 1 | 分散低減。SMP相互作用はF-03で別途 |
| USI_Hash | 256 (MB) | 秒読み1秒なら十分。TCを伸ばすなら増やす |
| 持ち時間 | 秒読み1000ms (`byoyomi 1000`) を基本。**採用判定前にLTC (例: 持時間5分+秒読み or 15分切れ負け) で追試** | 短TCはNPS差を誇張しがち。(*Scaler)注記のある変更 (AB-03/04/09等) は特にLTC必須 |
| 開始局面 | 互角局面集からランダム、**同一局面で先後入替のペア対局** | 同梱 `script/ab/openings.sfen` は駒得エンジン生成の暫定版。たややん互角局面集等の実績あるものを推奨 |
| 引き分け | 320手 (`MaxMovesToDraw=320` を両エンジンに設定) + 千日手 | |
| 投了 | 評価値±3000が3手連続 (ハーネス側裁定) | 対局高速化 |
| 固定ノード対局 | **使わない** | AB-01/02/09/10等はNPSと枝刈り量が変わるため時間制御でしか正しく測れない |

### 4.4 エンジンオプション (両者共通で設定)

```
setoption name Threads value 1
setoption name USI_Hash value 256
setoption name USI_Ponder value false
setoption name NetworkDelay value 0
setoption name NetworkDelay2 value 0
setoption name MinimumThinkingTime value 0
setoption name MaxMovesToDraw value 320
setoption name USI_OwnBook value false
setoption name BookFile value no_book
setoption name EvalDir value <共通のNNUE評価フォルダ>
```
このforkの本番構成 (進行度SFNN) で測る場合は追加で両者に:
```
setoption name LS_PROGRESS_COEFF value <progress.binのパス>
setoption name FV_SCALE value 28
```
(AGENTS.md の注意どおり、`isready` 前に EvalDir / LS_PROGRESS_COEFF を設定すること)

### 4.5 SPRT設定と判定基準

- 標準: **elo0 = 0, elo1 = 5, α = β = 0.05** (LLR境界 ±2.94)
- 効果が小さい想定のもの (AB-07/11/12): elo0 = 0, elo1 = 3
- 簡素化系 (AB-04: 機構の削除): elo0 = -3, elo1 = 1 (「悪化していないなら採用」型)
- 判定:
  - **H1受理** → LTCで追試 → 再度H1なら masterへ cherry-pick 統合
  - **H0受理** → 不採用 (ブランチは知見として残す)
  - 打ち切り → 実質差なし。簡素化を伴うなら採用可、複雑化なら不採用
- 複数採用時は「統合後master vs 統合前master」で最終確認 (test/ab-all の結果が参考)
- テスト優先順位 (根拠の強さ順):
  **AB-01 → AB-03 → AB-04 → AB-09 → AB-02 → AB-05 → AB-10 → AB-11 → AB-08 → AB-12 → AB-06 → AB-07**

### 4.6 補助ツール (shogibenchが使えない環境向け)

`script/ab/ab_match.py` — SPRT判定付きUSI対局ハーネス (先後入替ペア対局・並列・
投了/宣言勝ち/最大手数裁定。`pip install cshogi` で千日手/連続王手千日手/詰みの厳密判定)。
使い方は `script/ab/README.md`。互角局面の自作は `script/ab/make_openings.py`。

---

## 5. ビルド・スモーク検証結果 (2026-07-13実施)

環境: このリポジトリのコンテナ (4コア, g++ 13.3, AVX2)。
bench は `bench 16 1 13 default depth` (固定depth13・シングルスレッドなのでノード数は決定的)。
エディションは MATERIAL (評価ファイル不要のため)。NPSは共有VMのため±10%程度の揺れあり。

**ノード数は「探索木の形が意図した方向に変わったか」の確認用**であり、増減の善し悪しは
対局テストでしか判定できない。

| ブランチ | ビルド | depth13 nodes | NPS | 傾向の解釈 |
|---|---|---|---|---|
| base | ✅ (+unittest 84/84) | 2,675,037 | ~800k | 基準 (再ビルドでノード数完全一致を確認済み) |
| test/ab-01-capture-futility | ✅ | 1,009,597 | ~796k | futility見積り精緻化で木が大きく変形 (MATERIAL評価では捕獲価値=評価値変動そのものなので効果が誇張される) |
| test/ab-02-check-extension | ✅ | 7,809,834 | ~759k | 王手延長で木が拡大 (bench局面は王手の多い終盤なので誇張あり) |
| test/ab-03-iir-old-style | ✅ | 2,205,896 | ~800k | IIR強化で木が縮小 |
| test/ab-04-no-followpv | ✅ | 2,015,457 | ~763k | PV上の枝刈り解禁で木が縮小 |
| test/ab-05-nmp-eval-r | ✅ | 3,634,627 | ~759k | eval≈betaでのnull move検証が丁寧になり木が拡大 (eval>=betaガード込み) |
| test/ab-06-drop-lmr | ✅ | 1,267,977 | ~966k | 駒打ちreductionで木が縮小・NPS向上 |
| test/ab-07-statscore-conthist | ✅ | 2,814,843 | ~844k | 微増 (小さな変更) |
| test/ab-08-aspiration-delta | ✅ | 2,408,994 | ~793k | 再探索減で微減 |
| test/ab-09-gameply-futility | ✅ | 4,065,174 | ~811k | 終盤マージン拡大で刈り減 (bench局面は終盤寄り) |
| test/ab-10-mate1ply-depth | ✅ | 2,686,269 | ~820k | 木はほぼ不変で呼び出し削減ぶんNPS向上 (想定どおり) |
| test/ab-11-goodquiet-threshold | ✅ | 1,267,069 | ~863k | オーダリング変更で木が大きく変形 |
| test/ab-12-capture-statscore | ✅ | 1,346,385 | ~838k | 捕獲のreduction減で木が変形 |
| test/ab-all (全部乗せ) | ✅ MATERIAL + **NNUEクリーンビルドも成功** | 3,092,043 | ~777k | 12パッチの合成 |

- `test/ab-all` で NNUEエディションのクリーンビルドが通ることを確認済み → 全パッチはNNUE互換。
- ⚠ エディション切替時は `obj/` を削除 (`make clean`) しないとリンクエラーになる。
- 対局による効果測定は**未実施** — shogibenchで一括実施 (§4)。

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
| reduction() / reductions[] | L5515-5518 / L2490-2491 |
| TT置換ポリシー | tt.cpp L156-157 (save), L439-442 (probe) |
| 詰みルーチン群 | mate/mate.h L26 (mate_1ply), L177 (mate_odd_ply), L256 (df-pn) |
| TUNEフレームワーク | tune.h L290-294, 初期化 search L501-502 |

## 付録B: 主要定数の現在値 → §3.4 に統合した (SPSA対象リスト参照)
