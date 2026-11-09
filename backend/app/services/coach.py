"""AURA coach: explains a position or a move in Portuguese using ONLY

* Stockfish output (best lines with MultiPV, the evaluation after your move, the opponent's
  reply, and a null-move "what if they could move again" probe), and
* board facts computed by python-chess (captures, checks, forks, pins... see tactics.py).

Nothing here estimates an evaluation by itself: every number is a Stockfish number, and a move
is only ever called "the best" when it is Stockfish's first line. The optional AI (coach_ai.py)
receives these same facts and its answer is checked against them."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import chess
from sqlalchemy.orm import Session

from ..i18n import COLOR, SEVERITY, piece_name
from ..models import EngineCache
from .engine import MATE_CP, StockfishService, classify_loss, threat_gain, win_pct
from .explain import NOT_AN_IDEA, THEMES
from .tactics import VALUE, describe_material, en_prise, material_change, move_facts

VERSION = "coach-v2"
THREAT_CP = 150          # a probe gain below this is not reported as a threat
ONLY_MOVE_GAP = 150      # best is this much better than the 2nd line → "practically the only good move"
CLOSE_GAP = 30           # alternatives within this margin are "about as good"
LINE_PLIES = 10


# ------------------------------------------------------------------ evaluation formatting
def eval_text(cp: int | None, mate: int | None, stm_white: bool) -> dict:
    """Stockfish score (side-to-move POV) → White's POV text, as chess boards usually show it."""
    if mate is not None:
        m = mate if stm_white else -mate
        return {"white_cp": MATE_CP if m > 0 else -MATE_CP, "white_mate": m, "text": f"#{m}" if m > 0 else f"#-{abs(m)}",
                "words": f"mate em {abs(m)} para as {'Brancas' if m > 0 else 'Pretas'}"}
    w = cp if stm_white else -cp
    return {"white_cp": w, "white_mate": None, "text": f"{w / 100:+.2f}", "words": _cp_words(w)}


def _cp_words(w: int) -> str:
    a = abs(w)
    if a < 50:
        return "posição equilibrada"
    side = "Brancas" if w > 0 else "Pretas"
    if a < 150:
        return f"pequena vantagem das {side}"
    if a < 300:
        return f"vantagem clara das {side}"
    return f"vantagem decisiva das {side}"


def M(san: str) -> str:
    """Move marker the interface renders as a clickable move (figurine notation)."""
    return f"[[{san}]]"


# ------------------------------------------------------------------ engine facts
@dataclass
class Gathered:
    fen: str
    engine: str
    depth: int
    lines: list[dict]
    threat: dict | None = None
    user: dict | None = None
    best_threat: dict | None = None
    extra_evals: dict = field(default_factory=dict)


def _line(l, stm_white: bool) -> dict:
    return {"san": l.san, "uci": l.move, "cp": l.cp, "mate": l.mate, "depth": l.depth,
            "pv_san": l.pv_san[:12], "pv_uci": l.pv[:12], "eval": eval_text(l.cp, l.mate, stm_white)}


def _null_board(board: chess.Board) -> chess.Board:
    """The same position with the other side to move (a fresh board: no null move in its history)."""
    b = board.copy(stack=False)
    b.push(chess.Move.null())
    return chess.Board(b.fen())


