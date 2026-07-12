# Stochastic Ponder 有効時の「残り時間に関わらず即指し」調査ログ

## 2026-07-12: 実対局CSA棋譜(600秒+2秒加算)の0秒指し検証

### 対象

`dr7tsec+buoy_blackbid600_tsec7p2-3-top_4_suishoo_sojo-600-2F` の実対局棋譜。
sojo(後手=本エンジン)の104手中 **77手がT0**。後手の残り時間は常に188秒以上
(終局時207秒)で、時間切迫は一度もない。

### 静的解析: 時間管理は実装どおり正確に動いていた

CSAのT値から各局面の時計を復元し、timeman.cpp の式で
minimum/optimum/maximum を計算して照合した結果:

- 長考(T20〜42)15回のうち **13回が理論maximumTimeと厳密一致**
  (差は常に −0.88s = 秒切り上げ−NetworkDelay 120ms のオフセットそのもの)。
  ponder外れ時のフル思考として完全に実装どおり。
- 残り2回(T20)も optimum〜maximum の帯域内。
- この時間制御(600s+2F)での理論値: minimum 1.88s / optimum 7〜12s /
  maximum 26〜43s(残り時間により変動)。**1秒未満は時間管理からは出ない**。

### 実機リプレイ: T0はStochastic_Ponder有効では再現不可能

`script/csa_ponder_replay.py` で、実際の時計残量・実際の相手考慮時間を
再現しつつ全104手の白番を計測(always-hit USIポンダー手順)。

| モード | 対象 | 最短 | 中央値 | 最長 |
| --- | --- | --- | --- | --- |
| Stochastic_Ponder **ON** | 非詰み・合法手2手以上の93手 | **2880ms** | 5881ms | 34882ms |
| Stochastic_Ponder **OFF**(通常ponder) | 同 | **1880ms** | 6881ms | 36881ms |

- **ON: 棋譜でT0だった77手のうち67手は1.8秒以上を要した**(残り10手は
  詰み読み切り(mate-break)と合法手1手(502msキャップ)で、これは仕様どおり
  どのモードでも即指しになる)。ONの実装は ponderhit のたびに現局面を
  positionから再goするため、MinimumThinkingTime(2000)−NetworkDelay(120)
  +秒丸めの床(≈1.9〜2.9s)を必ず消費する。
- OFF(通常ponder)は、相手考慮中に思考予算(totalTime)を使い切ると
  ponderhit直後に指す設計(stopOnPonderhit / set_search_endのponderhit補正)。
  実測では相手考慮を実際の長さ(最大12秒)で再現しても 1880ms の床
  (CSA表記でT1相当)への収束までで、時計付きの正規手順では
  1秒未満(T0)には届かなかった(29手中13手が床、1秒未満は0)。
  真のT0(<1秒)を再現できたのは下記「(a) 時計なし go ponder」経路のみ。
- 序盤〜中盤前半(ply 8〜78)のT0について、当初は読み筋コメントから
  定跡ヒットを原因候補とした。しかし実運用の定跡ファイルとUSIログが無く、
  同じT0はShogiHome早期Ponderの時計欠落でも説明できるため、定跡とは未確定。
  T0やply範囲だけで分類せず、実運用の BookFile / BookMoves、定跡DBの局面、
  定跡hit出力を用いた独立検証が必要。

### 結論

1. 棋譜中の時間消費は全点で実装と整合し、**時間管理の不具合はない**。
2. **時計付きの正規USI手順である限り、この対局の0秒指しパターンは
   Stochastic_Ponder が有効な状態の本実装からは発生しない**
   (ONでは最短でも1.9〜2.9秒)。
   ⚠ ただしこれは時計欠落起因のT0についての話であり、
   **詰み読み切り(mate早期打ち切り)・合法手1手(502msキャップ)・
   定跡ヒット・MaxMovesToDraw超過の保険経路によるT0は仕様として残る**。
   T0の分布だけでは、定跡ヒットと早期Ponderの時計欠落を区別できない。
