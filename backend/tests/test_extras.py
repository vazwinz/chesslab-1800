"""0.4.0 extras: preferences, new-version notice, Chess.com import by username, real rating."""
from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app import db as dbmod
from app.services import updates
from app.version import __version__

from .conftest import PGN_FIXTURE


# ------------------------------------------------------------------ preferences
def test_prefs_roundtrip_and_validation(client):
    p = client.get("/api/prefs").json()
    assert p["theme"] == "system" and p["sound"] is True and p["goal_rating"] == 1800
    p2 = client.put("/api/prefs", json={"theme": "dark", "volume": 3, "player_names": " vaz ,  outro "}).json()
    assert p2["theme"] == "dark" and p2["volume"] == 1.0 and p2["player_names"] == "vaz, outro"
    assert client.get("/api/prefs").json()["theme"] == "dark", "remembered in the database"
    assert client.put("/api/prefs", json={"theme": "roxo"}).status_code == 422
    assert client.put("/api/prefs", json={"nao_existe": 1}).status_code == 422
    assert client.put("/api/prefs", json={"sound": "sim"}).status_code == 422


def test_animations_follow_the_system_unless_you_choose(client):
    assert client.get("/api/prefs").json()["motion"] == "system"
    assert client.put("/api/prefs", json={"motion": "on"}).json()["motion"] == "on"
    assert client.get("/api/prefs").json()["motion"] == "on", "remembered in the database"
    assert client.put("/api/prefs", json={"motion": "sempre"}).status_code == 422


def test_board_arrows_are_on_by_default_and_each_can_be_switched_off(client):
    kinds = ("arrows_best", "arrows_played", "arrows_opponent", "arrows_others")
    p = client.get("/api/prefs").json()
    assert all(p[k] is True for k in kinds)
    p = client.put("/api/prefs", json={"arrows_others": False, "arrows_opponent": False}).json()
    assert p["arrows_others"] is False and p["arrows_opponent"] is False and p["arrows_best"] is True
    assert client.get("/api/prefs").json()["arrows_others"] is False, "remembered in the database"
    assert client.put("/api/prefs", json={"arrows_best": "sim"}).status_code == 422


def test_validation_errors_are_in_portuguese(client):
    r = client.post("/api/sessions", json={"kind": "nonsense"})
    assert r.status_code == 422 and r.json()["detail"].startswith("Dados inválidos: modo de treino")
    assert client.get("/api/games/99999").json()["detail"] == "Não encontrado"


# ------------------------------------------------------------------ new version notice
def test_update_check_offline_never_errors(client, monkeypatch):
    def offline(repo):
        raise OSError("sem rede")

    monkeypatch.setattr(updates, "_fetch", offline)
    r = client.get("/api/update/check?force=true")
    assert r.status_code == 200
    j = r.json()
    assert j["available"] is False and j["ok"] is False and "conexão" in j["error"]


def test_update_check_reports_newer_release_and_caches(db, monkeypatch):
    calls = []

    dl = "https://github.com/vazwinz/chesslab-1800/releases/download/v9.9.0"

    def fake(repo):
        calls.append(repo)
        return {"ok": True, "latest": "9.9.0", "page_url": "https://example/rel", "notes": "novidades",
                "assets": [{"name": "AURA-Setup-9.9.0.exe", "url": f"{dl}/AURA-Setup-9.9.0.exe", "size": 1},
                           {"name": "AURA-linux-x64.tar.gz", "url": f"{dl}/AURA-linux-x64.tar.gz", "size": 1}]}

    pick = updates.pick_asset
    monkeypatch.setattr(updates, "pick_asset", lambda assets: pick(assets, "win32", "AMD64"))
    r = updates.check(db, force=True, fetch=fake)
    assert r["available"] and r["latest"] == "9.9.0" and r["download_url"].endswith(".exe")
    r2 = updates.check(db, fetch=fake)
    assert r2["available"] and len(calls) == 1, "second check comes from the cache"
    same = updates.check(db, force=True, fetch=lambda repo: {"ok": True, "latest": __version__})
    assert same["available"] is False
    assert updates.parse_version("v0.10.1") > updates.parse_version("0.9.9")


def test_update_check_can_be_disabled(client):
    client.put("/api/prefs", json={"update_check": False})
    assert client.get("/api/update/check").json()["enabled"] is False


# ------------------------------------------------------------------ Chess.com import + real rating
class _ChessCom(BaseHTTPRequestHandler):
    pgn = ""

    def log_message(self, *a):
        pass

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path == "/pub/player/testuser/games/archives":
            body = f'{{"archives": ["{base}/pub/player/testuser/games/2026/09", "{base}/pub/player/testuser/games/2026/10"]}}'
            ctype = "application/json"
        elif self.path.endswith("/2026/10/pgn"):
            body, ctype = _ChessCom.pgn, "application/x-chess-pgn"
        elif self.path.endswith("/2026/09/pgn"):
            body, ctype = "", "application/x-chess-pgn"
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def chesscom(monkeypatch):
    import re

    _ChessCom.pgn = re.sub(r'(\[TimeControl "[^"]*"\])', r'\1\n[WhiteElo "1432"]\n[BlackElo "1511"]',
                           PGN_FIXTURE.read_text()).replace("TestUser", "testuser")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _ChessCom)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from app.services import chesscom as cc

    monkeypatch.setattr(cc, "API", f"http://127.0.0.1:{srv.server_port}/pub/player/{{user}}/games/archives")
    yield
    srv.shutdown()


