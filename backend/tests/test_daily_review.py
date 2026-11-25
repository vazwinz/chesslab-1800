"""The day's session inside "Seus erros de partida": served first, then the old pool; the feedback
replays why your move failed and says when the position comes back."""
from __future__ import annotations

from datetime import date, timedelta

from app.models import Game, GameMistake

# White to move and in check from the queen on d2: Qxd2 (or Kxd2) wins it, Kf1?? loses the queen to Qxd1+
FEN = "4k3/8/8/8/8/8/3q4/3QK3 w - - 0 1"


def _seed(db, n: int = 2, played: date | None = None) -> list[int]:
    ids = []
    for i in range(n):
        g = Game(fingerprint=f"dr{i}-{played}", pgn="", white="TestUser", black=f"Rival{i}", result="0-1",
                 user_color="white", source="chess.com", played_on=played or date.today(), analyzed=True,
                 metrics={"criteria": 2, "deep": "done"})
        db.add(g)
        db.flush()
        m = GameMistake(game_id=g.id, ply=40, fen_before=FEN, move_uci="e1f1", move_san="Kf1", best_uci="d1d2",
                        best_san="Qxd2", eval_before_cp=900, eval_after_cp=-900, cp_loss=1000, win_pct_loss=60.0,
                        severity="blunder", phase="endgame", category="missed_opponent_threat", clock_s=42.0,
                        detail={"refutation": ["e1f1", "d2d1"]}, pv=["d1d2", "e8d7"])
        db.add(m)
        db.flush()
        ids.append(m.id)
    db.commit()
    return ids


def _start(client) -> int:
    return client.post("/api/sessions", json={"kind": "own_mistakes"}).json()["id"]


def test_session_items_come_first_then_the_old_pool(client, db):
    today_ids = _seed(db, 2)
    old_id = _seed(db, 1, played=date.today() - timedelta(days=30))[0]
    sid = _start(client)
    served = []
    for _ in range(3):
        ex = client.post(f"/api/sessions/{sid}/next").json()
        served.append((ex["game_mistake_id"], ex["mode"], ex["moment"]))
        client.post(f"/api/attempts/{ex['attempt_id']}/give-up", json={"elapsed_ms": 1000})
    assert [s[0] for s in served[:2]] == today_ids or sorted(s[0] for s in served[:2]) == sorted(today_ids)
    assert [s[2]["index"] for s in served[:2]] == [1, 2] and served[0][2]["total"] == 2
    assert served[0][1] == "daily_review"
    assert served[2][0] == old_id and served[2][1] == "standard" and served[2][2] is None


def test_kind_only_after_the_answer(client, db):
    _seed(db, 1)
    ex = client.post(f"/api/sessions/{_start(client)}/next").json()
    assert set(ex["moment"]) == {"index", "total", "source"}
    assert "moment_kind" not in ex and "moment_label" not in ex
    assert ex["context"] == {"opponent": "Rival0", "move_number": 1, "clock_s": 42.0}


def test_feedback_brings_the_refutation_and_when_it_returns(client, db):
    _seed(db, 2)
    sid = _start(client)
    ex = client.post(f"/api/sessions/{sid}/next").json()
    wrong = client.post(f"/api/attempts/{ex['attempt_id']}/move", json={"uci": "e1f1"}).json()
    assert wrong["correct"] is False
    assert wrong["refutation_uci"] == ["e1f1", "d2d1"] and wrong["refutation_san"] == ["Kf1", "Qxd1+"]
    assert wrong["best_line_san"][0] == "Qxd2" and wrong["fen_before"] == FEN
    assert wrong["moment_kind"] == "common" and wrong["moment_label"] == "Erro"
    assert wrong["next_in_days"] == 1
    ex = client.post(f"/api/sessions/{sid}/next").json()
    right = client.post(f"/api/attempts/{ex['attempt_id']}/move", json={"uci": "d1d2"}).json()
    assert right["correct"] is True and right["next_in_days"] == 1


def test_review_today_reports_progress(client, db):
    _seed(db, 2)
    r = client.get("/api/review/today").json()
    assert (r["done"], r["total"], r["new_games"]) == (0, 2, 0)
    ex = client.post(f"/api/sessions/{_start(client)}/next").json()
    client.post(f"/api/attempts/{ex['attempt_id']}/give-up", json={"elapsed_ms": 1000})
    assert client.get("/api/review/today").json()["done"] == 1


def test_after_the_session_with_nothing_old_left_it_says_the_session_is_done(client, db):
    _seed(db, 1)
    sid = _start(client)
    ex = client.post(f"/api/sessions/{sid}/next").json()
    client.post(f"/api/attempts/{ex['attempt_id']}/give-up", json={"elapsed_ms": 1000})
    r = client.post(f"/api/sessions/{sid}/next")
    assert r.status_code >= 400 and "Sessão do dia feita" in r.json()["detail"]


def test_feedback_says_in_one_sentence_why_the_game_move_failed(client, db):
    _seed(db, 1)
    ex = client.post(f"/api/sessions/{_start(client)}/next").json()
    r = client.post(f"/api/attempts/{ex['attempt_id']}/give-up", json={"elapsed_ms": 1000}).json()
    assert r["why"] == "Depois de [[Kf1]], ele captura a dama em d1."