3. T0を実際に発生させうる構成不備を2つ、実機で特定した。
   ランナーのUSIログで以下の2点を確認すれば確定できる。

   **(a) `go ponder` に時計パラメータが無い場合(最有力)**:
   Stochastic_Ponder の ponderhit 処理は保存した go ponder コマンド行を
   そのまま再実行するため、そこに btime/wtime が無いと再探索は
   持ち時間0(remain_time 下限100ms)で走る。実測:

   ```text
   go ponder                                  → ponderhit後  105ms で bestmove (=T0)
   go ponder btime 300000 wtime 300000 ...    → ponderhit後 2884ms で bestmove
   ```

   この場合 **Stochastic_Ponder が正しくONでも、残り時間に関わらず
   ponderhitのたびに即指しになる**。将棋所/ShogiGUIは常に時計付きで
   go ponder を送るため顕在化しない。
   (通常ponderでも時計なしgo ponderは同様にhit後ほぼ即指しになる。)

   **→ 発生源を特定: ShogiHome の「早期Ponder」(enableEarlyPonder)。**
   本対局のGUIは ShogiHome(エンジンをラッパー登録)であり、
   `src/background/usi/engine.ts` に次の実装がある(2026-07-12 main確認):

   - `goPonder()`:
     `timeState: this.option.enableEarlyPonder ? undefined : timeState`
     — 早期Ponder有効時は **go ponder に時計を付けない**。
   - `buildPonderTimeOptions()`: timeState が undefined なら空文字。
     コメント「これは**やねうら王の拡張仕様**で、標準の USI では ponder
     には必ず具体的な時間を付与する。」
   - `ponderHit()`: 早期Ponder有効時のみ `ponderhit btime .. wtime ..` と
     **時計は ponderhit の引数としてのみ**送る。
   - enableEarlyPonder はエンジン個別設定で既定 false。

   一方、やねうら王側でこの拡張を受けるパーサ `parse_ponderhit()`
   (usi.cpp「"ponderhit"に"go"で使うようなwtime,btime,winc,binc,byoyomiが
   書けるような拡張。(やねうら王独自拡張。USI拡張プロトコル)」)は、
   **V9.60系では定義のみで呼び出し箇所が無い(死にコード)**
   (upstream master も 2026-07-12 時点で同様。upstreamでは `#if 0` 内)。

   歴史的な正確性のための補足: V8.30 で `parse_ponderhit(is)` →
   `Time.reinit()` を呼んでいたのは**通常ponder分岐だけ**であり、
   Stochastic Ponder 分岐は当時から保存した go ponder を再実行するのみで
   ponderhit の時刻引数を参照していない。つまり
   - 通常ponder経路: V8.30では対応 → V9.60で失われた(**退行**)
   - Stochastic経路: **当初から未対応**(下記パッチで新規対応)
   であり、分類としては「特定コミットの退行」よりも
   **GUI・エンジン間の拡張プロトコル互換処理(特にStochastic Ponder
   ヒット時)の統合不具合**が適切。

   この組み合わせにより、早期Ponder有効のShogiHome + V9.60系 +
   Stochastic_Ponder ON では、ponderhit のたびに時計なしの go ponder が
   内部再実行され、remain_time 下限100msで即指しになる。
   通常ponderでも go ponder の探索自体が持ち時間0で時間管理されるため、
   ponderhit 後ほぼ即指しになる(どちらのモードでも発生する)。

   **対処**: 即効はShogiHomeのエンジン設定で「早期Ponder」を無効にする
   (go ponder に時計が付く形式に戻り、ON/OFFとも正常動作になる)。
   恒久対応はエンジン側で ponderhit 引数の解析(parse_ponderhitの接続)を
   復活させ、Stochastic Ponder の再goにその時計を反映すること。

### 2026-07-12: 恒久対応を実装 (usi.cpp)

保存済み `go ponder` を `LimitsType` へ解析し、`ponderhit` 専用パーサが
`btime/wtime/binc/winc/byoyomi`(V8.30互換の `rtime` も維持)だけを
部分上書きする。これにより `searchmoves` が行末まで引数を消費する場合でも
hit時計は失われず、`nodes/depth/infinite` などの仕様外引数も注入されない。

Stochastic Ponderと、通常Ponderの時刻付きhitは、旧探索のbestmoveを抑止して
停止し、実局面から通常探索を再開する。再探索の `startTime` は
ponderhit受信時に固定し、停止・局面復元の時間も対局時計に課金する。
引数なしの標準 `ponderhit` は再起動せず、従来どおり探索を継続する。

テストマトリクス(MATERIALビルド、3秒読みの直接go基準1932ms):

```text
[OFF] 時計付きgo ponder + 時計なしponderhit : 1940ms
[ON ] 時計付きgo ponder + 時計なしponderhit : 1941ms
[OFF] 時計なしgo ponder + 時計付きponderhit : 1942ms
[ON ] 時計なしgo ponder + 時計付きponderhit : 1932ms
[ON ] searchmoves付きgo ponder + 時計付きhit        : 1935ms
[ON ] ponderhit nodes 1 + 時計                       : 1941ms (nodesは無視)
[ON ] 両方時計なし                                  :  160ms + Warning
```

実棋譜の局面での修正前後比較 (early-ponder形式リプレイ、ply82〜92):

```text
修正前(配布バイナリ): 全手 0.10〜0.11s  ← 棋譜のT0を完全再現
修正後(パッチ版)   : 3.88〜17.88s      ← 正常な時間管理
```

`script/ponderhit_regression_test.py` は上記経路とhit優先、部分上書き、
ponder missをPTYで検証し、不適合時は非0で終了する。
`Stochastic_Ponder` は `getoption` で設定値を読み戻すだけでなく、Ponder中の
PV先頭手を検査する。ONでは最後の1手を戻した局面、OFFでは実局面の合法手集合に
属することを確認するため、通常Ponderの再探索経路だけが動いていても合格しない。
また各応答後0.5秒と次ケース開始前の出力を検査し、停止した旧探索から遅れて出る
二重 `bestmove` も失敗として扱う。通常の0.3秒Ponderと待機なしhitで全件合格した。

通常Ponderの時刻付きhitはV8.30の `Time.reinit()` による同一探索継続と異なり、
現行の非同期構造でdata raceを避けるため内部再探索する。TTは維持するが、
反復深化とroot統計は再開時に初期化される。

   **(b) setoption の値の文字列が不正な場合**:
   `setoption name Stochastic_Ponder value True` (大文字) / `1` / `on` は
   usioption.cpp の check 型判定 (`v != "true" && v != "false"`) により
   **エラー表示なしで無視され、falseのまま**になる(実機確認済み。
   Python の `str(True)` が "True" を生成する点に注意)。
   この場合は通常ponderとして動作し、相手考慮中に思考予算を使い切った
   ponderhit で即指しになる(こちらは正規のponder動作)。
   オプション名の誤り(例: `StochasticPonder`)は "No such option" が
   表示されるが、**値の誤りは沈黙する**。

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
