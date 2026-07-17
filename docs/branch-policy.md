# ブランチ命名・運用規則

本リポジトリ(keinoda/YaneuraOu)のブランチ命名と運用の規則を定める。
制定: 2026-07-12(ponderhit時間制御修正のブランチ整理を機に策定)
改訂: 2026-07-14(アーカイブ先を refs/archive へ変更(§5)、第2回棚卸し(§6)、
`sojo_tsec7` の例外指定。生きているブランチの台帳は docs/branches.md に分離)
改訂: 2026-07-15(第3回棚卸しと実験運用の改訂(§7))
改訂: 2026-07-17(固定値SPRTと再SPSA後の最終採否を分離(§7))

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
- `sojo_tsec7`(SOJO TSEC7 大会提出構成)は、わかりやすさを優先して
  命名規則の例外として現名のまま維持する(2026-07-14ユーザー決定)。
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
   履歴を残したい場合は削除の代わりに隠し名前空間
   `refs/archive/<ブランチ名>` へ退避する(手順は §5)。
   【2026-07-14改訂】従来の `archive/<ブランチ名>` タグ方式
   (repository-organization-plan.md P2 の実績運用)は、タグ一覧が
   アーカイブで埋まり提示用タグ(§5)が見えなくなるため廃止。
   既存の archive タグは §6 の棚卸しで移行・削除する。
5. ブランチの「改名」は、新名称ブランチの作成+旧ブランチの削除で行う。
   旧ブランチは新ブランチの push 確認後に削除する。

## 3. 本規則の初回適用

`claude/stochastic-ponder-immediate-moves-ef5xzl`(ponderhit時間制御の
未反映による即指し問題の調査・修正・検証)を対象に、そのHEADから
`fix/ponderhit-time-control` を切り出す。作業文書(docs/ 以下の調査ログ・
検証データ)は規則2に従い切り出し時点では保持し、master マージ時に
規則3に従って整理する。

2026-07-13、旧作業ブランチは
`archive/claude/stochastic-ponder-immediate-moves-ef5xzl` タグで保全し、
ブランチrefを削除した。以後の修正と検証は `fix/ponderhit-time-control` を用いる。

また、`danbo-tuned2` に `fix/ponderhit-time-control` をマージした検証用
ブランチ `test/danbo-tuned2-ponderhit` を作成し、素の `danbo-tuned2`
(改名後は `tune/danbo2`)との比較テストに用いる。比較テスト終了後は
規則2-4に従い処置する。

2026-07-14、比較テスト完了後、`test/danbo-tuned2-ponderhit` の確定内容を
`master` へsquash統合した。調査・検証ログ、計測生データ、セッション向け
指示書は正本から除外し、実装、恒久回帰テスト、再利用可能な計測ツール、
本規則を残した。統合元は次のタグで保全し、対応するブランチrefを削除した。

- `archive/fix/ponderhit-time-control`
- `archive/tune/danbo2`
- `archive/test/danbo-tuned2-ponderhit`

(これらのタグは §6 の棚卸しで `refs/archive/*` へ移設する)

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

## 5. アーカイブ名前空間とタグの運用(2026-07-14改訂)

### タグ(refs/tags)は提示用専用とする

タグは「対外的に提示したいもの」だけに使う(大会提出構成、配布ビルドの
リリース版など)。提示したいタグには GitHub Release の作成も推奨
(Releases ページで説明・成果物付きで見せられる)。
履歴保全のためのアーカイブをタグに置くことは今後行わない。

### アーカイブは refs/archive/*(隠し名前空間)

ブランチ・タグのどちらの一覧にも表示されない任意ref名前空間を使う。
refが指すオブジェクトはGCされず保全され、コミットURLも生きる。
GitHub UI から一覧できないため、退避したものは必ず docs/branches.md の
台帳に記録する。

操作(いずれもローカルから。リモートセッションのgitプロキシでは不可):

