# Agent Notes

## Opening target SFEN testing

When testing USI `go` commands, do not send `quit` in the same piped input block
immediately after `go`. The engine can receive `quit` while searching and return
an artificial `nodes 0` result. Use an interactive session instead:

1. Start the engine with a PTY.
2. Send `usi`, required `setoption` commands, then `isready`.
3. Send `position` and `go ...`.
4. Wait for `bestmove`.
5. Send `quit` only after `bestmove` is observed.

For the nagisa opening-target build, use the same runtime data as the packaged
engine when testing directly:

```text
setoption name EvalDir value /workspace/nagisa-768-900sb/eval
setoption name ProgressFilePath value /workspace/nagisa-768-900sb/progress.bin
setoption name FV_SCALE value 28
setoption name USI_OwnBook value false
setoption name BookFile value no_book
```

The opponent-hidden opening target behavior is easiest to detect with a larger
node budget, not shallow fixed depth. A useful regression case is:

```text
setoption name OpeningTargetPenalty value 300
setoption name OpeningTargetSfenWhite value 9/9/9/7p1/9/9/9/9/9
position startpos moves 2g2f
go nodes 10000000
```

The old behavior can fall to about `score cp -300` or worse from White's root
search because Black's replies effectively know White's target. The fixed
behavior should keep the score much closer to the natural evaluation.

Also test color-preserving target masks. For example, this White target includes
a Black pawn and a White pawn:

```text
setoption name OpeningTargetSfenWhite value 9/9/7p1/7P1/9/9/9/9/9
position startpos moves 2g2f
go nodes 10000000
```

The parser must preserve the piece colors from the SFEN mask; do not collapse
all target pieces to the side named by `OpeningTargetSfenBlack` or
`OpeningTargetSfenWhite`.
