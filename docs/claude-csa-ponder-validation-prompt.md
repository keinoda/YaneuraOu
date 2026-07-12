# Claude向け実棋譜Ponder検証プロンプト

以下をClaude Codeへそのまま渡してください。

---

`keinoda/YaneuraOu` のブランチ
`claude/stochastic-ponder-immediate-moves-ef5xzl` にある最新実装を、
実対局CSA棋譜で独立検証してください。

## 目的

ShogiHomeの早期Ponderと `Stochastic_Ponder=true` の組み合わせで、
`ponderhit` の時計情報を反映する修正後の時間配分が正常か確認すること。

あわせて、標準USIの引数なし `ponderhit` が次の意図どおり動くか確認すること。

- 標準Ponder:
  `go ponder btime ... wtime ... binc ... winc ...` の時計を使い、
  引数なし `ponderhit` でPonderから通常探索へ切り替える。
- 通常Ponderでは、同じ実局面の探索を停止・再起動せず継続し、
  hit時刻を自時計での時間計測基準にする。
- Stochastic Ponderでは、Ponder中は最後の1手を戻した局面を探索しているため、
  hit時に保存済み時計を使って実局面から通常探索を再開する。
- ShogiHome早期Ponderでは、時計なし `go ponder` と時計付き
  `ponderhit btime ...` を使う。

## 対象

- リポジトリ: `/Users/keinoda/Documents/YaneuraOu`
- ブランチ: `claude/stochastic-ponder-immediate-moves-ef5xzl`
- 棋譜:
  `/tmp/codex-remote-attachments/019f5589-36b4-73e1-a591-d59248419a81/F884BA72-2FB6-40A0-ACF3-B34ED698263F/1-dr7tsec-buoy_blackbid600_tsec7p2-3-top_4_suishoo_sojo-600-2F-suishoo-sojo-20260711212454.csa`
- テスト対象: sojo、後手、104手
- 時間制御: 600秒、1手2秒加算

棋譜が上記パスに無い場合は、同名の添付CSAファイルを探してください。
見つからなければ推測で別棋譜を使わず、未検証として報告してください。

## 前提

1. ビルド構成、評価データ、実行バイナリは自分で調査して選んでください。
   選定理由、ビルドコマンド、エンジンidentity、主要USI設定を報告してください。
2. 現在のブランチの実装を検証対象とし、別コミットや既存配布バイナリを
   修正後バイナリとして扱わないでください。
3. ソース、テスト、文書は編集しないでください。gitの
   checkout/reset/stash/commit/branch/pushも禁止します。
4. 必要な補助スクリプト、ビルド、ログ、結果は `/tmp` 配下へ作成してください。
5. 既存の未追跡ファイル `source/YaneuraOu-by-macos-arm64` は
   上書き・削除しないでください。
6. 次の既存資料は参照できますが、過去の計測値を新規実測の代用にしないでください。

   - `docs/stochastic-ponder-immediate-move-test.md`
   - `docs/data/stochastic-ponder-t0/`
   - `script/csa_ponder_replay.py`
   - `script/ponderhit_regression_test.py`

## 定跡の扱い

以前の調査で、sojo側の **ply 8〜78にあるT0着手** は定跡起因と
判断済みです。これらは `book-expected` として扱い、定跡かどうかを
再判定しないでください。

- 同一の定跡ファイルが無く、リプレイ時にエンジンが思考しても修正失敗とはしない。
- 元棋譜全体の分類表では、該当する元棋譜T0を「定跡即指し」として残す。
- ply 78より後を根拠なく定跡扱いしない。

## 必須検証

### 1. ShogiHome早期Ponderの全数リプレイ

sojo側全104手について、次のコマンド形を再現してください。

```text
position ...
go ponder
<相手の実考慮時間に相当する待機>
ponderhit btime ... wtime ... binc 2000 winc 2000
```

`Stochastic_Ponder=true` とし、CSAのT値から各局面の時計を復元してください。

CSA冒頭4手はbuoy setupです。先手第1手の `T602` を相手考慮602秒として
sleepしてはいけません。実対局部分では、以後の相手考慮時間を可能な限り
CSAのT値どおり再現してください。

各手について、少なくとも次をJSONLまたはCSVへ保存してください。

- ply
- 棋譜の着手とT値
- hit直前の両者の残り時計
- 再現した相手考慮時間
- `ponderhit` から `bestmove` までの実測時間
- score種別 (`cp` / `mate`)
- 合法手数
- bestmoveと、その出力回数
- 警告の有無と内容
- 元棋譜T0の分類

### 2. 時間配分の判定

非定跡、非mate、合法手2手以上の全手について、`timeman.cpp` から求めた
minimum / optimum / maximum と実測を照合してください。

特にply 82〜104の元棋譜T0を省略せず、次を一覧化してください。

- 1秒未満
- MinimumThinkingTime相当未満
- maximum超過
- 時計情報欠落のWarning
- 二重bestmove
- 非合法bestmove

異常があれば、原因となるコードのファイルと行を示してください。

### 3. 元棋譜T0の分類

元棋譜でsojoがT0だった77手を、少なくとも次へ分類してください。

- `book-expected`
- `mate-early-break`
- `legal-one`
- `other`

修正後の再現で、`other` に時計欠落によるT0が残るか結論を出してください。

### 4. 引数なしponderhitの対照

定跡外、非mate、合法手2手以上の代表局面を複数選び、次を実測してください。

```text
go ponder btime ... wtime ... binc 2000 winc 2000
ponderhit
```

- `Stochastic_Ponder=true`:
  hit後に実局面から正常な時計で再探索されること。
- `Stochastic_Ponder=false`:
  Ponder中とhit後のPV・depth・nodesの連続性を記録し、同一探索を継続すること。
  相手考慮時間を自時計へ誤課金せず、hit時刻を基準に停止すること。

全104手を追加で回すか代表局面に絞るかは、実行時間と判別力を根拠に
決めて構いません。

### 5. 負の対照

可能なら修正前バイナリでも同じ早期Ponder形式の代表局面を実行し、
約100msの時計欠落即指しを再現してください。修正後の結果と明確に分けてください。

## 完了条件

- 提案だけで終わらず、実測が完了するまで待つ。
- テストが失敗しても、ソースを場当たり的に修正しない。
- 実行できなかった項目を成功扱いしない。
- リポジトリの変更前後で `git status --short` を取り、検証による変更が
  増えていないことを確認する。

## 報告形式

日本語で、次の順に報告してください。

1. 結論
2. 使用したビルドと、その選定理由
3. 実行コマンド
4. 早期Ponder全104手の集計
5. 元棋譜T0 77手の分類
6. 引数なしponderhitの対照結果
7. 異常行
8. 生成物の絶対パス
9. 未確認事項
10. 検証前後のgit status

---
