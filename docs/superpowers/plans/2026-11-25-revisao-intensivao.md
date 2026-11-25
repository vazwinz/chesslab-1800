# Revisão intensivão — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "Seus erros de partida" starts with a daily session of the day's most valuable moments (try first, answer straight after, back in 1/3/7/21 days, one if-then rule a day), fed by games that arrive and get analysed on their own; the game review screen gets the graph, phase accuracy and "Próximo momento".

**Architecture:** Backend services: `moments.py` (classify moments, build and store the day's session, the spaced ladder), `motifs.py` (one Portuguese sentence for why a move fails), `rules.py` (the rule of the day); `games.analyze_game` stores the win curve, think times, phase accuracy and the refutation line; `game_jobs` gets the two-pass queue and auto import; `trainer` serves the session inside the `own_mistakes` kind. Frontend: Train (session flow, refutation replay, end screen with the rule), Home/Play (active rule), Settings (auto import switch), Games (phase 3).

**Tech Stack:** FastAPI, SQLAlchemy, python-chess, Stockfish; React + TypeScript + Tailwind; pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-revisao-intensivao-design.md`

## Global Constraints

- UI copy in Brazilian Portuguese; code, comments and dev docs in English.
- The mode and the routine step keep the name "Seus erros de partida" and the key `own_mistakes`.
- No takeback and no hint inside a moment; the answer comes straight after the attempt; no confidence tap.
- No database migration: new data goes in `Game.metrics`, `GameMistake.detail` (JSON) and KV rows.
- Judging criteria stays `CRITERIA = 2`.
- Session size: 5 new moments + up to 5 returns (light day 3 + 3); max 2 moments from one game.
- Ladder: correct → +1, +3, +7, +21 days; wrong → tomorrow and one step down; 3 correct in a row at 21 days → mastered.
- Tests never touch the network or the owner's data: background jobs and auto import are off under pytest (`AURA_BACKGROUND_JOBS=0` set in `conftest.py`).

## Builder calls (deviations from the spec, to tell the owner)

- **Deep pass re-analyses the whole game at depth 18**, not only selected moves: the engine has no cache to reuse the quick pass, and a full deep pass also catches what the quick one missed. Games are still reviewable seconds after import (quick pass at 12).
- **The "lance bom" moment (one ! or !! a day) is left out of v1**: attempts point at `GameMistake` rows, and a good move has none. Later, if wanted.
- **"Onde você acha que perdeu?" lives on the game review screen** (lost games, asked once), not inside the daily session, so the session flow stays one kind of step.
- **Stale (old-criteria) games are not resumed automatically at start**; only unanalysed and deep-pending ones.

## Review Focus

1. A game with no clock tags (`think` all None): the session and the time line must work, the time line simply absent.
2. A game played from a position (FEN header) or as Black: the win curve indexes plies of that game, the moment's FEN and orientation must be right.
3. The owner's existing data: 1583 mistakes and 179 game-position attempts from before — returns computed from that history must be capped (5 a day), never flood the session.
4. Opening the app twice the same day, or the routine planned before games arrive: the stored session must not change under the owner; new games show as a second round.
5. "Atualizar agora" while a deep pass runs: the queue is cancelled, the update goes on, and the next start rebuilds the queue (no game left half-analysed or lost).

---

## Phase 1

### Task 1: Analysis stores the win curve, think times, phase accuracy and the refutation line

**Files:**
- Modify: `backend/app/services/games.py` (`analyze_game`, metrics dict)
- Test: `backend/tests/test_review.py`

**Interfaces:**
- Produces: `Game.metrics["wins"]: list[float | None]` (win-% from the owner's side for every position, length `len(plies)+1`, same array the accuracy uses, after `_filled`), `metrics["think"]: list[float | None]` (seconds per ply, None for the opponent's plies and when the PGN has no clock), `metrics["phase_accuracy"]: {"opening"|"middlegame"|"endgame": float | None}` (mean of `judgement.move_accuracy(before, after)` per phase), `metrics["deep"]: "pending" | "done"` (`"pending"` when `depth < settings.game_analysis_depth`), `GameMistake.detail["refutation"]: list[str]` (UCI, `s.user.pv[:8]`, the played move first).

- [ ] **Step 1: Failing test** `test_analysis_keeps_the_curve_think_times_and_refutation` (needs_engine): import the fixture's first game with names `["TestUser"]`, `analyze_game(db, g, engine, depth=8)`; assert `len(m["wins"]) == plies + 1`, every value in 0..100; `m["think"][ply]` is a float for a user ply with a clock and None for an opponent ply; `set(m["phase_accuracy"]) == {"opening","middlegame","endgame"}`; `m["deep"] == "pending"`; every stored mistake has `detail["refutation"][0] == mistake.move_uci`.
- [ ] **Step 2:** Run `pytest tests/test_review.py -k curve -v` → FAIL (KeyError "wins").
- [ ] **Step 3:** Implement in `analyze_game`: keep a `think_by_ply` list and a per-phase list of move accuracies; add the keys to `metrics`; put `refutation` into the `GameMistake(detail=...)` dict next to `f.as_dict()`.
- [ ] **Step 4:** Run the test → PASS; run `pytest tests/test_review.py tests/test_judgement.py -q` → all pass.
- [ ] **Step 5:** Commit `Analysis: keep the win curve, think times, phase accuracy and the refutation line`.

### Task 2: Two-pass queue, resume at start, and the update pauses the analysis

**Files:**
- Modify: `backend/app/services/game_jobs.py`, `backend/app/services/updater.py` (`_busy_reason`), `backend/app/main.py` (lifespan), `backend/app/config.py` (`background_jobs`), `backend/tests/conftest.py`
- Test: `backend/tests/test_game_jobs.py` (new), `backend/tests/test_updater.py`

**Interfaces:**
- Produces: `game_jobs.QUICK_DEPTH = 12`; `game_jobs.enqueue_analysis(ids, depth=None, two_pass=False) -> dict` (two_pass: quick tasks for all ids first, then deep tasks `depth=None`; dedupe by `(gid, depth)`); `game_jobs.deep_pending_ids(db) -> list[int]`; `game_jobs.resume(db) -> dict | None` (queues `pending_ids` two-pass + `deep_pending_ids` deep; None when nothing); `settings.background_jobs: bool` (env `AURA_BACKGROUND_JOBS`, default `"1"`). `_chesscom(...)` queues new games with `two_pass=True`.

- [ ] **Step 1: Failing tests** (no engine; patch `game_jobs._ensure_worker` to a no-op and read `_queue`):
  - `test_two_pass_queues_quick_then_deep`: `enqueue_analysis([3, 4], two_pass=True)` → queue `[("analyze",3,12),("analyze",4,12),("analyze",3,None),("analyze",4,None)]`.
  - `test_the_same_game_can_wait_for_both_passes_but_not_twice`: calling it again adds nothing.
  - `test_resume_queues_unanalysed_and_deep_pending`: one game unanalysed, one with `metrics["deep"]="pending"`, one done → queue holds quick+deep for the first, deep for the second, nothing for the third.
  - in `test_updater.py`, replace the refusal test with `test_update_cancels_a_running_game_analysis` (game_jobs state "running" → `_busy_reason()` is None and `game_jobs.cancel` was called) and keep `puzzle import still blocks`.
- [ ] **Step 2:** Run `pytest tests/test_game_jobs.py tests/test_updater.py -q` → the new tests FAIL.
- [ ] **Step 3:** Implement. `resume` is called from `lifespan` after `updater.cleanup()` only when `settings.background_jobs`; conftest sets `os.environ.setdefault("AURA_BACKGROUND_JOBS", "0")`. `_busy_reason` calls `game_jobs.cancel()` and logs instead of returning the analysis message.
- [ ] **Step 4:** Run the two files and then the whole suite → pass.
- [ ] **Step 5:** Commit `Game analysis: a quick pass then a deep one, resumed at start; Atualizar agora pauses it`.

### Task 3: Auto import from Chess.com

**Files:**
- Modify: `backend/app/services/game_jobs.py`, `backend/app/services/prefs.py`, `backend/app/main.py`
- Test: `backend/tests/test_game_jobs.py`

**Interfaces:**
- Produces: pref `chesscom_auto_import: True`; `game_jobs.maybe_auto_import(db, now=None) -> bool` (False without username or with the pref off, or when KV `"last_auto_import"` is under 60 min old; otherwise stores the time, calls `enqueue_chesscom(username, months, analyze=True)` with `months = 2 if today.day <= 2 else 1`, returns True). Called from `lifespan` (when `background_jobs`) and from the daily session endpoint (Task 6).

- [ ] **Step 1: Failing tests** (patch `enqueue_chesscom`): `test_auto_import_needs_a_username_and_the_switch`, `test_auto_import_at_most_once_an_hour` (second call 30 min later → False; 61 min → True), `test_auto_import_takes_last_month_too_on_the_first_two_days` (now=day 2 → months=2; day 3 → 1).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `Chess.com: your games arrive on their own when AURA opens`.

### Task 4: Moments and the ladder (`moments.py`)

**Files:**
- Create: `backend/app/services/moments.py`
- Test: `backend/tests/test_moments.py`

**Interfaces:**
- Produces:
  - `KIND_WEIGHT = {"decisive": 2.0, "missed": 1.8, "common": 1.0}`, `PATTERN_BONUS = 1.3`, `INTERVALS = (1, 3, 7, 21)`, `NEW = {False: 5, True: 3}`, `RETURNS = {False: 5, True: 3}`.
  - `kind_of(wins: list[float | None] | None, ply: int) -> str`: `"decisive"` when `wins[ply] >= 50`, `wins[ply+1] < 25` and no later value from the owner's side goes above 40; `"missed"` when `wins[ply] >= 70`, `wins[ply] - wins[ply-2] >= 20` and `wins[ply] - wins[ply+1] >= 10`; else `"common"`; `"common"` when `wins` is None.
  - `ladder(history: list[tuple[bool, datetime]]) -> tuple[date | None, int]`: (due date, step index 0..4); `None` = mastered.
  - `due_returns(db, day: date, limit: int) -> list[int]` (GameMistake ids whose ladder date ≤ day, most overdue first, from all `game_position` attempts; mistakes with severity `retired` excluded).
  - `build_session(db, day: date, light: bool) -> dict` and `today_session(db, day: date | None = None, light: bool | None = None) -> dict`: `{"day", "items": [{"mistake_id", "game_id", "kind", "source": "new"|"return"}], "built_at"}` stored in KV `"daily_review"`; `today_session` returns the stored one for that day or builds it. Candidates: `mistake`/`blunder` rows of games with `played_on` in the last 24 h (yesterday and today) not marked `metrics["reviewed_on"]`, widened to 3 days when empty; unanswered items of the previous stored session come first as returns; considered games get `reviewed_on = day.isoformat()`.
  - `new_games_since(db, session: dict) -> int` (analysed games imported after `built_at` and not reviewed: the "Chegaram N partidas novas" second round) and `second_round(db, day) -> dict` (appends their moments with the same rules).

- [ ] **Step 1: Failing tests** (synthetic `Game`/`GameMistake` rows with hand-made `wins`, no engine):
  - `test_a_drop_that_never_comes_back_is_decisive`, `test_a_drop_after_the_opponents_gift_is_a_missed_chance`, `test_old_games_without_a_curve_are_common`.
  - `test_ladder_goes_1_3_7_21_and_masters_after_three_at_21`, `test_a_miss_brings_it_back_tomorrow_one_step_down`.
  - `test_session_has_five_new_and_at_most_five_returns` (12 candidates, 9 due → 5 + 5; light → 3 + 3).
  - `test_no_more_than_two_moments_from_one_game` and `test_neighbours_differ_in_game_when_possible`.
  - `test_session_is_built_once_a_day` (second call returns the stored dict even after new games arrive; `new_games_since` counts them).
  - `test_no_games_today_uses_returns_and_the_last_three_days`.
  - `test_history_before_the_feature_is_capped` (40 old attempts due → 5 returns).
- [ ] **Step 2:** Run `pytest tests/test_moments.py -q` → FAIL (module missing).
- [ ] **Step 3:** Implement. Ordering: greedy, pick the highest-scored item whose game and category differ from the previous one, else the highest; then interleave returns (new, return, new, …).
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `Moments: the day's session of your most valuable mistakes, and the ladder that brings them back`.

### Task 5: The session inside "Seus erros de partida" (trainer + routine + API)

**Files:**
- Modify: `backend/app/services/trainer.py` (`next_exercise` own_mistakes branch, `_payload`, `finish` game-position feedback), `backend/app/services/routine.py` (`_plan` target, `STEPS["own_mistakes"]` unit), `backend/app/routers/core.py` (GET `/api/review/today`, POST `/api/review/today/more`)
- Test: `backend/tests/test_daily_review.py` (new), `backend/tests/test_routine.py`

**Interfaces:**
- Consumes: `moments.today_session`, `moments.ladder`, `moments.second_round`, `game_jobs.maybe_auto_import`.
- Produces:
  - Exercise payload for a session item adds `"moment": {"index": i, "total": n, "source"}` and `"context": {"opponent", "move_number", "clock_s"}` (no kind before the answer); `Attempt.mode = "daily_review"`. After the session, the existing `_own_mistake` with mode `"standard"`, and the payload has `"moment": None`.
  - `finish` feedback for game positions adds `"refutation_san": list[str]`, `"refutation_uci": list[str]` (from `detail["refutation"]`, empty for old rows), `"best_line_san"`, `"best_line_uci"` (from `gm.pv[:6]`), `"kind"`, `"kind_label"` (`"Erro decisivo"`, `"Chance perdida"`, `"Erro"`), `"next_in_days": int | None` (None = dominado), `"fen_before"`.
  - `GET /api/review/today` → `{"session": ..., "done": int, "total": int, "new_games": int}` (calls `maybe_auto_import`); `POST /api/review/today/more` → `second_round`.
  - Routine: `own_mistakes` target = `len(today_session.items)` (light day per `routine` light flag), step left out when 0; `_done` unchanged (attempts in `own_mistakes` sessions).

- [ ] **Step 1: Failing tests**: `test_session_items_come_first_then_the_old_pool` (client: create session `own_mistakes`, `next` serves session items in order with `moment.index` 1..n, then `moment` None), `test_feedback_brings_the_refutation_and_when_it_returns` (wrong move → `refutation_uci[0] == mistake.move_uci`, `next_in_days == 1`; right move → `next_in_days == 1` first time), `test_kind_only_after_the_answer` (`"kind"` absent in the exercise payload), `test_review_today_reports_progress`; in `test_routine.py`, `test_own_mistakes_target_is_the_session_size`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run these and then the whole suite → pass (adjust the routine tests that pinned target 5).
- [ ] **Step 5:** Commit `Seus erros de partida: starts with the day's session; feedback shows why your move failed`.

### Task 6: Train screen for the session + Settings switch

**Files:**
- Modify: `frontend/src/pages/Train.tsx`, `frontend/src/lib/prefs.tsx`, `frontend/src/pages/Settings.tsx`, `frontend/src/lib/help.ts`

**Interfaces:**
- Consumes: the Task 5 payloads.
- Produces UI:
  - header "Momento 2 de 7" and the context line `vs. {opponent} · lance {n} · você tinha {m:ss}`;
  - after the answer: kind chip, then on a wrong answer the refutation stepped on the board (your move, then the reply with an arrow), then the best line, each with ← → like the puzzle solution;
  - "Volta amanhã" / "volta em N dias" / "Dominado";
  - end-of-session screen "Sessão do dia feita" with "Continuar com erros antigos" and, when `new_games > 0`, "Revisar as N novas";
  - Settings → Partidas: "Buscar minhas partidas do Chess.com ao abrir" (`chesscom_auto_import`).

- [ ] **Step 1:** Implement; `npx tsc -b` → no errors.
- [ ] **Step 2:** Browser check on a temporary data folder (0.5.2 data with 2 analysed test games and one old attempt): header and context, wrong answer replays the refutation, right answer, end screen, routine step count. No console errors.
- [ ] **Step 3:** Commit `Treinar: the day's session, with the refutation replayed on the board`.

## Phase 2

### Task 7: Motif sentence (`motifs.py`)

**Files:** Create `backend/app/services/motifs.py`; modify `trainer.finish` (adds `"why": str`); test `backend/tests/test_motifs.py`.

**Interfaces:** `describe(fen: str, refutation_uci: list[str]) -> str | None` in Portuguese, first match wins: mate in the line → "Depois de {seu lance}, ele dá mate em {n}."; reply captures a piece left without enough defence (`judgement.see`) → "Depois de {seu lance}, ele captura {peça} em {casa}."; the reply attacks two pieces worth ≥ 3 (or the king and one) → "Depois de {seu lance}, {resposta} ataca {peça} e {peça} ao mesmo tempo."; a piece of yours pinned to king/queen after the reply → "Depois de {resposta}, seu {peça} fica cravado."; else None (the frontend then says "Depois de {seu lance}, ele ganha vantagem com {resposta}.").

- [ ] **Step 1:** Failing tests with fixed FENs: `test_mate`, `test_hanging_piece`, `test_fork`, `test_pin`, `test_quiet_line_has_no_motif`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `Feedback: one sentence for why your move fails (mate, loose piece, fork, pin)`.

### Task 8: Time × weight and the rule of the day

**Files:** Create `backend/app/services/rules.py`; modify `trainer.finish` (adds `"time_note": str | None`), `routers/core.py` (GET/PUT/DELETE `/api/rule`), `frontend/src/pages/Train.tsx` (end screen), `frontend/src/pages/Home.tsx`, `frontend/src/pages/Play.tsx`; tests `backend/tests/test_rules.py`, `test_daily_review.py`.

**Interfaces:**
- time note when `kind in ("decisive","missed")` and `think_s` is known and `< 5` or `< 0.5 × metrics["median_think_s"]`: "Você pensou {s} s no lance que decidiu a partida." (missed: "…na chance que ele te deu.").
- `rules.TEMPLATES: dict[category, str]` with the 8 texts of the spec's table, verbatim.
- `rules.suggestion(db, day) -> dict | None` (most frequent `GameMistake.category` among today's wrong `daily_review` attempts; ties → the later one); `rules.accept(db, text, category) -> dict`, `rules.active(db, day) -> dict | None` (accepted on an earlier day, newest), `rules.trend(db, category, day) -> {"before": n, "after": m, "games_before", "games_after"}` (criteria-2 games, 7 days each side), KV `"rules"`.

- [ ] **Step 1:** Failing tests: `test_suggestion_is_the_most_frequent_missed_category`, `test_no_suggestion_without_a_wrong_answer`, `test_active_rule_is_yesterdays`, `test_trend_counts_the_category_before_and_after`, `test_time_note_only_for_fast_decisive_moves`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement backend; end screen shows the suggestion (Aceitar / Editar / Pular), Home and Play setup show the active rule and its trend line. **Step 4:** Tests pass; `npx tsc -b` clean; browser check of the end screen, Home and Play.
- [ ] **Step 5:** Commit `Rule of the day and the time spent on the moves that decided a game`.

## Phase 3

### Task 9: Game review screen

**Files:** Modify `backend/app/routers/core.py` (GET `/api/games/{gid}` adds `"moments": [{"ply","kind"}]` via `moments.kind_of` for mistake/blunder rows plus `highlights`), `frontend/src/pages/Games.tsx`, `frontend/src/lib/help.ts`; test `backend/tests/test_review.py`.

**Interfaces / UI:** win-% graph (SVG from `metrics.wins`, click → that ply, think-time bars under it from `metrics.think`); "Precisão por fase" row from `metrics.phase_accuracy`; "Próximo momento" button (next ply in `moments`); "Seus erros" shows mistakes and blunders, inaccuracies behind "mostrar N imprecisões"; for a lost game not yet asked, the marks start hidden behind "Onde você acha que perdeu? Clique no lance." → reveal and compare with the first `decisive` moment, stored in KV `"calibration"` (`{game_id, picked_ply, decisive_ply}`), with "você acertou onde perdeu em X de Y" shown under it.

- [ ] **Step 1:** Failing test `test_game_detail_lists_its_moments`. **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** pass; `tsc` clean; browser check on a game with and without `wins`.
- [ ] **Step 5:** Commit `Game review: the graph, accuracy by phase, Próximo momento and where you think you lost`.

### Task 10: Numbers that say whether it works; CI with the engine; docs; full verification

**Files:** `backend/app/services/moments.py` (`stats(db, day) -> {"returns_ok_3d", "returns_ok_7d", "sessions_week", "median_session_min"}`: accuracy of returns answered at ladder step ≥ 2 and ≥ 3, days of this week with the session finished, median minutes per finished session), `backend/app/routers/core.py` (in `/api/review/today`), `frontend/src/pages/Diagnosis.tsx` (a "Seus erros de partida" card with those numbers and the rule trend), `.github/workflows/desktop.yml` (download the same Stockfish the Windows build bundles, set `STOCKFISH_PATH`), `README.md` (What's new for the next version, test count), `docs/ROADMAP.md` (verified / not verified), `docs/CONFIGURATION.md` (`AURA_BACKGROUND_JOBS`).

- [ ] **Step 0:** Failing test `test_review_stats_counts_returns_and_sessions` (synthetic attempts) → implement `stats` → pass.
- [ ] **Step 1:** Workflow change; whole backend suite locally with Stockfish → pass; `npx tsc -b` and `npm run build` → pass.
- [ ] **Step 2:** The update path simulation (0.5.2 backend fills a temporary folder, the new backend opens it): session builds, routine counts, nothing lost.
- [ ] **Step 3:** Commit `CI with Stockfish; docs for the daily session`. Then show the owner the full diff (`git diff origin/main...revisao-intensivao`) before any merge, push or tag.
