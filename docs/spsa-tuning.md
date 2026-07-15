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

V940の範囲をそのまま保持しているため、次の8項目は範囲に0を含む一方で除数として
使われる。0を設定すると除算エラーになるので、SPSAログの範囲張り付きとエンジン終了を
監視する。範囲を変更する場合は、V940正本からの仕様変更として別途判断する。

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
