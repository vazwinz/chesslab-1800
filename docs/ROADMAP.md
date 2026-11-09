# Status and remaining work

This list covers everything that is minimal, unverified or missing. "Verified" means an automated test or a manual run in the build environment (Linux, Python 3.13, Stockfish 16 from apt, Chromium via Playwright, NSIS 3.09).

## Verified in the build environment (0.4.0)

- **Backend tests**: 91 pass (Stockfish tests ran against the real engine).
- **Migrations**: a database written by the real 0.3.0 code (`tests/fixtures/TEST_ONLY_db_v0_3_0.sqlite`) is recognised, checked, backed up, stamped at the 0.3.0 baseline and upgraded with every row intact. A migration that crashes halfway leaves the database as it was (tables, columns and row counts checked). Models and migrations are compared on every test run.
- **Frozen app**: a Linux PyInstaller build of this spec started headless on a copy of that 0.3.0 database, migrated it from inside the bundle (Alembic reads the shipped migration files), wrote the backup and served 0.4.0.
- **Installer script**: `desktop/installer.nsi` compiles with NSIS 3.09 without warnings (with the Linux payload as a stand-in).
- **Browser tests** (`frontend/e2e/smoke.mjs`, 50 checks, light and dark): solving right and wrong, the explanation, opening the analysis and coming back with the session intact, game review, every Diagnóstico tab, every screen, the "?" popovers, Stockfish on the analysis board, and on a phone (iPhone 13 emulation) every screen without horizontal scrolling and a board with squares of 45 px. `first_run.mjs`: the tour (desktop and phone) and the empty states on a new database. No page errors.
- **Puzzle selection**: about 1 ms per pick on a synthetic 3-million-puzzle database (was 0.7 s mixed, 1.25 s assessment); `/next` answers in 5–20 ms.
- **Import speed**: about 6,700 puzzles per second on synthetic rows in the Lichess format, so roughly 15 minutes for the full dump on the development machine.
- **Resumable download**: drop and resume (HTTP Range), a locked rename (retries, then import straight from the finished download), reuse of an already complete download, all with a local test server.
- **Coach**: board facts (fork, pin, skewer, discovered attack, mate patterns, pieces left en prise, net material) on known positions; the AI answer validator rejects unknown moves, numbers, false "best move" claims and non-JSON answers, using a fake model.

## Not verified here: please check on your PC

- **Windows build and installer.** `desktop/build_windows.ps1` was not run (no Windows here), and the installer was not run on real Windows with the real app: the "close AURA first" check, the upgrade over 0.3.0 (it replaces the old uninstaller, which deleted the whole install folder, with the new one that deletes only AURA's files), and the optional deletion of your data on uninstall.
- **Windows-only code paths.** DPAPI key encryption, the single-instance lock, the native error dialogs, the window colour read from the Windows theme, and WebView2 behaviour (sounds through WebAudio, the persistent profile in `%LOCALAPPDATA%\AURA\webview`, text selection, Ctrl +/- zoom).
- **Real services.** The Anthropic API, Ollama and other OpenAI-compatible services were never called (only a fake model in the tests). The Chess.com public API and the GitHub Releases check were tested with recorded or fake responses only. For the update notice to work, the repository must be public and have a Release with `AURA-Setup-<version>.exe` (the workflow creates it when you push a tag).
- **The real Lichess dataset.** database.lichess.org is blocked from the build environment, so the 300 MB download and the import of the real file were not run here.
- **Stockfish download for the build.** `fetch_stockfish.py` assumes the release asset names of `sf_17.1`. If the download fails, use `--from <path to stockfish.exe>`.
- **PostgreSQL.** Untested.

## The WinError 5 download failure (fixed in 0.4.0)

0.3.0 downloaded the dump to `lichess_db_puzzle.csv.zst.part` and renamed it at the end. On Windows, antivirus software (and sometimes the search indexer) opens a file right after it is written to scan it; while it holds the file, renaming it fails with `[WinError 5] Acesso negado`, even though the download itself was complete. 0.4.0 retries the rename for a few seconds, and if it is still blocked, imports straight from the complete `.part` file. A complete download is reused instead of downloaded again, an interrupted one resumes where it stopped, and the file is deleted after a successful import.

## Minimal versions: what's missing

- **Opening module.** Repertoires from PGN/SAN/FEN, drills, common-mistake review, pawn-structure summary, Stockfish plans and your own notes. Missing: variation trees (each line is linear), spaced repetition for opening moves, and an opening-explorer database.
- **Endgames.** 10 textbook positions played against Stockfish, plus endgame puzzles from the Lichess database. Missing: tablebase-exact verdicts (Syzygy), a larger curated set, and step-by-step lessons.
- **Coach.** The rule-based text covers the common tactical motifs. Positional ideas (pawn structure, piece activity, plans) are only described through Stockfish's line, not explained.
- **Ratings.** Glicko-1 against fixed puzzle ratings. RD does not grow with inactivity. Everyone starts in the first difficulty band; the band jumps to the rating's band once the rating is established (RD ≤ 110) and more than 100 points outside it.
- **Fatigue and complexity thresholds.** Chosen by design, not calibrated on data. They should be tuned once you have weeks of your own data.
- **Error DNA.** Heuristic rules. Good candidates for refinement: separating "missed threat" from "tactical blindness" when both apply (the priority order decides), and deeper analysis for game imports (`GAME_ANALYSIS_DEPTH`).
- **Closed-loop outcome.** Simple pre/post comparison with no control condition. A natural next step is an A/B design that alternates two interventions within the same error category.
- **Auth and multi-user.** Not implemented. AURA is a single-user local application and the server only accepts connections from the same computer.
- **Frontend tests.** Only the Playwright tests, no component tests. The chart library is the largest chunk (about 400 kB) and loads only on the screens that use it.
- **WebAssembly Stockfish fallback.** Not built. A native binary is required.
- **Code signing.** The Windows build is not signed, so SmartScreen warns on first run.
