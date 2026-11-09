"""Optional AI wording for the coach: Ollama (local, free), Claude (your Anthropic API key) or any
OpenAI-compatible service. OFF by default; AURA works the same without it.

Guarantees:
* The model receives only the facts the rule-based coach computed from Stockfish and the
  board (no evaluation numbers at all), never your games or your database.
* Its answer is checked before it is shown. It is rejected (and the rule-based text is shown
  instead) if it cites a move that is not in the facts, writes an evaluation number or a mate
  count Stockfish did not give, calls a move other than Stockfish's first line "the best", or
  is not the requested JSON.
* The API key never leaves this computer except in the request to the address it was saved for.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from ..models import KV
from . import secrets

KEY = "coach_settings"
PROVIDERS: dict[str, dict] = {
    "none": {"label": "Desligada (só a explicação por regras)", "kind": None, "needs_key": False, "base_url": ""},
    "ollama": {"label": "Ollama, no seu PC (grátis)", "kind": "openai", "needs_key": False,
               "base_url": "http://localhost:11434/v1", "default_model": "",
               "model_hint": "o nome de um modelo que você baixou, ex.: qwen2.5:7b"},
    "anthropic": {"label": "Claude, com a sua chave da Anthropic", "kind": "anthropic", "needs_key": True,
                  "base_url": "https://api.anthropic.com", "default_model": "claude-haiku-5-5",
                  "model_hint": "claude-haiku-5-5 (rápido e barato) ou claude-sonnet-5-5"},
    "openai_compatible": {"label": "Outro serviço compatível com OpenAI", "kind": "openai", "needs_key": False,
                          "base_url": "", "default_model": "", "model_hint": "o nome do modelo nesse serviço"},
}
ANTHROPIC_VERSION = "2026-10-21"
TIMEOUTS = {"ollama": 120.0, "anthropic": 45.0, "openai_compatible": 60.0}


class AIError(RuntimeError):
    pass


# ------------------------------------------------------------------ settings
def get_settings(db: Session) -> dict:
    kv = db.get(KV, KEY)
    s = {"provider": "none", "base_url": "", "model": ""}
    if kv and isinstance(kv.value, dict):
        s.update({k: kv.value.get(k, s[k]) for k in s})
    if s["provider"] not in PROVIDERS:
        s["provider"] = "none"
    p = PROVIDERS[s["provider"]]
    url = s["base_url"] or p.get("base_url", "")
    return {**s, "base_url": url, "enabled": s["provider"] != "none", "needs_key": p["needs_key"],
            "key": secrets.key_status(url) if url else {"has_key": False},
            "providers": {k: {kk: vv for kk, vv in v.items() if kk != "kind"} for k, v in PROVIDERS.items()}}


def _is_local(host: str) -> bool:
    h = (host or "").lower()
    return h in ("localhost", "127.0.0.1", "::1") or h.endswith(".local") or h.startswith("192.168.") \
        or h.startswith("10.") or re.match(r"^172\.(1[6-9]|2\d|3[01])\.", h) is not None


def update_settings(db: Session, provider: str, base_url: str | None, model: str | None,
                    api_key: str | None = None) -> dict:
    if provider not in PROVIDERS:
        raise ValueError("provedor de IA desconhecido")
    p = PROVIDERS[provider]
    old = get_settings(db)
    url = (base_url or p.get("base_url") or "").strip().rstrip("/")
    model = (model or p.get("default_model") or "").strip()
    note = None
    if provider != "none":
        u = urlsplit(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise ValueError("endereço inválido: use algo como http://localhost:11434/v1 ou https://api.anthropic.com")
        if not model:
            raise ValueError("informe o nome do modelo")
        if u.scheme == "http" and not _is_local(u.hostname) and (api_key or p["needs_key"]):
            raise ValueError("para enviar uma chave de API a um servidor fora do seu PC/rede, use https")
    if api_key == "":
        secrets.delete_api_key()
    elif api_key:
        secrets.save_api_key(api_key, url)
    elif provider != "none":
        st = secrets.key_status()
        if st.get("has_key") and st.get("bound_to") != secrets.origin_of(url):
            # a key saved for another address is never sent to this one
            secrets.delete_api_key()
            note = "A chave salva era de outro endereço e foi apagada. Salve a chave de novo para este endereço."
    value = {"provider": provider, "base_url": url if provider != "none" else old.get("base_url", ""), "model": model}
    kv = db.get(KV, KEY)
    if kv is None:
        db.add(KV(key=KEY, value=value))
    else:
        kv.value = value
    db.commit()
    out = get_settings(db)
    if p["needs_key"] and not out["key"].get("has_key"):
        note = note or "Falta salvar a chave de API para usar este provedor."
    return {**out, "note": note}


# ------------------------------------------------------------------ HTTP calls
def _client(timeout: float):
    import httpx

    return httpx.Client(timeout=httpx.Timeout(timeout, connect=6.0), follow_redirects=False)


def _friendly(exc: Exception, provider: str, url: str) -> str:
    import httpx

    if isinstance(exc, httpx.ConnectError):
        if provider == "ollama":
            return (f"Não consegui falar com o Ollama em {url}. Ele está aberto? Instale em ollama.com, rode "
                    "`ollama pull <modelo>` e deixe o Ollama aberto.")
        return f"Não consegui conectar em {url} (sem internet ou endereço errado)."
    if isinstance(exc, httpx.TimeoutException):
        return "A IA demorou demais para responder (tempo esgotado). A explicação por regras continua valendo."
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        try:
            j = exc.response.json()
            msg = (j.get("error") or {}).get("message") if isinstance(j.get("error"), dict) else j.get("error")
        except Exception:
            msg = None
        if code in (401, 403):
            return "A chave de API foi recusada (401/403). Confira a chave nas Configurações."
        if code == 404:
            return f"Modelo ou endereço não encontrado (404){': ' + str(msg) if msg else ''}."
        if code == 429:
            return "Limite de uso da API atingido (429). Tente mais tarde."
        return f"O serviço de IA respondeu com erro {code}{': ' + str(msg)[:200] if msg else ''}."
    return f"Falha ao chamar a IA ({type(exc).__name__})."


def _openai_chat(url: str, key: str | None, model: str, system: str, user: str, timeout: float,
                 json_mode: bool) -> str:
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2, "stream": False}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    with _client(timeout) as c:
        r = c.post(f"{url}/chat/completions", json=body, headers=headers)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""


def _anthropic_base(url: str) -> str:
    return url[:-3] if url.endswith("/v1") else url


def _anthropic_chat(url: str, key: str, model: str, system: str, user: str, timeout: float) -> str:
    headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
    body = {"model": model, "max_tokens": 1200, "system": system, "messages": [{"role": "user", "content": user}]}
    with _client(timeout) as c:
        r = c.post(f"{_anthropic_base(url)}/v1/messages", json=body, headers=headers)
        r.raise_for_status()
        j = r.json()
    return "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text")


def test_connection(db: Session) -> dict:
    s = get_settings(db)
    if not s["enabled"]:
        return {"ok": False, "message": "A IA está desligada."}
    p = PROVIDERS[s["provider"]]
    key = secrets.get_api_key(s["base_url"])
    if p["needs_key"] and not key:
        return {"ok": False, "message": "Salve a chave de API primeiro."}
    try:
        with _client(15.0) as c:
            if p["kind"] == "anthropic":
                r = c.get(f"{_anthropic_base(s['base_url'])}/v1/models",
                          headers={"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION})
            else:
                r = c.get(f"{s['base_url']}/models", headers={"Authorization": f"Bearer {key}"} if key else {})
            r.raise_for_status()
            models = [m.get("id") for m in r.json().get("data", []) if m.get("id")]
    except Exception as exc:
        return {"ok": False, "message": _friendly(exc, s["provider"], s["base_url"])}
    has = s["model"] in models if models else None
    msg = "Conexão funcionando." + ("" if has is None else (" O modelo está disponível." if has else
                                                           f" Atenção: o modelo '{s['model']}' não está na lista."))
    return {"ok": True, "models": models[:50], "model_available": has, "message": msg}


# ------------------------------------------------------------------ prompt
SYSTEM = """Você é um treinador de xadrez paciente. Explica para um jogador de clube (rating perto de 1500), \
em português do Brasil, de forma clara e curta.
Você recebe FATOS calculados pelo Stockfish e pelo tabuleiro. Regras obrigatórias:
1. Use somente os fatos recebidos. Não invente lances, ameaças, temas ou avaliações.
2. Não escreva números de avaliação, porcentagens ou centipeões: o aplicativo já mostra os números do Stockfish.
3. Escreva cada lance entre colchetes duplos, exatamente como aparece nos fatos (notação inglesa): [[Nxe5]], [[O-O]].
4. Só chame de "melhor" (ou "mais forte", "correto") o lance indicado em "melhor_lance".
5. Use os termos brasileiros: garfo, cravada, espeto, ataque descoberto, xeque duplo, capivarada, lance intermediário.
6. Responda APENAS com um objeto JSON, sem texto antes ou depois, com estas chaves (até 2 frases cada):
{"ideia": "a ideia do melhor lance", "ameaca": "a ameaça do adversário, ou que não há ameaça",
 "por_que_pior": "por que o lance do jogador foi pior (texto vazio se não houver lance do jogador)",
 "linha": [{"lance": "primeiro lance da linha principal", "comentario": "o que ele faz"}],
 "dica": "uma pergunta curta para as próximas partidas, começando com 'Da próxima vez, se pergunte:'"}"""


def build_prompt(rules: dict, ctx: dict) -> str:
    sec = rules["sections"]
    lines = rules["engine"]["lines"]
    best = lines[0]
    facts = {
        "contexto": ctx.get("kind", "análise"),
        "perspectiva": rules["position"]["perspective"],
        "lado_a_jogar": rules["position"]["side_to_move"],
        "em_xeque": rules["position"]["in_check"],
        "melhor_lance": best["san"],
        "linha_principal": best["pv_san"][:10],
        "fatos_da_linha": [{"lance": x["san"], "cor": x["color"], "fatos": x["comment"]} for x in sec["line"]],
        "alternativas": [{"lance": l["san"], "em_relacao_ao_melhor":
                          "quase igual" if best["mate"] is None and l["mate"] is None and best["cp"] - l["cp"] <= 30
                          else "pior"} for l in lines[1:]],
        "ameaca": sec["threat"],
        "ideia_por_regras": sec["idea"],
        "temas": [{"nome": t["name"], "definicao": t["text"]} for t in sec["themes"]],
        "nota_do_puzzle": sec.get("puzzle_note") or None,
        "lances_permitidos": rules["allowed_moves"],
    }
    u = sec.get("user")
    if u and not u.get("is_best"):
        facts["lance_do_jogador"] = {"classificacao": u["verdict"], "resumo": u["headline"], "motivos": u["reasons"],
                                     "linha_depois": u.get("refutation", [])}
    if ctx.get("error_category_label"):
        facts["categoria_do_erro"] = ctx["error_category_label"]
    return "FATOS (JSON):\n" + json.dumps(facts, ensure_ascii=False, indent=1) + "\n\nResponda só com o JSON pedido."


# ------------------------------------------------------------------ validation
MOVE_TOKEN = re.compile(r"\[\[([^\[\]]{1,14})\]\]")
SAN_LIKE = re.compile(r"(?<![\w\[\-])(O-O(?:-O)?|[KQRBNCDT][a-h]?[1-8]?x?[a-h][1-8](?:=[QRBNDTC])?[+#]?|"
                      r"[a-h]x[a-h][1-8](?:=[QRBN])?[+#]?|[a-h][1-8]=[QRBN][+#]?)(?![\w\]])")
SQUARE = re.compile(r"\b[a-h][1-8]\b")
DECIMAL = re.compile(r"\d+[.,]\d+|\d+\s*%|centipe|pontos? de vantagem", re.I)
SUPERLATIVE = re.compile(r"\b(melhor|mais fort[ea]|corret[oa]|o lance certo|vencedor|decisivo)\b", re.I)
HEDGE = re.compile(r"\b(pior|não|nem|em vez|ao invés|inferior|parecia|mas|que o)\b", re.I)
PT_TO_EN = str.maketrans({"C": "N", "D": "Q", "T": "R"})


def _norm(san: str) -> str:
    return san.strip().rstrip("+#!?").replace("0-0-0", "O-O-O").replace("0-0", "O-O")


def _extract_json(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise AIError("a IA não respondeu no formato combinado (JSON)")
    try:
        return json.loads(t[a:b + 1])
    except ValueError as exc:
        raise AIError("a IA respondeu um JSON inválido") from exc


def validate(answer: dict, rules: dict) -> dict:
    """Return cleaned sections or raise AIError with the reason the answer was rejected."""
    allowed = {_norm(s) for s in rules["allowed_moves"]}
    lines = rules["engine"]["lines"]
    best = _norm(lines[0]["san"])
    best_pv_mine = {_norm(s) for s in lines[0]["pv_san"][0::2]}
    mates = {abs(x) for x in [lines[0].get("mate"), (rules["engine"].get("threat") or {}).get("mate")] if x}
    user = rules["sections"].get("user") or {}
    for key in ("ideia", "ameaca", "por_que_pior", "dica"):
        if key in answer and not isinstance(answer[key], str):
            raise AIError(f"campo '{key}' veio em formato errado")
    texts = {k: (answer.get(k) or "").strip() for k in ("ideia", "ameaca", "por_que_pior", "dica")}
    raw_line = answer.get("linha") or []
    if not isinstance(raw_line, list):
        raise AIError("campo 'linha' veio em formato errado")
    comments = []
    pv = rules["sections"]["line"]
    for i, item in enumerate(raw_line[:len(pv)]):
        if not isinstance(item, dict):
            break
        if _norm(str(item.get("lance", ""))) != _norm(pv[i]["san"]):
            break  # the model drifted from Stockfish's line: keep only the matching prefix
        texts[f"linha{i}"] = str(item.get("comentario", "")).strip()
        comments.append({"san": pv[i]["san"], "comment": texts[f"linha{i}"]})
    if not texts["ideia"]:
        raise AIError("a IA não explicou a ideia do lance")
    for name, text in texts.items():
        for tok in MOVE_TOKEN.findall(text):
            if _norm(tok) not in allowed:
                raise AIError(f"a IA citou um lance que não está nos fatos do Stockfish ({tok})")
        bare = MOVE_TOKEN.sub(" ", text)
        for tok in SAN_LIKE.findall(bare):
            t = _norm(tok)
            if t not in allowed and _norm(tok.translate(PT_TO_EN)) not in allowed:
                raise AIError(f"a IA citou um lance que não está nos fatos do Stockfish ({tok})")
        if DECIMAL.search(bare):
            raise AIError("a IA escreveu um número de avaliação (só o Stockfish dá números)")
        for n in re.findall(r"\d+", SQUARE.sub(" ", bare)):
            if int(n) not in mates:
                raise AIError(f"a IA escreveu um número que não está nos fatos ({n})")
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if SUPERLATIVE.search(sentence) and not HEDGE.search(sentence):
                cited = {_norm(t) for t in MOVE_TOKEN.findall(sentence)}
                if cited and not cited <= ({best} | best_pv_mine):
                    raise AIError("a IA chamou de melhor um lance que o Stockfish não colocou em primeiro")
    if user and not user.get("is_best") and texts["por_que_pior"] == "":
        texts["por_que_pior"] = ""
    return {"idea": texts["ideia"], "threat": texts["ameaca"], "why_worse": texts["por_que_pior"],
            "tip": texts["dica"], "line_comments": comments}


def ask(db: Session, rules: dict, ctx: dict, call=None) -> dict:
    """Ask the configured AI to word the explanation. Never raises: returns {"ok": False, ...}."""
    s = get_settings(db)
    if not s["enabled"]:
        return {"ok": False, "error": "IA desligada"}
    p = PROVIDERS[s["provider"]]
    key = secrets.get_api_key(s["base_url"])
    if p["needs_key"] and not key:
        return {"ok": False, "error": "falta a chave de API nas Configurações"}
    prompt = build_prompt(rules, ctx)
    timeout = TIMEOUTS.get(s["provider"], 60.0)
    try:
        if call is not None:
            text = call(s, key, SYSTEM, prompt)
        elif p["kind"] == "anthropic":
            text = _anthropic_chat(s["base_url"], key, s["model"], SYSTEM, prompt, timeout)
        else:
            text = _openai_chat(s["base_url"], key, s["model"], SYSTEM, prompt, timeout,
                                json_mode=s["provider"] == "ollama")
    except Exception as exc:
        return {"ok": False, "error": _friendly(exc, s["provider"], s["base_url"])}
    try:
        sections = validate(_extract_json(text), rules)
    except AIError as exc:
        return {"ok": False, "rejected": True, "error": f"Resposta da IA descartada: {exc}. "
                "Mostrando a explicação por regras, que vem direto do Stockfish."}
    return {"ok": True, "sections": sections, "provider": s["provider"], "provider_label": p["label"],
            "model": s["model"]}
