# Cognitive Engine

The Cognitive Engine is a modular extension of ChessLab (`backend/app/cognitive/`, API under `/api/cognitive/*`). Its loop is MEASURE → DIAGNOSE → INTERVENE → PRACTICE → REASSESS → ADAPT, and its main outcome is **error rates in your real games**.

It only measures observable chess performance: accuracy, timing, success by line length, engine-evaluated move quality. It does **not** measure IQ, brain activity, working-memory capacity or any clinical or psychological trait, and the UI says so.

## 1. Raw data: what gets recorded per attempt

Every exercise is an `Attempt` row with: mode, puzzle/game-position id, themes and primary concept, `served_at`, `first_move_ms`, per-move cumulative times (`move_times_ms`), `total_ms`, time limit, minimum think lock, timeout flag, correctness, `fail_ply` (which of your moves failed), moves played, expected move, **hesitation** (piece-selection changes and cancelled drags, counted by the board), listed candidates and their score, puzzle rating, expected score (Glicko) and rating before/after. A failed attempt also gets its cp loss, Error DNA category and the full feature dictionary used to label it.

Timing comes from the client, which measures it to the millisecond. The server bounds it with its own clock: any client value larger than the server-observed elapsed time plus 1.5 s is replaced by the server value, and a claimed timeout that can't have happened yet is rejected.

Real games come from PGN import (`[%clk]` comments give think time and clock). For each of your moves Stockfish evaluates the position (MultiPV 3), the reply after your move, and a **null-move threat probe**. Moves losing ≥10 win-% points are stored as `GameMistake` rows (inaccuracy ≥10, mistake ≥20, blunder ≥30, the Lichess model).

## 2. Cognitive profiling (`profiling.py`)

Every metric reports n and a 95% Wilson interval, and is flagged insufficient below n=10.

| Measure | Operational definition |
|---|---|
| Pattern recognition | First-move accuracy on 1–2-move puzzles with the board visible, plus the difficulty-adjusted residual (actual − Glicko-expected) |
| Calculation depth/accuracy | Success by solution length (1…5+). "Depth reached" is the longest length solved ≥50% with n≥5. Also blind-mode accuracy |
| Threat detection | Accuracy on `defensiveMove`/`equality` puzzles, plus missed-threat errors per 100 analysed game moves |
| Candidate generation | In candidates mode: 1 if the solution is in your list, 0.5 if any Stockfish top-3 move is, else 0 |
| Working-memory demand | Board-visible vs blind accuracy at equal line length. This is a task measure, not a capacity test |
| Decision latency | Median time to first move, for correct and wrong attempts |
| Consistency under time pressure | Pressure-mode decision quality (timeouts excluded) vs normal mode, plus game error rate when the clock is ≤ max(10 s, 5% of base time) |

## 3. Error DNA (`error_dna.py`) — experimental

The **first matching rule wins** (priority order). Every feature is stored with the label so you can audit it.

| # | Category | Rule (puzzle / game) |
|---|---|---|
| 1 | Time-management failure | Timed out, **or** the move was made with clock ≤ max(10 s, 5% of base) |
| 2 | Impulsive decision | Think time < threshold and >1 legal move. Puzzles: threshold = max(2.5 s, 35% of your own median first-move time on correct puzzles within ±200 rating; 3 s until 8 samples exist). Games: max(1.5 s, min(5 s, 1% of base + 0.3×increment)) |
| 3 | Missed opponent threat | Puzzle themed `defensiveMove`/`equality`, **or** the null-move probe shows the opponent threatened ≥200 cp and the engine's refutation of your move is that threat (same move or same target square) |
| 4 | Endgame technique failure | Endgame phase (non-pawn material ≤13, or no queens and ≤20) or endgame-themed puzzle |
| 5 | Calculation error | Puzzle: first move right, a later move wrong (`fail_ply > 0`), or a failed blind line. Game: your move was forcing and the refutation is forcing |
| 6 | Tactical blindness | Puzzle: first move wrong (not covered above). Game: the best move was forcing and ≥150 cp better than the 2nd best |
| 7 | Poor candidate selection | Candidates mode with the solution missing from your list, or (games) the top-3 engine moves were within 60 cp and you chose outside them |
| 8 | Positional misunderstanding | Everything else: a quiet evaluation error |

**Recurring patterns** are aggregated over games and puzzles in a 90-day window, weighted by recency (21-day half-life). A pattern is *recurring* when it appears ≥3 times in ≥2 different games or sessions.

Limits: one mistake can have several causes, and the label can't see your thoughts. The priority order is a design choice. Treat the labels as coaching hints.

In the app (0.4.0) the categories are shown in Portuguese, each with a one-line description, how it is recognised and a question to ask yourself next time (`app/cognitive/error_dna.py`, `INFO`): Problema de relógio, Decisão impulsiva, Ameaça ignorada, Técnica de final, Erro de cálculo, Cegueira tática, Candidatos ruins, Erro posicional. The stored keys did not change.

## 4. Adaptive interventions (`interventions.py`)

