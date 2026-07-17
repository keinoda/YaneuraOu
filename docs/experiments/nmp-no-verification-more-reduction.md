# NMP検証探索削除 + reduction増加

## 実装

- ブランチ: `feature/nmp-no-verification-more-reduction`
- 初回実装の基点: `master@9a349509`
- 現在の比較基点: `master@dca723e5`（`nmpMinPly`初期化修正後）
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

### 修正版比較（正本）

- テスト: [ShogiBench #71](https://shogibench.fly.dev/test/71/)
- 状態: ユーザー判断で0局のまま停止。再開しない
- dev: `feature/nmp-no-verification-more-reduction@0631ed57`
- base: `master@dca723e5`
- 評価関数: `danbo-v16-progress` (`674A1218`)
- 条件: `8.0+0.08`, Threads=1, Hash=64MB, ponder off
- 開始局面集: `yaneuraou2025_ply24_shogi_sfen.epd`
- SPRT: Elo `[0.00, 4.00]`, `alpha=0.05`, `beta=0.10`
- workload size: 32

base/devとも未初期化動作を含まないため、固定値SPRTを再度行うなら#71の比較条件が
正しい。ただし、ユーザー判断でSPSA試験を先行するため0局のまま停止しており、
#71は再開しない。

### 初期化修正前の比較（参考値）

- テスト: [ShogiBench #68](https://shogibench.fly.dev/test/68/)
- 状態: 削除済み・参考記録（復元しない）
- dev: `feature/nmp-no-verification-more-reduction@a34962c1`
- base: `master@9a349509`
- 評価関数: `danbo-v16-progress` (`674A1218`)
- 条件: `8.0+0.08`, Threads=1, Hash=64MB, ponder off
- 開始局面集: `yaneuraou2025_ply24_shogi_sfen.epd`
- SPRT: Elo `[0.00, 4.00]`, `alpha=0.05`, `beta=0.10`
- workload size: 32
- 局数: 1,808
- W/L/D: `706 / 738 / 364`（dev視点）
- 最終LLR: `-0.54`（境界未到達）
- Elo: `-6.15 ± 14.06` (95%)

#66と同じ条件で作成したが、baseだけが後述の未初期化動作を含む。このため
#68は最終判断に使わず、参考値としてのみ保存する。

### base側NMP初期化の注意

`master@9a349509`では、upstreamのNMP rollback (`436b1174`) が
`nmpMinPly`のメンバーと参照を復活させた一方、`c641394d`で
`#if STOCKFISH`内へ移された初期化を復活させていない。通常のやねうら王
ビルドでは最初のNMP条件で未初期化値を読む。

devは#4として`nmpMinPly`自体を削除するため、#68はbaseだけに未定義動作が
残る非対称な比較になっている。初期化修正は`master@dca723e5`へ直接反映し、
#4+#5ブランチにも同masterを取り込んだ。以後の比較は#71を正本とする。

## 再SPSA後の最終評価

ShogiBenchのSPSA経路試験#75が完了した後、本ブランチに対して同じ148項目の
軽量SPSAを行う。軽量SPSAは経路と傾向の確認であり、結果をmasterへ反映しない。
有望な場合だけ本調整規模のSPSAへ進み、学習に使用していない対局で現行masterと
比較する。masterへの反映は、結果提示後にユーザーから明示的な許可を得た場合に限る。
