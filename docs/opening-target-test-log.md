# Opening Target Test Log

This file records behavior checks for each opening-target implementation change.
Keep new verification runs as dated entries instead of overwriting older results.

## 2026-06-15: Soft penalty with deadline-root gating

Source state: local changes after `d20a95de Add Apple Silicon build script`.

Implementation summary:

- Reverted the strict opponent-hidden behavior. Target penalty is again part of
  the ordinary search value, so the opponent can indirectly see the penalty
  through minimax propagation.
- `openingTargetHidden[color]` now means "this target is out of scope for this
  root search" rather than "hide target on opponent nodes".
- Only the root side-to-move target is in scope. Targets for the opposite side
  are ignored even if configured.
- If the root position starts after `OpeningTargetMaxPly`, target enforcement is
  disabled for that search.
- If the root search starts at or before `OpeningTargetMaxPly`, then branches
  that reached the target by the deadline remain unpenalized forever, while
  branches that did not reach it are penalized at every later node.
- Removed the separate root move bias to avoid double-counting the same penalty.

Build:

```text
make -C source -j32 tournament YANEURAOU_EDITION=YANEURAOU_ENGINE_SFNN1536 TARGET_CPU=AVX2
```

Result: succeeded.

Common direct-engine runtime options:

```text
setoption name EvalDir value /workspace/<engine>/eval
setoption name ProgressFilePath value /workspace/<engine>/progress.bin
setoption name FV_SCALE value 28
setoption name USI_OwnBook value false
setoption name BookFile value no_book
setoption name Threads value 1
setoption name MultiPV value 1
setoption name PvInterval value 100000000
```

### Deadline-root, unreachable target stays penalized

Control without target:

```text
position startpos moves 2g2f
go nodes 1000000
```

Observed:

```text
info depth 22 ... score cp -88 ... pv 3c3d 7g7f
bestmove 3c3d ponder 7g7f
```

Unreachable-by-deadline target:

```text
setoption name OpeningTargetSfenWhite value 9/6r2/9/p5p2/9/9/9/9/9
setoption name OpeningTargetMaxPly value 2
setoption name OpeningTargetPenalty value 3000
position startpos moves 2g2f
go nodes 1000000
```

Observed:

```text
info depth 25 ... score cp -3397 ... pv 4a3b 2f2e 8c8d ...
bestmove 4a3b ponder 2f2e
```

Notes: starting before/at the deadline and failing to reach the target keeps the
penalty active in deeper search nodes.

### Root after deadline ignores target

Control without target:

```text
position startpos moves 2g2f 8c8d 2f2e
go nodes 1000000
```

Observed:

```text
info depth 23 ... score cp -88 ... pv 4a3b 6i7h
bestmove 4a3b ponder 6i7h
```

Same position with the unreachable target:

```text
setoption name OpeningTargetSfenWhite value 9/6r2/9/p5p2/9/9/9/9/9
setoption name OpeningTargetMaxPly value 2
setoption name OpeningTargetPenalty value 3000
position startpos moves 2g2f 8c8d 2f2e
go nodes 1000000
```

Observed:

```text
info depth 25 ... score cp -52 ... pv 4a3b 6i7h
bestmove 4a3b ponder 6i7h
```

Notes: no large target penalty remains when the search root itself is already
after the configured max ply.

### Already reached before search, then left target square

Control without target:

```text
position startpos moves 2g2f 8b3b 2f2e 3b8b 7g7f
go nodes 1000000
```

Observed:

```text
info depth 20 ... score cp -290 ... pv 3c3d 6i7h
bestmove 3c3d ponder 6i7h
```

Target was reached by `8b3b` before the root, but is no longer matched at the
root because of `3b8b`:

```text
setoption name OpeningTargetSfenWhite value 9/6r2/9/9/9/9/9/9/9
setoption name OpeningTargetMaxPly value 8
setoption name OpeningTargetPenalty value 3000
position startpos moves 2g2f 8b3b 2f2e 3b8b 7g7f
go nodes 1000000
```

