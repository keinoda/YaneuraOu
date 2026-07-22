# 探索パラメーターのSPSAチューニング

`make tune` でビルドしたやねうら王は、V940由来の探索パラメーター146個を
USI `spin` オプションとして公開する。現行探索で使わないNMP検証探索用の2項目は
対象に含めない。通常ビルドと大会用ビルドでは同じ項目が`constexpr`のままになり、
USIオプションにはならない。

## 1. tuneビルド

ビルドフラグが異なる成果物を同じ `source/obj` へ混在させない。normal、tournament、
tuneは別々のcloneまたは別々の作業ディレクトリでビルドする。

Apple Silicon MacでNAGISA_V3の1024x16x64評価関数を使う例:

```bash
make -C source -j"$(sysctl -n hw.ncpu)" tune \
  YANEURAOU_EDITION=YANEURAOU_ENGINE_SFNN_halfkahm2_1024_15_64_ls9 \
  TARGET_CPU=APPLEM1 \
  COMPILER=clang++ \
  PYTHON=python3 \
  'EXTRA_CPPFLAGS=-DHASH_KEY_BITS=128 -DTT_CLUSTER_SIZE=4 -DUSE_LAZY_EVALUATE'

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

出力形式は次の146行で、`[[NOT USED]]` 行は追加しない。

```text
name,int,default,min,max,c_end,0.002
```

`c_end` は `(max - min) / 20`。生成時に対象2ファイルの件数、名前の一意性、
既定値と範囲も検証される。

次の9項目は、小さい係数の変化を整数化で失わないようにQ8固定小数点を使う。
paramsとUSI optionに現れる値は実際の値を256倍した整数で、たとえば
`MovePicker_quiet_score_1=576`は係数`2.25`を表す。

- `Search_static_evaluation_1a_1`
- `Search_static_evaluation_1a_2`
- `Search_static_evaluation_1a_3`
- `Search_static_evaluation_1a_4`
- `Search_static_evaluation_2a_1`

- `MovePicker_low_ply_history_score_1`
- `MovePicker_quiet_score_1`
- `MovePicker_quiet_score_2`
- `MovePicker_capture_score_1`

ソースへ焼き込む値もQ8の整数値であり、これら9項目をさらに256で割ってから
`apply_params.py`へ渡してはならない。静的評価差の式ではclampの上下限と加算値をQ8で
計算し、main historyとpawn historyの係数もQ8として、積をQ16から整数へ戻す。
MovePickerでは採点式をQ8のまま合算してから整数スコアへ戻す。既定値ではどちらも
Q8化前と同じ整数結果になる。

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
0を設定できると整数除算ゼロの未定義動作になるため、本実装では下限を1に狭める。
既定値は変更しないので、normal/tournamentビルドの探索には影響しない。

- `aspiration_window_2`
- `Search_futility_1_5`
- `Search_Continuation_history_based_pruning1_3`
- `Search_Extensions1_3`
- `Search_Extensions2_1`
- `Search_Decrease_reduction_for_PvNodes_3_2`
- `Search_fail_low_quiet_bonus_2`
- `MovePicker_good_capture_see_1`

## 4. ShogiBenchからの実行

ShogiBenchはGitHub上のcommitを取得してワーカーでビルドする。ローカルだけで
変更しても利用できないため、対象ブランチの`origin`へのpush完了後にSPSAチューニングを
作成する。

`/tune/new/`で次を指定する。

1. エンジンは`YaneuraOu-nagisa`、ブランチは調整対象を選ぶ。正本を調整する場合は
   `master`を選ぶ。
2. ビルドはcustomにし、通常ビルドではなく`make tune`相当になるよう、
   build argsに`tune`を含める。
3. `python3 script/spsa/gen_params.py`の出力全146行をSPSA parametersへ渡す。
4. wrapperはrshogi、mappingは`NONE`を使う。YO形式の名前がUSI option名と
   一致するため、名前変換は不要である。
5. 評価関数、開始局面集、時間制御、seed、batch、総ペア数を実験計画どおりに指定し、
   作成後にapproverの承認を受ける。

NAGISA_V3の1024x16x64評価関数をAVX512ワーカーで調整するbuild args例:

```text
YANEURAOU_EDITION=YANEURAOU_ENGINE_SFNN_halfkahm2_1024_15_64_ls9 PYTHON=python3 TARGET_CPU=AVX512 COMPILER=clang++ tune 'EXTRA_CPPFLAGS=-DHASH_KEY_BITS=128 -DTT_CLUSTER_SIZE=4 -DUSE_LAZY_EVALUATE'
```

`TARGET_CPU`は実際に割り当てるワーカーのCPUに合わせる。AVX512非対応CPUへ
この例をそのまま使用しない。開始後は詳細ページで、rshogi wrapper、146 parameters、
期待したcommit SHA、network、開始局面集、build argsを確認する。

新規runでは`stats.csv`と`values.csv`由来のスコア差・パラメーター推移が
ShogiBenchへ保存される。履歴保存対応より前に完走したrunの軌跡は遡及生成されない。
完走した`final.params`はShogiBenchからソースへ自動適用されない。次節のdry-runと
別途の採用判断を経て、明示的に焼き込む。

## 5. 結果の焼き込みと検証

まず書き込みなしで全146名と入力形式を検証する。

```bash
python3 script/spsa/apply_params.py /absolute/path/to/final.params --dry-run
```

完了したrunの最終 `.params` であることを確認してから適用する。途中再開用の
`state.params` を最終結果と取り違えない。

```bash
python3 script/spsa/apply_params.py /absolute/path/to/final.params
```

rshogiは`int`型パラメーターでもSPSA内部の連続値θを小数のまま
`final.params`へ保存する。`apply_params.py`は小数値が元の範囲内であることを
検証してから、本家の`int(round(...))`と同じく最近傍整数へ確定する。
ちょうど0.5の場合は0から遠い側へ丸め、丸めた項目数を警告として表示する。
小数を保持する`state.params`や`final.params`自体は書き換えない。

既知の146名がactive行としてすべて揃った場合だけ、2つのソースファイルにある
`TUNABLE_PARAM` の既定値を書き換える。未知名と未知の `[[NOT USED]]` 行は警告して
無視するが、重複名、不正値、既知名の欠落、範囲定義の不一致があれば書き込まない。

焼き込み後はtuneビルドのオブジェクトを再利用せず、新しいcloneまたは分離した
ビルドディレクトリでnormalビルドを作る。既定値benchとUSIオプション非公開を確認し、
そのバイナリをShogiBenchのSPRTで検証する。

## 6. パラメーターの追加

1. 対象リテラルを、別の物理行に置いた
   `TUNABLE_PARAM(name, default, min, max)` 1行へ置き換える。
2. 探索式から変数を直接参照できる場合はコピーを作らない。
3. 配列などコピー型の派生値が必要な場合は、normalビルドでは
   `TUNE_CONSTEXPR` にし、`#if defined(ENABLE_TUNE)` で囲んだ `isready` 転写を追加する。
