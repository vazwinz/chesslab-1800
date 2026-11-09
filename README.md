# AURA (ChessLab 1800)

A local chess training app aimed at reaching ~1800 on Chess.com. It uses real chess rules (python-chess and chess.js), runs Stockfish over UCI, trains on the Lichess puzzle database and tracks your progress. On top of that sits the **Cognitive Engine**, which measures how you decide, classifies your mistakes, picks targeted exercises, schedules spaced reviews and learns which interventions actually help you. Your results in real games are the main outcome it measures.

The whole interface is in Brazilian Portuguese. These developer docs stay in English.

> Status: every module has a working version. What is minimal, experimental or still unverified is listed in [`docs/ROADMAP.md`](docs/ROADMAP.md). Read that file before you trust any number.

| Layer | Tech |
|---|---|
| Frontend | React 18 + TypeScript, Vite, Tailwind CSS, chess.js, react-chessboard, Recharts, Zustand |
| Backend | Python 3.11+ (tested on 3.13), FastAPI, SQLAlchemy 2, Alembic, python-chess |
| Database | SQLite (`%LOCALAPPDATA%\AURA\chesslab.db` in the desktop app). Migrations run on every start. PostgreSQL via `DATABASE_URL` is untested |
| Engine | Stockfish (native binary, UCI), bundled in the desktop app |
| Puzzles | Lichess puzzle database (CC0), downloaded and imported from inside the app |

## Since 0.4.0 (next version)

- **Jogar**: a game against the computer at a level that follows you. Eleven levels from 400 to 2500 (Iniciante to Grande mestre) play weaker by searching less deep, picking among Stockfish's top moves with some randomness and, at the bottom, now and then a random move. The automatic level is your rating against AURA (Glicko-1, from the games you play without help), so each game is about even. Stockfish judges every move you make on the spot: a mistake or a *capivarada* turns the whole screen red for about a second, with just the word on it. It does not stop the game, explain anything or offer a way back: there is no takeback, and the better move is shown only when the game is over (a red frame, "Só a borda", and "Desligado" are options). After a blunder the computer always plays the punishing move, at any level, unless you switch that off. Start from the initial position, 14 openings, your repertoire, the textbook endgames, the position before one of your own mistakes or a FEN; optional clock (only yours runs), hints (first the piece, then the move), draw offers and an evaluation bar. Finished games go to Partidas and are analysed like any other. "Jogar daqui" on the game review and on the analysis board starts a game from the position on screen.
- **Review and analysis boards**: the board stays in view while the explanation scrolls; more arrows (best move, your move, the opponent's threat and the reply that punishes your move, Stockfish's 2nd and 3rd moves), each one switchable; right-click marks squares red and draws arrows that stay; "Próxima partida" and "Anterior" go through your analysed games.
- **Linux**: pieces can be dragged with the mouse again (the Qt window reports touch support, which switched the board to its touch-only backend).
- **Move list**: it scrolls itself to the current move without moving the page (on a phone the page used to jump down to the list at every move).

## What's new in 0.4.0

- **New interface**: minimalist, light and dark themes (follows the system until you choose), the board as the main element, works on desktop and phone. A welcome tour, a one-line purpose on every screen, a "?" next to every metric and chart, empty states that say what to do next, and an in-app guide ("Como treinar com o AURA").
- **Everything in Portuguese**: interface, API error messages, tactical themes, Error DNA, the installer. Chess terms in Portuguese (garfo, cravada, espeto…), with figurine notation by default.
- **"Explicar" coach**, after each puzzle and on each mistake in your games: the idea of the best move, the opponent's threat, the tactical theme, why your move was worse, and the main line commented move by move, always built from Stockfish facts. **Optional AI** (Ollama on your PC, or your own Anthropic/OpenAI-compatible key) only rewrites those facts: its answer is checked and discarded if it mentions a move outside the facts, any evaluation number, or calls a move "best" that Stockfish didn't put first. The source (rules or AI) is always shown. The key stays on your PC (DPAPI on Windows) and the app works 100% without AI.
- **Automatic database migrations** (Alembic) on every start, with a backup first. Databases created by 0.3.0 (which had no migrations) are recognised, checked and upgraded with their progress intact.
- **New-version notice** from GitHub Releases, silent when offline.
- **Chess.com import by username** (public API) with background analysis and a progress line. Your real rating comes from the game headers, by time control.
- **Faster puzzles**: picking a puzzle takes about 1 ms instead of 0.7–1.25 s on a 3-million-puzzle database.
- **Training session survives navigation**: analysing a position and coming back keeps your puzzle and your streak. Board sounds and chess.com-style moves (click or drag, legal-move dots, promotion picker).
- **Security**: the local server refuses other hosts (DNS rebinding) and cross-site writes; path traversal in static files fixed.
- **Download fix**: the puzzle download resumes after a drop and no longer fails with `WinError 5` when antivirus software holds the file for a moment (details in `docs/ROADMAP.md`).

