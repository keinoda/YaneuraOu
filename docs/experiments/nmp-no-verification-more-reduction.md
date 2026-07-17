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

- テスト: [ShogiBench #68](https://shogibench.fly.dev/test/68/)
- 状態: 承認待ち（2026-07-17作成）
- dev: `feature/nmp-no-verification-more-reduction@a34962c1`
- base: `master@9a349509`
- 評価関数: `danbo-v16-progress` (`674A1218`)
- 条件: `8.0+0.08`, Threads=1, Hash=64MB, ponder off
- 開始局面集: `yaneuraou2025_ply24_shogi_sfen.epd`
- SPRT: Elo `[0.00, 4.00]`, `alpha=0.05`, `beta=0.10`
- workload size: 32

#66と同じ条件で作成した。この結果が負けまたは不明瞭でも、それだけで
不採用としない。

### base側NMP初期化の注意

`master@9a349509`では、upstreamのNMP rollback (`436b1174`) が
`nmpMinPly`のメンバーと参照を復活させた一方、`c641394d`で
`#if STOCKFISH`内へ移された初期化を復活させていない。通常のやねうら王
ビルドでは最初のNMP条件で未初期化値を読む。

devは#4として`nmpMinPly`自体を削除するため、#68は「現行masterへ#4+#5を
差し込む実用効果」を測れるが、tanuki原実験の純粋な再現ではなく、この
未初期化不整合を解消する効果も含む。#4+#5を最終不採用にする場合も、
初期化だけの修正は別ブランチで評価する。

## 再SPSA後の最終評価

base/dev双方でNMP関連パラメータを同条件で再SPSAし、学習に使用していない
対局で最終採否を判定する。