```
# 退避(ブランチ→アーカイブ)。新refの作成を確認してからブランチを消す
git push origin refs/heads/<名前>:refs/archive/<名前>
git ls-remote origin refs/archive/<名前>
git push origin :refs/heads/<名前>

# 一覧
git ls-remote origin 'refs/archive/*'

# 手元へ取得・閲覧
git fetch origin '+refs/archive/*:refs/archive/*'
git log refs/archive/<名前>

# ブランチとして復元
git push origin refs/archive/<名前>:refs/heads/<名前>
```

注意: GitHub はカスタムrefのpushを受け付ける。§6 の一括スクリプトは
退避の成功(11件)を確認できた場合にのみ削除を行う設計のため、pushが
拒否されても失われるものはない。万一恒常的に拒否される場合の代替は
アーカイブ専用リポジトリへの退避(不採用案、必要になったら再検討)。

### 改名残骸タグを作らない

ブランチ改名(§2規則5)の際、旧名を archive タグとして残さない。
同一コミットを指す現役ブランチがある限りタグは情報を持たず、
旧名→新名の対応は §4 のような台帳で追跡できるため。

## 6. 第2回棚卸し(2026-07-14)

実験作業ブランチの堆積と、archive タグによるタグ一覧の占有(20個全てが
archive タグ)を解消する。処置後の各ブランチの目的・状態は
docs/branches.md(台帳)を正とする。
影響確認(2026-07-14): 未クローズPRなし。

### タグの処置(20個 → 0個)

| 処置 | 対象 | 理由 |
|---|---|---|
| 削除(14個) | `archive/claude/search-ab/01〜09`(9個)、`archive/danbo-tuned`、`archive/fuuppi-tuned`、`archive/spsa-danbo`、`archive/spsa-v930`、`archive/suisho11-tuned` | 同一コミットを指す現役ブランチ(`test/ab-01〜09`、`tune/*`)が存在する改名残骸。削除で失う情報はない(全件同一SHA検証済み) |
| `refs/archive` へ移設(6個) | `archive/claude/stochastic-ponder-immediate-moves-ef5xzl`、`archive/fix/ponderhit-time-control`、`archive/test/danbo-tuned2-ponderhit`、`archive/test/danbo-tuned2-ponderhit-test37`、`archive/tune/danbo2`、`archive/tune/danbo2-before-fix-parent-20260713` | ブランチ削除済みの履歴保全実体。タグ名から `archive/` 接頭辞を外した名前で移設 |

### ブランチの処置

| 処置 | 対象 | 理由 |
|---|---|---|
| 削除 | `claude/opening-book-repetition-t64nol` | master に完全包含(unique commit 0) |
| 削除 | `claude/search-ab/all` | `test/ab-all` に完全包含。01〜09改名時(§4とは別の07-13作業)の取り残し |
| 維持(例外) | `sojo_tsec7` | 命名規則外だが、わかりやすさ優先で現名のまま維持(2026-07-14ユーザー決定。§1) |
| refs/archive へ移設 | `codex/android-build-v941-refresh`、`codex/android-v941-sfnn1536-stack`、`codex/fukauraou-policyvalue`、`backup/yaneuraou-home-20260702`、`backup/yaneuraou-1-android-20260702` | 休止中の実験と正本化前の退避スナップショット。必要になれば §5 の手順で復元できる(2026-07-14ユーザー決定) |
| 維持 | `master`、`search-v9.22/9.30/9.40`、`tune/*`(5本)、`test/ab-01〜12`・`test/ab-all`、`claude/yaneuraou-search-optimization-qxvzz0` | 規則準拠の現役。`test/ab-*` は実験完了時に規則2-4で処置 |

### 実施手順(ローカルから実行。§4と同じ制約により)

以下のスクリプトをローカルクローンで実行する(ファイルに保存して `bash`
で実行、またはターミナルへそのまま貼り付け。bash/zsh両対応)。
SHAを含まず ref名だけで動くため、転記ミスはエラーになるだけで
誤った対象に作用しない。削除は refs/archive への退避11件を確認できた
場合にのみ実行され、どの時点で失敗・中断しても履歴は失われない
(再実行も安全)。