def _wait_job(client, timeout=120):
    for _ in range(int(timeout / 0.2)):
        j = client.get("/api/games/jobs").json()
        if j["status"] != "running":
            return j
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_chesscom_import_by_username_fills_real_rating(client, chesscom):
    r = client.post("/api/games/import/chesscom", json={"username": "testuser", "months": 2, "analyze": False})
    assert r.status_code == 200 and r.json()["status"] == "running"
    j = _wait_job(client)
    assert j["status"] == "done" and j["imported"] == 4 and not j["errors"], j
    games = client.get("/api/games").json()
    assert {g["source"] for g in games} == {"chess.com"}
    assert all(g["time_class"] == "blitz" and g["user_elo"] in (1432, 1511) for g in games)
    rr = client.get("/api/dashboard").json()["real_rating"]
    assert rr["main"]["games"] == 4 and rr["goal"] == 1800 and rr["to_goal"] == 1800 - rr["main"]["current"]
    assert "testuser" in client.get("/api/prefs").json()["player_names"]
    again = client.post("/api/games/import/chesscom", json={"username": "testuser", "months": 2, "analyze": False})
    j2 = _wait_job(client)
    assert again.status_code == 200 and j2["imported"] == 0 and j2["duplicates"] == 4


def test_chesscom_unknown_user_is_reported(client, chesscom):
    client.post("/api/games/import/chesscom", json={"username": "ninguem", "months": 1})
    j = _wait_job(client)
    assert j["errors"] and "não encontrado" in j["errors"][0]
    assert client.post("/api/games/import/chesscom", json={"username": "a b", "months": 1}).status_code == 422


def test_pending_analysis_with_nothing_to_do(client):
    assert "Nenhuma partida pendente" in client.post("/api/games/analyze-pending").json()["message"]


def test_app_info_and_meta(client):
    info = client.get("/api/app").json()
    assert info["version"] == __version__
    meta = client.get("/api/meta").json()
    assert meta["themes"]["fork"]["name"] == "Garfo" and meta["themes"]["pin"]["name"] == "Cravada"
    assert meta["themes"]["skewer"]["name"] == "Espeto"
    assert meta["severity"]["blunder"] == "capivarada"
    assert meta["error_dna"]["missed_opponent_threat"]["tip"].startswith("Da próxima vez")


def test_dashboard_days_follow_local_time(client, monkeypatch):
    """An attempt finished at 23:30 in São Paulo (02:30 UTC next day) counts for the local day.
    Without time.tzset (Windows) the computer's own time zone is used: the case is the same on a
    PC set to São Paulo or anywhere west of UTC, and still checks the local day elsewhere."""
    import os
    from datetime import date, datetime, timedelta, timezone

    if hasattr(time, "tzset"):
        monkeypatch.setenv("TZ", "America/Sao_Paulo")
        time.tzset()
    try:
        from app.models import Attempt

        today = date.today()
        local_2330 = datetime.combine(today, datetime.min.time()) + timedelta(hours=23, minutes=30)
        utc = local_2330.astimezone(timezone.utc).replace(tzinfo=None)  # stored as naive UTC
        with dbmod.SessionLocal() as s:
            s.add(Attempt(exercise_kind="puzzle", mode="standard", correct=True, total_ms=60000, served_at=utc,
                          themes="fork", moves_played=[], move_times_ms=[], hesitation={}, candidates=[],
                          error_detail={}))
            s.commit()
        if utc.date() > date.today():
            pass  # still "today" locally
        d = client.get("/api/dashboard").json()
        assert d["daily_minutes"][-1]["day"] == today.isoformat()
        assert d["daily_minutes"][-1]["minutes"] == 1.0
    finally:
        monkeypatch.delenv("TZ", raising=False)
        os.environ.pop("TZ", None)
        if hasattr(time, "tzset"):
            time.tzset()


def test_band_follows_an_established_rating_but_not_a_provisional_one(db):
    """Everyone starts in the first band; an established rating far above it moves the band there."""
    from app.models import RatingPoint
    from app.services import adaptive

    assert adaptive.band_for(db)["index"] == 0
    db.add(RatingPoint(rating=1700, rd=300))  # provisional: a few lucky puzzles must not jump bands
    db.flush()
    assert adaptive.update_after_attempt(db) is None
    db.add(RatingPoint(rating=1272, rd=60))
    db.flush()
    ch = adaptive.update_after_attempt(db)
    assert ch == {"from": 0, "to": 1, "reason": "rating", "rating": 1272}
    assert adaptive.target_rating(db, 1272) == (1172, 1372)
    # inside the band's margin: no change
    db.add(RatingPoint(rating=1350, rd=60))
    db.flush()
    assert adaptive.update_after_attempt(db) is None
    # far below: back down
    db.add(RatingPoint(rating=850, rd=60))
    db.flush()
    assert adaptive.update_after_attempt(db)["to"] == 0


def test_no_puzzle_message_tells_empty_bank_from_exhausted_bank(db):
    from app.services import trainer
    from app.services.importer import import_puzzles

    from .conftest import PUZZLE_FIXTURE

    assert "Importe os puzzles do Lichess" in trainer._no_puzzle_message(db)
    import_puzzles(db, PUZZLE_FIXTURE)
    assert "já resolveu todos os puzzles" in trainer._no_puzzle_message(db)


def test_pressure_loss_is_capped_like_game_acpl(db):
    """One missed mate (~10000 cp) must not swamp the mean loss shown for a pressure level."""
    from app.cognitive import pressure
    from app.models import Attempt

    for loss in (10000, 200):
        db.add(Attempt(exercise_kind="puzzle", mode="pressure", pressure_level=1, correct=False, cp_loss=loss,
                       total_ms=5000, time_limit_ms=60000, timed_out=False, themes="", moves_played=[],
                       move_times_ms=[], hesitation={}, candidates=[], error_detail={}))
    db.flush()
    assert pressure.pressure_report(db)["by_level"][1]["mean_cp_loss_when_wrong"] == 600.0
