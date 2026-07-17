# NMP検証探索削除 + reduction増加

## 実装

- ブランチ: `feature/nmp-no-verification-more-reduction`
- 基点: `master@9a349509`
- 元実装:
  - [nodchip/tanuki- #4](https://github.com/nodchip/tanuki-/pull/4)
  - [nodchip/tanuki- #5](https://github.com/nodchip/tanuki-/pull/5)
- 変更:
  - YaneuraOu探索から`nmpMinPly`と高深度のNMP検証探索を削除
  - NMPのdynamic reductionを`7 + depth / 3`から`7 + depth / 2`へ変更
  - unproven mate scoreは`beta`に丸め、mate scoreのまま返さない

generic Stockfish探索は変更せず、`yaneuraou-engine`だけを対象とする。

## tanuki側の実測

### #4 NMP検証探索の削除

- Elo: `+7.78 ± 5.49` (95%)
- SPRT: `[0.00, 4.00]`, LLR `2.90` (`-2.25`, `2.89`)
- 局数: `14,600` (`7,173 / 6,846 / 581`)
- 条件: `8.0+0.08`, Threads=1, Hash=16MB

### #5 NMP reductionの増加

#4を取り込んだブランチ上で試験されている。

- Elo: `+7.56 ± 5.35` (95%)
- SPRT: `[0.00, 4.00]`, LLR `2.92` (`-2.25`, `2.89`)
- 局数: `15,172` (`7,445 / 7,115 / 612`)
- 条件: `8.0+0.08`, Threads=1, Hash=16MB

## ローカル検証

- 日付: 2026-07-17
- ビルド:

```sh
make -C source -j8 \
  TARGETDIR=/tmp/yaneuraou-nmp-build.ED6FGj \
  OBJDIR=/tmp/yaneuraou-nmp-build.ED6FGj/obj \
  YANEURAOU_EDITION=YANEURAOU_ENGINE_NNUE \
  TARGET_CPU=APPLEM1 COMPILER=clang++ PYTHON=python3 tournament
```

- 結果: 成功(Mach-O arm64)
- USI起動: `usiok`を確認
- 静的確認:
  - `yaneuraou-engine`内の`nmpMinPly`参照は0件
  - `Depth R = 7 + depth / 2;`は1件
  - `git diff --check`成功

## ShogiBench 固定値SPRT

未実施。この結果が負けまたは不明瞭でも、それだけで不採用としない。

## 再SPSA後の最終評価

base/dev双方でNMP関連パラメータを同条件で再SPSAし、学習に使用していない
対局で最終採否を判定する。