```sh
#!/bin/sh
# keinoda/YaneuraOu ブランチ・タグ第2回棚卸し(2026-07-14)の一括実施
# 詳細: docs/branch-policy.md §6 / docs/branches.md
#
# 安全設計:
#  - SHAを使わず ref名だけで動く(名前の転記ミスは「エラーで失敗」になるだけで、
#    誤った対象に作用することがない)
#  - 削除は、refs/archive への退避が11件そろったことを確認できた場合のみ実行
#  - どの時点で中断・再実行しても履歴は失われない(再実行も安全)
#
# 実行方法: このリポジトリのローカルクローンで
#   bash yaneuraou-branch-cleanup-20260714.sh
# (bash/zsh どちらのターミナルへの直接貼り付けでも動く)

# 実体のある旧archiveタグ6件 → refs/archive/<名前> へ移設
TAG_ARCHIVES='
claude/stochastic-ponder-immediate-moves-ef5xzl
fix/ponderhit-time-control
test/danbo-tuned2-ponderhit
test/danbo-tuned2-ponderhit-test37
tune/danbo2
tune/danbo2-before-fix-parent-20260713
'

# 休止ブランチ5件 → refs/archive/<名前> へ移設(いつでも復元可)
DEAD_BRANCHES='
codex/android-build-v941-refresh
codex/android-v941-sfnn1536-stack
codex/fukauraou-policyvalue
backup/yaneuraou-home-20260702
backup/yaneuraou-1-android-20260702
'

# 現役ブランチと同一コミットを指す改名残骸タグ14件 → 削除のみ
LEFTOVER_TAGS='
claude/search-ab/01-capture-futility
claude/search-ab/02-check-extension
claude/search-ab/03-iir-old-style
claude/search-ab/04-no-followpv
claude/search-ab/05-nmp-eval-r
claude/search-ab/06-drop-lmr
claude/search-ab/07-statscore-conthist
claude/search-ab/08-aspiration-delta
claude/search-ab/09-gameply-futility
danbo-tuned
fuuppi-tuned
spsa-danbo
spsa-v930
suisho11-tuned
'

# 統合先に完全包含のブランチ2件 → 削除のみ
MERGED_BRANCHES='
claude/opening-book-repetition-t64nol
claude/search-ab/all
'

echo '== 1) 全refの取得 =='
git fetch origin --prune --tags

echo '== 2) refs/archive へ退避(タグ6件+ブランチ5件) =='
for n in $(echo "$TAG_ARCHIVES");  do git push origin "refs/tags/archive/${n}:refs/archive/${n}"; done
for n in $(echo "$DEAD_BRANCHES"); do git push origin "refs/remotes/origin/${n}:refs/archive/${n}"; done

echo '== 3) 退避の検証 =='
COUNT=$(git ls-remote origin 'refs/archive/*' | wc -l | tr -d ' \t')
echo "refs/archive: ${COUNT}件 (期待値 11)"

if [ "$COUNT" = "11" ]; then
  echo '== 4) タグ20件を削除(6件は退避済み・14件は改名残骸) =='
  for n in $(echo "$TAG_ARCHIVES") $(echo "$LEFTOVER_TAGS"); do git push origin ":refs/tags/archive/${n}"; done
  echo '== 5) ブランチ7件を削除(5件は退避済み・2件は統合済み) =='
  for n in $(echo "$DEAD_BRANCHES") $(echo "$MERGED_BRANCHES"); do git push origin ":refs/heads/${n}"; done
  echo '== 6) 最終状態 =='
  echo "残タグ数 (期待値 0): $(git ls-remote --tags origin | wc -l | tr -d ' \t')"
  echo "refs/archive (期待値 11): $(git ls-remote origin 'refs/archive/*' | wc -l | tr -d ' \t')"
  echo '-- 残ブランチ一覧 --'
  git ls-remote --heads origin
  git fetch --prune --prune-tags origin
  echo '完了。docs/branches.md 冒頭の「実施状況」を実施済みに更新してください。'
else
  echo '!! 退避が11件そろっていないため、削除は実行しませんでした。'
  echo '!! 手順2のpush結果のエラーを確認してください(この時点で失われたものはありません)。'
fi
```

