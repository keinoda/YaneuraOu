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

## Linux独立検証 (53263ff, 2026-07-12)

修正コミット `53263ff` を、SIGSEGVを当初観測したLinux環境で独立に再検証した。

環境: Linux 6.18 / clang++ 18.1.3 + LTO / ld.lld / AVX512VNNI /
`YANEURAOU_ENGINE_SFNN_halfkahm2_2048_15_64_ls9` / stack soft limit 8192KB(既定) /
hard limit unlimited。cleanビルド成功(警告なし)。

| 項目 | 修正前(同環境での実測) | 修正後 53263ff |
|---|---|---|
| `unittest`(既定8192KB stack) | SIGSEGV, exit 139(fab4935・6de7cab・配布バイナリ・upstream 9133c52 全てで再現) | **84 / 84 passed, exit 0**(13.6s) |
| `unittest random_player_loop 1`(既定stack) | ―(進入時SIGSEGVのため到達不能) | **85 / 85 passed, exit 0**(`GamesOfRandomPlayer game 1` passed = `StateList s(512)` 経路を実行) |
| `unittest`(`ulimit -s unlimited`, 対照) | 84 / 84 passed | 84 / 84 passed, exit 0 |
| `isready`前の`position`(A. 変更対象外) | exit 139 | exit 139(変更なし・意図どおり) |
| `script/ponderhit_regression_test.py` | 15 / 15 合格(fab4935) | **15 / 15 合格, exit 0** |

コードレビュー所見(53263ff差分):

- 変更はすべて `Position::UnitTest()` 内に閉じており、探索・対局経路に影響しない。
  `docs/` 以外の変更ファイルは `source/position.cpp` のみ。
- `StateList`(`std::deque<StateInfo>`)は実対局の局面管理で既に使われている型で、
  C++17以降のaligned newによりNNUE accumulatorのalignment要件も満たす。
- 確保数と最大添字の照合: 千日手 `s(4)`→最大`s[3]`、SEE `s(4)`→`s[3]`、
  null move `s(1)`→`s[0]`、partial key `states(MAX_PLY + 1)`→`states[MAX_PLY]`、
  random player `s(512)`→`s[511]`。全て確保数内。従来の
  `si[MAX_PLY]`に対する最大添字`MAX_PLY`の範囲外書き込みも解消している。
- partial keyテストの`states`を1000回ループの外に出した点は、
  `set_hirate()`/`do_move()`が受け取った`StateInfo`を必要分すべて初期化するため
  再利用しても安全(従来も未初期化のスタック領域だったので同等の前提)。
- `deque(count)`のdefault-insertは従来の未初期化スタック配列と同じ初期化意味論。
- 副次的な堅牢化: `MAX_PLY_NUM`を2000に再定義するエディション(config.h)では
  従来の`StateInfo si[MAX_PLY]`だけで約16.6MBに達するが、ヒープ化により
  エディション非依存で安全になった。

結論: **適合**。(B)は53263ffで解消。同一バイナリ・同一環境・既定スタックで
再現→合格に転じたことを確認した。(A)は記載どおり対象外で挙動不変。
