# Licensing and attribution

## Third-party components

| Component | Licence | How ChessLab uses it | Obligations |
|---|---|---|---|
| **Stockfish** (<https://stockfishchess.org>) | GPL-3.0 | Separate executable that you install. ChessLab talks to it over the UCI protocol and does not bundle it. | Credit Stockfish. If you ever *distribute* Stockfish with ChessLab, you must also ship its licence and offer its source code. |
| **Lichess puzzle database** (<https://database.lichess.org/#puzzles>) | CC0 (public domain) | Imported locally by `import_puzzles.py`. | None legally. Attribution to lichess.org is good practice and is shown here and in the README. Each puzzle keeps its `GameUrl` back to the source game. |
| **python-chess** | GPL-3.0 | Imported by the backend (rules, PGN, UCI). | A program that imports a GPL library and is distributed has to be GPL-3.0-compatible. |
| chess.js | BSD-2-Clause | Rules in the browser | Keep the copyright notice. |
| react-chessboard | MIT | Board rendering | Keep the copyright notice. |
| React, Vite, Tailwind CSS, Recharts, Zustand, FastAPI, SQLAlchemy, Pydantic, Uvicorn, zstandard | MIT / BSD / Apache-2.0 | Framework code | Keep the notices (they ship in `node_modules` / site-packages). |

## ChessLab / AURA licence

GPL-3.0 (`LICENSE`), chosen when the installer for sharing with friends was added. Distributing the app with Stockfish and python-chess inside requires a GPL-3.0-compatible licence anyway. When you share the installer, also share where the source is (the repo, or the source zip). The installer shows `desktop/LICENSE-NOTICE.txt`.

## Data you import

Your own PGNs stay in your local database. Nothing is sent to any external service, unless you configure the optional LLM coach adapter, which sends engine facts about the position you ask about.
