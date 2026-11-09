"""Coach: the rule-based explanation must say only what Stockfish and the board say, and the
optional AI must be rejected whenever it strays from those facts."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import chess
import pytest

from app.services import coach, coach_ai, secrets
from app.services.engine import get_engine

from .conftest import needs_engine

FORK = "6k1/3q1p1p/8/8/4N3/8/5PPP/6K1 w - - 0 1"          # Nf6+ forks king and queen
BACK_RANK = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"        # Ra8#
HANG_QUEEN = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"  # ...Qh4?? Nxh4
SCHOLAR = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"   # ...Nf6?? Qxf7#


@pytest.fixture(scope="module")
def eng():
    return get_engine("analysis")


@needs_engine
def test_fork_is_found_and_material_is_counted(eng):
    r = coach.explain(eng, FORK, None, {"user_color": chess.WHITE}, depth=14)
    best = r["engine"]["lines"][0]
    assert best["san"] == "Nf6+"
    s = r["sections"]
    assert "garfo" in s["idea"] and "dama em d7" in s["idea"] and "rei em g8" in s["idea"]
    assert "uma dama a mais" in s["idea"]
    assert any(t["key"] == "fork" for t in s["themes"])
    assert s["line"][0]["san"] == "Nf6+" and "garfo" in s["line"][0]["comment"]
    # every evaluation number in the text is one Stockfish produced
    assert best["eval"]["text"] in s["line_end"]


@needs_engine
def test_mate_and_no_fake_threat(eng):
    r = coach.explain(eng, BACK_RANK, None, {"user_color": chess.WHITE}, depth=12)
    s = r["sections"]
    assert s["idea"] == "[[Ra8#]] é xeque-mate."
    assert "Nenhuma ameaça" in s["threat"], "a forced mate must not turn the opponent's reply into a 'threat'"
    assert any(t["key"] == "backRankMate" for t in s["themes"])


@needs_engine
def test_hanging_queen_explained_as_capture_not_recapture(eng):
    r = coach.explain(eng, HANG_QUEEN, "d8h4", {"user_color": chess.BLACK}, depth=14)
    u = r["sections"]["user"]
    assert u["verdict"] == "capivarada" and not u["is_best"]
    text = " ".join(u["reasons"])
    assert "[[Nxh4]]" in text and "captura a dama em h4" in text and "recaptura" not in text
    assert "uma dama a menos" in text
    assert "[[Nxe5]]" in r["sections"]["threat"]  # the threat that existed before the move


@needs_engine
def test_missed_mate_threat(eng):
    r = coach.explain(eng, SCHOLAR, "g8f6", {"user_color": chess.BLACK}, depth=14)
    s = r["sections"]
    assert "[[Qxf7#]]" in s["threat"] and "xeque-mate" in s["threat"]
    reasons = " ".join(s["user"]["reasons"])
    assert "mate em 1" in reasons and "já existia antes do seu lance" in reasons
    assert "mate em 1 para as Brancas" in s["user"]["headline"]
    assert coach.tip({}, r).startswith("Da próxima vez, se pergunte:")


@needs_engine
def test_explain_endpoint_for_puzzle_attempt_and_terminal(client_with_puzzles):
    c = client_with_puzzles
    sid = c.post("/api/sessions", json={"kind": "mixed"}).json()["id"]
    ex = c.post(f"/api/sessions/{sid}/next").json()
    assert c.post("/api/coach/explain", json={"attempt_id": ex["attempt_id"]}).status_code == 409  # not finished
    c.post(f"/api/attempts/{ex['attempt_id']}/give-up", json={})
    out = c.post("/api/coach/explain", json={"attempt_id": ex["attempt_id"]}).json()
    rules = out["rules"]
    assert out["ai"] is None and rules["source"]["kind"] == "rules" and rules["sections"]["puzzle_note"]
    assert rules["sections"]["tip"].startswith("Da próxima vez")
    mate = c.post("/api/coach/explain", json={"fen": "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"}).json()
    assert mate["rules"]["terminal"] is True
    assert c.post("/api/coach/explain", json={"fen": "nonsense"}).status_code == 422


# ------------------------------------------------------------------ AI validation
def _rules_for_validation():
    return {
        "engine": {"lines": [{"san": "Nf6+", "mate": None, "cp": 528, "pv_san": ["Nf6+", "Kf8", "Nxd7+", "Ke7"]},
                             {"san": "f3", "mate": None, "cp": -487, "pv_san": ["f3"]}],
                   "threat": {"san": "Qd1#", "mate": 1}},
        "allowed_moves": ["Nf6+", "Kf8", "Nxd7+", "Ke7", "f3", "Qd1#"],
        "sections": {"line": [{"san": "Nf6+"}, {"san": "Kf8"}, {"san": "Nxd7+"}], "user": None},
        "position": {"perspective": "você", "side_to_move": "Brancas", "in_check": False},
    }


GOOD = {"ideia": "[[Nf6+]] é o melhor lance: um garfo no rei e na dama.",
        "ameaca": "O adversário ameaça [[Qd1#]], mate em 1 no corredor.",
        "por_que_pior": "", "linha": [{"lance": "Nf6+", "comentario": "xeque e garfo"},
                                       {"lance": "Kf8", "comentario": "o rei foge"}],
        "dica": "Da próxima vez, se pergunte: quais são os xeques?"}


def test_ai_answer_that_sticks_to_the_facts_is_accepted():
    out = coach_ai.validate(dict(GOOD), _rules_for_validation())
    assert out["idea"].startswith("[[Nf6+]]") and len(out["line_comments"]) == 2


@pytest.mark.parametrize("field,text,why", [
    ("ideia", "[[Qh5]] ganha na hora.", "lance que não está nos fatos"),
    ("ideia", "Depois de Nxe5 as Brancas ganham.", "lance que não está nos fatos"),
    ("ideia", "[[Nf6+]] deixa as Brancas com +5.3.", "número de avaliação"),
    ("ideia", "[[Nf6+]] dá 87% de chance de vitória.", "número de avaliação"),
    ("ameaca", "O adversário tem mate em 3.", "número que não está nos fatos"),
    ("ideia", "O melhor lance é [[f3]].", "chamou de melhor"),
    ("ideia", "Cd5 é o lance.", "lance que não está nos fatos"),
])
def test_ai_answer_that_invents_is_rejected(field, text, why):
    bad = dict(GOOD, **{field: text})
    with pytest.raises(coach_ai.AIError) as e:
        coach_ai.validate(bad, _rules_for_validation())
    assert why in str(e.value)


def test_ai_line_comments_keep_only_the_prefix_matching_stockfish():
    drift = dict(GOOD, linha=[{"lance": "Nf6+", "comentario": "ok"}, {"lance": "Kh8", "comentario": "inventado"}])
    out = coach_ai.validate(drift, _rules_for_validation())
    assert [c["san"] for c in out["line_comments"]] == ["Nf6+"]


# ------------------------------------------------------------------ AI providers over HTTP (fake servers)
class _Fake(BaseHTTPRequestHandler):
    answer: str = ""
    seen: list = []

    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        _Fake.seen.append(("GET", self.path, dict(self.headers)))
        self._send({"data": [{"id": "modelo-teste"}, {"id": "claude-haiku-5-5"}]})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n))
        _Fake.seen.append(("POST", self.path, dict(self.headers), body))
        if self.path.endswith("/chat/completions"):
            self._send({"choices": [{"message": {"content": _Fake.answer}}]})
        elif self.path.endswith("/v1/messages"):
            self._send({"type": "message", "content": [{"type": "text", "text": _Fake.answer}]})
        else:
            self._send({"error": {"message": "nope"}}, 404)


@pytest.fixture()
def fake_ai(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    _Fake.seen = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@needs_engine
def test_ollama_flow_end_to_end(client, fake_ai):
    _Fake.answer = "```json\n" + json.dumps({
        "ideia": "[[Nf6+]] é o melhor lance: garfo no rei e na dama.", "ameaca": "Há a ameaça [[Qd1#]].",
        "por_que_pior": "", "linha": [{"lance": "Nf6+", "comentario": "garfo"}],
        "dica": "Da próxima vez, se pergunte: quais são os xeques?"}) + "\n```"
    s = client.put("/api/settings/coach", json={"provider": "ollama", "base_url": fake_ai + "/v1",
                                                 "model": "modelo-teste"}).json()
    assert s["enabled"] and s["provider"] == "ollama"
    t = client.post("/api/settings/coach/test").json()
    assert t["ok"] and t["model_available"] is True
    out = client.post("/api/coach/explain", json={"fen": FORK, "ai": True}).json()
    assert out["ai"]["ok"], out["ai"]
    assert out["ai"]["sections"]["idea"].startswith("[[Nf6+]]")
    post = next(x for x in _Fake.seen if x[0] == "POST")
    prompt = post[3]["messages"][1]["content"]
    assert "lances_permitidos" in prompt and "Nf6+" in prompt
    assert "+5." not in prompt and "cp" not in json.loads(prompt.split("FATOS (JSON):\n", 1)[1].split("\n\nResponda")[0]), \
        "no evaluation numbers are sent to the AI"
    _Fake.answer = json.dumps({"ideia": "[[Nf6+]] vale +5.28.", "ameaca": "", "por_que_pior": "", "linha": [],
                               "dica": ""})
    bad = client.post("/api/coach/explain", json={"fen": FORK, "ai": True}).json()
    assert bad["ai"]["ok"] is False and bad["ai"]["rejected"] and "número de avaliação" in bad["ai"]["error"]
    assert bad["rules"]["sections"]["idea"], "the rule-based explanation is always there"


@needs_engine
def test_anthropic_flow_and_key_stays_local(client, fake_ai):
    _Fake.answer = json.dumps({"ideia": "[[Nf6+]] ataca rei e dama.", "ameaca": "", "por_que_pior": "",
                               "linha": [], "dica": "Da próxima vez, se pergunte: há garfos?"})
    r = client.put("/api/settings/coach", json={"provider": "anthropic", "base_url": fake_ai, "model": "claude-haiku-5-5",
                                                 "api_key": "sk-ant-TESTE-1234567890"})
    s = r.json()
    assert s["key"]["has_key"] and s["key"]["hint"] == "7890"
    assert "sk-ant" not in r.text and "sk-ant" not in client.get("/api/settings/coach").text
    out = client.post("/api/coach/explain", json={"fen": FORK, "ai": True}).json()
    assert out["ai"]["ok"], out["ai"]
    post = next(x for x in _Fake.seen if x[0] == "POST")
    assert post[1] == "/v1/messages" and post[2]["x-api-key"] == "sk-ant-TESTE-1234567890"
    assert post[2]["anthropic-version"] == coach_ai.ANTHROPIC_VERSION and "temperature" not in post[3]
    assert post[3]["system"].startswith("Você é um treinador")
    # changing the address drops the key instead of sending it to the new host
    s2 = client.put("/api/settings/coach", json={"provider": "anthropic", "base_url": "https://outro.example.com",
                                                  "model": "claude-haiku-5-5"}).json()
    assert s2["key"]["has_key"] is False and "apagada" in s2["note"]
    assert secrets.get_api_key("https://outro.example.com") is None
    # plain http to a remote host with a key is refused
    assert client.put("/api/settings/coach", json={"provider": "anthropic", "base_url": "http://remoto.example.com",
                                                    "model": "x", "api_key": "abc12345"}).status_code == 422


def test_ai_off_and_unreachable_never_break_the_explanation(client, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "d"))
    assert client.get("/api/settings/coach").json()["enabled"] is False
    client.put("/api/settings/coach", json={"provider": "ollama", "base_url": "http://127.0.0.1:9/v1", "model": "x"})
    t = client.post("/api/settings/coach/test").json()
    assert t["ok"] is False and "Ollama" in t["message"]


def test_mating_move_mentions_only_the_mate():
    """After mate the game is over: a fork or pin by the mating queen is noise in the explanation."""
    import chess

    from app.services.tactics import move_facts

    # the queen mates on f7 and also "attacks" the rook on h8 and the knight on f6 -- irrelevant after mate
    b = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
    f = move_facts(b, chess.Move.from_uci("h5f7"))
    assert f.mate and f.tags[0] == "xeque-mate"
    assert not f.fork and not f.pins and not f.skewers
    assert not any(t.startswith(("garfo", "crava", "espeto", "ataque descoberto", "ameaça")) for t in f.tags)
    assert "fork" not in f.motifs and "mate" in f.motifs
