# リポジトリ正本化プラン(keinoda/YaneuraOu)

- 作成日: 2026-07-03
- 目的: この fork を「自分にとっての正本」として運用できる状態に整理する
- 状態: 計画(P0 の方針決定後、フェーズ単位で実施)

## 1. なぜごちゃついているか(診断)

2026-07-02〜03 の旧運用名(本構成の評価関数版に紐づくエンジンディレクトリ名)構成の
再ビルド作業で、ビルド元の特定に長時間を要した。原因を調査した結果、
以下の7点に整理できる。

### A. 正本ブランチの不在(最大の原因)

実運用エンジン(旧運用名でのビルド)のソースは `sfnnwop1536-progress-v941` だが、リポジトリ上で
それが「主力」だと分かる印がどこにもない。`master` は「upstream v9.41 + Android統合」のみで
実運用機能を含まず、「どのブランチが本番か」が記録されていなかった。

### B. 履歴が実体を表さない

- `sfnnwop1536-progress-v941` の履歴に **768化コミット(06d62aad)が含まれるが最終実体は1536**
  (後のマージで実質的に戻っている)。ブランチ名・履歴・実体の三者が食い違う。
- 同名コミットの重複: 「progress進行度でSlowMoverを補正」が 74de8fff と a4c10b00 の
  **2つとも同一ブランチ履歴に存在**(ブランチ間 cherry-pick の乱れ)。
- cherry-pick 多用のため、ブランチ間の機能の包含関係が git のマージ関係から追えない。

### C. 運用必須パッチのリポジトリ外流出

NNUEヘッダ version 警告化(本構成の nn.bin 読込に必須)が、どのブランチにも
コミットされず **iShogi リポジトリの docker/v9.42-private/Dockerfile 内の patch** として
存在していた。ソースだけ見ても再現できない状態だった。

### D. 命名と実体の乖離

- edition 名 `SFNN_halfkahm2_1536_15_32_k3k3` の「k3k3」は重みレイアウト名で、実際の
  バケット選択は進行度(progress8kpabs 相当)。名前から実体が読めない。
  → **解消(2026-07-04)**: バケット数のみを表す `SFNN_..._ls<N>` を正式サポートし、
  ビルドは `..._ls9` を推奨名とした(`_k3k3`/`_king3_by_king3` は同一レイアウトの
  alias として存続)。選択方式は実行時の `LS_BUCKET_MODE` が唯一の決定点。
  詳細は docs/progress-sfnn-1536-build.md を参照。
- エンジン表示名は 560e6890 で旧表示名から変更されたが、運用上は旧運用名で呼ぶ。

### E. 実験の生死が不明

- ensemble(22コミット + wip退避)、policyvalue(worktree)、opening-target、768系が
  「進行中/完了/廃棄」のどれなのかリポジトリから読めない。

### F. 世代違い・残骸の堆積

- v940ベース4ブランチ(sfnnwop1536-progress-v940 / sfnn-halfka-hm-768 / <旧768系> /
  codex/progress-slowmover-scaling)は、機能的には v941 系へ統合済みの旧世代。
- `codex/android-build-v921-refresh` は master に完全包含(0 ahead)。
- prunable な worktree 残骸(/private/tmp/YaneuraOu_old_android)。

### G. ビルドレシピの分散

iShogi/docker 4種(うち private 2種)、Dockerfile 内パッチ、<旧768系>ブランチ内だけにある
Apple Silicon ビルドスクリプト、リモートでの手動ビルド、と4箇所以上に分散。

## 2. 改善プラン(フェーズ単位・独立採否可)

### P0: 方針決定(要ユーザー判断)

**→ 決定(2026-07-03): 案A「master に直接統合」を採用。**

- 案B: `keinoda-main` を新設。master は upstream 追従専用に保つ(不採用)。
- 案A(採用): master に直接統合する。upstream 更新の取り込みは master への
  マージで行う(取り込み時のコンフリクト解決は都度対応)。

### P1: 正本ブランチの確立(小・即効)

**→ 実施済み(2026-07-03)**: 旧エンジン名を冠したビルドブランチ(= b593284a + version警告化 +
book修正。実機で評価値一致検証済み)を master へマージ(124bba44)。
ビルド記録ドキュメントも「正本 = master」へ更新済み。
以後のビルドは master から行う(追加パッチ不要)。
残: fork への push(ユーザー確認後)。

### P2: ブランチ台帳と仕分け(中)

**→ 実施済み(2026-07-03、ユーザー確認のうえ)**。結果:

| 処置 | ブランチ |
|---|---|
| 削除(masterに統合済み/不要) | <旧エンジン名ビルドブランチ>、feature/book-repetition-avoidance、sfnnwop1536-progress-v941、codex/android-build-v921-refresh、<旧エンジン名ビルドブランチ-v2> |
| `archive/` タグ化して削除 | progress-ensemble-engine、wip-progress-ensemble-20260702、sfnnwop1536-progress-v940、sfnn-halfka-hm-768-7-32-progress-v940、<旧768系>-opening-target-sfen、progress-slowmover-scaling、android-build、android-build-shinden3-yo9(計8タグ・ローカルのみ) |
| 継続 | master(正本)、codex/fukauraou-policyvalue(worktree)、codex/android-build-v941-refresh、codex/android-v941-sfnn1536-stack(worktree) |

worktree の prune 実施済み。fork への push は行っていない(fork 側のブランチは未整理のまま)。
また評価関数の版に依存する呼称を構成名から外し、
ビルド記録は docs/progress-sfnn-1536-build.md へ改名した。

### P3: ビルドレシピの一元化(中)

1. `script/build-progress-sfnn-1536.bash` を正本に追加(edition・TARGET_CPU・COMPILER を固定した
   再現ビルド。version パッチは正本にコミット済みとなるため patch 手順が消える)。
2. <旧768系>ブランチにしかない Apple Silicon ビルドスクリプトを正本へ移す。
3. iShogi 側 docker/v9.42-private の Dockerfile を「正本ブランチの特定コミットを
   clone してビルド」へ更新し、Dockerfile 内 patch を削除(iShogi 側の作業)。

### P4: 命名・表示の整理(小・任意)

- Makefile に progress バケットを明示する edition 別名を追加するか、
  docs での明示(済み)に留めるかを判断。
- エンジン表示名(旧表示名 / 旧運用名)の関係を整理。

### P5: 運用ルールの文書化(小)

- `docs/branches.md`: 生きているブランチの台帳(目的・状態)。
- ルール例: 実験は `codex/` プレフィックス → 完了したら正本へマージ or
  `archive/` タグ化して削除。正本へ入れる機能は「コミットされていないパッチ」を残さない。

## 3. 実施順の推奨

```
P0(方針決定) → P1(正本確立) → P2(仕分け・要ユーザー確認)
→ P3(レシピ一元化) → P5(台帳) → P4(任意)
```

P1 だけでも「次に何かをビルドする時に迷わない」状態になる。