Observed:

```text
info depth 22 ... score cp -235 ... pv 3c3d 5i6h ...
bestmove 3c3d ponder 5i6h
```

Notes: a previously reached target remains satisfied even if the current root
position no longer matches the target mask.

### Already matched at root

Control without target from startpos:

```text
position startpos
go nodes 1000000
```

Observed:

```text
info depth 24 ... score cp 47 ... pv 2g2f 4a3b ...
bestmove 2g2f ponder 4a3b
```

Target already matches the initial black rook position:

```text
setoption name OpeningTargetSfenBlack value 9/9/9/9/9/9/9/7R1/9
setoption name OpeningTargetMaxPly value 1
setoption name OpeningTargetPenalty value 3000
position startpos
go nodes 1000000
```

Observed:

```text
info depth 27 ... score cp 41 ... pv 2g2f 8c8d
bestmove 2g2f ponder 8c8d
```

Notes: matching the target at the root prevents the large penalty from applying.

### Deadline move can still satisfy target

```text
setoption name OpeningTargetSfenWhite value 9/6r2/9/9/9/9/9/9/9
setoption name OpeningTargetMaxPly value 2
setoption name OpeningTargetPenalty value 3000
position startpos moves 2g2f
go nodes 1000000
```

Observed:

```text
info depth 19 ... score cp -615 ... pv 8b3b 2f2e ...
bestmove 8b3b ponder 2f2e
```

Notes: the move on the configured deadline is still counted as reaching the
target.

### Late MaxPly root no longer distorts score

```text
setoption name OpeningTargetSfenWhite value 9/9/7p1/7P1/9/9/9/9/9
setoption name OpeningTargetMaxPly value 7
setoption name OpeningTargetPenalty value 300
position startpos moves 2g2f 8c8d 2f2e 8d8e 7g7f 1c1d 8h7g
go nodes 10000000
```

Observed:

```text
info depth 34 ... score cp -55 ... pv 3c3d 7i8h 2b7g+ 8h7g ...
bestmove 3c3d ponder 7i8h
```

Notes: this is the earlier regression class where the score could become
approximately `-1300` to `-1400` after the target deadline. The late-root search
now ignores target enforcement.

### Unit test

Command:

```text
printf 'usi\nsetoption name EvalDir value /workspace/<engine>/eval\nsetoption name ProgressFilePath value /workspace/<engine>/progress.bin\nsetoption name FV_SCALE value 28\nisready\nunittest\nquit\n' | ./YaneuraOu-by-gcc
```

Observed result:

```text
Summary : 87 / 87 passed.
-> Passed all UnitTests.
```

## 2026-06-17 Ponder miss maximum scaling

Build:

```text
make -C source -j4 normal TARGET_CPU=APPLEM1 YANEURAOU_EDITION=YANEURAOU_ENGINE_SFNN1536
```

Result: succeeded.

Runtime setup:

```text
usi
setoption name EvalDir value /Users/keinoda/<engine>/eval
setoption name ProgressFilePath value /Users/keinoda/<engine>/progress.bin
setoption name USI_OwnBook value false
setoption name BookFile value no_book
setoption name Threads value 1
setoption name MultiPV value 1
setoption name PvInterval value 100000000
setoption name USI_Ponder value true
isready
```

USI option check:

```text
option name USI_Ponder type check default false
option name SlowMover type spin default 100 min 1 max 1000
option name SlowMover_black type spin default 0 min 0 max 1000
option name SlowMover_white type spin default 0 min 0 max 1000
option name ProgressMtg type check default false
```

Notes: no `PonderMissMaximumScale` option is exposed; Ponder miss uses the
fixed built-in 2x maximumTime scale.

### Actual go ponder miss

First normal search:

```text
position startpos moves 2g2f
go nodes 100000
```

Observed:

```text
info depth 16 seldepth 23 multipv 1 score cp -48 lowerbound nodes 100005 nps 420189 hashfull 0 time 238 pv 3c3d 7g7f
bestmove 3c3d ponder 7g7f
```