def gather(engine: StockfishService, board: chess.Board, depth: int, user_move: chess.Move | None = None,
           also_eval: list[chess.Move] | None = None) -> Gathered:
    stm_white = board.turn == chess.WHITE
    top = engine.analyse(board, depth=depth, multipv=3)
    g = Gathered(fen=board.fen(), engine=engine.name or "Stockfish", depth=max((l.depth for l in top), default=0),
                 lines=[_line(l, stm_white) for l in top])
    if not top:
        return g
    best = top[0]
    # what does the opponent threaten? (null-move probe: let them move twice)
    if not board.is_check():
        null = _null_board(board)
        if null.is_valid() and not null.is_game_over():
            tl = engine.analyse(null, depth=max(8, depth - 6))
            if tl:
                g.threat = {"san": tl[0].san, "uci": tl[0].move, "mate": tl[0].mate,
                            "gain_cp": threat_gain(best.cp, best.mate, tl[0].cp, tl[0].mate),
                            "pv_san": tl[0].pv_san[:6], "pv_uci": tl[0].pv[:6]}
    # what does the best move threaten next? (only for quiet best moves)
    bm = chess.Move.from_uci(best.move)
    if best.mate is None and not board.is_capture(bm) and not board.gives_check(bm):
        a2 = board.copy()
        a2.push(bm)
        if not a2.is_game_over():
            n2 = _null_board(a2)
            if n2.is_valid() and not n2.is_game_over():
                t2 = engine.analyse(n2, depth=max(8, depth - 6))
                if t2:
                    # our gain if we could move again after the best move (mates handled like threat_gain)
                    gain = MATE_CP if (t2[0].mate is not None and t2[0].mate > 0) else \
                        max(-1500, min(1500, t2[0].cp)) - max(-1500, min(1500, best.cp))
                    g.best_threat = {"san": t2[0].san, "uci": t2[0].move, "gain_cp": gain,
                                     "mate": t2[0].mate, "pv_san": t2[0].pv_san[:6], "pv_uci": t2[0].pv[:6],
                                     "after_fen": n2.fen()}
    if user_move is not None:
        g.user = _user_facts(engine, board, user_move, depth, top, stm_white)
    for mv in also_eval or []:
        if mv.uci() in [l["uci"] for l in g.lines] or mv not in board.legal_moves:
            continue
        g.extra_evals[mv.uci()] = _user_facts(engine, board, mv, depth, top, stm_white)
    return g


def _user_facts(engine, board: chess.Board, mv: chess.Move, depth: int, top, stm_white: bool) -> dict:
    after = board.copy()
    after.push(mv)
    reply = None
    if after.is_checkmate():
        user_cp, user_mate = MATE_CP, 1
    elif after.is_game_over():
        user_cp, user_mate = 0, None
    else:
        rl = engine.analyse(after, depth=depth)
        reply = rl[0] if rl else None
        user_cp = -(reply.cp if reply else 0)
        user_mate = -reply.mate if reply and reply.mate is not None else None
    best = top[0]
    loss = max(0, best.cp - user_cp)
    wl = max(0.0, win_pct(best.cp) - win_pct(user_cp))
    return {"san": board.san(mv), "uci": mv.uci(), "cp": user_cp, "mate": user_mate,
            "eval": eval_text(user_cp, user_mate, stm_white), "cp_loss": loss, "win_pct_loss": round(wl, 1),
            "verdict": classify_loss(wl), "is_best": mv.uci() == best.move,
            "in_top": mv.uci() in [l.move for l in top],
            "reply": None if reply is None else {"san": reply.san, "uci": reply.move, "mate": reply.mate,
                                                 "pv_san": reply.pv_san[:LINE_PLIES], "pv_uci": reply.pv[:LINE_PLIES]}}


# ------------------------------------------------------------------ the commented main line
def commented_line(board: chess.Board, pv_uci: list[str], prev: chess.Move | None = None,
                   prev_capture: bool = False) -> tuple[list[dict], chess.Board]:
    b = board.copy()
    out = []
    for i, u in enumerate(pv_uci[:LINE_PLIES]):
        mv = chess.Move.from_uci(u)
        if mv not in b.legal_moves:
            break
        f = move_facts(b, mv, prev if prev_capture else None)
        prev_capture = b.is_capture(mv)
        comment = "; ".join(f.tags) if f.tags else _quiet_comment(b, mv)
        out.append({"ply": i, "san": f.san, "uci": u, "white": b.turn == chess.WHITE, "move_no": b.fullmove_number,
                    "color": f.color, "comment": comment, "motifs": f.motifs})
        b.push(mv)
        prev = mv
    return out, b


def settled(board: chess.Board, pv_uci: list[str], max_plies: int = LINE_PLIES) -> chess.Board:
    """Position where the forcing part of a line ends (no capture or check comes next), so the
    material count is not muddied by later, unrelated trades."""
    b = board.copy()
    for i, u in enumerate(pv_uci[:max_plies]):
        mv = chess.Move.from_uci(u)
        if mv not in b.legal_moves:
            break
        b.push(mv)
        if b.is_check() or i + 1 >= len(pv_uci):
            continue
        nxt = chess.Move.from_uci(pv_uci[i + 1])
        if nxt in b.legal_moves and not b.is_capture(nxt) and not b.gives_check(nxt):
            break
    return b


