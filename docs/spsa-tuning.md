# 探索パラメーターのSPSAチューニング

`make tune` でビルドしたやねうら王は、V940由来の探索パラメーター148個を
USI `spin` オプションとして公開する。通常ビルドと大会用ビルドでは同じ項目が
`constexpr` のままになり、USIオプションにはならない。

## 1. tuneビルド

ビルドフラグが異なる成果物を同じ `source/obj` へ混在させない。normal、tournament、
tuneは別々のcloneまたは別々の作業ディレクトリでビルドする。

Apple Silicon MacでSOJO/TSEC7の評価関数を使う例:

```bash
make -C source -j"$(sysctl -n hw.ncpu)" tune \
  YANEURAOU_EDITION=YANEURAOU_ENGINE_SFNN_halfkahm2_2048_15_64_ls9 \
  TARGET_CPU=APPLEM1 \
  COMPILER=clang++ \
  PYTHON=python3

cp source/YaneuraOu-by-gcc source/YaneuraOu-tune
```

動的生成されるNNUE architectureを使うため、`PYTHON=python3` をMakeの
コマンドライン変数として渡す。別の評価関数を使う場合は、そのネットワークに対応する
`YANEURAOU_EDITION` を指定する。

`FOR_TOURNAMENT` と `ENABLE_TUNE` は併用できず、同時に指定するとコンパイルエラーになる。

## 2. YO形式 `.params` の生成

リポジトリルートから実行する。

```bash
python3 script/spsa/gen_params.py -o tune.params
```

標準出力へ出す場合は `-o` を省略する。既存ファイルを意図して置き換える場合だけ
`--force` を付ける。

```bash
python3 script/spsa/gen_params.py > tune.params
python3 script/spsa/gen_params.py -o tune.params --force
```

出力形式は次の148行で、`[[NOT USED]]` 行は追加しない。

```text
name,int,default,min,max,c_end,0.002
```

`c_end` は `(max - min) / 20`。生成時に対象2ファイルの件数、名前の一意性、
既定値と範囲も検証される。

## 3. rshogi SPSAのケースA

rshogiの `crates/tools/docs/spsa_runbook.md` §10.6.1にある「ケースA」を使う。
生成したYO形式 `.params` の名前はtuneビルドのUSIオプション名と一致するため、
変換ツールや `yo_rshogi_mapping.toml` は不要である。

```bash
RUN_DIR="runs/spsa/$(date -u +%Y%m%d_%H%M%S)_yo_v940"

cargo run --release -p tools --bin spsa -- \
  --run-dir "${RUN_DIR}" \
  --init-from /absolute/path/to/tune.params \
  --engine-path /absolute/path/to/YaneuraOu-tune \
  --total-pairs 6400 --batch-pairs 32 \
  --concurrency 8 --threads 1 --hash-mb 256 --byoyomi 1000 \
  --startpos-file /absolute/path/to/openings.txt \
  --usi-option EvalDir=/absolute/path/to/eval \
  --usi-option LS_PROGRESS_COEFF=/absolute/path/to/eval/progress.bin \
  --usi-option LS_BUCKET_MODE=progress8kpabs \
  --usi-option FV_SCALE=28 \
  --usi-option USI_OwnBook=false \
  --usi-option BookFile=no_book \
  --seed 1
```

評価関数、進行度係数、開始局面、エンジン、`.params` はすべて絶対パスで指定する。
相対パスはrshogiを起動したCWDから解釈されるため、進行度係数を読み込めず別の
LayerStackへフォールバックするなど、探索条件が変わる原因になる。

`EvalDir` に `eval_options.txt` がある場合は `isready` 時に読み込まれる。
同じオプションをコマンドラインとファイルの両方に書く場合は、実際の起動ログで
最終値、NNUE architecture、進行度ファイルのロード成功を確認する。

V940では次の8項目の範囲に0が含まれていたが、いずれも除数として使われる。
0を設定できると整数除算ゼロの未定義動作になるため、本ブランチでは下限を1に狭める。
既定値は変更しないので、normal/tournamentビルドの探索には影響しない。

