# V9.30相当探索と現行master探索の差分

調査日: 2026-07-17

## 1. 比較対象

| 対象 | commit | 内容 |
|---|---|---|
| upstream V9.30探索 | [`80f66ac`](https://github.com/yaneurao/YaneuraOu/commit/80f66acdc47bf77fb111470b4ceb0c737414133b) | 2026-04-30。「LMR以外、Stockfish最新にほぼ追いついた」時点 |
| このforkの`search-v9.30` | `996c4796` | [`3788b4ac`](https://github.com/keinoda/YaneuraOu/commit/3788b4ac5df5069dadd66ab6582aade626da701f)で探索部をV9.30相当にし、fork機能を維持 |
| このforkの現行`master` | `9a349509` | V9.60git系 + fork独自機能 + danbo-v16向けSPSA |
| upstream調査時点最新 | [`98455708`](https://github.com/yaneurao/YaneuraOu/commit/98455708e115affb3a81848c400b3f628b85252c) | 2026-07-16 |

`search-v9.30`はエンジン全体をV9.30へ戻したブランチではない。主に
`yaneuraou-search.cpp/.h`をV9.30相当にした比較用ブランチであり、
`ENGINE_VERSION`の表示は`9.60git`のままである。

また、現行masterはupstream V9.60そのものではない。特に
[`5e5f0b53`](https://github.com/keinoda/YaneuraOu/commit/5e5f0b53becffff96fdf8e11afe9c9c12e23c8ed)
でdanbo-v16向けSPSA結果を探索定数へ広く焼き込み、`f16f3cb6`で
ponder時間制御などとともに正本へ統合している。したがって、以下では
「upstreamでV9.30後に入った変更」と「このforkで追加された変更」を分ける。

## 2. 結論

1. **V9.30からV9.60で探索方式が全面的に変わったわけではない。**
   `followPV`、correction history、per-thread continuation history、
   prior reduction、cutoff count、LMR後の深さ再調整など、主要な構造は
   `search-v9.30`にも存在する。
2. 通常対局へ最も広く効く実差分は、現行masterへ焼き込まれた
   **danbo-v16向けSPSAの多数の数値**である。枝刈り、LMR、NMP、
   singular extension、history、qsearchを同時に変えている。
3. upstreamでV9.30後に恒久的に残った通常探索の主変更は、
   `dc943f89`のStockfish追随LMR定数更新である。ただし現行masterでは、
   その後さらにdanbo-v16向けSPSA値へ置き換わっている。
4. **現行masterにはNMP rollback時の未初期化不整合がある。**
   これはソースから確定できる正しさの問題であり、V9.60系の弱体化候補として
   数値差より先に切り分ける価値が高い。
5. 「V9.60の方が弱い」という評判自体は、同一fork基盤・同一評価関数での
   対局結果がまだないため未確認である。現行masterだけがdanbo-v16に合わせて
   SPSAされているので、固定値SPRTだけでも、再SPSAだけでも結論は出せない。

## 3. 通常探索の構造差

| 項目 | V9.30相当 | 現行master | 判断 |
|---|---|---|---|
| `followPV`によるIIR/quiet pruning抑制 | あり | あり | V9.60で生じた差ではない |
| correction history一式 | あり | あり | 構造は共通、合成・更新係数が大きく異なる |
| per-thread `continuationHistory[2][2]` | あり | あり | V9.60で生じた差ではない |
| `priorReduction`、`cutoffCnt`、`allNode` | あり | あり | 構造は共通、閾値・係数が異なる |
| `doDeeperSearch` / `doShallowerSearch` | `+48` / `+9` | 同じ | 差ではない |
| NMP dynamic reduction | `7 + depth / 3` | 同じ | #4+#5ブランチだけが`depth / 2`へ変更 |
| NMP verification search | あり | あり | upstreamで一度削除後、V9.30相当へrollback |
| 駒取り手の二重・三重singular extension | 許可 | 許可 | #66の変更は現行masterには未導入 |
| qsearchのTT読み取り | あり | 通常探索ではあり | `ReadTT=false`は`qsearch_psv`専用で対局に影響しない |
| Stockfish用`#if STOCKFISH` | 参照コード | 参照コード | やねうら王ビルドでは選ばれない |

以前の`docs/search-improvement-plan.md`は`followPV`とper-thread
continuation historyを「V9.60で入った変更」と分類していたが、今回の
`search-v9.30`実コード照合では両方ともV9.30相当に存在した。この2点は
V9.30→V9.60弱体化の説明には使えない。

## 4. danbo-v16向けSPSAによる主な数値差

下表は全差分ではなく、探索木へ広く影響する代表値である。

| 系統 | `search-v9.30` | 現行master |
|---|---|---|
| aspiration初期幅 | `5 + ... / 9000` | `23 + ... / 6792` |
| reductions表 | `2809 / 128 * log(i)` | `2760 / 128 * log(i)` |
| correction合成 | `12153, 8620, 12355, 7982` | `7494, 7423, 10975, 14031` |
| razoring | `alpha - 502 - 306*d*d` | `alpha - 368 - 275*d*d` |
| child futility倍率 | `76 - 21*!ttHit` | `46 - 24*!ttHit` |
| NMP発動margin | `beta - 16*d - 53*improving + 378` | `beta - 22*d - 53*improving + 278` |
| ProbCut | `beta + 224 - 61*improving` | `beta + 128 - 79*improving` |
| capture futility | `218 + 223*lmrDepth + 131*hist/1024` | `383 + 405*lmrDepth + 145*hist/1024` |
| quiet futilityのLMR項 | `120*lmrDepth` | `60*lmrDepth` |
| quiet SEE pruning | `-25*lmrDepth^2` | `-41*lmrDepth^2` |
| singular beta | `(60 + 66*flag)*depth/55` | `(73 + 117*flag)*depth/33` |
| LMR `ttPv`加算 | `946` | `469` |
| LMR moveCount係数 | `66` | `13` |
| LMR `cutNode`加算 | `3094 + 1056*!ttMove` | `2279 + 1510*!ttMove` |
| LMR後の追加深さ閾値 | `3212`, `4784` | `2529`, `3700` |
| qsearch futility base | `staticEval + 328` | `staticEval + 79` |
| quiet成功時bonus | `min(128*d-77,1529)+353*tt` | `min(196*d-44,1529)+550*tt` |
| quiet失敗時malus | `min(882*d-204,2122)` | `min(481*d-205,2122)` |

各値は独立ではなく、historyの分布、LMRの深さ、枝刈り率を介して強く相互作用する。
現行masterへ探索方式だけを差し込むと、danbo-v16用に得た最適点から外れ、
方式自体の価値より低い結果が出るという懸念は妥当である。一方、固定値SPRTは
「今のmasterへそのまま入れたときの実用効果」を測るため、第1段階としては必要である。

## 5. NMP rollbackの未初期化不整合

履歴は次の順序になっている。

1. [`c117c9c8`](https://github.com/yaneurao/YaneuraOu/commit/c117c9c8496661ba2cea985c29df284a02e2e1bc):
   NMP verification searchを削除。
2. [`c641394d`](https://github.com/yaneurao/YaneuraOu/commit/c641394d573a2da5f679b255e8720d604d078e0b):
   やねうら王側から`nmpMinPly`を外し、初期化を`#if STOCKFISH`内へ移動。
3. [`436b1174`](https://github.com/yaneurao/YaneuraOu/commit/436b117451b0fe0673b4671c4677211163e5755e):
   NMPをV9.30相当へrollbackし、メンバーと探索中の参照を復活。
   しかし初期化の`#if STOCKFISH`は外していない。

その結果、通常のやねうら王ビルドでは`nmpMinPly`がコンストラクタでも
`pre_start_searching()`でも初期化されず、最初の
`ss->ply >= nmpMinPly`で未初期化値を読む。これは未定義動作である。

- `search-v9.30`は`nmpMinPly = 0`を無条件に実行するため、この不整合がない。
- #66はbase/dev双方が同じ不整合を持つため、比較条件としては対称である。
- #68のdevは#4により`nmpMinPly`自体を削除しているため、#68には
  NMP verification削除・reduction増加に加え、この不整合解消の効果も含まれる。
- #4+#5を不採用にする場合でも、`nmpMinPly`初期化だけは別の1アイデア・1ブランチで
  修正候補にする。

## 6. upstream V9.30後の変更履歴

通常対局に関係するものを分類すると次のようになる。

| commit | 変更 | 現行での意味 |
|---|---|---|
| [`dc943f89`](https://github.com/yaneurao/YaneuraOu/commit/dc943f89) | LMR/reduction定数を当時のStockfishへ同期 | 恒久的な探索変更。ただしforkでは後にdanbo SPSAで再変更 |
| [`db295b89`](https://github.com/yaneurao/YaneuraOu/commit/db295b89) | 駒取り手の二重・三重extensionを抑制 | 後の`067f6552`で消え、現行には残らない。#66で再試験中 |
| `c117c9c8`, `c641394d` | NMP verificationを削除 | 後にrollback。#4+#5で再試験予定 |
| `067f6552` | Makefile大改修と同時に探索分岐も変更 | 上記#66相当を消し、NMPの返値処理も変更 |
| `436b1174` | NMPをV9.30相当へrollback | アルゴリズムはV9.30相当だが初期化漏れを残す |
| `c9061de3`, `f898bc64` | `qsearch_psv`追加・専用TT読み取り抑止 | 教師局面変換用。通常対局には影響しない |
| `212fa42a`, `26d0252c` | bench決定性、最終PV出力修正 | 測定・表示の修正 |
| `14653630`, `98455708` | 秒未満・increment時の時間管理修正 | 持時間付き対局には影響し得るが探索方式とは別 |
| `9bc84691` | ResignValue判定・最終PV修正 | 投了・表示経路。通常の指し手選択ロジックとは別 |

## 7. `search-v9.30`を使う対局設計

現在の`search-v9.30@996c4796`は2026-07-08時点のfork基盤で、現行masterにある
ponder修正、increment上限修正、その他の互換変更をすべては含まない。このまま
現行masterと対局させると「探索V9.30対V9.60」以外の差も混ざる。

比較は次の順序で行う。

1. **比較基盤の更新**: 現行masterから派生し、現在のfork機能を保ったまま
   V9.30探索だけを移植した新しい比較ブランチを作る。既存`search-v9.30`は
   結果が確認できるまで上書きしない。
2. **固定値SPRT**: 現行master対V9.30相当を同一評価関数・同一条件で測る。
   これは配布状態の実用差を見る第1段階とする。
3. **原因別ablation**: NMP初期化、LMR群、枝刈り群、history/qsearch群、
   時間管理を別ブランチに分ける。複数群を一度に戻さない。
4. **paired SPSA**: base/dev双方を同一評価関数・同一対局条件・同一予算で調整する。
5. **未使用対局で最終評価**: SPSAに使った対局と分離し、danbo-v16だけでなく
   少なくとも別評価関数でも交差確認する。

固定値SPRTが負けても、それだけで方式を不採用にしない。paired SPSAと未使用対局を
含む総合判断で不採用になった場合は、その時点で実験ブランチを削除する。

## 8. `STOCKFISH`分岐の扱い

`source/config.h`には、`STOCKFISH`は「Stockfishの元のコードを示す」ための
シンボルであり「定義してもビルドエラーになる」と明記されている。したがって、
やねうら王をStockfishとして使わない場合、実行時機能としては不要である。

一方、この分岐はStockfish原典との差分確認と将来の追随作業の目印として使われる。
削除しても棋力や速度は改善せず、大量の非機能差分によってupstream追随を難しくする。
よって今回の強化実験では削除しない。削除するなら棋力候補とは別のrefactorブランチで
行うが、現時点では利点より保守コストが大きい。