def _ev(e: dict) -> str:
    """Evaluation for prose: '+1.25', or 'mate em 2 para as Brancas'."""
    return e["words"] if e.get("white_mate") is not None else e["text"]


def _quiet_comment(b: chess.Board, mv: chess.Move) -> str:
    p = b.piece_at(mv.from_square)
    rank_to = chess.square_rank(mv.to_square) if p.color == chess.WHITE else 7 - chess.square_rank(mv.to_square)
    rank_from = chess.square_rank(mv.from_square) if p.color == chess.WHITE else 7 - chess.square_rank(mv.from_square)
    if p.piece_type == chess.PAWN:
        return "avança o peão" + (" rumo à promoção" if rank_to >= 5 else "")
    if p.piece_type == chess.KING:
        return "ativa o rei" if len(b.piece_map()) <= 12 else "move o rei"
    if rank_from == 0 and rank_to > 0:
        return f"desenvolve {piece_name(p.piece_type)}"
    return f"reposiciona {piece_name(p.piece_type)} em {chess.square_name(mv.to_square)}"


# ------------------------------------------------------------------ text
def _who(ctx: dict, color: chess.Color) -> str:
    if ctx.get("user_color") is not None and ctx["user_color"] == color:
        return "você"
    return f"as {COLOR[color]}"


def _sentence(s: str) -> str:
    s = s.strip()
    return (s[0].upper() + s[1:]) if s else s


