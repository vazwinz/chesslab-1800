# Status and remaining work

This list covers everything that is minimal, unverified or missing. "Verified" here means an automated test or a manual run in the build environment (Linux, Python 3.13, Stockfish 16 from apt, Chromium via Playwright).

## Verified in the build environment

- Stockfish answers over UCI: native Stockfish 16, mate-in-1 test, MultiPV, move comparison, API cache.
- The streaming importer works on a **test-only** file in the exact Lichess format. Covered: validation of illegal rows, incremental re-import that updates ratings and themes, bulk speed of about 6k new rows/s and 9k updates/s on 200k synthetic rows, constant memory.
- Puzzle solutions replay legally, and move checking accepts alternative mating moves.
- Progress persists after an app restart (test: new app instance on the same database file).
- The dashboard uses only stored data. An empty database shows "—", never invented numbers.
- Every Cognitive Engine module has unit or integration tests. One full closed-loop cycle (measure → adapt) runs through the HTTP API with reduced block sizes.
- PGN import plus Stockfish analysis plus Error DNA on synthetic test games.
- Browser smoke test: desktop solve (correct and wrong) with feedback and Error DNA shown, dashboard updated, analysis board running Stockfish, and on mobile (iPhone 13 emulation) a board that fits with no horizontal scroll.

## Not verified here: please check on your PC

- **AURA on Windows.** The Linux build was built and run here: native Qt window, bundled Stockfish, browser fallback. The Windows build (`desktop/build_windows.ps1`, PyInstaller + Edge WebView2) and the GitHub Actions workflow could not be run. The Stockfish download in `fetch_stockfish.py` assumes the release asset names of `sf_17.1` (github.com is blocked here). If the download fails, use `--from <path>`.
- **Linux package size.** About 670 MB unpacked (274 MB tar.gz), mostly Qt WebEngine. A future GTK/WebKit build could be much smaller.

- **The real Lichess dataset.** database.lichess.org is blocked from the build environment. Run the import plus `scripts/verify_install.py` locally (README).
- **Windows.** `setup.ps1` and `run.ps1` were written for PowerShell but could not be executed here. The Python and Node code is cross-platform. Stockfish is found through `STOCKFISH_PATH`.
- **PostgreSQL.** SQLAlchemy supports it and the code is dialect-neutral (bulk insert and update use Core statements), but it is untested.
- **The optional LLM coach adapter** (`COACH_PROVIDER=openai_compatible`) has never been called.
- **Real Chess.com games.** Only synthetic PGNs were tested. Chess.com exports include `[%clk]`, which time-management detection needs.

## Minimal versions: what's missing

- **Chess.com API import.** Not implemented, so export your PGN from Chess.com.
- **Opening module.** Repertoires from PGN/SAN/FEN, drills, common-mistake review, pawn-structure summary, Stockfish plans and your own notes. Missing: variation trees (each line is linear), spaced repetition for opening moves, and an opening-explorer database.
- **Endgames.** 10 textbook positions played against Stockfish, plus endgame and zugzwang puzzles from the Lichess database. Missing: tablebase-exact verdicts (Syzygy), a larger curated set, and step-by-step lessons. Goals were checked with Stockfish at depth 30, not with tablebases.
- **AI coach.** Rule-based explanations generated only from Stockfish output. The LLM path is an untested adapter.
- **Ratings.** Glicko-1 against fixed puzzle ratings. RD does not grow with inactivity.
- **Selection.** Random puzzles without a theme filter take about 25 ms on 200k rows; themed selection takes about 2 ms. Fine for local use; could be tuned for 5M+ rows.
- **Fatigue and complexity thresholds.** Chosen by design, not calibrated on data. They should be tuned once you have weeks of your own data.
- **Error DNA.** Heuristic rules. Good candidates for refinement: separating "missed threat" from "tactical blindness" when both apply (the priority order decides), and using deeper analysis for game imports (`GAME_ANALYSIS_DEPTH`).
- **Closed-loop outcome.** Simple pre/post comparison with no control condition. A natural next step is an A/B design that alternates two interventions within the same error category.
- **Background work.** Game analysis runs inside the request, which is slow for many games at once. A job queue with progress reporting would help.
- **Auth and multi-user.** Not implemented. The app is a single-user local application.
- **Frontend.** No component or unit tests (only the Playwright smoke test). The bundle is about 750 kB and could be code-split. No offline or PWA support.
- **WebAssembly Stockfish fallback.** Not built. A native binary is required, and it is the recommended setup.
