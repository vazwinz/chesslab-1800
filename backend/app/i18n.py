"""Portuguese (pt-BR) texts shared by the API: HTTP status texts, validation errors and chess
vocabulary. Chess terms follow Brazilian usage (garfo, cravada, espeto, capivarada...)."""
from __future__ import annotations

import chess

STATUS_TEXT = {
    400: {"en": "Bad Request", "pt": "Pedido inválido"},
    401: {"en": "Unauthorized", "pt": "Não autorizado"},
    403: {"en": "Forbidden", "pt": "Acesso negado"},
    404: {"en": "Not Found", "pt": "Não encontrado"},
    405: {"en": "Method Not Allowed", "pt": "Operação não permitida"},
    409: {"en": "Conflict", "pt": "Conflito com o estado atual"},
    422: {"en": "Unprocessable Entity", "pt": "Dados inválidos"},
    500: {"en": "Internal Server Error", "pt": "Erro interno"},
    503: {"en": "Service Unavailable", "pt": "Serviço indisponível"},
}

FIELD_NAMES = {
    "fen": "FEN", "move": "lance", "uci": "lance", "moves": "lances", "pgn": "PGN", "depth": "profundidade",
    "movetime": "tempo de análise", "multipv": "número de linhas", "kind": "modo de treino", "theme": "tema",
    "name": "nome", "color": "cor", "minutes": "minutos", "limit": "limite", "min_rating": "rating mínimo",
    "max_rating": "rating máximo", "path": "caminho do arquivo", "elapsed_ms": "tempo", "plans": "planos",
    "position_id": "posição", "provider": "provedor", "base_url": "endereço", "model": "modelo",
    "api_key": "chave de API", "user_color": "cor", "ply": "lance",
}

_MSG = {
    "missing": "é obrigatório",
    "string_too_short": "está vazio ou curto demais",
    "string_too_long": "está longo demais",
    "too_short": "tem itens de menos",
    "too_long": "tem itens demais",
    "greater_than_equal": "deve ser no mínimo {ge}",
    "less_than_equal": "deve ser no máximo {le}",
    "greater_than": "deve ser maior que {gt}",
    "less_than": "deve ser menor que {lt}",
    "int_parsing": "deve ser um número inteiro",
    "int_type": "deve ser um número inteiro",
    "float_parsing": "deve ser um número",
    "bool_parsing": "deve ser sim/não",
    "bool_type": "deve ser sim/não",
    "string_type": "deve ser um texto",
    "list_type": "deve ser uma lista",
    "literal_error": "tem um valor inválido (aceitos: {expected})",
    "enum": "tem um valor inválido",
    "json_invalid": "não é um JSON válido",
    "model_attributes_type": "não está no formato esperado (JSON)",
    "dict_type": "não está no formato esperado",
    "value_error": "é inválido",
    "url_parsing": "não é um endereço válido",
}


def _field(loc) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    if not parts:
        return "O corpo do pedido"
    name = parts[-1]
    return FIELD_NAMES.get(name, name)


def validation_message(errors: list[dict]) -> str:
    out = []
    for e in errors[:3]:
        tmpl = _MSG.get(e.get("type", ""), "é inválido")
        ctx = {k: str(v) for k, v in (e.get("ctx") or {}).items()}
        try:
            text = tmpl.format(**ctx)
        except (KeyError, IndexError):
            text = tmpl.split(" (")[0].replace("{ge}", "").replace("{le}", "")
        out.append(f"{_field(e.get('loc', []))} {text}")
    return "Dados inválidos: " + "; ".join(out) + "."


# ---------------------------------------------------------------- chess vocabulary
PIECE = {chess.PAWN: "peão", chess.KNIGHT: "cavalo", chess.BISHOP: "bispo", chess.ROOK: "torre",
         chess.QUEEN: "dama", chess.KING: "rei"}
PIECE_ARTICLE = {chess.PAWN: "o", chess.KNIGHT: "o", chess.BISHOP: "o", chess.ROOK: "a", chess.QUEEN: "a",
                 chess.KING: "o"}
PIECE_PLURAL = {chess.PAWN: "peões", chess.KNIGHT: "cavalos", chess.BISHOP: "bispos", chess.ROOK: "torres",
                chess.QUEEN: "damas", chess.KING: "reis"}
SEVERITY = {"inaccuracy": "imprecisão", "mistake": "erro", "blunder": "capivarada", "good": "bom lance"}
COLOR = {chess.WHITE: "Brancas", chess.BLACK: "Pretas"}
COLOR_NAME = {"white": "Brancas", "black": "Pretas"}
PHASE = {"opening": "abertura", "middlegame": "meio-jogo", "endgame": "final"}


def piece_on(board: chess.Board, square: int) -> str:
    p = board.piece_at(square)
    return f"{PIECE_ARTICLE[p.piece_type]} {PIECE[p.piece_type]}" if p else "a casa"


def piece_name(piece_type: int, article: bool = True) -> str:
    return f"{PIECE_ARTICLE[piece_type]} {PIECE[piece_type]}" if article else PIECE[piece_type]


def material_words(diff: dict[int, int]) -> str:
    """{piece_type: count} → 'um cavalo e dois peões'."""
    nums = {1: ("um", "uma"), 2: ("dois", "duas"), 3: ("três", "três")}
    parts = []
    for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
        n = diff.get(pt, 0)
        if n <= 0:
            continue
        fem = PIECE_ARTICLE[pt] == "a"
        word = nums.get(n, (str(n), str(n)))[1 if fem else 0]
        parts.append(f"{word} {PIECE[pt] if n == 1 else PIECE_PLURAL[pt]}")
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " e " + parts[-1]
