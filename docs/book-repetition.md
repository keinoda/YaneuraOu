# 定跡使用時の千日手回避

定跡probe時のrepetition処理の設計メモと、floodgateで観測された千日手事例の分析、
および運用推奨設定。

## 事例分析: floodgate 2026-07-04 test_mypeta vs test768

対象棋譜:
`wdoor+floodgate-300-10F+test_mypeta+test768+20260704143005.csa`
(54手で %SENNICHITE。先手 test_mypeta が全手定跡 (T0/T1、コメントなし)、
後手 test768 は毎手探索して評価値コメントを出力)

棋譜を機械的に検証した結果(同一局面の出現プライを全列挙):

| ply | 指し手 | 指した側 | 出現回数 |
|----:|--------|----------|---------|
| 42  | -5152OU 後 | ―  | P0 の 1回目 |
| 46  | 4b5b(-5242OU区間の玉往復) | **後手(探索側)** | P0 の 2回目 |
| 49  | 4g5f(+4756GI) | **先手(定跡側)** | 45手目後局面の 2回目 |
| 50  | 4b5b | **後手** | P0 の 3回目 |
| 54  | 4d3c(-4433GI) | **後手** | P0 の 4回目 → 千日手成立 |

- 千日手を構成する P0 の再出現(2〜4回目)は **すべて相手(後手)の手** で完成しており、
  先手が「既出局面に飛び込む手」を指したのは 49手目の一度だけ。
- 先手は P0 への訪問のたびに別の手待ち手をローテーションしている
  (43手目 +2926HI → 47手目 +5647GI → 51手目 +4838KI)。これは当時の実装
  (候補手を1手進めた局面が対局履歴と一致したら実効値をdraw値へ置換し、
  通常手を優先する)が **正しく作動した痕跡**。置換された手は抽選から外れ、
  まだ既出局面に入らない別の手待ち手が選ばれ続けた。
- 評価値面: 後手の評価は序盤 +24〜+80(後手良し)で推移し、終盤の手待ち合戦では
  0〜+2。先手の定跡値は(選択挙動から逆算して)draw値(既定 DrawValueBlack=-2
  → 実効約-1)以上、つまりほぼ互角圏。**互角圏では draw値≒0 に忌避圧力がなく**、
  手待ち同士の応酬で相手が千日手を完成させる進行を止められない。

結論: この千日手は実装の不具合ではなく、当時の実装の守備範囲
(**1手先の対局履歴照合**)の外で起きた。定跡グラフ内の手待ちサイクルは
1手先チェックでは原理的に見えず、千日手を完成させる手を相手側が指す形では
候補手の除外機会も来ない。

## 対策(3段構え)

### 1. BookRepetitionPly: 定跡ライン先読みによるサイクル検知(新規)

候補手を指した直後の局面だけでなく、そこから **双方が定跡の実効値ベストを
交互に辿るライン** を最大 `BookRepetitionPly` 手(候補手自身を1手目と数える。
既定16、1で従来動作)まで進め、対局履歴・ライン内を問わず同一局面の再現
(REPETITION_DRAW)へ到達する候補手の実効値を draw値へ置き換える。

- 上記事例では P0 の初回訪問(43手目)時点で `+2926HI` などの手待ち手が
  「4手で千日手ライン」と判定され、draw値(負に設定していれば)未満の代替手が
  なければ定跡不採用→探索へフォールバックする。
- ラインが定跡から外れたら判定打ち切り(候補手は元の定跡値のまま)。
  千日手以外のrepetition(連続王手・優等劣等)がラインの先に現れた場合も、
  実際にそこへ進むかは双方の選択次第なので断定せず打ち切る。
- 相手の応手局面が定跡DBに載っていないラインのサイクルは検知できない
  (→ 対策2が補完する)。

### 2. BookIgnoreRepeatedRoot: root局面再訪で定跡から離脱(新規)

root局面自体が対局履歴上2回目以降の出現なら、定跡ラインがループしている
明確な兆候(前回この局面で選んだ定跡手ではループを断ち切れなかった)なので、
定跡を使わず通常探索へフォールバックする(既定 true)。

- 上記事例では47手目(P0 の2回目)で発火し、探索(DrawValue負なら千日手忌避)
  に切り替わる。定跡DBのカバレッジにも相手の挙動にも依存しない保険。
