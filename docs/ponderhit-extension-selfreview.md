# ponderhit時間制御拡張パッチのセルフレビュー報告 (2026-07-12)

## 2026-07-13追補: 通常PonderをV8.30基準へ変更

2026-07-12時点の内部再探索は現行の実装ではない。通常Ponderは、
時計付きhitでもroot、反復深化、PV、nodes、root統計を維持する。
USIスレッドは時計をpending eventとして渡し、探索メインスレッドが
`TimeManagement` だけを再初期化してからPonderを解除する。
Stochastic Ponderは従来どおり、一手前のrootから実局面へ再探索する。

対象: コミット `6de7cab`「ponderhitの時間制御引数をStochastic Ponderの再goに反映する」
比較元: ブランチ基点 `23faf0a` (master)。
source配下の差分は `source/usi.cpp` のみ (+51/−1)。
`git diff 23faf0a..HEAD --stat -- source/timeman.* source/engine/` は空
(時間配分式・探索部は無変更)。

レビュー方針: コード変更なし。実際の git diff と現在のコードを読み直し、
PTY(pexpect)による実機テストマトリクスで検証した。

## 追補: 未対応項目の実装 (2026-07-12)

以下の初回レビューで指摘した F1、F2と、追加レビューで判明した
ponderhit受信時刻の未課金を修正した。

- `ponderhit` は `btime/wtime/binc/winc/byoyomi` と、V8.30互換の
  `rtime` だけを専用パーサで解析する。
- 保存済み `go ponder` を `LimitsType` へ構造化してから、hit側で
  指定された時計項目だけを上書きする。`searchmoves` の後ろに
  時計文字列を連結しない。
- Stochastic Ponder は従来どおり再探索する。通常Ponderも時刻付き
  hitの場合だけ、旧探索のbestmoveを抑止して停止し、同一局面の
  通常探索を再開する。引数なしの標準 `ponderhit` は再起動せず
  従来どおり探索を継続する。
- 再探索の `startTime` は停止完了時ではなく、ponderhit受信時に
  固定する。停止・局面復元の時間も対局時計に課金される。

通常Ponderの時刻付きhitは、V8.30の `Time.reinit()` による同一探索継続と
は内部動作が異なる。現行の非同期構造でUSIスレッドから探索中の
`TimeManagement` を書き換えるdata raceを避けるためである。TTは維持されるが、
反復深化とroot統計は再開時に初期化される。

判定可能な `script/ponderhit_regression_test.py` を追加し、MATERIAL構成で
標準/早期×通常/Stochasticの4経路、hit優先、部分上書き、
`searchmoves`、非対応 `nodes` の非注入、時計なし、ponder missを確認した。
ON/OFF設定の読み戻しに加え、Ponder中PVの先頭手がONでは1手前の局面、
OFFでは実局面の合法手であることを確認し、Stochastic経路自体を検証した。
各bestmove後は0.5秒の無出力区間も検査した。通常の0.3秒Ponderと、
`go ponder` 直後のhitの両方で全件合格した。
修正前バイナリは経路CでAssertionErrorとなり、非0終了することも確認した。
FukauraOu CoreML構成はビルドと `usiok` まで確認した。

## 初回パッチの判定: 一部不適合

- **Stochastic Ponder (ON)**: 標準USI形式(時計付き go ponder + 引数なし
  ponderhit)・やねうら王拡張形式(時計なし go ponder + 時計付き ponderhit)の
  **両方に適合**。時計欠落による約100ms探索は解消。
- **通常Ponder (OFF) + 時計付き ponderhit(仕様経路C)**: **不適合**。
  未実装(警告のみ)。既知・宣言済みの残課題。

## Findings(重要度順)

### F1【中】通常Ponderで時計付きponderhitが時間管理に反映されない(仕様経路C)

- ファイル/行: `source/usi.cpp:306-320`(elseブランチ。警告出力のみで
  `engine.set_ponderhit(false)` する)
- 実際の動作: OFF + 時計なし `go ponder` + `ponderhit btime ...` で
  **150ms** で bestmove(警告は表示される)
- 期待される動作: hit の時計で時間管理を再計算する
- 原因: V9.60系に `TimeManagement::reinit()` が存在しない
  (`source/timeman.h:150-165` の `lastcall_*` は `#if 0` の TODO)。
  実行中探索の tm 更新は新規実装が必要なため、パッチ時に意図的に
  スコープ外とし警告で可視化した
