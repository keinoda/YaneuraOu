# 実行時SIGSEGVの調査記録 (2026-07-12)

対象: `claude/stochastic-ponder-immediate-moves-ef5xzl` の検証中に見つかった
2件のSIGSEGV。現行 `fab4935`、Ponder実装の異なる `6de7cab`、配布バイナリ、
upstream `9133c52` で再現し、Ponder変更とは独立している。

## A. isready前のposition

`position startpos` を `isready` より先に送ると、未ロードのNNUE networkを
`Position::set()` から参照してSIGSEGVになる。

正規のUSI手順ではGUIが `isready` と `readyok` を完了してから `position` を
送るため、実対局経路には該当しない。upstreamと同じ既存動作であり、今回の
Ponder修正ブランチでは変更しない。

## B. Position::UnitTestのスタック枯渇

2048次元NNUEでは `StateInfo` が約8.3KBとなる。`Position::UnitTest()` は
従来、次の自動配列を同じ関数内に持っていた。

- `StateInfo s[512]` が4本
- `StateInfo si[MAX_PLY]` が1本

Linux clang 18 + LTOではこれらが大きな関数フレームとなり、既定8MB stackで
関数進入時にSIGSEGVになった。同一バイナリを `ulimit -s unlimited` で実行すると
84 / 84件が合格するため、原因は評価計算やPonderではなくstack overflowである。

過去の87 / 87件合格記録はApple M1 + SFNN1536の結果であり、このLinux環境で
以前に同じUnitTestが通っていた事実はない。Apple clang 17では2048次元の
修正前コードでも8176KB stackで84 / 84件が合格し、同じ失敗は再現しなかった。
したがって、発生有無はコンパイラのframe配置にも依存する。

## 修正

UnitTest内の履歴配列を、既存の `StateList` (`std::deque<StateInfo>`) に変更した。
探索コードや通常の局面管理は変更していない。

- 千日手テスト: 512局面から実使用数の4局面へ変更
- SEEテスト: 512局面から実使用数の4局面へ変更
- null moveテスト: 512局面から実使用数の1局面へ変更
- partial keyテスト: `MAX_PLY + 1` 局面をheap確保
- random playerテスト: 512局面をheap確保

partial keyテストは従来 `si[MAX_PLY]` に対して `si[j + 1]` を参照し、最大添字が
`MAX_PLY` になる確保数不足もあった。手順と添字は維持し、確保数を
`MAX_PLY + 1` に合わせた。

## 検証

- SFNN `halfkahm2_2048_15_64_ls9` / APPLEM1 / clang++ / LTO: build成功
- 既定stack 8176KB、2048次元NNUE: 84 / 84 passed、exit 0
- 同条件の `unittest random_player_loop 1`: 85 / 85 passed、exit 0
- `script/ponderhit_regression_test.py`: 全15経路合格、exit 0
- `isready` 前の `position startpos`: exit 139のまま (意図どおり変更対象外)

Linux環境でコード修正前にUnitTestだけを継続する場合は、hard limitがunlimitedで
あることを確認したうえで `ulimit -s unlimited` を前置すればよい。環境再作成は
不要である。