- `aspiration_window_2`
- `Search_futility_1_5`
- `Search_Continuation_history_based_pruning1_3`
- `Search_Extensions1_3`
- `Search_Extensions2_1`
- `Search_Decrease_reduction_for_PvNodes_3_2`
- `Search_fail_low_quiet_bonus_2`
- `MovePicker_good_capture_see_1`

## 4. 結果の焼き込みと検証

まず書き込みなしで全148名と入力形式を検証する。

```bash
python3 script/spsa/apply_params.py /absolute/path/to/final.params --dry-run
```

完了したrunの最終 `.params` であることを確認してから適用する。途中再開用の
`state.params` を最終結果と取り違えない。

```bash
python3 script/spsa/apply_params.py /absolute/path/to/final.params
```

既知の148名がactive行としてすべて揃った場合だけ、2つのソースファイルにある
`TUNABLE_PARAM` の既定値を書き換える。未知名と未知の `[[NOT USED]]` 行は警告して
無視するが、重複名、不正値、既知名の欠落、範囲定義の不一致があれば書き込まない。

焼き込み後はtuneビルドのオブジェクトを再利用せず、新しいcloneまたは分離した
ビルドディレクトリでnormalビルドを作る。既定値benchとUSIオプション非公開を確認し、
そのバイナリをShogiBenchのSPRTで検証する。

## 5. パラメーターの追加

1. 対象リテラルを、別の物理行に置いた
   `TUNABLE_PARAM(name, default, min, max)` 1行へ置き換える。
2. 探索式から変数を直接参照できる場合はコピーを作らない。
3. 配列などコピー型の派生値が必要な場合は、normalビルドでは
   `TUNE_CONSTEXPR` にし、`#if defined(ENABLE_TUNE)` で囲んだ `isready` 転写を追加する。
4. `gen_params.py` の期待件数とテストを更新し、normal/tournament/tuneを分離ビルドする。
5. normalとtournamentの固定深さbenchが変更前と完全一致し、tuneビルドでは
   `setoption` 後に探索結果が変化することを確認する。

現実装で `isready` 転写が必要なのは `conthist_bonuses_1` から `_6` の1ブロックだけで、
`update_correction_history_nonPawnWeight_1` を含む残り142項目は直接参照である。

## 6. 旧パラメーター名との互換性

`YaneuraOuWorker_clear1_1/2/3` と `update_all_stats_1c_6` は、suisho10時代には
`[[NOT USED]]` の旧実体として扱われたが、V940では同じ名前が別実体の現役パラメーターに
再利用されている。ケースBのmapping経由やrshogi形式との相互移植では、名前だけで同一視せず
対応するソース位置と意味を再確認する。

また、fuuppi側だけにある旧別名
`Search_nullmove_1/2` と
`Search_Decrease_reduction_for_PvNodes_6_1/2` は追加しない。
V940の `Search_nullmove_1_1/_1_3` と
`Search_Decrease_reduction_for_PvNodes_6a_2/_6a_3` が対応する実体を扱う。

## 7. 支援スクリプトのテスト

```bash
python3 -m unittest discover -s script/spsa -p 'test_*.py' -v
```

テストは一時ディレクトリだけを書き換え、実リポジトリの148名契約は読み取り専用で確認する。

## 8. rshogiからの直接SPSA検証

2026-07-17、ShogiBench workerとして提供中のVast.ai instance `45136916`を、
対局workload停止後に直接操作して検証した。ShogiBench経由のSPSAはこの時点では
未検証であり、本節はその前段となる直接実行の記録である。

使用した版と成果物:

- rshogi: `e0388e581c1cf4f83e9d492f79f27074649d6e28`
- YaneuraOu: `64015ceab9d242e0525919c4143a05ad972d57c0`
- rshogi `spsa` SHA-256:
  `8333f5349d2880bde02bb5e80f903807781f842a95a827addee7ec981313efdd`
