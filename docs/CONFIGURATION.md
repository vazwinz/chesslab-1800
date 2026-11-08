# Configuration

All settings are environment variables (see `backend/app/config.py`). On Windows, `setx NAME "value"` stores one permanently (open a new terminal afterwards); `$env:NAME="value"` sets it for the current PowerShell session.

| Variable | Default | Meaning |
|---|---|---|
| `STOCKFISH_PATH` | `stockfish` on PATH, else `/usr/games/stockfish`, … | Full path to the Stockfish executable (Windows: the `.exe`). |
| `DATABASE_URL` | `sqlite:///backend/data/chesslab.db` | SQLAlchemy URL. PostgreSQL (`postgresql+psycopg://user:pw@host/db`, needs `pip install psycopg[binary]`) is supported by SQLAlchemy but **untested** here. |
| `ENGINE_DEPTH` | `16` | Default search depth for analysis requests. |
| `ENGINE_MAX_DEPTH` | `30` | Upper bound accepted by the API. |
| `ENGINE_MAX_TIME` | `10` | Max seconds per `movetime` request (depth searches are capped at 3× this). |
| `ENGINE_THREADS` | `1` | Stockfish `Threads`. |
| `ENGINE_HASH_MB` | `64` | Stockfish `Hash`. |
| `GAME_ANALYSIS_DEPTH` | `12` | Depth used to analyse imported games (higher = slower, more precise Error DNA). |
| `CHESSLAB_PLAYER_NAMES` | empty | Your usernames (comma separated) to detect your colour in PGNs. Can also be given in the Games page. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed origins for the Vite dev server. |
| `FRONTEND_DIST` | `frontend/dist` | Built frontend served by FastAPI. |
| `COACH_PROVIDER` | `none` | `none` (rule-based explanations from Stockfish output) or `openai_compatible`. |
| `COACH_BASE_URL`, `COACH_API_KEY`, `COACH_MODEL` | empty | For `openai_compatible` (any `/chat/completions` endpoint). Untested; the app never depends on it. |

Frontend: `VITE_API_PROXY` (dev proxy target, default `http://127.0.0.1:8000`), `VITE_API_BASE` (API prefix when served elsewhere).

Puzzle import is never run at startup: use `backend/scripts/import_puzzles.py` (`--limit`, `--min-rating`, `--max-rating`, `--batch-size`, `--no-validate`, `--database-url`).
