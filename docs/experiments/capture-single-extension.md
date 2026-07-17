# 駒取り手の多重singular extension抑制

## 実装

- ブランチ: `codex/capture-single-extension-master`
- 基点: `master@71fdb38d`
- 実装commit: `6c3acd5e`
- 元実装:
  - [yaneurao/YaneuraOu #328](https://github.com/yaneurao/YaneuraOu/pull/328)
  - [upstream commit `db295b89`](https://github.com/yaneurao/YaneuraOu/commit/db295b894df4fe685bcacdee434c0312d2d8826a)
- 変更:
  - 駒を取るsingular moveは1段だけ延長
  - 駒を取らないsingular moveは従来どおり最大3段まで延長
  - 条件を純粋関数に分け、4ケースを`static_assert`で検証

## ローカル検証

- NNUE tournamentビルド成功
- `usiok`を確認
- `git diff --check`成功

## ShogiBench 固定値SPRT

- テスト: [ShogiBench #66](https://shogibench.fly.dev/test/66/)
- 状態: 完了・第1段階は負け（エラーなし）
- dev: `codex/capture-single-extension-master@6c3acd5e`
- base: `master@71fdb38d`
- 評価関数: `danbo-v16-progress` (`674A1218`)
- 条件: `8.0+0.08`, Threads=1, Hash=64MB, ponder off
- 開始局面集: `yaneuraou2025_ply24_shogi_sfen.epd`
- SPRT: Elo `[0.00, 4.00]`, `alpha=0.05`, `beta=0.10`
- LLR境界: `[-2.251292, 2.890372]`
- workload size: 32
- 局数: 3486
- W/L/D: `1273 / 1431 / 782`（dev視点）
- pentanomial: `288 / 283 / 702 / 239 / 231`
- 最終LLR: `-2.336791`

### 第1段階の判定

現行danbo-v16調整値へこの変更だけを差し込む条件では、Elo `[0,4]`の
改善仮説を支持せず下側境界に達した。これは固定値でのdrop-in効果の判定であり、
実装アイデアそのものの最終不採用判定ではない。

base/dev双方は同じNMP rollback実装を持つため、別途判明した`nmpMinPly`の
未初期化不整合はこの比較では対称である。

## 再SPSA後の最終評価

未実施。base/dev双方を同一評価関数・同一条件・同一予算で再SPSAし、
調整に使用していない対局で最終採否を判定する。それまではブランチを保持する。
総合判断で不採用となった場合は、ユーザー方針に従いブランチを削除する。
