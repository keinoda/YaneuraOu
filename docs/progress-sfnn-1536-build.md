# progress SFNN 1536 エンジンの評価関数とビルド設定(再現手順)

最終更新: 2026-07-03(V9.60取り込み後も評価値一致・book仕様の全検証合格を確認済み)

本書は、rshogi / nnue-pytorch 系で学習した SFNN(PSQTなし・進行度バケット・FT1536)評価関数を
YaneuraOu に載せた構成を、後から同一挙動で再現するための記録。
本構成には評価関数の特定の版に紐づく旧運用名があったが、
構成自体は評価関数の版に依存しないため、本書は構成名 "progress SFNN 1536" で記述する。

## 0. オリジナルのビルド記録(確定情報)

過去のビルドログにより、オリジナルは2系統あったことが確定している:

1. **軽量 image**(private image、タグ名は省略): バイナリはビルドせず、
   ビルド済みバイナリ(SHA `34bb5c68…`)を private context 経由で COPY。
   設定は旧形式 `LS_BUCKET_MODE progress8kpabs` / `LS_PROGRESS_COEFF eval/progress.bin`。
2. **full image**(private image、タグ名は省略): iShogi リポジトリの
   `docker/v9.42-private/Dockerfile` 内で、本リポジトリの **commit `b593284a`
   (= sfnnwop1536-progress-v941 先端)** から下記 §2 のコマンドでビルド。
   NNUE header mismatch を warning 継続化する patch も **Dockerfile 内で適用**していた
   (§2 の必須パッチと同内容)。検証は ProgressFilePath / FV_SCALE 28 で readyok 確認。

また `YANEURAOU_ENGINE_NNUE_SFNNwoP1536_V2` を progress8kpabs 系 branch からビルドした
形跡もあるが、この nn.bin では FileReadError となり**最終採用ルートではない**(§5 参照)。

## 1. 評価関数ファイル

| ファイル | SHA256 | 内容 |
|---|---|---|
| `eval/nn.bin` | `ad7818250d38ead343f181e7ca56704fdc0a382ccef4e446e6bdb05e849828e8` | NNUE本体(約116MB) |
| `eval/progress.bin` | `d77f47e874558d42fa2d87d173de3aba054eef51bcca9c1fc9f3a8daf93630d8` | 進行度重み f64[81][fe_old_end](約1MB) |

- nn.bin のアーキテクチャはヘッダに平文で入っており、次で確認できる:

  ```bash
  head -c 4096 nn.bin | strings | head -1
  # Features=HalfKaHmMerged(Friend)[73305->1536x2],Network=...,fv_scale=28
  ```

- 構成: HalfKaHmMerged 73305→1536×2、その後 16→30(=15×2 の二乗ペア)→32→1、
  LayerStack 9バケット、fv_scale=28。
- **バケット選択は玉位置(k3k3)ではなく進行度**。本リポジトリでは
  `source/tanuki_progress.cpp` の `Tanuki::Progress::LayerStackIndex()` が
  k3k3 の9分岐を置換する実装になっている(edition 名には現れないので注意。
  外部の系統では同じ分割を "progress8kpabs" と呼ぶ)。

## 2. ビルド設定

- ビルド元: **`master`(2026-07-03 の統合以降が正本。upstream V9.60 取り込み済み、マージコミット b5d9a4fb)**。歴史的には commit `b593284a`
  (旧ブランチ `sfnnwop1536-progress-v941` 先端)が本構成の旧運用名でのビルド元で、
  その内容 + version 警告化 + 定跡repetition回避が master へ統合済み
  (マージコミット 124bba44)。version 警告化パッチも統合済みのため、
  **master からのビルドでは追加パッチ不要**。
- ビルドコマンド(Linux x86_64 / AVX512VNNI):

  ```bash
  cd source
  make -j"$(nproc)" tournament \
    YANEURAOU_EDITION=YANEURAOU_ENGINE_SFNN_halfkahm2_1536_15_32_k3k3 \
    TARGET_CPU=AVX512VNNI \
    COMPILER=clang++ \
    PYTHON=python3 \
    TARGET=<出力パス>
  ```

  - edition 名を Makefile が Python ジェネレータに渡し、
    `architectures/SFNN_halfkahm2_1536_15_32_k3k3.h` を動的生成する。
  - id name は `YaneuraOu NNUE 9.60git 64AVX512VNNI TOURNAMENT`(V9.60取り込み後)、
    `FV_SCALE` の default は 28 になる。

- **必須パッチ(version 警告化)**: この nn.bin は NNUE ヘッダの version が
  `2062757665`(ソース側の kVersion は `2062757654`)のため、素のソースでは
  `FileMismatch` で読み込みを拒否する。`source/eval/nnue/evaluate_nnue.cpp` の
  `ReadHeader` を「警告を出して続行」に変更する(レイアウト互換のため実害なし):

  ```
  info string NNUE header version mismatch: expected ... got ... (continuing anyway)
  ```

  当時のビルドブランチのコミット「NNUEヘッダのversion不一致を警告のみで続行する」参照。
  hash mismatch の warning も同様に無害(既定で警告のみ)。