| Intervention | Targets | Exercise design |
|---|---|---|
| Pattern drill | tactical blindness | Short puzzles of the motif you miss, starting 200 below your rating |
| Blind calculation ladder | calculation error | Blind mode. Required line length grows as success raises difficulty |
| Threat scan | missed threat | Defensive puzzles with an 8 s board lock ("what does my opponent threaten?") |
| Slow-down protocol | impulsive decision | 15 s board lock, comfortable difficulty |
| Candidate listing | poor candidate selection, positional | List 3 candidates first. Quiet, defensive and intermezzo themes |
| Your own game mistakes | all | Positions from your analysed games. Correct = Stockfish rates your move "good" (<10 win-% loss) |
| Endgame technique | endgame failure | Endgame-themed puzzles |
| Clock ladder | time management | Comfortable puzzles under a clock that shrinks 2 s per exercise (minimum 10 s) |

- **Selection:** Thompson sampling over your personal Beta(α, β) posterior of "this intervention reduced this error category". Interventions designed primarily for a category get a +1 prior on α.
- **Controlled difficulty:** the rating offset moves ±50 based on the last 6 attempts, aiming for 70–85% success, bounded to −350…+200 around your rating.
- **Interleaving and spacing:** every 4th exercise is a due retention review or a different concept.

## 5. Retention engine (`retention.py`)

- Each concept (primary tactical theme) has SM-2-style state. Intervals are 1 d, then 3 d, then × ease (1.3–3.0), capped at 120 d. The grade comes from correctness, speed relative to your median, and hesitation.
- **Anti-cramming:** a success before half of the current interval has passed does not grow the interval.
- **Genuine retention:** the probe is usually a **transfer** probe, a *new* puzzle of the concept you have never seen. Every 4th probe is a **recall** probe on a puzzle you solved at least ~0.8 × interval ago. The two are counted separately.
- The retention curve shows success by delay since the last exposure (<1 d … >3 w), with a "new positions only" column. If you only recognise recently seen positions, the long-delay, new-position success collapses.

## 6. Attention and fatigue (`attention.py`) — experimental

A break is suggested when, with ≥16 attempts in the session:

- the last 8 attempts' difficulty-adjusted residual is ≥0.20 below the early part of the session and ≤−0.15 overall,
- **and** both halves of that window are below the early level (consistent, not one streak),
- **and** decisions became ≥25% slower, or hesitation rose by ≥1 event per attempt, or the session has lasted ≥100 min.

Two flagged sessions in 3 days, or a 3-day residual ≤ −0.15 over ≥30 attempts, make the daily plan offer a lighter day. This is a performance signal, not a diagnosis.

## 7. Pressure simulation (`pressure.py`)

Eight levels, from 60 s down to 12 s per puzzle. Higher levels add defensive, intermezzo, quiet-move and long themes plus higher target **complexity**, a 0–1 score built from:

- the number of forcing moves (several tempting candidates),
- the number of legal moves,
- line length,
- defending or in check,
- the Lichess rating deviation (uncertainty about the puzzle's difficulty).

You move up a level with ≥4 of 6 good decisions in time, and down with ≤2. **Decision quality** (correctness and cp lost when wrong, timeouts excluded; each wrong move's loss is capped at 1000 cp, like the games' ACPL, so one missed mate scored at ~10000 cp cannot swamp the mean) is reported separately from **speed** (share of the clock used, timeout rate). Pressure attempts don't change your puzzle rating.

## 8. Performance prediction (`prediction.py`) — experimental

OLS trend with a 95% CI on the slope and 95% **prediction** intervals at +14 and +30 days, for:

- game accuracy and blunders per 100 moves (needs ≥10 analysed games),
- puzzle rating (needs ≥14 training days).

Below those thresholds you get "insufficient data". There is no Elo forecast, and the disclaimer is always shown.

## 9. Scientific validation (`principles.py`)

Validated learning principles, with references, linked to the features that use them: active retrieval, spaced repetition, interleaving, feedback, deliberate practice, progressive challenge. Experimental features are listed separately: Error DNA, intervention-effectiveness inference, fatigue detection, pressure complexity, prediction, and the transfer-probe definition of retention. Evidence that these principles transfer to *chess playing strength* is limited, which is why ChessLab measures your games.

## 10. Closed loop (`loop.py`)

| Phase | Advances when |
|---|---|
| MEASURE | ≥20 non-targeted graded puzzles (or ≥3 analysed games). Loop sessions serve unseen puzzles near your rating, plus a due review every 5th |
| DIAGNOSE | Recurring patterns are computed. The top category (and its most frequent theme) becomes the target. With no recurring pattern the loop goes back to MEASURE and asks for 20 more |
| INTERVENE | An assignment is created via Thompson sampling. The pre-metric is the category's error rate on the baseline set, plus the game rate |
| PRACTICE | 30 intervention exercises (persisted, can span days) |
| REASSESS | 20 mixed, *non-targeted*, unseen puzzles |
| ADAPT | If ≥3 games with ≥100 user moves exist both before and after the assignment start, the outcome is the **game** error rate. Otherwise it is the reassessment rate. "Improved" means the rate fell by ≥2 points or by ≥20% relative, and the Beta posterior is updated. The next cycle starts at DIAGNOSE, using the reassessment as its measurement |

Caveats, also shown in the UI: no control group, small samples, regression to the mean and general improvement all confound "it worked". The posterior is a per-user hint that becomes more useful over many cycles.

Each cycle keeps a log. Since 0.4.0 every entry has a stable `code` (`cycle_started`, `baseline_sufficient`, `no_recurring_error`, `target`, `assigned`, `practice_done`, `outcome_recorded`, `reassessment_reused`) plus its data (`target` stores `category` and `theme`, `assigned` stores `intervention`), and the interface writes the sentence from the code. Entries written by 0.3.0 are translated by migration `0002_v040_ptbr`.