- 再現方法: 下記テスト C_f
- 最小修正方針: `lastcall_*` を有効化して `TimeManagement::reinit(limits)` を
  追加し、else側で `ponderhit_args` をパース→保存limitsへ部分上書き→
  `tm.reinit()`→`main_manager()->stopOnPonderhit = false`→
  `set_ponderhit(false)` の順に適用(V8.30 の `parse_ponderhit()` +
  `Time.reinit()` + `reset_for_ponderhit()` 相当を現行構造へ移植)

### F2【低】保存go ponder引数に searchmoves があると連結したhit引数が飲み込まれる

- ファイル/行: `source/usi.cpp:294`(連結)、`source/usi.cpp:595-608`
  (parse_limits の searchmoves は行末まで全トークンを消費)
- 実際/期待: `go ponder searchmoves ...` + 時計付きhitで hit時計が無視される
  /hit時計が優先されるべき
- 原因: 「後勝ち」を得るために hit引数を末尾連結している構造上の制約
- 再現方法: 机上確認のみ(実GUIは go ponder に searchmoves を付けない)
- 最小修正方針: 連結前に `saved_go_args` から searchmoves以降を分離し、
  「時計部 + hit引数 + searchmoves部」の順で再構成する

### F3【低】byoyomiとincの混在残留

- ファイル/行: `source/usi.cpp:294` + `source/timeman.cpp:232-233`
  (remain_time = time + byoyomi + inc)
- 実際の動作: 保存側にbyoyomi・hit側にbincのみ等の場合、両方が残って
  remainがやや過大になる
- 期待される動作: 拡張仕様の字義(「hitで指定されなかった項目は元の値を
  維持する」)には**適合**。V8.30 の parse_ponderhit も同じ部分上書き意味論
- 実害: byoyomi/inc併用の時間制御は実在しないため無し(報告のみ)

### F4【中】stochastic hit の stop→再go 間の数msは予算に課金されない

`usi.cpp:271-276`(停止待ち)→ `usi.cpp:574`(再goのparse_limitsで
startTime=now)。思考時間が増える方向であり、時間切れ安全性では危険側。
追補実装ではhit受信時刻を停止前に保存し、再探索の `startTime` に使う。

### F5【情報】時計なし go ponder + 引数なし ponderhit の約100ms挙動は従来どおり

既存の下限 `timeman.cpp:237`(remain_time≧100ms)は不変。パッチは警告
(`usi.cpp:298-302`)を追加したのみ。

## 経路追跡(時計情報の流れ)

| 経路 | 時計の入口 | Limitsへの到達 | TimeManagementへの到達 | hit時の扱い |
|---|---|---|---|---|
| A: OFF+時計付きgp+bare hit | `go ponder btime...`→parse_limits (usi.cpp:571-717) | go()→engine.go (usi.cpp:811)→start_thinking→worker.limits | tm.init (yaneuraou-search.cpp:1274、startTime=go ponder受信時) | set_ponderhit (yaneuraou-search.cpp:574-582) が ponderhitTime=now のみ更新。予算は元の時計+ponderhit補正 (timeman.cpp:476) |
| B: ON+時計付きgp+bare hit | 同上(コマンド行保存: usi.cpp:356) | hit時: saved_go_args抽出 (usi.cpp:284-288)→連結 (294)→go(iss3) (304)→新規parse_limits | 新規tm.init(startTime=hit時点、search_end=0: timeman.cpp:227-228) | 旧探索は bestmove抑制付き停止 (usi.cpp:271-276) |
| C: OFF+bare gp+時計付きhit | hit引数は usi.cpp:265 で取得されるが**未使用**(警告のみ: 314-318) | 到達しない | go ponder時に time=0 で init 済み(remain=100ms床: timeman.cpp:237) | **F1: 即指しのまま** |
| D: ON+bare gp+時計付きhit | `ponderhit btime...` (usi.cpp:265) | 連結 (294、saved側は空)→go(iss3)→parse_limits | tm.init(hit時計、startTime=hit時点) | 適合(実測で直接goと一致) |

## 検証結果

- 実行: PTY (pexpect 4.9, echo=False)。quit は最終 bestmove 受信後のみ送信。
- エンジン: sojotsec7 配布物の環境で HEAD からビルドした
  `YaneuraOu-patched`(SFNN_halfkahm2_2048_15_64_ls9 / AVX512VNNI / normal。
  テスト中に本パッチ固有の警告文字列が出力されることで同一性を確認)。
