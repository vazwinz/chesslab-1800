# Configuration

Everyday settings (theme, board, notation, sounds, goal rating, the coach AI, update notice) are changed in the app, under **Configurações**, and stored in the database. The environment variables below are for development and special setups (see `backend/app/config.py`). On Windows, `setx NAME "value"` stores one permanently (open a new terminal afterwards); `$env:NAME="value"` sets it for the current PowerShell session.

| Variable | Default | Meaning |
|---|---|---|
| `CHESSLAB_DATA_DIR` | desktop app: `%LOCALAPPDATA%\AURA` (Linux `~/.local/share/aura`); dev: `backend/data` | Folder for the database, `backups/`, `secrets.json`, `aura.log` and the window's browser profile. |
| `DATABASE_URL` | `sqlite:///<data dir>/chesslab.db` | SQLAlchemy URL. PostgreSQL (`postgresql+psycopg://user:pw@host/db`, needs `pip install psycopg[binary]`) is supported by SQLAlchemy but **untested** here. |
| `STOCKFISH_PATH` | the bundled binary, else `stockfish` on PATH, else `/usr/games/stockfish` | Full path to the Stockfish executable (Windows: the `.exe`). |
| `ENGINE_DEPTH` | `16` | Default search depth for analysis requests. |
| `ENGINE_MAX_DEPTH` | `30` | Upper bound accepted by the API. |
| `ENGINE_MAX_TIME` | `10` | Max seconds per `movetime` request (depth searches are capped at 3× this). |
| `ENGINE_THREADS` | `0` (automatic: half the CPU cores, at most 4) | Stockfish `Threads` for the analysis board and the coach. Puzzle checking and background game analysis use their own single-thread instances, so neither waits for the other. |
| `ENGINE_HASH_MB` | `64` | Stockfish `Hash`. |
| `GAME_ANALYSIS_DEPTH` | `12` | Depth used to analyse imported games (higher = slower, more precise Error DNA). |
| `COACH_DEPTH` | `18` | Depth of the Stockfish facts behind "Explicar" (rules and AI both start from them). |
| `CHESSLAB_PLAYER_NAMES` | empty | Your usernames (comma separated) to detect your colour in PGNs. Normally set in the app. |
| `AURA_UPDATE_REPO` | `vazwinz/chesslab-1800` | Public GitHub repository whose latest Release announces new versions. Empty = never check. |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost,::1,testserver` | Host headers the server answers to. Anything else gets 400 (protection against DNS rebinding). |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed origins for the Vite dev server. Writes from any other origin are refused. |
| `FRONTEND_DIST` | `frontend/dist` | Built frontend served by FastAPI. |

Frontend: `VITE_API_PROXY` (dev proxy target, default `http://127.0.0.1:8000`), `VITE_API_BASE` (API prefix when served elsewhere).

## Coach AI ("Explicar")

Off by default. **Configurações → IA do coach** offers:

| Provider | Address | Key |
|---|---|---|
| Ollama (free, runs on your PC) | `http://localhost:11434/v1` | none. Install Ollama, `ollama pull <model>` (e.g. `qwen2.5:7b`), keep it running |
| Claude (Anthropic) | `https://api.anthropic.com` (Messages API, `anthropic-version: 2026-10-21`) | your key from console.anthropic.com; default model `claude-haiku-5-5` |
| Any OpenAI-compatible service | e.g. LM Studio, OpenRouter, OpenAI (`/chat/completions`) | depends on the service |

"Testar conexão" lists the models the service reports. What the AI receives: the position, Stockfish's best lines and the board facts as text, **without** evaluation numbers. What the app accepts back: a JSON with the explanation sections, mentioning only moves that are in the facts, with no numbers except mate distances, and never calling a move "best" unless it is Stockfish's first line. Anything else is discarded and the rule-based explanation is shown, with the reason.

The key is stored in `<data dir>/secrets.json`: encrypted with Windows DPAPI for your Windows user on Windows; elsewhere readable only by your user (`chmod 600`). It is bound to the address it was saved for, so changing the address requires typing the key again. It is never returned by the API and never written to the database or the log.

## Puzzle import

**Configurações → Puzzles** downloads the Lichess dump and imports it in the background. The download resumes after a drop (HTTP Range), retries the final rename when antivirus software holds the file, imports straight from the finished download if the rename is still blocked, and deletes the file after a successful import. From the command line: `backend/scripts/import_puzzles.py` (`--limit`, `--min-rating`, `--max-rating`, `--batch-size`, `--no-validate`, `--database-url`). The import never runs at startup.

## Database migrations

They run automatically every time the app starts (`backend/app/migrate.py`). Before changing an existing database, a full copy goes to `<data dir>/backups/chesslab-copia-da-<previous version>-<date>.db` (the 5 newest are kept). The whole upgrade is one SQLite transaction: if any step fails, nothing changes and the app shows the error instead of starting.

To create a new migration during development, from `backend/`:

```bash
.venv/bin/python -m alembic -c alembic.ini revision --autogenerate -m "describe the change"
```

`tests/test_migrations.py` fails if the models and the migrations disagree.
