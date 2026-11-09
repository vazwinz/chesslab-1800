# Status and remaining work

This list covers everything that is minimal, unverified or missing. "Verified" means an automated test or a manual run in the build environment (Linux, Python 3.13, Stockfish 16 from apt, Chromium via Playwright, NSIS 3.09).

## Verified in the build environment (0.4.0)

- **Backend tests**: 91 pass (Stockfish tests ran against the real engine). The Windows check below added 7, for 98.
- **Migrations**: a database written by the real 0.3.0 code (`tests/fixtures/TEST_ONLY_db_v0_3_0.sqlite`) is recognised, checked, backed up, stamped at the 0.3.0 baseline and upgraded with every row intact. A migration that crashes halfway leaves the database as it was (tables, columns and row counts checked). Models and migrations are compared on every test run.
- **Frozen app**: a Linux PyInstaller build of this spec started headless on a copy of that 0.3.0 database, migrated it from inside the bundle (Alembic reads the shipped migration files), wrote the backup and served 0.4.0.
- **Installer script**: `desktop/installer.nsi` compiles with NSIS 3.09 without warnings (with the Linux payload as a stand-in).
- **Browser tests** (`frontend/e2e/smoke.mjs`, 50 checks, light and dark): solving right and wrong, the explanation, opening the analysis and coming back with the session intact, game review, every Diagnóstico tab, every screen, the "?" popovers, Stockfish on the analysis board, and on a phone (iPhone 13 emulation) every screen without horizontal scrolling and a board with squares of 45 px. `first_run.mjs`: the tour (desktop and phone) and the empty states on a new database. No page errors.
- **Puzzle selection**: about 1 ms per pick on a synthetic 3-million-puzzle database (was 0.7 s mixed, 1.25 s assessment); `/next` answers in 5–20 ms.
- **Import speed**: about 6,700 puzzles per second on synthetic rows in the Lichess format, so roughly 15 minutes for the full dump on the development machine.
- **Resumable download**: drop and resume (HTTP Range), a locked rename (retries, then import straight from the finished download), reuse of an already complete download, all with a local test server.
- **Coach**: board facts (fork, pin, skewer, discovered attack, mate patterns, pieces left en prise, net material) on known positions; the AI answer validator rejects unknown moves, numbers, false "best move" claims and non-JSON answers, using a fake model.

## Verified on Windows 11 (0.4.0)

On the developer's PC (Windows 11 Pro 26200, Python 3.14.5, Node 26, NSIS 3, Edge WebView2 157), with the real 0.3.0 installation and data, driving the installed app (UI Automation for the installer and dialogs, the DevTools protocol for the window):

- **Build**: `desktop/build_windows.ps1` builds the installer and the portable zip (PyInstaller 6.22, pywebview 6.2.1); `fetch_stockfish.py` downloads Stockfish 17.1 (sse41-popcnt). The 98 backend tests pass with Stockfish 17.1, none skipped; `npx tsc -b` passes.
- **Upgrade over 0.3.0** installed in a folder of its own (`D:\AURA`): the installer proposes that folder, replaces `_internal` entirely and renames the shortcuts. The first start migrated a real 4 GB database (backup 15 s, migration 0.1 s, the row count of every table unchanged), showed the "Seus dados foram atualizados" notice and wrote `backups/chesslab-copia-da-0.3.0-<date>.db`. The window appears about 19 s after the click, with nothing on screen before it.
- **"Close AURA first"**: with 0.4.0 open, the installer and the uninstaller both ask to close it; Repetir asks again while it is open and continues once it is closed; Cancelar stops. An open 0.3.0 is not detected (it has no lock).
- **Uninstall**: deletes only `AURA.exe`, `_internal`, `LICENSE-NOTICE.txt` and `Uninstall.exe` (another file in the folder stayed), removes the shortcuts and registry keys and asks about the data with Não as the default button; Não keeps `%LOCALAPPDATA%\AURA` intact. Reinstalling then proposes `%LOCALAPPDATA%\Programs\AURA` (the custom folder is forgotten on uninstall).
- **Single instance**: a second start shows "O AURA já está aberto" and exits.
- **Window**: the colour before the page loads matches the saved theme (light from the first frame; dark too, apart from the frame described below); the chosen theme survives a restart; a move on the board starts a running WebAudio context whose clock advances (the sound itself was not listened to); text can be selected and copied (FEN field, PGN box, page text, the Copiar buttons); Ctrl + / Ctrl - / Ctrl 0 and Ctrl + wheel zoom.
- **Error dialog**: a corrupted `chesslab.db` gives a dialog in Portuguese with the data folder, the backups and the `aura.log` path; no window opens and the file is not touched.
- **DPAPI**: a key saved for Claude is stored with `"scheme": "dpapi"`, decrypts only for the Windows user, appears nowhere in plain text in the data folder (database, WAL, log, WebView2 profile), and "Apagar a chave salva" removes it.
- **The real Lichess dump** (in a temporary data folder): the 310 MB download resumes after closing AURA halfway (HTTP Range; SHA-256 identical to a complete download), the rename works, the import finishes and the file is deleted. All 6,193,530 rows of the November 2026 dump are read.
- **Chess.com import** of a public account's last month: games downloaded and analysed in the background; real rating and time class come from the headers.

Fixed during this check: the launcher ignored `CHESSLAB_DATA_DIR` for `aura.log` and the window profile; Ctrl + / Ctrl - did nothing (pywebview switches WebView2's browser accelerator keys off); Ctrl+F flipped the analysis board and Ctrl+A opened the analysis after a puzzle; the corrupted-database dialog showed SQLAlchemy's English text; the real Lichess dump (it starts with a pzstd skippable frame) was read as plain CSV and could not be imported.

## Still not verified

- **AI services.** The Anthropic API (waiting for the owner's key), Ollama (not installed on the test PC) and other OpenAI-compatible services were never called; only a fake model in the tests.
- **The update notice against a real release.** At test time the repository answered 404 to anonymous requests (private), so the check ends in "nenhuma versão publicada (ou repositório privado)". It needs a public repository with a Release containing `AURA-Setup-<version>.exe` (the workflow creates it when you push a tag).
- **"Seguir o sistema" with Windows in light mode.** The test PC uses dark mode, and Windows settings were not changed for the test.
- **A dark frame at start.** In the dark theme one or two captured frames (100–200 ms) are `#121212` instead of `#14181F` while the page loads. It does not come from the app's CSS (an explicit root background did not remove it); cosmetic.
- **Linux.** The Linux build was not re-run after the Windows fixes; the changed launcher code is either Windows-only or covered by tests that run on Linux too.
- **PostgreSQL.** Untested.

## The WinError 5 download failure (fixed in 0.4.0)

0.3.0 downloaded the dump to `lichess_db_puzzle.csv.zst.part` and renamed it at the end. On Windows, antivirus software (and sometimes the search indexer) opens a file right after it is written to scan it; while it holds the file, renaming it fails with `[WinError 5] Acesso negado`, even though the download itself was complete. 0.4.0 retries the rename for a few seconds, and if it is still blocked, imports straight from the complete `.part` file. A complete download is reused instead of downloaded again, an interrupted one resumes where it stopped, and the file is deleted after a successful import.

On the developer's PC the failure had a second cause: the first import had stopped at 5,605,000 of 6,193,530 puzzles without finishing (its job record still says "running"), and 0.3.0 closed the dump only when an import read it to the end, so AURA itself still held the `.zst` open when the second download tried to replace it. 0.4.0 closes the file whenever an import ends and refuses a second import while one is running.

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
