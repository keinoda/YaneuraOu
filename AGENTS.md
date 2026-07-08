# Agent Notes

## Opening target SFEN testing

Record the result of each opening-target behavior change in
`docs/opening-target-test-log.md`. Include the build command, runtime options,
position, target SFENs, node budget, final score, and bestmove. If a test is
rerun after another code change, add a new dated entry instead of overwriting the
old result.

When testing USI `go` commands, do not send `quit` in the same piped input block
immediately after `go`. The engine can receive `quit` while searching and return
an artificial `nodes 0` result. Use an interactive session instead:

1. Start the engine with a PTY.
2. Send `usi`, required `setoption` commands, then `isready`.
3. Send `position` and `go ...`.
4. Wait for `bestmove`.
5. Send `quit` only after `bestmove` is observed.

For the opening-target build, use the same runtime data as the packaged
engine when testing directly:

```text
setoption name EvalDir value /workspace/<engine>/eval
setoption name LS_PROGRESS_COEFF value /workspace/<engine>/progress.bin
setoption name FV_SCALE value 28
setoption name USI_OwnBook value false
setoption name BookFile value no_book
```

For `unittest`, initialize the engine first with `usi`, point `EvalDir` and
`LS_PROGRESS_COEFF` at the packaged runtime data, then run `isready`.
Running `unittest` before the engine has loaded its runtime files can fail before
the test suite is actually meaningful.

Opening target uses a soft penalty in the ordinary search value. The opponent can
see the penalty through minimax propagation; tune `OpeningTargetPenalty` to
control how strongly the engine prefers target-reaching lines. Do not reintroduce
separate opponent-hidden value propagation without adding dedicated regression
tests for TT, pruning, root sorting, and qsearch.

Always test these edge cases after changing opening-target behavior:

- If the root starts at or before `OpeningTargetMaxPly`, branches that miss the
  target by the deadline stay penalized at deeper nodes.
- If the root itself starts after `OpeningTargetMaxPly`, target enforcement is
  ignored.
- If the target was already reached before the root, including cases where the
  current root no longer matches the target mask, no penalty should apply.
- If the current root already matches the target mask, no penalty should apply.

Useful regression cases:

```text
setoption name OpeningTargetPenalty value 3000
setoption name OpeningTargetSfenWhite value 9/6r2/9/p5p2/9/9/9/9/9
setoption name OpeningTargetMaxPly value 2
position startpos moves 2g2f
go nodes 1000000
```

This target cannot be fully reached by White's first move from this root, so the
score should include a large penalty. From a root after the deadline, for example
`position startpos moves 2g2f 8c8d 2f2e`, the same target should not add a large
penalty.

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
