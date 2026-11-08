# ChessLab 1800

A local chess training platform aimed at reaching ~1800 on Chess.com. It has real chess rules (python-chess and chess.js), runs Stockfish over UCI, trains on the Lichess puzzle database and tracks your progress. On top of that sits the **Cognitive Engine**, which measures how you decide, classifies your mistakes, picks targeted exercises, schedules spaced reviews and learns which interventions actually help you. Your results in real games are the main outcome it measures.

> Status: working minimal versions of every module. The parts that are minimal, experimental or still unverified are listed in [`docs/ROADMAP.md`](docs/ROADMAP.md). Please read that file before you trust any number.

| Layer | Tech |
|---|---|
| Frontend | React 18 + TypeScript, Vite, Tailwind CSS, chess.js, react-chessboard, Recharts |
| Backend | Python 3.11+ (tested on 3.13), FastAPI, SQLAlchemy 2, python-chess |
| Database | SQLite by default (`backend/data/chesslab.db`). PostgreSQL via `DATABASE_URL` is untested |
| Engine | Stockfish (native binary, UCI). The path is set with `STOCKFISH_PATH` |
| Puzzles | Lichess puzzle database (CC0), loaded by a streaming importer |

## Quick start: Windows (PowerShell)

You need: **Python 3.11+**, **Node.js 18+**, **Git**, and **Stockfish** for Windows from <https://stockfishchess.org/download/>. Unzip Stockfish somewhere, e.g. `C:\Tools\stockfish\`.

```powershell
git clone https://github.com/vazwinz/chesslab-1800.git
cd chesslab-1800
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

# tell ChessLab where Stockfish is (use the name of the .exe you unzipped), then open a NEW PowerShell window
setx STOCKFISH_PATH "C:\Tools\stockfish\stockfish-windows-x86-64-avx2.exe"
```

### Import the real Lichess puzzles (one time, roughly 10–20 min)

```powershell
cd chesslab-1800
curl.exe -L -o lichess_db_puzzle.csv.zst https://database.lichess.org/lichess_db_puzzle.csv.zst
backend\.venv\Scripts\python.exe backend\scripts\import_puzzles.py lichess_db_puzzle.csv.zst
# optional, for a quick start:  --limit 300000   or   --min-rating 700 --max-rating 2400
backend\.venv\Scripts\python.exe backend\scripts\verify_install.py
```

`verify_install.py` checks four things: Stockfish answers a known mate-in-1, the database came from a real import (not the test fixture), a sample of puzzles replays legally, and Stockfish agrees with a sample of solutions. You can re-run the import on a newer dump at any time: existing puzzles are updated and new ones are added.

### Run

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run.ps1
# open http://127.0.0.1:8000
```

For frontend development, use `scripts\run.ps1 -Dev`. It also starts Vite with hot reload on http://localhost:5173.

## Quick start: Linux / macOS

```bash
sudo apt install stockfish            # or brew install stockfish, or set STOCKFISH_PATH
bash scripts/setup.sh
curl -L -o lichess_db_puzzle.csv.zst https://database.lichess.org/lichess_db_puzzle.csv.zst
backend/.venv/bin/python backend/scripts/import_puzzles.py lichess_db_puzzle.csv.zst
backend/.venv/bin/python backend/scripts/verify_install.py
bash scripts/run.sh                   # http://127.0.0.1:8000
```

## Using it

1. **Games → Import + analyse.** Paste or upload your Chess.com PGN export and give your username. Stockfish then labels every inaccuracy, mistake and blunder with an Error DNA category. These game metrics are the main outcome measure.
2. **Train → Closed-loop training.** The loop measures a baseline, diagnoses your top recurring error, assigns an intervention (for example *Threat scan* or *Blind calculation ladder*), reassesses you on mixed puzzles, then records whether the error rate fell, preferring real-game data when it has enough.
3. **Cognitive** has the profile, Error DNA, retention curve, intervention effectiveness, fatigue trend, pressure ladder, prediction (with intervals) and the science page (validated principles vs experimental features).
4. The other modes are mixed or single-theme tactics, blind calculation, candidate moves, retention review, pressure, endgame puzzles and your own game mistakes. There are also an analysis board (FEN/PGN, Stockfish, coach), an opening repertoire with drills, textbook endgames played against Stockfish, and a daily plan of about 3 hours with a lighter-day option.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q          # Windows: .venv\Scripts\python.exe -m pytest -q
```

There are 30 tests covering legality, the importer (streaming, validation, incremental updates), engine communication (real Stockfish), persistence across restarts, the API, Error DNA, retention, interventions, a full closed-loop cycle, fatigue, pressure and prediction. Tests that need Stockfish are skipped when it is missing.

The browser smoke test needs Playwright (`npm i -D playwright && npx playwright install chromium`). Start the server, then run `node frontend/e2e/smoke.mjs http://127.0.0.1:8000 .`.

**Test data:** `backend/tests/fixtures/TEST_ONLY_*` holds puzzles and games that Stockfish generated in the Lichess CSV format. It is **not Lichess data** and is only used by tests. The import script refuses to load it.

## Documentation

- [`docs/COGNITIVE_ENGINE.md`](docs/COGNITIVE_ENGINE.md): design, exact rules and thresholds, data model, closed loop
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md): environment variables
- [`docs/LICENSING.md`](docs/LICENSING.md): Stockfish, Lichess, python-chess attribution and licence obligations
- [`docs/ROADMAP.md`](docs/ROADMAP.md): what is minimal, unverified or missing

## Architecture

```
backend/app/
  config.py, db.py, models.py      settings, SQLAlchemy models (attempts store full timing data)
  services/   engine.py            Stockfish UCI wrapper (python-chess), cached analysis
              importer.py          streaming .csv.zst Lichess importer (bulk, incremental, validated)
              puzzles.py           indexed random selection, recent-repeat avoidance, move checking
              trainer.py           exercise orchestration + attempt finalisation (rating, DNA, retention, loop)
              rating.py, adaptive.py, games.py, openings.py, endgames.py, plan.py, dashboard.py, coach.py
  cognitive/  profiling.py  error_dna.py  retention.py  interventions.py  loop.py
              attention.py  pressure.py   prediction.py principles.py     stats.py
  routers/    core.py (base API)  cognitive.py (/api/cognitive/*)
frontend/src/ components/Board.tsx, pages/*.tsx
```

The Cognitive Engine is an extension module. It reads the same `attempts`, `games` and `game_mistakes` tables the base system writes, and keeps its own state in `concept_memory`, `loop_cycles`, `intervention_assignments` and `intervention_stats`.