- YaneuraOu tune binary SHA-256:
  `89be558cd1d260920bd111e3c516b8983fb09f1c7f34d1c84122e7eb1f7eb9a4`
- 起点params SHA-256:
  `b003964e4db6edb3f4a6a316cf98115661535cce8603d00f31dfc67e0fafa8cd`

ビルド条件は `make tune`、
`YANEURAOU_ENGINE_SFNN_halfkahm2_2048_15_64_ls9`、AVX512、clang++、
`HASH_KEY_BITS=128`、`TT_CLUSTER_SIZE=4`、`USE_LAZY_EVALUATE`。
生成した148行のparams名は、tune binaryが公開した同名`spin` USI optionに
全件存在し、欠落は0件だった。

対局条件は共通で、Threads=1、Hash=16MB、100ms秒読み、最大320手、seed=1、
`taya36_shogi_sfen.epd`を使用した。評価関数はdanbo-v16-progress (`674A1218`)で、
`EvalDir`、`LS_PROGRESS_COEFF`、`LS_BUCKET_MODE=progress8kpabs`、`FV_SCALE=28`を
USI optionで指定し、定跡は無効化した。

### 8.1 razoring 2件のprotocol smoke

- run dir: `/root/spsa-yaneuraou-direct/runs/razoring-smoke-20260717T075512Z`
- `--active-only-regex '^Search_razoring_'`
- 4ペア8局、1 batch
- plus 4勝、minus 3勝、1分、raw result `+1`
- active 2件中2件が更新、平均更新量 `0.111376`、最大 `0.127485`
- `final.params` SHA-256:
  `f9e4e2cbdebcaafedbccb158823ad7f245a3672e5eb5be3175b5e961ab8b10e1`

`Search_razoring_1`は`368`から`368.127485`、
`Search_razoring_2`は`275`から`275.095267`へ更新された。

### 8.2 全148件のintegration smoke

- run dir: `/root/spsa-yaneuraou-direct/runs/all148-smoke-20260717T075622Z`
- 4ペア8局、1 batch
- plus 3勝、minus 5勝、raw result `-2`
- active `148/148`、148件すべてが更新
- 平均更新量 `2.583810`、最大 `192.657940`
- `final.params` SHA-256:
  `ff3153104ff909d8b9174e83d53386691969b9158b746462de8b93749da8d0b5`

### 8.3 ShogiBench smoke条件の直接再現

ShogiBench #73で予定した固定`N=10000`、総64ペア、batch 16、seed 1を、
同じinstance上でrshogiから直接実行した。

- run dir:
  `/root/spsa-yaneuraou-direct/runs/all148-nodes10000-pairs64-20260717T075925Z`
- 64ペア128局、4 batches、最大32並列
- 各batchのraw result: `-6`, `+6`, `-1`, `+8`
- 各batchともactive `148/148`で、最終的に148件すべてが起点から変化
- 各batchの平均更新量: `11.411361`, `7.596654`, `0.989338`, `6.709198`
- `final.params` SHA-256:
  `68cc284b729fc7a5bdbb05364b1145c1a32e44622b4e3dc377da6957fdf4a27b`

以上により、rshogiのSPSAループからYO形式paramsを読み、摂動値をYaneuraOuへ
USI optionとして渡し、対局結果からparamsを更新して`final.params`を確定する
直接経路は、複数batchを含むShogiBench smoke相当の規模まで動作した。
64ペアは収束や棋力を判断する規模ではないため、得られた数値自体は調整結果として使用しない。

直接検証前に作成されていたShogiBench #73は、操作ログ上`Nagisa`により削除された。
削除理由はログから確定できないため推測せず、#73は復元しない。

