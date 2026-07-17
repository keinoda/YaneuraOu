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

### Q8移行直後の再SPSA

Q8化を検証する最初のrunに限り、全項目を元の既定値から調整し直さない。直前の
7,680ペアSPSAの小数最終値を丸めずに初期値として引き継ぎ、上記9項目だけその
小数値を256倍してQ8表現へ変換する。それ以外の項目も小数最終値をそのまま使い、同じ条件で再度
7,680ペアを実行する。

初期paramsを作るときはQ8対応ブランチの`gen_params.py`出力を土台にする。上記9項目は
初期値を256倍するだけでなく、Q8対応後の`min`、`max`、`c_end`を使う。旧paramsの
範囲や摂動幅を混ぜない。`apply_params.py`でソースへ焼き込んだ整数値や、その途中で
丸めた値を移行元にしてはならない。その他の項目も、直前runの小数最終値だけを初期値欄へ移し、
範囲と摂動幅はQ8対応ブランチが生成した値を維持する。

再SPSA後は、各項目について最終値とこの引き継ぎ初期値を比較する。Q8の9項目は
差分を256で割った実効係数でも確認し、丸めで消えていた小さい変化が実際に残ったかを
記録する。Q8以外の項目は前run最終値からの差分をそのまま確認する。

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
`master`へmergeしても利用できないため、`origin/master`へのpush完了後に
SPSAチューニングを作成する。

`/tune/new/`で次を指定する。

1. エンジンは`YaneuraOu-nagisa`、ブランチは`master`を選ぶ。
2. ビルドはcustomにし、通常ビルドではなく`make tune`相当になるよう、
   build argsに`tune`を含める。
3. `python3 script/spsa/gen_params.py`の出力148行をSPSA parametersへ渡す。
4. wrapperはrshogi、mappingは`NONE`を使う。YO形式の名前がUSI option名と
   一致するため、名前変換は不要である。
5. 評価関数、開始局面集、時間制御、seed、batch、総ペア数を実験計画どおりに指定し、
   作成後にapproverの承認を受ける。

SOJO/TSEC7評価とAVX512ワーカーで検証済みのbuild args例:

```text
YANEURAOU_EDITION=YANEURAOU_ENGINE_SFNN_halfkahm2_2048_15_64_ls9 PYTHON=python3 TARGET_CPU=AVX512 COMPILER=clang++ tune 'EXTRA_CPPFLAGS=-DHASH_KEY_BITS=128 -DTT_CLUSTER_SIZE=4 -DUSE_LAZY_EVALUATE'
```

`TARGET_CPU`は実際に割り当てるワーカーのCPUに合わせる。AVX512非対応CPUへ
この例をそのまま使用しない。開始後は詳細ページで、rshogi wrapper、148 parameters、
期待したcommit SHA、network、開始局面集、build argsを確認する。

新規runでは`stats.csv`と`values.csv`由来のスコア差・パラメーター推移が
ShogiBenchへ保存される。履歴保存対応より前に完走したrunの軌跡は遡及生成されない。
完走した`final.params`はShogiBenchからソースへ自動適用されない。次節のdry-runと
別途の採用判断を経て、明示的に焼き込む。

## 5. 結果の焼き込みと検証

まず書き込みなしで全148名と入力形式を検証する。

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

既知の148名がactive行としてすべて揃った場合だけ、2つのソースファイルにある
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
`update_correction_history_nonPawnWeight_1` を含む残り142項目は直接参照である。

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

テストは一時ディレクトリだけを書き換え、実リポジトリの148名契約は読み取り専用で確認する。

## 9. 導入時の検証実績

導入時にはbase、normal、tournament、tuneを分離してビルドし、次を確認した。

- normalとtuneの既定値探索はbaseと同じ`451934 nodes`
- tournamentは変更前後とも`316571 nodes`
- tuneビルドだけUSI `spin`が28件から176件へ増加し、増分148名がparamsと一致
- razoring、conthist、movepickの代表値を`setoption`すると探索結果が変化
- normalビルドの`unittest`は`84 / 84 passed`
- rshogiの直接SPSAで148件すべてが更新され、複数batchのrunが完走

ShogiBench経路は、検証時commit
`0920807bb101fa1ec17f21171e283765007efd81`を用いた
[#75](https://shogibench.fly.dev/tune/75/)で確認した。

- 開始局面集: `yaneuraou2025_ply24_shogi_sfen.epd`
- 評価関数: danbo-v16-progress (`674A1218`)
- 7,680ペア、15,360局、batch 48、seed 1、early stopなし
- 時間制御: `2.0+0.02`、DEV 1,000,000 NPS基準
- 全160 batchesを完走し、timeout 0、crash 0
- 7,511勝、7,395敗、454分で、plus/minus側に顕著な偏りなし
- `final.params`は148行、有限値、定義範囲内、min/max到達0件

#75はSPSA実行基盤の実証であり、得られた`final.params`はソースへ適用していない。
探索変更を比較するときは、masterとfeatureを同じ条件で個別にSPSA調整し、
調整後同士の対局結果を含めて採否を判断する。

### Q8固定小数点化の検証

`codex/tanuki-4-5-6`の`5ac71993`をbaseとして、Q8対応版と分離ビルドして確認した。

- normalとtuneの固定深さ15は、baseとQ8対応版がともに`345335 nodes`
- tournamentの固定深さ15は、baseとQ8対応版がともに`254432 nodes`
- Q8対象9項目は、tuneビルドのUSI `spin`に256倍した既定値・範囲で公開された
- 9項目を個別にQ8値で1だけ動かした固定深さ16探索は、全項目で既定値の
  `410918 nodes`から変化した
- SPSA支援スクリプトは`26 / 26 passed`、normalビルドの`unittest`は
  `84 / 84 passed`

速度は各局面250,000 nodes、4局面、1 threadの短いbenchを交互順で21組実行し、
外れ値を避けるため組ごとの速度差の中央値で比較した。tournamentは中央値`+5.065%`、
四分位範囲`+0.237%`から`+13.183%`で、Q8対応版が速い組は16/21だった。
tuneは中央値`+0.750%`、normalは中央値`-1.998%`だった。測定環境のばらつきが大きいため
高速化したとは断定しないが、実運用対象のtournamentでは速度低下を認めなかった。