## AURA desktop app (Windows + Linux)

AURA is packaged as a normal desktop program: double-click it, a window opens, and Stockfish ships inside. Your data is kept in `%LOCALAPPDATA%\AURA` on Windows and `~/.local/share/aura` on Linux. On first start a short tour walks you through downloading the puzzles, importing your games and starting the training loop.

| | Build it yourself | Or let GitHub build it |
|---|---|---|
| Windows | `powershell -ExecutionPolicy Bypass -File desktop\build_windows.ps1` creates **`desktop\dist\AURA-Setup-<version>.exe`** (installer) and a portable zip. The version comes from `backend/app/version.py` | Actions → **desktop** → Run workflow → download `AURA-Windows` |
| Linux | `bash desktop/build_linux.sh` creates `desktop/dist/AURA/AURA`, a menu entry "AURA" and an `aura` command | Same workflow → `AURA-Linux` |

**Updating:** run the new `AURA-Setup-<version>.exe` over the old one (close AURA first; the installer asks). Your data lives in another folder and is migrated automatically on the next start; a copy of the database is saved first in `%LOCALAPPDATA%\AURA\backups` (the 5 newest are kept).

**Uninstalling** removes only AURA's own files, never the whole folder it was installed in. It asks whether to delete your training data too (default: keep).

**Sharing with friends:** send them `AURA-Setup-<version>.exe`. No admin rights are needed, and it can be removed from "Apps & features". Because the app isn't code-signed, Windows SmartScreen shows a warning: they click *Mais informações → Executar assim mesmo*. AURA is GPL-3.0 (see `LICENSE`), so share the source link along with it.

You need Python 3.11+ and Node 18+ for the build only, not to run the app. The window uses Edge WebView2 on Windows (built into Windows 10/11) and Qt WebEngine on Linux. On Ubuntu/Debian, if the window doesn't open, install `sudo apt install libxcb-cursor0`. If the window still fails, AURA opens in your browser instead. For development without packaging, run `python desktop/aura.py`.

**Publishing a version** (for the update notice): bump `backend/app/version.py` and `frontend/package.json`, commit, then push a tag `vX.Y.Z`. The workflow builds both platforms and publishes a GitHub Release with `AURA-Setup-X.Y.Z.exe`; installed apps see it at their next start. The repository must be public (or set `AURA_UPDATE_REPO` to a public one).

## Quick start for development: Windows (PowerShell)

You need **Python 3.11+**, **Node.js 18+**, **Git**, and **Stockfish** for Windows from <https://stockfishchess.org/download/>.

```powershell
git clone https://github.com/vazwinz/chesslab-1800.git
cd chesslab-1800
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
setx STOCKFISH_PATH "C:\Tools\stockfish\stockfish-windows-x86-64-avx2.exe"   # then open a NEW PowerShell window
powershell -ExecutionPolicy Bypass -File scripts\run.ps1                        # http://127.0.0.1:8000
```

Download the puzzles from **Configurações → Puzzles** in the app (about 300 MB; the import takes roughly 15 minutes: about 6,700 puzzles per second were measured on the development machine). From the command line instead:

```powershell
curl.exe -L -o lichess_db_puzzle.csv.zst https://database.lichess.org/lichess_db_puzzle.csv.zst
backend\.venv\Scripts\python.exe backend\scripts\import_puzzles.py lichess_db_puzzle.csv.zst
backend\.venv\Scripts\python.exe backend\scripts\verify_install.py
```

`verify_install.py` checks that Stockfish answers a known mate-in-1, that the database came from a real import (not the test fixture), that a sample of puzzles replays legally, and that Stockfish agrees with a sample of solutions. Re-running the import on a newer dump updates existing puzzles and adds new ones.

For frontend development, `scripts\run.ps1 -Dev` also starts Vite with hot reload on http://localhost:5173.

## Quick start for development: Linux / macOS

```bash
sudo apt install stockfish            # or brew install stockfish, or set STOCKFISH_PATH
bash scripts/setup.sh
bash scripts/run.sh                   # http://127.0.0.1:8000, then Configurações → Puzzles
```

## Using it

The in-app guide (**Como treinar**) is the user manual. In short:

1. **Configurações → Puzzles**: download the Lichess puzzles once.
2. **Partidas**: import your Chess.com games by username (or paste a PGN). Stockfish analyses them in the background and labels each inaccuracy, mistake and *capivarada* (blunder) with an Error DNA category. These games are the main outcome measure, and their headers give your real rating.
3. **Treinar → Treino em ciclo**: measure (20 mixed puzzles), diagnose your top recurring error, practise 30 exercises built for it, reassess, and record whether the error became rarer (in your games when there are enough).
4. **Diagnóstico**: the loop, Error DNA, retention, fatigue, pressure, skill profile, prediction (with intervals), what has worked for you, and the science page (validated principles vs experimental features).
5. **Jogar**: play the computer at your level after training. Your mistakes turn the screen red on the spot, and every game is analysed like an imported one.
6. Other screens: **Análise** (free board with Stockfish and the coach), **Aberturas** (repertoire drills), **Finais** (textbook endgames against Stockfish), **Plano do dia**.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q          # Windows: .venv\Scripts\python.exe -m pytest -q
cd frontend && npx tsc -b                             # type check
```

110 backend tests cover legality, the importer (streaming, validation, incremental updates, the multi-frame file Lichess publishes, resumable download), engine communication (real Stockfish), migrations (a real 0.3.0 database, rollback on failure, a corrupted file, models vs migrations), the desktop launcher (data folder, default and `CHESSLAB_DATA_DIR`; the WebView2 zoom keys; the error dialog), local-only security, the coach (board facts, AI answer validation), Chess.com import, update check, playing against the computer (levels, the move judge, the level that follows you, saved games), persistence across restarts, the API, and every Cognitive Engine module including a full closed-loop cycle. Tests that need Stockfish are skipped when it is missing.

Browser tests (Playwright): start the server with puzzles imported, then `node frontend/e2e/smoke.mjs http://127.0.0.1:8000 <dir>` (light and dark desktop, explanation, analysis and back, every Diagnóstico tab, every screen, phone layout) and `node frontend/e2e/first_run.mjs <url> <dir>` on an empty database (tour and empty states). Both save screenshots.

**Test data:** `backend/tests/fixtures/TEST_ONLY_*` holds puzzles and games that Stockfish generated in the Lichess CSV format, plus a database written by the real 0.3.0 code. It is **not Lichess data** and is only used by tests. The import script refuses to load it.

## Documentation

- [`docs/COGNITIVE_ENGINE.md`](docs/COGNITIVE_ENGINE.md): design, exact rules and thresholds, data model, closed loop
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md): environment variables, the coach AI, where data is kept
- [`docs/LICENSING.md`](docs/LICENSING.md): Stockfish, Lichess, python-chess and font attribution, licence obligations
- [`docs/ROADMAP.md`](docs/ROADMAP.md): what is verified, what is not, what is minimal

## Architecture

```
backend/app/
  main.py                          app, local-only middleware, PT-BR error handlers, SPA serving
  config.py, db.py, models.py      settings, engine/session, SQLAlchemy models
  migrate.py, migrations/          Alembic migrations run on start (0.3.0 baseline, backups, one transaction)
  security.py, i18n.py, version.py
  services/   engine.py            Stockfish UCI (one instance per role: train / analysis / background / play)
              importer.py          streaming .csv.zst Lichess importer; import_jobs.py: resumable download
              puzzles.py           indexed selection by equality probes, recent-repeat avoidance, move checking
              trainer.py           exercise orchestration + attempt finalisation (rating, DNA, retention, loop)
              coach.py, tactics.py rule-based "Explicar" from Stockfish facts; coach_ai.py: optional AI + validation
              chesscom.py, game_jobs.py, games.py   Chess.com API import, background analysis queue
              secrets.py, updates.py, prefs.py      API key storage, update check, preferences
              play.py              Jogar: levels, the computer's move, the move judge, your level against it
              rating.py, adaptive.py, openings.py, endgames.py, plan.py, dashboard.py, explain.py
  cognitive/  profiling.py  error_dna.py  retention.py  interventions.py  loop.py
              attention.py  pressure.py   prediction.py principles.py     stats.py
  routers/    core.py  cognitive.py (/api/cognitive/*)  extras.py (app, prefs, coach, updates)  play.py (/api/play/*)
frontend/src/
  main.tsx                         router (pages load on first visit)
  components/                      Shell, Board, AnalysisBoard, Explain, Tour, Help, BlunderAlarm, ArrowToggles, charts, ui
  lib/                             api, prefs (theme), meta (PT names), sound, arrows, trainStore and playStore (session), help texts
  pages/                           Home, Train, Play, Games, Analysis, Openings, Endgames, Plan, Diagnosis, Guide, Settings
desktop/                           launcher (aura.py), PyInstaller spec, NSIS installer, build scripts
```

The Cognitive Engine is an extension module. It reads the same `attempts`, `games` and `game_mistakes` tables the base system writes, and keeps its own state in `concept_memory`, `loop_cycles`, `intervention_assignments` and `intervention_stats`.
