# ブランチ台帳

- 作成: 2026-07-14(第2回棚卸し。docs/branch-policy.md §6)
- 更新: 2026-07-15(第3回棚卸し。同 §7)
- 目的: 生きているブランチの目的・状態の一覧
  (docs/repository-organization-plan.md P5 の実施)
- 規則: docs/branch-policy.md。ブランチの追加・削除・処置のたびに本台帳を更新する
- 実施状況: **第3回実施済み(2026-07-15)**。リモート照合済み
  (refs/archive 16件・残ブランチ7本=本台帳と一致)

## 正本

| ブランチ | 説明 |
|---|---|
| `master` | 正本。実運用ビルドはここから行う(2026-07-15 探索部改善計画書v3 取り込み済み) |

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
| `tune/spsa-danbo` | danbo系SPSAチューニング導入パッチ(探索パラメータのグローバル変数化+tune.py用宣言。次回SPSA調整の土台) |
| `tune/spsa-v930` | v9.30系SPSAチューニング導入パッチ(同上。探索部はV9.30相当) |

(数値焼き込みの `tune/danbo`・`tune/fuuppi`・`tune/suisho11` は2026-07-15に
アーカイブへ移設。danbo2系は2026-07-14にmaster統合済みで履歴は
`refs/archive/tune/danbo2`)

## 実験

| ブランチ | 説明 | 状態 |
|---|---|---|
| `codex/capture-single-extension-master` | 駒を取る手の二重・三重singular extensionを抑制 | 初期化修正前の#66は参考値。修正版#72は承認待ち |
| `feature/nmp-no-verification-more-reduction` | NMP検証探索の削除 + reduction増加(tanuki #4+#5) | 初期化修正前の#68は参考値。修正版#71は承認待ち |

branch-policy.md §7 の運用(1テーマ=1ブランチ、A/Bテストは ShogiBench、
固定値SPRTだけで不採用にせず再SPSA後に最終判定)に従う。
改善テーマの候補は docs/search-improvement-plan.md を参照。

## 大会提出(命名規則の例外)

| ブランチ | 説明 |
|---|---|
| `sojo_tsec7` | SOJO TSEC7 大会提出構成(エンジン識別・danbo-v16進行度係数埋め込み)。わかりやすさ優先で現名のまま維持(2026-07-14決定。branch-policy.md §1) |

## アーカイブ(refs/archive/*)

GitHub UI には表示されない。一覧は `git ls-remote origin 'refs/archive/*'`、
取得・復元手順は docs/branch-policy.md §5。
現在16件(第2回で11件+第3回で5件)。

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
| `refs/archive/test/ab-all` | 探索部改善A/B実験(AB-01〜12)の全部乗せ。**個別12ブランチの全履歴を包含**(2026-07-15移設) |
| `refs/archive/claude/yaneuraou-search-optimization-qxvzz0` | 探索部改善計画とA/Bテスト基盤(script/ab: ab_match.py 等)。計画書はmasterへ取り込み済み(2026-07-15移設) |
| `refs/archive/tune/danbo` | danbo-v11-progress 向け探索パラメータSPSA結果焼き込み(102,400局 tc=2+0.02。2026-07-15移設) |
| `refs/archive/tune/fuuppi` | fuuppi-v3 向けSPSA結果焼き込み(2026-07-15移設) |
| `refs/archive/tune/suisho11` | 水匠11 向けSPSA結果焼き込み(2026-07-15移設) |

## 削除記録

### 2026-07-15(第3回棚卸し)

- ブランチ `test/ab-01〜12`(12本) — `test/ab-all`(アーカイブ済み)に全履歴が包含
- (ローカルのみ) `refactor/book-effective-value`・`refactor/ls-bucket-runtime` —
  master(4a0aa76f)に統合済み
- (ローカルのみ) アーカイブ退避済みブランチのworktree 2つと対応ブランチ
  (`codex/fukauraou-policyvalue`・`codex/android-v941-sfnn1536-stack`)

### 2026-07-14(第2回棚卸し)

- ブランチ `claude/opening-book-repetition-t64nol` — master に完全包含
- ブランチ `claude/search-ab/all` — `test/ab-all` に完全包含。01〜09改名時(§4とは別の07-13作業)の取り残し
- タグ `archive/claude/search-ab/01〜09`、`archive/danbo-tuned`、
  `archive/fuuppi-tuned`、`archive/spsa-danbo`、`archive/spsa-v930`、
  `archive/suisho11-tuned` — 現役ブランチと同一コミットの改名残骸(計14個)