## 3. 実行時設定(eval_options.txt)

エンジン自身は eval_options.txt を読まない。呼び出し側(アプリ/スクリプト)が
setoption に変換する運用ファイルで、内容は次の2行:

```
ProgressFilePath eval/progress.bin
FV_SCALE 28
```

### LS_BUCKET_MODE

SFNNwoPSQT ビルドでは、レイヤースタックの選択方式を `LS_BUCKET_MODE` で実行時に選ぶ。

- `auto`(既定): `isready` で `ProgressFilePath` の読み込みに成功した場合は
  `progress8kpabs`、失敗した場合は `kingrank9` として動作する。既存の
  eval_options.txt が `ProgressFilePath eval/progress.bin` を設定する運用では、
  従来どおり進行度バケットが使われる。
- `progress8kpabs`: `Tanuki::Progress::LayerStackIndex()` による 0..7 の8分岐。
  `LayerStacks >= 8` が必要。
- `kingrank9`: 双方の玉の段による 0..8 の9分岐。`LayerStacks >= 9` が必要。

`SFNN_..._ls<N>`、`SFNN_..._k3k3`、`SFNN_..._king3_by_king3` の末尾トークンは、
nn.bin のレイアウト、つまり格納される `LayerStacks` 数を指定する。これは選択方式の指定ではない。
選択方式は常に `LS_BUCKET_MODE` で決まる。不整合な組み合わせでは `isready` 時に warning を出し、
範囲外の `network[]` を参照しない方式へフォールバックする。

## 4. 再現検証の方法

再ビルドしたバイナリが既存バイナリと同一挙動であることは、次で確認する
(2026-07-03 に3局面とも score 完全一致を確認済み):

1. `usi` 出力の diff(オプション一覧・default 値が一致すること)
2. `isready` → version/hash mismatch の warning を経て `readyok`(約1秒)
3. 同一局面での評価比較: `Threads=1`・`USI_Hash=64`・`USI_OwnBook=false` で
   `go nodes 1000` の score cp を比較する(**depth 指定ではなく nodes 指定**。
   USI テストは PTY で対話し、`go` の後は `bestmove` を待ってから `quit` を送る)

## 5. 紛らわしい別系統(混同注意)

- `SH11235/YaneuraOu` の `feat/accumulator-caches-progress8kpabs` ブランチは
  この機能系の原典だが **v9.22 ベース**で、バケット指定が
  `LS_BUCKET_MODE progress8kpabs` + `LS_PROGRESS_COEFF` という別オプション体系。
  現行の本構成バイナリ(9.41git・ProgressFilePath 体系)とは別系統なので、
  差し替えビルドには使わない。過去記録でも `SFNNwoP1536_V2` ルートはこの nn.bin で
  FileReadError となり不採用。2026-07-03 の実測でも評価値が大きく乖離した。
- 768 系(FT次元 768。`archive/sfnn-halfka-hm-768-7-32-progress-v940` 等の
  アーカイブタグに保全)は nn.bin(1536)と互換がない。

## 6. 定跡千日手回避(book repetition)

`source/book/book.cpp` の `probe_impl` で、対局履歴に照らして repetition になる定跡候補を
次の規則で扱う(2026-07-03 確定仕様。master に統合済み):

1. **反則負け(連続王手の千日手)・劣等局面**になる手: 無条件除外
2. **BookEvalDiff(品質)**: 元の定跡値で判定(千日手化による繰り上がりで質の低い手が
   採用されるのを防ぐ)
3. **BookEvalLimit(下限)**: 実効値(通常探索側と同じ drawValueTable の値)で判定。
   千日手化で下限を割った手は指さず、候補が尽きれば通常探索へフォールバック。
   千日手手を拾いたい運用では BookEvalBlack/WhiteLimit を負に設定する
4. **最終選択**: 置換手は残候補中の実効値最大の場合のみ採用(同値なら通常手優先)。
   multipv 表示・返却値は実効値で、置換は
   `info string BookRepetition : <move> book_value X -> Y (draw等)` として可視化される

検証済みの代表動作(DrawValue=-2、cp→内部値変換により表示は -1):
- 最善(60)が千日手・次善(59)が diff 内 → 次善を採用
- 最善(50)が千日手・次善(40)が diff(5)外 → 探索へフォールバック(繰り上がり防止)
- DrawValueBlack=100 なら千日手手(実効90)を採用(千日手が得な設定)

配置慣行: エンジンディレクトリに `<name>-YaneuraOu-avx512vnni` + `eval/`
(nn.bin / progress.bin はハードリンク可)+ `eval_options.txt` + `book/` +
`SHA256SUMS`(sha256sum で生成)。