4. `gen_params.py` の期待件数とテストを更新し、normal/tournament/tuneを分離ビルドする。
5. normalとtournamentの固定深さbenchが変更前と完全一致し、tuneビルドでは
   `setoption` 後に探索結果が変化することを確認する。

現実装で `isready` 転写が必要なのは `conthist_bonuses_1` から `_6` の1ブロックだけで、
`update_correction_history_nonPawnWeight_1` を含む残り140項目は直接参照である。

## 7. 旧パラメーター名との互換性

`YaneuraOuWorker_clear1_1/2/3` と `update_all_stats_1c_6` は、suisho10時代には
`[[NOT USED]]` の旧実体として扱われたが、V940では同じ名前が別実体の現役パラメーターに
再利用されている。ケースBのmapping経由やrshogi形式との相互移植では、名前だけで同一視せず
対応するソース位置と意味を再確認する。

また、fuuppi側だけにある旧別名
`Search_nullmove_1/2` と
`Search_Decrease_reduction_for_PvNodes_6_1/2` は追加しない。
V940の `Search_nullmove_1_1/_1_3` と
`Search_Decrease_reduction_for_PvNodes_6a_2/_6a_3` が対応する実体を扱う。

## 8. 支援スクリプトのテスト

```bash
python3 -m unittest discover -s script/spsa -p 'test_*.py' -v
```

テストは一時ディレクトリだけを書き換え、実リポジトリの146名契約は読み取り専用で確認する。