- 探索は全合法手から選ぶので、本当に千日手が最善(それ以外すべて draw値より
  悪い)ならば探索も千日手進行を選ぶ。判断を評価関数に委ねるのが趣旨。

### 3. DrawValueBlack/White と BookEvalLimit の整合(運用設定)

定跡の実効値置換も探索の千日手スコアも `drawValueTable`
(= `DrawValue{Black,White} × PawnValue / 100`)を参照する。既定の -2 では
忌避圧力がほぼゼロなので、千日手を避けたい運用では負値を明示的に設定する。

「千日手にしかならない定跡手しか残らない局面」で探索へフォールバックさせる
には、置換後の実効値が下限を割る必要がある:

```
DrawValue{Black,White} × PawnValue/100  <  BookEval{Black,White}Limit
```

PawnValue=90 の場合の例:

| 設定 | 実効draw値 | 既定Limit | フォールバック |
|------|-----------|-----------|----------------|
| DrawValueBlack=-100 | -90 | BookEvalBlackLimit=0 | する ✓ |
| DrawValueWhite=-100 | -90 | BookEvalWhiteLimit=-140 | **しない** ✗ |
| DrawValueWhite=-200 | -180 | BookEvalWhiteLimit=-140 | する ✓ |
| DrawValueWhite=-100 + BookEvalWhiteLimit=-80 | -90 | -80 | する ✓ |

floodgate運用の推奨例(千日手を積極的に避ける):

```text
setoption name DrawValueBlack value -100
setoption name DrawValueWhite value -100
setoption name BookEvalBlackLimit value 0
setoption name BookEvalWhiteLimit value -80
```

(BookRepetitionPly=16 / BookIgnoreRepeatedRoot=true は既定で有効)

## 検証

MATERIAL版(`make normal YANEURAOU_EDITION=YANEURAOU_ENGINE_MATERIAL`)+
玉往復のサイクルを含むミニ定跡で確認(2026-07-04):

```text
#YANEURAOU-DB2016 1.00
sfen lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1
5i5h none 10 32 0
2g2f none 8 32 0
sfen lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B2K2R1/LNSG1GSNL w - 2
5a5b none 0 32 0
sfen lnsg1gsnl/1r2k2b1/ppppppppp/9/9/9/PPPPPPPPP/1B2K2R1/LNSG1GSNL b - 3
5h5i none 10 32 0
sfen lnsg1gsnl/1r2k2b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL w - 4
5b5a none 0 32 0
```

(IgnoreBookPly=true, BookMoves=30, DrawValueBlack=-100, BookEvalBlackLimit=0)

1. `position startpos` + 既定(BookRepetitionPly=16):
   `BookRepetition : 5i5h book_value 10 -> -90 (draw line in 4 plies)` が出力され、
   bestmove は 2g2f(サイクル回避)。
2. BookRepetitionPly=1(従来動作) + BookEvalDiff=0: 置換なし、bestmove 5i5h。
3. `position startpos moves 5i5h 5a5b 5h5i 5b5a`(root再訪) + 既定:
   `BookRepetition : root position occurred 2 times in this game, ignoring book.`
   が出力され、通常探索の bestmove(4g4f)。
4. 同上 + BookIgnoreRepeatedRoot=false: 従来の1手チェックが
   `5i5h book_value 10 -> -90 (draw)` と置換し、bestmove 2g2f。

本番edition(`YANEURAOU_ENGINE_SFNN_halfkahm2_1536_15_32_k3k3`)もクリーンビルドで
コンパイルが通ることを確認済み。

## 残る限界

- 相手が定跡外の探索で千日手を強要してくる進行のうち、こちらの定跡DBに相手側
  局面が載っていないものは BookRepetitionPly では見えない。BookIgnoreRepeatedRoot
  が2回目の再訪で発火するので千日手成立(4回目)までは至らないが、それまでの
  手待ちの往復は消費する。
- こちらが本当に劣勢で千日手が最善の場合、DrawValue を負にしていると探索は
  あえて悪い進展手を選ぶ。DrawValue の絶対値は「どこまで悪くても千日手より
  戦い続けるか」の閾値なので、レーティング差・大会規定に応じて調整すること。
- 定跡DB自体に手待ちサイクルの値(≒0)が焼き込まれている問題の根本対策は、
  makebook 側でサイクルを負値評価して再生成すること(未着手)。