直接検証の完了後、同じ固定`N=10000`、総64ペア、batch 16、seed 1、
全148件を対象とするShogiBench #74を新規作成した。作成時のブランチheadは
`b22fb9768dbb9283ccde3e687e267393b68c3e6d`で、直接ビルドした
`64015ceab9d242e0525919c4143a05ad972d57c0`との差分は本節の文書追記のみである。
起点paramsのSHA-256は上記と同じ`b003964e...`である。#74は作成時点で未承認・
0/64ペアだった。その後、全64ペア（128局、4 batches）を完走し、最終paramsの
SHA-256は直接実行と同じ`68cc284b...`になった。これにより、同一条件では直接実行と
ShogiBench経路が決定論的に一致することを確認した。ただし64ペアはprotocol smokeであり、
得られた値を調整結果として使用しない。開始局面集も実装比較用の24手局面集ではなく
`taya36_shogi_sfen.epd`だったため、#74は`Nagisa`により削除された（操作ログ`DELETE`、
Unix時刻`1784276670`）。削除後も直接実行と一致した検証記録は本節に残す。

### 8.4 ShogiBench軽量SPSA（master対照）

実装候補の比較前に行う調整は、51,200ペア（102,400局）の最終調整より軽量にする。
rshogiの目安である「対象パラメータ数×50」の下限は148件で7,400ペアとなるため、
96並列を使い切れる48ペア単位へ切り上げ、7,680ペア（15,360局、160 batches）とした。

2026-07-17、master相当の探索を対照としてShogiBench #75を作成した。

- URL: `https://shogibench.fly.dev/tune/75/`
- ブランチ: `feature/tunable-search-params`
- 作成時head: `0920807bb101fa1ec17f21171e283765007efd81`
- 起点params: 148件、SHA-256 `b003964e4db6edb3f4a6a316cf98115661535cce8603d00f31dfc67e0fafa8cd`
- 総量: 7,680ペア（15,360局）、batch 48、seed 1、early stopなし
- 時間制御: `2.0+0.02`、スケール基準DEV、1,000,000 NPS
- 開始局面集: `yaneuraou2025_ply24_shogi_sfen.epd`
- 評価関数: danbo-v16-progress (`674A1218`)
- Threads=1、Hash=16MB、`USI_OwnBook=false`、`BookFile=no_book`、
  `NetworkDelay=0`、`NetworkDelay2=0`、`MinimumThinkingTime=100`、
  `RoundUpToFullSecond=false`、`FV_SCALE=28`
- SPSA schedule: alpha `0.602`、gamma `0.101`、A-ratio `0.1`、mappingなし、全148件
- 完了: 2026-07-17、160/160 batches、7,680/7,680ペア、15,360局
- 最終成績（plus側視点）: 7,511勝、7,395敗、454分、timeout 0、crash 0
- 最終batch: raw result `-6`（`-6/48 = -0.125`）、平均更新量 `4.487348`
- final.params: 148行すべて7カラム、有限値、定義範囲内
- final.params SHA-256:
  `cdf3004041cd68b3e433270677449b092b01213481bfdc57b655ddb18bc430ad`
- 初期値からの絶対移動量（可動範囲比）: 中央値 `1.120%`、95%点 `3.530%`、
  最大 `5.365%`
- min/max到達: 0件、境界から1%以内: 0件、境界から5%以内: 0件

累積の勝敗差116は決着局14,906局に対して約0.95標準偏差であり、plus/minus側の
有意な偏りを示さない。監視中のraw resultは正負の両側へ変動し、最終batchの
`-6`も単一batchの通常の揺らぎの範囲である。現行ShogiBenchは各batchの履歴を
サーバーに保持せず直近値だけを残すため、完走後に16 batch移動平均を厳密再計算する
ことはできない。この観測不足はShogiBenchの`codex/spsa-trajectory-chart`で
`stats.csv` / `values.csv`履歴を保存・可視化する変更として別管理する。

#75はmaster対照の軽量調整であり、この結果単独で探索実装を採否決定しない。
同じ条件・seedで各featureを独立に調整し、調整後master対調整後featureの対局結果で判断する。
また、#75のfinal.paramsをmasterへ適用しない。
