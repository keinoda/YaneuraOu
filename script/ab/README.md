# script/ab — 探索部改善のA/Bテスト基盤

`docs/search-improvement-plan.md` の改善ブランチ群 (`claude/search-ab/*`) を
統計的に検証するためのツール一式。

## 構成

| ファイル | 役割 |
|---|---|
| `ab_match.py` | USIエンジン同士の自己対局ハーネス。SPRT判定・先後入替ペア対局・並列実行・投了/宣言勝ち/最大手数の裁定。cshogiがあれば千日手/連続王手千日手/詰みも厳密判定 |
| `make_openings.py` | エンジンのMultiPVを使って互角開始局面集を生成 |
| `openings.sfen` | 同梱の開始局面集 (**駒得エンジンで生成した暫定版**。本測定では強い評価関数で生成し直すこと) |
| `build_branches.sh` | ブランチ群を git worktree で一括ビルドして `build/ab/*.bin` に配置 |

## クイックスタート

```bash
# 0) (推奨) 厳密なルール判定のため cshogi を導入
pip install cshogi

# 1) ベースとテスト対象ブランチをビルド (NNUE / AVX2)
script/ab/build_branches.sh -e YANEURAOU_ENGINE_NNUE -a AVX2 \
    claude/yaneuraou-search-optimization-qxvzz0 \
    claude/search-ab/01-capture-futility

# 2) (推奨) 手元の評価関数で開始局面集を生成し直す
python3 script/ab/make_openings.py \
    --engine build/ab/claude_yaneuraou-search-optimization-qxvzz0.bin \
    --eval-dir /path/to/eval --count 100 --plies 12 --nodes 200000 \
    --out script/ab/openings.sfen

# 3) SPRT対局 (base=engine1 vs test=engine2)
python3 script/ab/ab_match.py \
    --engine1 build/ab/claude_yaneuraou-search-optimization-qxvzz0.bin \
    --engine2 build/ab/claude_search-ab_01-capture-futility.bin \
    --eval-dir /path/to/eval \
    --byoyomi 1000 --concurrency 2 \
    --openings script/ab/openings.sfen \
    --sprt 0 5 --max-games 20000
```

- `LLR >= +2.94` → **H1受理: 改善あり** (elo1=+5基準)。持ち時間を伸ばして追試 → master統合へ。
- `LLR <= -2.94` → **H0受理: 改善なし**。
- 進行中は 1行/局 で `W-L-D / elo±err / LLR` を表示。全対局は `ab_results.jsonl` に記録。

## 重要な注意

1. **評価関数は両者で完全に同一にする** (探索部のみの差を測る)。
2. **concurrencyはコア数の半分以下** (1エンジン=1スレッド設定時)。負荷でNPSが揺れると分散が増える。
3. NPSに影響する変更 (AB-01等) を `--nodes` 固定ノードで測ってはいけない (時間制御で測る)。
4. 短い秒読み (`--byoyomi 100` 等) は差が誇張/歪曲されることがある。判定は1秒以上を推奨し、
   採用前に長い持ち時間で追試する。
5. `--time 600000 --inc 2000` のような時計制も可 (`--byoyomi` と併用可)。
6. fork独自機能 (OpeningTarget / LS_PROGRESS) を使う場合は `--option` / `--option1/2` で
   `LS_PROGRESS_COEFF=... FV_SCALE=28` などを渡す。

## SPRTパラメータの目安

| 目的 | 設定 | 期待対局数の目安 |
|---|---|---|
| 通常の改善検証 | `--sprt 0 5` | 真+5eloなら ~3-8千局 |
| 微小改善/簡素化 | `--sprt 0 3` / `--sprt -3 1` | ~1-3万局 |
| 大きな変更の粗選別 | `--sprt 0 10` | ~1-2千局 |

## トラブルシューティング

- `readyok timeout` → EvalDirの指定ミス (エンジンバイナリのある場所からの相対 or 絶対パスで指定)。
- 対局が異常に長い → cshogi未導入だと千日手が最大手数まで続く。`pip install cshogi` を推奨。
- ワーカーが `restart engines` を繰り返す → エンジン単体を手で起動して `usi`→`isready` を確認。
