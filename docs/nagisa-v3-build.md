# NAGISA_V3 ビルド・配布

## エンジン識別情報

- エンジン名: `NAGISA_V3`
- 作者名: `nagisa`
- バージョン: `9.60`
- NNUE構成: `HalfKA_hm2 1024x16x64 / LayerStack 9`

## 固定ビルド設定

`source/Makefile`の`nagisa-v3`ターゲットは、次の配布用設定を固定する。

```text
YANEURAOU_EDITION=YANEURAOU_ENGINE_SFNN_halfkahm2_1024_15_64_ls9
PYTHON=python3
COMPILER=clang++
target=tournament
EXTRA_CPPFLAGS=-DHASH_KEY_BITS=128 -DTT_CLUSTER_SIZE=4 -DUSE_LAZY_EVALUATE
```

CPU向けの命令セットだけを`TARGET_CPU`で指定する。配布用ビルドでは上記の追加フラグを
外さない。

## 評価ファイル

`EvalDir`には次の3ファイルを置く。

```text
eval/
  nn.bin
  progress.bin
  eval_options.txt
```

`LS_PROGRESS_COEFF`の既定値は`progress.bin`であり、ファイル名だけの場合は`EvalDir`
を基準に解決される。`<internal>`は利用できない。通常の配布設定は次のとおりとする。

```text
FV_SCALE 28
LS_BUCKET_MODE progress8kpabs
```

配布用`nn.bin`には、相入玉局面でslot 8だけを追加学習した9-slot評価関数を使う。
共有部とslot 0–7が追加学習前の基準ネットとbit一致し、slot 8だけが変化したことを
manifestで確認する。`progress8kpabs`を既定動作とし、通常利用では学習済みのslot 0–7だけを
使う。`progress8ek`を明示した場合だけ、双方の玉がそれぞれ五段目以上へ進出した局面を
追加学習済みのslot 8へ送る。未学習のslot 8を持つ別の9-slot評価関数へ差し替えない。

## USIオプション表示

開始局面誘導、進行度連動の時間管理、先後別の時間管理、ponder miss時の時間延長、
定跡の千日手対策に関するオプションは、USIの`option`行に出力しない。
内部登録は維持するため、既存の設定ファイルや`setoption`からは利用できる。

`FullTimeMode`、`LS_PROGRESS_COEFF`、`LS_BUCKET_MODE`はUSIオプションとして表示する。

## Apple Silicon

M1以降のMacでは、リポジトリルートから次を実行する。

```bash
make -C source -j"$(sysctl -n hw.ncpu)" nagisa-v3 TARGET_CPU=APPLEM1
```

実行ファイルは`source/YaneuraOu-by-gcc`に生成される。配布時はCPU種別が分かる名前へ
コピーし、ビルド元commitとSHA-256を記録する。

## Windows

GitHub Actionsの`Build NAGISA_V3 Windows` workflowは、同じ`nagisa-v3`ターゲットを
使い、次の2種類を生成する。

- `NAGISA_V3-Windows-AVX2.exe`
- `NAGISA_V3-Windows-SSE42.exe`

各artifactには実行ファイルのほか、ビルドログ、USI起動確認、ビルド引数、
SHA-256 checksumを含める。workflowは対象branchをpushしたcommitに対して実行し、
正式配布には最終SPSA値を適用したcommitのartifactだけを使う。

## SPSA結果の適用

最終結果を適用する前に、入力が全146項目を含むことをdry-runで検査する。

```bash
python3 script/spsa/apply_params.py /absolute/path/to/final.params --dry-run
python3 script/spsa/apply_params.py /absolute/path/to/final.params
```

途中再開用の`state.params`を使わない。Q8対象9項目は256倍された整数をそのまま適用し、
再度256で割らない。適用後はtuneビルドのobjectを再利用せず、配布用バイナリを新しく
ビルドする。採用したSPSA run、入力paramsのSHA-256、適用commitを`BUILD_SOURCE.txt`
へ記録する。

## 配布物

配布archiveは少なくとも次を含める。

```text
NAGISA_V3/
  README.md
  BUILD_SOURCE.txt
  LICENSE
  SHA256SUMS
  NAGISA_V3-<OS>-<CPU>
  eval/
    nn.bin
    progress.bin
    eval_options.txt
```

`BUILD_SOURCE.txt`には、source repository、branch、commit、完全なビルド設定、NNUEの
生成元、追加学習のinvariance manifest、SPSA run、`nn.bin`と`progress.bin`のSHA-256を
記録する。`SHA256SUMS`には
archive内の配布ファイルを列挙する。定跡を含めるかはREADMEに明記し、評価関数だけの
パッケージへ暗黙に定跡を追加しない。

## 配布前検証

1. 最終commitからApple Silicon、Windows AVX2、Windows SSE4.2をビルドする。
2. `usi`でエンジン名、作者名、版、既定bucket mode、表示・非表示オプションを確認する。
3. 同梱する`eval`で`isready`が`readyok`まで完走することを確認する。
4. `Threads=1`、固定Hash、定跡無効、固定nodesで初期局面と代表局面を探索する。
5. `progress8ek`を同梱する場合は、相入玉境界局面と非相入玉局面のrouting・評価を確認する。
6. Windows AVX2版とSSE4.2版を実際のWindows PCで起動し、`usi`、`isready`、固定nodes探索を確認する。
7. 配布archiveを展開した状態でSHA-256を照合し、READMEの手順だけで起動できることを確認する。