Ponder search on the predicted opponent move, stopped as a miss:

```text
position startpos moves 2g2f 3c3d 7g7f
go ponder btime 300000 wtime 300000 byoyomi 10000
stop
```

Observed:

```text
info depth 25 seldepth 38 multipv 1 score cp -95 lowerbound nodes 3458684 nps 767402 hashfull 22 time 4507 pv 4c4d 2f2e
bestmove 4c4d ponder 2f2e
```

Normal search after the actual opponent move differs from the previous ponder:

```text
position startpos moves 2g2f 3c3d 2f2e
go btime 300000 wtime 300000 byoyomi 10000
```

Observed:

```text
info string PonderMiss maximumTime=63868->127736
info depth 35 seldepth 22 multipv 1 score cp -12 lowerbound nodes 4055098 nps 830962 hashfull 21 time 4880 pv 2b3c 7g7f
bestmove 2b3c ponder 7g7f
```

Notes: the stopped ponder search returned `bestmove 4c4d ponder 2f2e`, but it
did not overwrite the previous real `bestmove 3c3d ponder 7g7f` used for miss
detection. The following normal search doubled maximumTime.

### OpeningTarget suppresses miss scaling

Start from the same previous `bestmove 3c3d ponder 7g7f`, then stop the
predicted ponder search:

```text
position startpos moves 2g2f 3c3d 7g7f
go ponder btime 300000 wtime 300000 byoyomi 10000
stop
```

Observed stopped ponder:

```text
info depth 26 seldepth 33 multipv 1 score cp -87 lowerbound nodes 3893267 nps 924107 hashfull 25 time 4213 pv 4c4d 2f2e
bestmove 4c4d ponder 2f2e
```

Enable an active White root target before the actual move search:

```text
setoption name OpeningTargetPenalty value 3000
setoption name OpeningTargetMaxPly value 20
setoption name OpeningTargetSfenWhite value 9/6r2/9/p5p2/9/9/9/9/9
position startpos moves 2g2f 3c3d 2f2e
go btime 300000 wtime 300000 byoyomi 10000
stop
```

Observed:

```text
info depth 26 seldepth 37 multipv 1 score cp -382 lowerbound nodes 4914613 nps 920684 hashfull 28 time 5338 pv 2b3c 6i7h
bestmove 2b3c
```

Notes: no `PonderMiss maximumTime=...` log was emitted, and active target still
suppressed ponder output.

### Unit test

Command sequence:

```text
usi
setoption name EvalDir value /Users/keinoda/<engine>/eval
setoption name ProgressFilePath value /Users/keinoda/<engine>/progress.bin
setoption name USI_OwnBook value false
setoption name BookFile value no_book
isready
unittest
quit
```

Observed result:

```text
Summary : 84 / 84 passed.
-> Passed all UnitTests.
```

### Packaged engine replacement and bench comparison

Bench command, run before replacing the packaged engine:

```text
bench 1024 1 1000000 default nodes
bench 1024 4 1000000 default nodes
```

Runtime options:

```text
setoption name EvalDir value /workspace/<engine>/eval
setoption name ProgressFilePath value /workspace/<engine>/progress.bin
setoption name FV_SCALE value 28
setoption name USI_OwnBook value false
setoption name BookFile value no_book
```

Old packaged engine:

```text
sha256 28baa1e68cdb71a290f073e6809ea71e8e389145ef9351626c5c3f8c50742919
threads=1 Nodes/second 1171042
threads=4 Nodes/second 4865770
```

New build:

```text
sha256 4bff32d0a38d21304dfb647e656e262f4b15d3181153e65bc581978640b1e0b7
threads=1 Nodes/second 1192327
threads=4 Nodes/second 4916433
```

Result: no measured NPS drop in this bench run. The new build was about 1.8%
faster with one thread and about 1.0% faster with four threads.

The packaged engine was replaced at:

```text
/workspace/<engine>/engine_yaneuraou_sfnn768_opening_target_v940_linux_x86_64_avx2_tournament
```