- 主要設定: Threads=2, USI_Hash=256, USI_Ponder=true, **USI_OwnBook=false +
  bookディレクトリ無し**(定跡無効)。
- 局面: `position startpos moves 2g2f 8c8d 7g7f`(後手番=エンジン、
  合法手30以上、詰みなし)。ponder中スリープ2.0秒。
- 全ケースで「ponderhit前のbestmove出力=0件」「hit後のbestmoveは1回のみ」
  「bestmoveは当該局面の合法手(python-shogiで照合)」を確認。
- 再現スクリプト: `script/ponderhit_selfreview_test.py`

| ケース | 実測 | bestmove | 備考 |
|---|---|---|---|
| R1 直接go fischer300k | 9931ms | 8d8e | 基準値 |
| R2 直接go byoyomi10000 | 8931ms | 8d8e | 基準値 |
| R3 直接go fischer50k | 2934ms | 8d8e | 基準値 |
| A_f OFF gp(fischer300k)+bare hit | 3931ms | 8d8e | 継続探索。警告なし |
| A_b OFF gp(byo10000)+bare hit | 8931ms | 4a3b | isFinalPushのminimum()-from-hit (timeman.cpp:476) と公式一致 |
| B_f ON gp(fischer300k)+bare hit | 2932ms | 4a3b | ≥1.8s、[min,max]内 |
| **B_b ON gp(byo10000)+bare hit** | **8935ms** | 8d8e | **R2と4ms差 = 保存時計が再goへ正しく到達** |
| **C_f OFF bare gp+hit(fischer300k)** | **150ms+警告** | 8d8e | **F1(仕様C不適合)** |
| D_f ON bare gp+hit(fischer300k) | 2933ms | 8d8e | hit時計が有効 |
| **D_b ON bare gp+hit(byo10000)** | **8933ms** | 8d8e | **R2と2ms差 = hit時計で直接goと同等の時間配分** |
| P1 ON gp(byo2000)+hit(byo10000) | 8931ms | 4a3b | hit優先(増方向) |
| P1r ON gp(byo10000)+hit(byo2000) | 933ms | 8d8e | hit優先(減方向)。remain=2000−NetworkDelay2(1120)=880ms の公式値と一致 |
| **P3 ON gp(byo9000)+hit(btime/wtimeのみ)** | **7931ms** | 8d8e | **未指定項目(byoyomi)の維持を確認**。remain=9000−1120=7880ms と公式一致(喪失なら約150msのはず) |
| P3r ON gp(fischer300k)+hit(byoyomi9000のみ) | 4932ms | 8d8e | 混在維持(F3) |
| N ON bare gp+bare hit | 152ms+警告 | 4a3b | 既存100ms床の維持(項目14) |
| miss flow: gp(fischer)→stop→bestmove1回→実局面position→go | 4932ms | 8d8e | 重複なし |

備考:
- tm内部値(minimum/optimum/maximum)の直接読み出しはコード変更なしでは
  不可能なため、**min=opt=max が確定する byoyomi系ケース
  (A_b/B_b/D_b/P1/P1r/P3)の公式値一致(±4ms)**をもって
  TimeManagement 到達の検証とした。
- fischer系の wall time は探索動態(fallingEval等)により [minimum,maximum]
  内で変動するため、合否判定には使用していない
  (通常Ponderの即指し自体はUSI上合法、という基準に対応)。
- 当初の P2(fischer系の部分上書き判定)は wall time の判別力不足のため
  無効と判断し、決定的な P3(byoyomi維持判定)で代替した。

## 未確認事項

- tm 内部値の直接ダンプ(コード変更なしでは不可。byoyomi公式一致で代替)
- ShogiHome 実機を接続した E2E(pexpect PTY で代替。ShogiHome 側は
  ソース静的確認のみ)
- FukauraOuの実モデルを使用した探索実行(ビルドと `usiok` のみ確認)
- Windows 環境・高負荷(スレッド競合)時の挙動

## 変更状況

- レビュー・検証のフェーズ中、リポジトリのファイルは一切変更していない
  (テストはセッション作業領域のスクリプトで実施)。
- 本報告ファイルと再現テストスクリプト
  (`script/ponderhit_selfreview_test.py`)は、レビュー完了後に
  利用者の指示によりコミットしたものである。
