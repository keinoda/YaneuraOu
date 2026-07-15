# ブランチ台帳

- 作成: 2026-07-14(第2回棚卸し。docs/branch-policy.md §6)
- 目的: 生きているブランチの目的・状態の一覧
  (docs/repository-organization-plan.md P5 の実施)
- 規則: docs/branch-policy.md。ブランチの追加・削除・処置のたびに本台帳を更新する
- 実施状況: **実施済み(2026-07-14)**。リモート照合済み
  (タグ0件・refs/archive 11件・残ブランチ25本=本台帳と一致)

## 正本

| ブランチ | 説明 |
|---|---|
| `master` | 正本。実運用ビルドはここから行う(2026-07-14 ponderhit修正・danbo2調整 統合済み) |

## upstream追随(search-v*)

探索部のみを当該版相当に変更したA/B比較基準。fork機能・互換性はmaster維持。

| ブランチ | 説明 |
|---|---|
| `search-v9.22` | 探索部 V9.22 相当 |
| `search-v9.30` | 探索部 V9.30 相当 |
| `search-v9.40` | 探索部 V9.40(717da87)相当 |

## 調整(tune/*)

| ブランチ | 説明 |
|---|---|
| `tune/danbo` | danbo-v11-progress 向け探索パラメータSPSA焼き込み(102,400局 tc=2+0.02) |
| `tune/fuuppi` | fuuppi-v3 向けSPSA焼き込み |
| `tune/spsa-danbo` | danbo系SPSA実験 |
| `tune/spsa-v930` | v9.30系SPSA実験 |
| `tune/suisho11` | suisho11 向け調整 |

(danbo2系は2026-07-14にmaster統合済み。履歴は `refs/archive/tune/danbo2`)

## 実験(test/*、claude/)

| ブランチ | 説明 | 状態 |
|---|---|---|
| `claude/yaneuraou-search-optimization-qxvzz0` | 探索部改善計画(計画書v3)とA/Bテスト基盤(ab_match.py 等) | 現役。test/ab-* シリーズの統括 |
| `test/ab-01〜12`(12本) | 探索部改善のA/B実験(1ブランチ1テーマ) | 現役(2026-07-13開始)。完了時に規則2-4で処置 |
| `test/ab-all` | ab-01〜12 の全部乗せ | 現役。同上 |
| `claude/branch-organization-cleanup-jpeorn` | 本棚卸し(§6)の作業ブランチ | master統合後に削除 |

## 大会提出(命名規則の例外)

| ブランチ | 説明 |
|---|---|
| `sojo_tsec7` | SOJO TSEC7 大会提出構成(エンジン識別・danbo-v16進行度係数埋め込み)。わかりやすさ優先で現名のまま維持(2026-07-14決定。branch-policy.md §1) |

## アーカイブ(refs/archive/*)

GitHub UI には表示されない。一覧は `git ls-remote origin 'refs/archive/*'`、
取得・復元手順は docs/branch-policy.md §5。
現在の一覧(旧 archive タグ6件+休止ブランチ5件)。

| ref | 内容 |
|---|---|
| `refs/archive/claude/stochastic-ponder-immediate-moves-ef5xzl` | ponderhit即指し問題の調査・修正・検証の全過程(masterへsquash統合済み) |
| `refs/archive/fix/ponderhit-time-control` | 同修正の確定ブランチ(統合済み) |
| `refs/archive/test/danbo-tuned2-ponderhit` | danbo2×ponderhit修正の比較検証(統合済み) |
| `refs/archive/test/danbo-tuned2-ponderhit-test37` | 同・test37時点のスナップショット |
| `refs/archive/tune/danbo2` | danbo2調整の最終形(統合済み) |
| `refs/archive/tune/danbo2-before-fix-parent-20260713` | danbo2の親修正前スナップショット |
| `refs/archive/codex/fukauraou-policyvalue` | ふかうら王に policy/value 出力を追加(最終更新 2026-07-01) |
| `refs/archive/codex/android-build-v941-refresh` | Android ビルド更新(EvalDir解決ほか、独自3コミット。最終更新 2026-06-17) |
| `refs/archive/codex/android-v941-sfnn1536-stack` | Android SFNN1536ビルド・スタック設定(最終更新 2026-06-18) |
| `refs/archive/backup/yaneuraou-home-20260702` | 正本化前ローカルrepoの全退避(NNUE 512x2/768x2系) |
| `refs/archive/backup/yaneuraou-1-android-20260702` | 正本化前ローカルrepoの全退避(Androidビルド系) |

## 削除(2026-07-14棚卸しで実施済み)

- ブランチ `claude/opening-book-repetition-t64nol` — master に完全包含
- ブランチ `claude/search-ab/all` — `test/ab-all` に完全包含
- タグ `archive/claude/search-ab/01〜09`、`archive/danbo-tuned`、
  `archive/fuuppi-tuned`、`archive/spsa-danbo`、`archive/spsa-v930`、
  `archive/suisho11-tuned` — 現役ブランチと同一コミットの改名残骸(計14個)