`/workspace/<engine>/SHA256SUMS` was updated and verified with
`sha256sum -c SHA256SUMS`.

Post-replacement direct-engine check:

```text
setoption name OpeningTargetSfenWhite value 9/6r2/9/9/9/9/9/9/9
setoption name OpeningTargetMaxPly value 2
setoption name OpeningTargetPenalty value 3000
position startpos moves 2g2f
go nodes 100000
```

Observed:

```text
info depth 10 ... score cp -480 ... pv 8b3b 2f2e
bestmove 8b3b ponder 2f2e
```

## 2026-06-15: Restore target visibility on own nodes only

Source state: local changes after `d20a95de Add Apple Silicon build script`.

Implementation summary:

- Added per-search `openingTargetAllowed[color]` state.
- Only the root side-to-move color is allowed, so the opposite side's SFEN is ignored even if both target SFENs are configured.
- `openingTargetHidden[color]` now changes by node side-to-move: hidden on opponent choice nodes, visible again on the target side's own choice nodes.
- `openingTargetReached[color]` remains sticky once the target mask is reached before the configured max ply, so bias is not applied after arrival.

Build:

```text
make -C source -j32 tournament YANEURAOU_EDITION=YANEURAOU_ENGINE_SFNN1536 TARGET_CPU=AVX2
```

Result: succeeded.

Common direct-engine runtime options:

```text
setoption name EvalDir value /workspace/<engine>/eval
setoption name ProgressFilePath value /workspace/<engine>/progress.bin
setoption name FV_SCALE value 28
setoption name USI_OwnBook value false
setoption name BookFile value no_book
setoption name OpeningTargetPenalty value 300
```

### Corrected White rook/pawn target

Commands:

```text
setoption name OpeningTargetSfenWhite value 9/6r2/9/p5p2/9/9/9/9/9
position startpos moves 2g2f
go nodes 10000000
```

Observed result:

```text
info depth 25 seldepth 33 multipv 1 score cp -73 nodes 10001740 ... pv 3c3d 7g7f 4c4d 2f2e 2b3c 3i4h 8b3b ...
bestmove 3c3d ponder 7g7f
```

Notes: target influence is visible from White's own search; it no longer stays on the previous non-target `8c8d` line.

### Opponent-hidden regression check

Commands:

```text
setoption name OpeningTargetSfenWhite value 9/9/9/7p1/9/9/9/9/9
position startpos moves 2g2f
go nodes 10000000
```

Observed result:

```text
info depth 27 seldepth 45 multipv 1 score cp -136 nodes 10000684 ... pv 8c8d 7g7f ...
bestmove 8c8d ponder 7g7f
```

Notes: this did not regress to the old about `score cp -300` behavior where Black's replies effectively knew White's target.

### Color-preserving target mask

Commands:

```text
setoption name OpeningTargetSfenWhite value 9/9/7p1/7P1/9/9/9/9/9
position startpos moves 2g2f
go nodes 10000000
```

Observed result:

```text
info depth 26 seldepth 41 multipv 1 score cp -163 nodes 10000943 ... pv 3c3d 7g7f 8c8d ...
bestmove 3c3d ponder 7g7f
```

Notes: the SFEN mask includes both a Black pawn and a White pawn. The parser and search accept the colored piece placement.

### Opposite-side target ignored

Control, no target:

```text
setoption name Threads value 1
setoption name OpeningTargetSfenWhite value <empty>
setoption name OpeningTargetSfenBlack value <empty>
position startpos moves 2g2f
go nodes 2000000
```

Observed:

```text
info depth 25 seldepth 33 multipv 1 score cp -84 upperbound nodes 2000319 ... pv 8c8d 7g7f
bestmove 8c8d ponder 7g7f
```

Black-only target from a White-root position:

```text
setoption name OpeningTargetSfenBlack value 9/9/9/9/9/9/9/9/R8
setoption name OpeningTargetSfenWhite value <empty>
position startpos moves 2g2f
go nodes 2000000
```

Observed:

```text
info depth 25 seldepth 33 multipv 1 score cp -84 upperbound nodes 2000319 ... pv 8c8d 7g7f
bestmove 8c8d ponder 7g7f
```

White target alone:

```text
setoption name OpeningTargetSfenBlack value <empty>
setoption name OpeningTargetSfenWhite value 9/6r2/9/p5p2/9/9/9/9/9
position startpos moves 2g2f
go nodes 2000000
```

Observed:

```text
info depth 23 seldepth 41 multipv 1 score cp -84 nodes 2000184 ... pv 3c3d 7g7f 4c4d 9g9f 9c9d 2f2e 2b3c 3i4h 8b3b ...
bestmove 3c3d ponder 7g7f
```

White and Black targets together:

```text
setoption name OpeningTargetSfenBlack value 9/9/9/9/9/9/9/9/R8
setoption name OpeningTargetSfenWhite value 9/6r2/9/p5p2/9/9/9/9/9
position startpos moves 2g2f
go nodes 2000000
```

Observed:

```text
info depth 23 seldepth 41 multipv 1 score cp -84 nodes 2000184 ... pv 3c3d 7g7f 4c4d 9g9f 9c9d 2f2e 2b3c 3i4h 8b3b ...
bestmove 3c3d ponder 7g7f
```

Notes: adding the Black target did not change the White-root search result.

### Unit test

Command:

```text
printf 'usi\nsetoption name EvalDir value /workspace/<engine>/eval\nsetoption name ProgressFilePath value /workspace/<engine>/progress.bin\nsetoption name FV_SCALE value 28\nisready\nunittest\nquit\n' | ./YaneuraOu-by-gcc
```

Observed result:

```text
Summary : 87 / 87 passed.
-> Passed all UnitTests.
```

### Packaged engine binary replacement

Copied the verified build to:

```text
/workspace/<engine>/engine_yaneuraou_sfnn768_opening_target_v940_linux_x86_64_avx2_tournament
```

SHA256 after replacement:

```text
28baa1e68cdb71a290f073e6809ea71e8e389145ef9351626c5c3f8c50742919  /workspace/YaneuraOu/source/YaneuraOu-by-gcc
28baa1e68cdb71a290f073e6809ea71e8e389145ef9351626c5c3f8c50742919  /workspace/<engine>/engine_yaneuraou_sfnn768_opening_target_v940_linux_x86_64_avx2_tournament
```

`/workspace/<engine>/SHA256SUMS` was updated and verified:

```text
./MANIFEST.txt: OK
./README_ja.md: OK
./engine_yaneuraou_sfnn768_opening_target_v940_linux_x86_64_avx2_tournament: OK
./eval/eval_options.txt: OK
./eval/nn.bin: OK
./eval_option.txt: OK
./progress.bin: OK
./run.sh: OK
./tools/usi_inject.py: OK
```

Direct packaged-engine verification:

```text
setoption name EvalDir value /workspace/<engine>/eval
setoption name ProgressFilePath value /workspace/<engine>/progress.bin
setoption name FV_SCALE value 28
setoption name USI_OwnBook value false
setoption name BookFile value no_book
setoption name OpeningTargetPenalty value 300
setoption name OpeningTargetSfenWhite value 9/6r2/9/p5p2/9/9/9/9/9
position startpos moves 2g2f
go nodes 10000000
```

Observed:

```text
info depth 26 seldepth 38 multipv 1 score cp -82 nodes 10000944 ... pv 3c3d 7g7f 4c4d 2f2e 2b3c 4g4f 8b3b ...
bestmove 3c3d ponder 7g7f
```

## 2026-06-15: Investigation cases, no code change

These entries are diagnosis notes only. They document reproducible or candidate
conditions for future regression tests.

Common direct-engine runtime options:

```text
setoption name EvalDir value /workspace/<engine>/eval
setoption name ProgressFilePath value /workspace/<engine>/progress.bin
setoption name FV_SCALE value 28
setoption name USI_OwnBook value false
setoption name BookFile value no_book
```

### Late MaxPly penalty distortion

