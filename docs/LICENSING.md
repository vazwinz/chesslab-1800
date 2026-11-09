# Licensing and attribution

## Third-party components

| Component | Licence | How AURA uses it | Obligations |
|---|---|---|---|
| **Stockfish** (<https://stockfishchess.org>) | GPL-3.0 | Separate executable, talked to over UCI. The desktop builds bundle it (`desktop/fetch_stockfish.py` downloads the official `sf_17.1` release); development setups use the one you install. | Credit Stockfish, ship its licence notice and offer its source (the installer shows `desktop/LICENSE-NOTICE.txt` with the links). |
| **Lichess puzzle database** (<https://database.lichess.org/#puzzles>) | CC0 (public domain) | Downloaded and imported locally from inside the app. | None legally. Attribution to lichess.org is shown in the app, the installer and here. Each puzzle keeps its `GameUrl` back to the source game. |
| **python-chess** | GPL-3.0 | Imported by the backend (rules, PGN, UCI). | A program that imports a GPL library and is distributed has to be GPL-3.0-compatible. |
| **Atkinson Hyperlegible Next** (font, via `@fontsource-variable`) | SIL Open Font License 1.1 | The interface font, bundled in the frontend build. | Ship the licence with the font: `frontend/public/licenses/atkinson-hyperlegible-next-OFL-1.1.txt` ends up next to the font files in every build. |
| chess.js | BSD-2-Clause | Rules in the browser | Keep the copyright notice. |
| react-chessboard | MIT | Board rendering | Keep the copyright notice. |
| React, Vite, Tailwind CSS, Recharts, Zustand, FastAPI, SQLAlchemy, Alembic, Mako, Pydantic, Uvicorn, httpx, zstandard, pywebview | MIT / BSD / Apache-2.0 | Framework code | Keep the notices (they ship in `node_modules` / site-packages and inside the PyInstaller bundle). |
| PyInstaller | GPL-2.0 with the bootloader exception | Builds the desktop executable | The exception allows distributing the built app under any licence. |
| Qt / PyQt6 (Linux builds only) | LGPL-3.0 / GPL-3.0 | The window on Linux | Compatible with AURA's GPL-3.0. |

## AURA licence

GPL-3.0 (`LICENSE`). Distributing the app with Stockfish and python-chess inside requires a GPL-3.0-compatible licence anyway. When you share the installer, also share where the source is (the repository or the source zip). The installer shows `desktop/LICENSE-NOTICE.txt` (in Portuguese).

## Your data and the network

Everything you do stays in your local database. AURA connects to the internet only to:

- download the Lichess puzzle dump (when you ask);
- import your games from the public Chess.com API (when you ask; only your username is sent);
- ask GitHub for the latest release (at start-up; the answer is reused for 6 hours, or 30 minutes after a failed check; can be turned off in Configurações);
- talk to the coach AI, **only if you configure one**. Ollama runs on your PC. An online service receives the facts about the position you asked to explain (no evaluation numbers, nothing about you) and your API key, which is otherwise kept only on your computer.
