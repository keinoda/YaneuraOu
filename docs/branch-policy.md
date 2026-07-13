# ブランチ命名・運用規則

本リポジトリ(keinoda/YaneuraOu)のブランチ命名と運用の規則を定める。
制定: 2026-07-12(ponderhit時間制御修正のブランチ整理を機に策定)

前提: 正本ブランチは `master`(docs/repository-organization-plan.md P1で確立)。
本規則は同プランP2(既存ブランチの棚卸し)を引き継ぎ、以後に作成する
ブランチの命名とライフサイクルを定めるものである。

## 1. 命名規則

形式は `プレフィックス/トピック`。トピックは英小文字・数字・ハイフンのみの
kebab-case で、内容が分かる範囲で簡潔(目安4語以内)にする。

| プレフィックス | 用途 | 例 |
|---|---|---|
| `fix/` | 不具合修正 | `fix/ponderhit-time-control` |
| `feature/` | 新機能・機能拡張 | `feature/policy-book-v2` |
| `refactor/` | 挙動を変えない整理 | `refactor/timeman-cleanup` |
| `docs/` | 文書のみの変更 | `docs/build-instructions` |
| `test/` | テスト・検証の追加や実験 | `test/ponder-regression` |
| `tune/` | 評価関数・パラメータ調整 | `tune/danbo-3` |
| `backup/` | 退避スナップショット(日付付き) | `backup/yaneuraou-home-20260702` |
| `claude/` `codex/` | AIセッションの作業ブランチ。ツールの自動命名を許容 | `claude/stochastic-ponder-immediate-moves-ef5xzl` |

- upstream(yaneurao/YaneuraOu)追随ブランチは従来どおり `search-v<版>`
  (例: `search-v9.40`)とする。
- 既存ブランチにも本規則を遡及適用する(2026-07-12指示)。改名台帳と
  実施手順は §4 のとおり。

## 2. 運用規則(ライフサイクル)

1. **作業ブランチ**(`claude/`・`codex/`・実験系)では、調査ログ・検証データ・
   作業文書をコミットに含めてよい。作業の全過程を記録として残すためのブランチである。
2. 修正・機能が安定したら、作業ブランチのHEADから **確定ブランチ**
   (`fix/` または `feature/`)を切り出す。
   **切り出し時点では作業文書もそのまま残す**(検証・レビューの参照用)。
   実対局テストなどの確認はこの確定ブランチで行う。
3. **master へのマージ時**に履歴を整理する。squash merge を基本とし、
   マージ前に作業文書を整理する。
   - 整理(削除・別置き)対象: 調査・検証の作業ログ、計測生データ、
     セッション向け検証指示書など、その作業限りの文書
   - 残す対象: 恒久的な資産(本規則のような運用文書、回帰テストスクリプト、
     仕様に関わる文書)
4. マージ完了後、元の作業ブランチと確定ブランチは削除してよい。
   削除前に、参照しているPR・セッションがないことを確認する。
   履歴を残したい場合は削除の代わりに `archive/<ブランチ名>` タグで退避する
   (repository-organization-plan.md P2 の実績運用)。
5. ブランチの「改名」は、新名称ブランチの作成+旧ブランチの削除で行う。
   旧ブランチは新ブランチの push 確認後に削除する。

## 3. 本規則の初回適用

`claude/stochastic-ponder-immediate-moves-ef5xzl`(ponderhit時間制御の
未反映による即指し問題の調査・修正・検証)を対象に、そのHEADから
`fix/ponderhit-time-control` を切り出す。作業文書(docs/ 以下の調査ログ・
検証データ)は規則2に従い切り出し時点では保持し、master マージ時に
規則3に従って整理する。

また、`danbo-tuned2` に `fix/ponderhit-time-control` をマージした検証用
ブランチ `test/danbo-tuned2-ponderhit` を作成し、素の `danbo-tuned2`
(改名後は `tune/danbo2`)との比較テストに用いる。比較テスト終了後は
規則2-4に従い処置する。

## 4. 既存ブランチの遡及改名(台帳)

影響確認(2026-07-12実施): 未クローズPRなし。CIワークフローのブランチ指定は
すべてワイルドカード(`**`)であり、改名で失効するトリガーはない。
改名は同一コミットへ新しいrefを付け替える操作であり、内容は失われない。

| 旧名 | 新名 | 状態 |
|---|---|---|
| `danbo-tuned` | `tune/danbo` | 実施済み |
| `danbo-tuned2` | `tune/danbo2` | 実施済み |
| `fuuppi-tuned` | `tune/fuuppi` | 実施済み |
| `suisho11-tuned` | `tune/suisho11` | 実施済み |
| `spsa-danbo` | `tune/spsa-danbo` | 実施済み |
| `spsa-v930` | `tune/spsa-v930` | 実施済み |

変更しないもの: `master`(正本)、`search-v*`(§1の既存規約)、
`backup/*`・`claude/*`・`codex/*`(既に規則準拠)。

**実施方法**: リモートセッションのgitプロキシはブランチ作成は許可するが
削除を受け付けないため、改名(=新名作成+旧名削除)はセッションからは
完了できない。次のいずれかで行う。

- GitHub UI の branch rename(旧名URLのリダイレクトとPR付け替えが自動で行われ、
  最も安全)
- ローカルからの一括push:

```
git fetch origin
git push origin \
  origin/danbo-tuned:refs/heads/tune/danbo \
  origin/danbo-tuned2:refs/heads/tune/danbo2 \
  origin/fuuppi-tuned:refs/heads/tune/fuuppi \
  origin/suisho11-tuned:refs/heads/tune/suisho11 \
  origin/spsa-danbo:refs/heads/tune/spsa-danbo \
  origin/spsa-v930:refs/heads/tune/spsa-v930 \
  :danbo-tuned :danbo-tuned2 :fuuppi-tuned \
  :suisho11-tuned :spsa-danbo :spsa-v930
# 削除可否検証時の残骸プローブ(masterと同一コミットの空ブランチ)も削除する
git push origin :test/rename-probe
```

実施後、手元のスクリプトやビルドレシピ(iShogi の docker 等)が旧名を
参照している場合は新名へ更新すること。

**実施記録(2026-07-13)**: 全6件の改名とプローブ削除を完了。新refが旧refと
同一コミットを指すことを全件で検証済み(tune/danbo=a913b200,
tune/danbo2=5e5f0b53, tune/fuuppi=8b5dc706, tune/spsa-danbo=8136c5d0,
tune/spsa-v930=67e75fcf, tune/suisho11=180137d0)。