Target:

```text
setoption name OpeningTargetSfenWhite value 9/9/7p1/7P1/9/9/9/9/9
setoption name OpeningTargetMaxPly value 7
setoption name OpeningTargetPenalty value 300
```

Position:

```text
position startpos moves 2g2f 8c8d 2f2e 8d8e 7g7f 1c1d 8h7g
go nodes 10000000
```

Observed with target:

```text
info depth 42 seldepth 13 multipv 1 score cp -1463 nodes 10002039 ... pv 5a5b 2e2d
bestmove 5a5b ponder 2e2d
```

Observed without target:

```text
setoption name OpeningTargetSfenWhite value <empty>
position startpos moves 2g2f 8c8d 2f2e 8d8e 7g7f 1c1d 8h7g
go nodes 10000000

info depth 28 seldepth 44 multipv 1 score cp -23 nodes 10001519 ... pv 3c3d 7i6h ...
bestmove 3c3d ponder 7i6h
```

Penalty scaling check at the same position, `Threads=1`, `go nodes 3000000`:

```text
OpeningTargetPenalty 0   -> score cp -32, bestmove 3c3d
OpeningTargetPenalty 100 -> score cp -818, bestmove 4a3b
OpeningTargetPenalty 300 -> score cp -1461, bestmove 7a7b
```

Notes: this is much larger than a single 300 cp adjustment and should be treated
as target bias leaking into the search value, not as ordinary evaluation noise.

### Candidate opponent-node leakage: 1c1d branch

Target:

```text
setoption name OpeningTargetSfenWhite value 9/9/7p1/7P1/9/9/9/9/9
setoption name OpeningTargetMaxPly value 7
setoption name OpeningTargetPenalty value 300
```

Parent root, White to move, `Threads=1`, `MultiPV=5`, `go nodes 10000000`:

```text
position startpos moves 2g2f 8c8d 2f2e 8d8e 7g7f

info depth 18 seldepth 28 multipv 1 score cp -203 ... pv 4a3b 8h7g ...
info depth 18 seldepth 32 multipv 2 score cp -216 ... pv 1c1d 8h7g ...
bestmove 4a3b ponder 8h7g
```

Forced parent move:

```text
position startpos moves 2g2f 8c8d 2f2e 8d8e 7g7f
go nodes 3000000 searchmoves 1c1d

info depth 25 seldepth 42 multipv 1 score cp -222 lowerbound ... pv 1c1d 8h7g
bestmove 1c1d ponder 8h7g
```

Child root after `1c1d`, same target still configured but root side is Black, so
White target should be ignored:

```text
position startpos moves 2g2f 8c8d 2f2e 8d8e 7g7f 1c1d
go nodes 3000000

info depth 27 seldepth 39 multipv 1 score cp 90 lowerbound ... pv 2e2d 2c2d
bestmove 2e2d ponder 2c2d
```

Notes: this case shows suspicious disagreement, but the move pair may still be
too close and search-sensitive to use as a hard regression by itself.

### Candidate opponent-node leakage: 7七銀 target

User-reported target and position:

```text
setoption name OpeningTargetSfenWhite value 9/9/9/9/9/9/2S6/9/9
setoption name OpeningTargetMaxPly value 18
setoption name OpeningTargetPenalty value 300

position startpos moves 2g2f 8c8d 2f2e 8d8e 7g7f 4a3b 8h7g 3c3d 7i8h
```

User report: from this White-root position, the engine line after `2b7g+`
sometimes expects Black to answer `8i7g` (7七桂). But from the child position
after `2b7g+`, Black-root search prefers `8h7g` (7七銀) by about 100 cp or more.
This suggests White's parent search may still be assuming Black knows and avoids
White's target.

Local White-root check, `Threads=1`, `MultiPV=1`, `go nodes 10000000`:

```text
info depth 30 seldepth 43 multipv 1 score cp -26 nodes 8297157 ... pv 2b7g+ 8i7g ...
info depth 31 seldepth 42 multipv 1 score cp -36 lowerbound nodes 10000600 ... pv 2b7g+ 8h7g
bestmove 2b7g+ ponder 8h7g
```