実施したら docs/branches.md の「実施状況」を更新する。

**実施記録(2026-07-14)**: スクリプト(zsh互換修正版)で全38操作を完了。
タグ0件・refs/archive 11件(全SHA照合済み)・残ブランチ25本が
docs/branches.md の台帳と一致することをリモートで確認した。

## 7. 第3回棚卸しと実験運用の改訂(2026-07-15)

### 背景と方針転換

探索部改善のA/B実験(`test/ab-01〜12`+`test/ab-all`、13本同時)のような
「候補テーマの一括ブランチ化」はツリーを圧迫し、個々の検証も進まなかった。
実験ブランチ群を一掃し、以後は次の運用とする。

1. **実験は1テーマ=1ブランチ**で着手し、原則として同時に1本まで。
   通常は採否判定が出てから次のテーマに進むが、ユーザーが
   明示的に次候補のブランチ作成を指示した場合は併存を認める。
2. 現行パラメータを固定したShogiBench SPRTは、masterへの差し込み効果を
   測る第1段階とする。このSPRTが負けまたは不明瞭でも、それだけで不採用とせず、
   **テストURL、条件、局数、W/L/D、LLR、第1段階の判定をブランチ内に記録**し、
   base/dev双方を同条件で再SPSAした後の未使用対局で最終採否を決める。
3. 最終採用はmasterへ統合する。最終不採用は規則2-4に従いブランチを削除する
   (ユーザーが履歴保全を指示した場合のみ `refs/archive/*` へ退避)。
4. **A/Bテスト(SPRT)は外部の ShogiBench を使用**する。自前の対局基盤
   (script/ab)は正本に置かない
   (`refs/archive/claude/yaneuraou-search-optimization-qxvzz0` から復元可能)。
5. 改善テーマの候補カタログとして `docs/search-improvement-plan.md` を
   master に取り込んだ(計画書内の ab_match.py 関連の記述は基盤退避前の
   もので、現在は ShogiBench に読み替える)。

### ブランチの処置

影響確認(2026-07-15): 未クローズPRなし。`test/ab-all` が個別12本の
全コミットを履歴包含することを `git merge-base --is-ancestor` で全件検証済み。

| 処置 | 対象 | 理由 |
|---|---|---|
| refs/archive へ移設(5本) | `test/ab-all`、`claude/yaneuraou-search-optimization-qxvzz0`、`tune/danbo`、`tune/fuuppi`、`tune/suisho11` | 実験の一括中止と、数値焼き込みSPSA成果の退役。履歴は全て保全(2026-07-15ユーザー決定) |
| 削除(12本) | `test/ab-01〜12` | `test/ab-all` に全履歴が包含済みのため個別退避は冗長 |
| 維持(7本) | `master`、`sojo_tsec7`、`search-v9.22/9.30/9.40`、`tune/spsa-danbo`、`tune/spsa-v930` | search-v* はupstream追随のA/B比較基準。tune/spsa-* はSPSAチューニング導入パッチで次回調整の土台(2026-07-15ユーザー決定) |

### ローカルの整理(参考)

- リモート処置済みの追跡ブランチ4本(`test/danbo-tuned2-ponderhit`、
  `fix/ponderhit-time-control`、`tune/danbo2`、`codex/android-build-v941-refresh`)、
  master(4a0aa76f)へ統合済みのローカル専用2本(`refactor/book-effective-value`、
  `refactor/ls-bucket-runtime`)、アーカイブ退避済みブランチのworktree 2つと
  対応ブランチ(`codex/fukauraou-policyvalue`、`codex/android-v941-sfnn1536-stack`)
  を削除
- 2026-07-08棚卸し作業の残骸worktree登録8件をprune、stash・一時ファイルを整理

### 実施記録(2026-07-15)

ref名ベースの一括スクリプト(§6と同設計。退避16件の確認後にのみ削除実行)で、
退避5件→ブランチ17本の削除を完了。残ブランチ7本・refs/archive 16件が
docs/branches.md の台帳と一致することをリモートで確認した。