def build(board: chess.Board, g: Gathered, ctx: dict | None = None) -> dict:
    ctx = dict(ctx or {})
    stm = board.turn
    who = _who(ctx, stm)
    if not g.lines:
        msg = "A partida já acabou nesta posição: " + ("xeque-mate." if board.is_checkmate() else "empate.")
        return {"version": VERSION, "terminal": True, "summary": msg,
                "source": {"kind": "rules", "engine": g.engine, "depth": g.depth}, "sections": {"idea": msg}}
    best = g.lines[0]
    bm = chess.Move.from_uci(best["uci"])
    bf = move_facts(board, bm)
    line, end = commented_line(board, best["pv_uci"])
    mat = material_change(board, settled(board, best["pv_uci"]), stm)
    mat_end = material_change(board, end, stm)

    # ---- idea of the best move
    idea: list[str] = []
    if best["mate"] is not None and best["mate"] > 0:
        n = best["mate"]
        idea.append(f"{M(best['san'])} é xeque-mate." if bf.mate else
                    f"{M(best['san'])} força xeque-mate em {n} lance{'s' if n > 1 else ''}"
                    f" (linha do Stockfish: {' '.join(M(s) for s in best['pv_san'][:2 * n - 1])}).")
    else:
        head = f"{M(best['san'])} é o lance que o Stockfish prefere"
        motif = []
        if bf.fork:
            motif.append("é um garfo: ataca " + " e ".join(bf.fork) + " ao mesmo tempo")  # noqa: E501
        motif += [f"crava {p}" for p in bf.pins]
        motif += [f"faz um espeto: ataca {s}" for s in bf.skewers]
        motif += [f"abre um ataque descoberto ({d})" for d in bf.discovered]
        if bf.double_check:
            motif.append("dá xeque duplo")
        elif bf.discovered_check:
            motif.append("dá xeque descoberto")
        sac = bf.hangs and len(best["pv_uci"]) > 1 and chess.Move.from_uci(best["pv_uci"][1]).to_square == bm.to_square \
            and not (bf.capture_type and VALUE[bf.capture_type] >= VALUE[board.piece_type_at(bm.from_square)])
        if motif:
            idea.append(f"{head}. {_sentence(', '.join(motif))}.")
        elif sac:
            idea.append(f"{head}, e é um sacrifício: {piece_name(board.piece_type_at(bm.from_square))} pode ser "
                        f"capturad{'a' if board.piece_type_at(bm.from_square) in (chess.ROOK, chess.QUEEN) else 'o'} "
                        f"em {chess.square_name(bm.to_square)}, mas a linha continua a favor de {who}.")
        elif bf.tags:
            idea.append(f"{head}: {', '.join(bf.tags)}.")
        else:
            idea.append(f"{head} ({_quiet_comment(board, bm)}).")
        if mat["balance"] >= 2:
            idea.append(_sentence(f"na linha do Stockfish, {describe_material(mat, who)}."))
        if g.best_threat and g.best_threat["gain_cp"] >= THREAT_CP:
            nb = chess.Board(g.best_threat["after_fen"])
            tm = chess.Move.from_uci(g.best_threat["uci"])
            already = chess.square_name(tm.to_square) in " ".join(bf.attacks_unprotected)
            if not already:
                tf = move_facts(nb, tm)
                what = ", ".join(tf.tags) if tf.tags else "melhorar muito a posição"
                idea.append(f"Depois dele, a ameaça é {M(g.best_threat['san'])} ({what}).")
    if len(g.lines) >= 2 and best["mate"] is None:
        gap = best["cp"] - g.lines[1]["cp"]
        if gap >= ONLY_MOVE_GAP:
            idea.append(f"É praticamente o único lance bom: o segundo da lista, {M(g.lines[1]['san'])}, "
                        f"fica bem atrás ({g.lines[1]['eval']['text']} contra {best['eval']['text']}).")
        elif gap <= CLOSE_GAP:
            alts = [M(l["san"]) for l in g.lines[1:] if best["cp"] - l["cp"] <= CLOSE_GAP]
            idea.append(f"{' e '.join(alts)} {'também são' if len(alts) > 1 else 'também é'} bo{'ns' if len(alts) > 1 else 'm'}: "
                        "a avaliação é quase a mesma.")

    # ---- the opponent's threat in the position
    threat_txt, threat_ok = "", False
    if board.is_check():
        threat_txt = f"{_sentence(who)} {'está' if who == 'você' else 'estão'} em xeque: o primeiro passo é sair do xeque."
    elif g.threat and g.threat["gain_cp"] >= THREAT_CP:
        nb = _null_board(board)
        tmv = chess.Move.from_uci(g.threat["uci"])
        tf = move_facts(nb, tmv)
        what = ", ".join(tf.tags) if tf.tags else "um lance forte"
        mate = g.threat.get("mate")
        mate_note = f", que leva a mate em {mate}" if mate and mate > 0 and not (mate == 1 and tf.mate) else ""
        threat_txt = f"Atenção à ameaça do adversário: {M(g.threat['san'])} ({what}){mate_note}."
        threat_ok = True
        if _parries(board, bm, tmv):
            threat_txt += f" {M(best['san'])} resolve essa ameaça."
    else:
        threat_txt = ("Nenhuma ameaça imediata: mesmo se o adversário jogasse duas vezes seguidas, "
                      "o Stockfish não acha nada forte para ele.")

    # ---- tactical themes
    themes, seen = [], set()
    for key in (ctx.get("themes") or []):
        if key in THEMES and key not in NOT_AN_IDEA and key not in seen:
            themes.append({"key": key, "name": THEMES[key][0], "text": THEMES[key][1], "source": "puzzle"})
            seen.add(key)
    for item in [bf.motifs] + [l["motifs"] for l in line[2:7:2]]:  # our own next moves in the line
        for key in item:
            if key in THEMES and key not in seen and key != "mate":
                themes.append({"key": key, "name": THEMES[key][0], "text": THEMES[key][1], "source": "detectado"})
                seen.add(key)

    # ---- why the user's move was worse
    user = _user_section(board, g, bf, best, who, threat_ok) if g.user else None

    # ---- puzzle solution vs Stockfish
    puzzle_note = ""
    sol = ctx.get("solution_uci") or []
    if sol:
        s0 = sol[0]
        sol_san = ctx.get("solution_san") or []
        if s0 == best["uci"]:
            puzzle_note = f"O Stockfish confirma a solução do puzzle: {M(best['san'])}."
        else:
            s_line = next((l for l in g.lines if l["uci"] == s0), None) or g.extra_evals.get(s0)
            s_san = sol_san[0] if sol_san else s0
            ev = s_line["eval"]["text"] if s_line else "?"
            puzzle_note = (f"A solução do puzzle é {M(s_san)} ({ev}). Nesta profundidade o Stockfish prefere "
                           f"{M(best['san'])} ({best['eval']['text']}): pode haver mais de um caminho que ganha.")

    end_note = ""
    if end.is_checkmate():
        end_note = "A linha termina em xeque-mate."
    else:
        md = describe_material(mat_end, who)
        end_note = (f"Ao fim desta linha, {md}. " if md else "Ao fim desta linha, o material fica igual. ") + \
                   f"Avaliação do Stockfish: {best['eval']['text']} ({best['eval']['words']})."

    summary = idea[0] if idea else ""
    if user and not g.user["is_best"]:
        summary = user["headline"]
    return {
        "version": VERSION,
        "terminal": False,
        "summary": summary,
        "source": {"kind": "rules", "engine": g.engine, "depth": g.depth},
        "position": {"fen": g.fen, "side_to_move": COLOR[stm], "perspective": who, "in_check": board.is_check()},
        "engine": {"lines": g.lines, "threat": g.threat, "best_threat": g.best_threat},
        "sections": {"idea": " ".join(idea), "threat": threat_txt, "themes": themes, "user": user,
                     "line": line, "line_end": end_note, "puzzle_note": puzzle_note},
        "allowed_moves": _allowed_moves(g, line),
        "mate_numbers": sorted({abs(m) for m in [l["mate"] for l in g.lines]
                                + [(g.threat or {}).get("mate"), (g.best_threat or {}).get("mate"),
                                   ((g.user or {}).get("reply") or {}).get("mate")] if m}),
    }