Notes: local final output did not fully reproduce the user report, but an
intermediate PV did show `2b7g+ 8i7g`.

Child Black-root check after `2b7g+`, same target still configured, `Threads=1`,
`MultiPV=5`, `go nodes 10000000`:

```text
position startpos moves 2g2f 8c8d 2f2e 8d8e 7g7f 4a3b 8h7g 3c3d 7i8h 2b7g+

info depth 22 seldepth 28 multipv 1 score cp 30  ... pv 8h7g ...
info depth 22 seldepth 35 multipv 2 score cp -148 ... pv 8i7g ...
bestmove 8h7g ponder 3a2b
```

Notes: in the child Black-root search, `8h7g` (7七銀) is clearly better than
`8i7g` (7七桂) under these local conditions. This is a stronger candidate pair
than the `1c1d` example for testing whether opponent-node selection receives
target-distorted child values.

50M-node follow-up, parent White-root position, `Threads=4`, `MultiPV=1`:

```text
position startpos moves 2g2f 8c8d 2f2e 8d8e 7g7f 4a3b 8h7g 3c3d 7i8h
go nodes 50000000

info depth 32 seldepth 46 multipv 1 score cp -10 lowerbound nodes 50001923 ... pv 2b7g+ 8i7g
bestmove 2b7g+ ponder 8i7g
```

50M-node follow-up, child Black-root position after `2b7g+`, `Threads=4`,
`MultiPV=5`:

```text
position startpos moves 2g2f 8c8d 2f2e 8d8e 7g7f 4a3b 8h7g 3c3d 7i8h 2b7g+
go nodes 50000000

info depth 24 seldepth 37 multipv 1 score cp 7    nodes 50000536 ... pv 8h7g ...
info depth 24 seldepth 38 multipv 2 score cp -130 nodes 50000536 ... pv 8i7g ...
bestmove 8h7g ponder 3a2b
```

Notes: this 50M-node run stabilizes the mismatch. In the parent search, White
expects Black to choose `8i7g`, while the independent Black-root search after
`2b7g+` prefers `8h7g` by 137 cp.

## 2026-06-15: Stochastic ponder ignores OpeningTarget

Source state: local changes after the soft-penalty deadline-root gating fix.

Implementation summary:

- Added `Search::LimitsType::ignoreOpeningTarget`.
- Set `ignoreOpeningTarget = true` only in the existing `Stochastic_Ponder`
  `go ponder` path, after parsing limits and before starting the rewound
  opponent-side ponder search.
- Normal ponder is intentionally unchanged. It remains available for use cases
  where no opening target is configured.
- Root opening-target initialization treats `ignoreOpeningTarget` as all targets
  being out of scope, so both the penalty path and TT salt ignore target state
  during stochastic ponder.

Build:

```text
make -C source -j32 tournament YANEURAOU_EDITION=YANEURAOU_ENGINE_SFNN1536 TARGET_CPU=AVX2
```

Result: succeeded.

Runtime setup:

```text
usi
setoption name EvalDir value /workspace/<engine>/eval
isready
setoption name Threads value 1
setoption name Stochastic_Ponder value false
setoption name OpeningTargetSfenWhite value 9/6r2/9/9/9/9/9/9/9
setoption name OpeningTargetMaxPly value 2
setoption name OpeningTargetPenalty value 3000
```

### Normal target search still applies

Commands:

```text
position startpos moves 2g2f
go nodes 100000
```

Observed:

```text
info depth 14 ... score cp -513 nodes 100029 ... pv 8b3b 2f2e ...
bestmove 8b3b ponder 2f2e
```

Notes: this confirms the new stochastic-ponder flag did not disable ordinary
opening-target guidance.

### Stochastic ponder does not see the target

Commands:

```text
setoption name Stochastic_Ponder value true
position startpos moves 2g2f 8c8d
go ponder nodes 100000
stop
```

Observed:

```text
info depth 40 ... score cp -40 nodes 46902341 ... pv 4a3b 2f2e ...
bestmove 4a3b ponder 2f2e
```

Notes: the stochastic ponder implementation rewinds the saved position by one
move and thinks from the opponent side. Without `ignoreOpeningTarget`, this test
would be the same White-root situation that chooses the target move `8b3b`.
With the new flag, the ponder search chooses the ordinary-looking `4a3b`
instead.

Operational note: in this engine, `go ponder nodes 100000` continued well past
the node limit during the ponder search. For reproducible manual checks, send
`stop` separately after the desired amount of output and wait for `bestmove`.

Do not send `quit` on the same input batch as `go`.

### Unit test

Command sequence:

```text
usi
setoption name EvalDir value /workspace/<engine>/eval
isready
unittest
quit
```

Observed result:

```text
Summary : 87 / 87 passed.
-> Passed all UnitTests.
```

## 2026-06-17: Allow normal ponder only when root target is inactive

Source state: local `sfnnwop1536-progress-v941` changes after adding
ProgressMtg and side-specific SlowMover options.

Implementation summary:

- `OpeningTargetMaxPly=0` now disables opening target entirely even if a target
  SFEN remains configured.
- Normal `bestmove ... ponder ...` output is suppressed only when the root
  position is still actively guided by the root side's opening target.
- Normal ponder remains available when the target is unset, disabled, already
  reached, or the root is after the target deadline.

Build:

```text
make -C source -j4 normal TARGET_CPU=APPLEM1 YANEURAOU_EDITION=YANEURAOU_ENGINE_SFNN1536
```

Result: succeeded.

Runtime setup:

```text
usi
setoption name EvalDir value /Users/keinoda/<engine>/eval
setoption name ProgressFilePath value /Users/keinoda/<engine>/progress.bin
setoption name USI_OwnBook value false
setoption name BookFile value no_book
setoption name Threads value 1
setoption name MultiPV value 1
setoption name PvInterval value 100000000
isready
```

### MaxPly zero disables target

Commands:

```text
setoption name OpeningTargetSfenWhite value 9/6r2/9/9/9/9/9/9/9
setoption name OpeningTargetMaxPly value 0
setoption name OpeningTargetPenalty value 3000
position startpos moves 2g2f
go nodes 100000
```

Observed:

```text
info depth 16 ... score cp -48 ... pv 3c3d 7g7f
bestmove 3c3d ponder 7g7f
```

Notes: configured target SFEN no longer affects the move or ponder output when
`OpeningTargetMaxPly` is zero.

### Active root target suppresses ponder

Commands:

```text
setoption name OpeningTargetMaxPly value 2
position startpos moves 2g2f
go nodes 100000
```

Observed:

```text
info depth 15 ... score cp -465 ... pv 8b3b 2f2e ...
bestmove 8b3b
```

Notes: White's root target is active and unreached, so the opponent-response
ponder move is not returned.

### Reached or expired target allows ponder

Commands:

```text
position startpos moves 2g2f 8b3b 2f2e
go nodes 100000
```

Observed:

```text
info depth 13 ... score cp -524 ... pv 3c3d 2e2d ...
bestmove 3c3d ponder 2e2d
```

Notes: the target was already reached by White's `8b3b`, and the root is after
the target deadline, so normal ponder output is restored.

### No target remains ordinary

Commands:

```text
setoption name OpeningTargetSfenWhite value <empty>
position startpos moves 2g2f
go nodes 100000
```

Observed:

```text
info depth 16 ... score cp -46 ... pv 3c3d 7g7f ...
bestmove 3c3d ponder 7g7f
```

Notes: clearing the target keeps the previous ordinary ponder behavior.

### Unit test

Command sequence:

```text
usi
setoption name EvalDir value /Users/keinoda/<engine>/eval
setoption name ProgressFilePath value /Users/keinoda/<engine>/progress.bin
isready
unittest
quit
```

Observed result:

```text
Summary : 87 / 87 passed.
-> Passed all UnitTests.
```
