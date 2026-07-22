# NAGISA_V3 ビルド

## 固定設定

`source/Makefile` の `nagisa-v3` ターゲットは、次の配布用設定を固定する。

```text
YANEURAOU_EDITION=YANEURAOU_ENGINE_SFNN_halfkahm2_1024_15_64_ls9
PYTHON=python3
COMPILER=clang++
target=tournament
EXTRA_CPPFLAGS=-DHASH_KEY_BITS=128 -DTT_CLUSTER_SIZE=4 -DUSE_LAZY_EVALUATE
```

CPU向けの命令セットだけを `TARGET_CPU` で指定する。

## Apple Silicon

M1以降のMacでは、リポジトリルートから次を実行する。

```bash
make -C source -j"$(sysctl -n hw.ncpu)" nagisa-v3 TARGET_CPU=APPLEM1
```

実行ファイルは `source/YaneuraOu-by-gcc` に生成される。

## Windows

GitHub Actionsの `Build NAGISA_V3 Windows` workflowは、同じ `nagisa-v3`
ターゲットを使い、次の2種類を生成する。

- `NAGISA_V3-Windows-AVX2.exe`
- `NAGISA_V3-Windows-SSE42.exe`

各artifactには実行ファイルのほか、ビルドログ、USI起動確認、ビルド引数、
SHA-256 checksumを含める。