def _parries(board: chess.Board, best: chess.Move, threat: chess.Move) -> bool:
    """Board-level check that the best move deals with the threat: it moves the target away,
    captures the threatening piece, blocks the line, or the threat move is no longer legal/strong."""
    if best.from_square == threat.to_square or best.to_square == threat.from_square:
        return True
    if chess.BB_SQUARES[best.to_square] & chess.between(threat.from_square, threat.to_square):
        return True
    after = board.copy()
    after.push(best)
    if threat not in after.legal_moves:
        return True
    if board.is_capture(threat):  # the attacked piece moved away or is now protected well enough
        return after.piece_at(threat.to_square) is None or not en_prise(after, threat.to_square)
    return False


def _user_section(board: chess.Board, g: Gathered, bf, best: dict, who: str, threat_ok: bool) -> dict:
    u = g.user
    stm = board.turn
    um = chess.Move.from_uci(u["uci"])
    verdict = SEVERITY.get(u["verdict"], u["verdict"])
    if u["is_best"]:
        return {"san": u["san"], "verdict": "melhor", "headline": f"{M(u['san'])} é o lance que o Stockfish prefere.",
                "reasons": [], "eval_best": best["eval"]["text"], "eval_user": u["eval"]["text"], "is_best": True}
    head = (f"{M(u['san'])}: {verdict} segundo o Stockfish. A avaliação vai de {_ev(best['eval'])} "
            f"(com {M(best['san'])}) para {_ev(u['eval'])}.")
    if u["verdict"] == "good":
        head = (f"{M(u['san'])} é um lance aceitável: o Stockfish avalia {u['eval']['text']}, perto de "
                f"{M(best['san'])} ({best['eval']['text']}).")
    reasons: list[str] = []
    after = board.copy()
    after.push(um)
    r = u.get("reply")
    if after.is_checkmate():
        pass
    elif r:
        rm = chess.Move.from_uci(r["uci"])
        rf = move_facts(after, rm, um if board.is_capture(um) else None)
        if r.get("mate") is not None and r["mate"] > 0:
            reasons.append(f"Depois de {M(u['san'])}, o adversário tem mate em {r['mate']} começando com {M(r['san'])}.")
        else:
            desc = ", ".join(rf.tags) if rf.tags else "e fica melhor"
            reasons.append(f"A resposta do adversário segundo o Stockfish é {M(r['san'])}: {desc}.")
        if rf.capture_type and rm.to_square == um.to_square:
            reasons.append(f"{piece_name(board.piece_type_at(um.from_square)).capitalize()} que você moveu para "
                           f"{chess.square_name(um.to_square)} fica sem a proteção necessária.")
        if threat_ok and g.threat and (g.threat["uci"] == r["uci"] or chess.Move.from_uci(g.threat["uci"]).to_square
                                       == rm.to_square):
            reasons.append(f"Essa ameaça ({M(g.threat['san'])}) já existia antes do seu lance e ele não a resolveu.")
        ch = material_change(board, settled(after, r["pv_uci"]), stm)
        if ch["balance"] <= -2:
            reasons.append(_sentence(f"na linha do Stockfish depois do seu lance, {describe_material(ch, who)}."))
    if bf.fork or bf.pins or bf.skewers or bf.discovered or (best["mate"] and best["mate"] > 0):
        reasons.append(f"Você perdeu uma tática: com {M(best['san'])}, " + (
            f"havia mate em {best['mate']}." if best["mate"] and best["mate"] > 0 else ", ".join(bf.tags) + "."))
    if u["verdict"] in ("inaccuracy", "good") and not any("perde" in x for x in reasons):
        reasons.append(f"Seu lance não entrega material de imediato, mas {M(best['san'])} mantém uma avaliação melhor.")
    return {"san": u["san"], "verdict": verdict, "verdict_key": u["verdict"], "headline": head, "reasons": reasons,
            "eval_best": best["eval"]["text"], "eval_user": u["eval"]["text"], "win_pct_loss": u["win_pct_loss"],
            "refutation": (r or {}).get("pv_san", [])[:LINE_PLIES], "is_best": False}


def _allowed_moves(g: Gathered, line: list[dict]) -> list[str]:
    out = []
    for l in g.lines:
        out += l["pv_san"][:12]
    if g.threat:
        out += g.threat["pv_san"][:4]
    if g.best_threat:
        out += g.best_threat["pv_san"][:4]
    if g.user:
        out.append(g.user["san"])
        if g.user.get("reply"):
            out += g.user["reply"]["pv_san"]
    out += [x["san"] for x in line]
    for e in g.extra_evals.values():
        out.append(e["san"])
    seen, res = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            res.append(s)
    return res


def tip(ctx: dict, rules: dict) -> str:
    """One question to carry into the next games, chosen from what actually happened here."""
    from ..cognitive.error_dna import INFO

    cat = ctx.get("error_category")
    if cat in INFO:
        return INFO[cat]["tip"]
    sec = rules.get("sections", {})
    user = sec.get("user")
    if user and not user.get("is_best") and sec.get("threat", "").startswith("Atenção"):
        return INFO["missed_opponent_threat"]["tip"]
    first = (sec.get("line") or [{}])[0]
    if first.get("motifs"):
        return INFO["tactical_blindness"]["tip"]
    return "Da próxima vez, se pergunte: o que mudou com o último lance do adversário?"


# ------------------------------------------------------------------ entry point with cache
def _cache_key(fen: str, move: str | None, depth: int, also: list[str]) -> str:
    raw = f"{VERSION}|{fen}|{move or '-'}|{depth}|{','.join(sorted(also))}"
    return "coach:" + hashlib.sha1(raw.encode()).hexdigest()


def gathered_cached(db: Session | None, engine: StockfishService, board: chess.Board, depth: int,
                    move: chess.Move | None, also: list[chess.Move]) -> Gathered:
    key = _cache_key(board.fen(), move.uci() if move else None, depth, [m.uci() for m in also])
    if db is not None:
        row = db.get(EngineCache, key)
        if row is not None:
            return Gathered(**row.result)
    g = gather(engine, board, depth, move, also)
    if db is not None and g.lines:
        db.merge(EngineCache(key=key, result=g.__dict__))
        db.commit()
    return g


def explain(engine: StockfishService, fen: str, move_uci: str | None = None, ctx: dict | None = None,
            depth: int = 18, db: Session | None = None) -> dict:
    board = chess.Board(fen)
    move = chess.Move.from_uci(move_uci) if move_uci else None
    if move is not None and move not in board.legal_moves:
        raise ValueError("lance ilegal nesta posição")
    also = []
    sol = (ctx or {}).get("solution_uci") or []
    if sol:
        try:
            m = chess.Move.from_uci(sol[0])
            if m in board.legal_moves:
                also.append(m)
        except ValueError:
            pass
    g = gathered_cached(db, engine, board, depth, move, also)
    return build(board, g, ctx)
