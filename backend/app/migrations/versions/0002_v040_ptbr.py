"""0.4.0: the app speaks Portuguese. Translates the English texts that 0.3.0 stored in the
database (default daily-plan block titles and closed-loop log messages). Titles you typed
yourself are left untouched. No table or column changes.

Revision ID: 0002_v040_ptbr
Revises: 0001_baseline_030
Create Date: 2026-11-08
"""
from __future__ import annotations

import json
import re

import sqlalchemy as sa
from alembic import op

revision = "0002_v040_ptbr"
down_revision = "0001_baseline_030"
branch_labels = None
depends_on = None

PLAN_TITLES = {
    "Tactical patterns": "Padrões táticos",
    "Deep calculation": "Cálculo profundo",
    "Endgames": "Finais",
    "Opening preparation": "Preparação de aberturas",
    "Serious games": "Partidas sérias",
    "Mistake analysis": "Análise dos erros",
}
# (code, English pattern as written by 0.3.0, Portuguese template)
LOOP_MESSAGES = [
    ("cycle_started", r"^cycle started$", "ciclo iniciado"),
    ("baseline_sufficient", r"^baseline sufficient$", "linha de base suficiente"),
    ("no_recurring_error", r"^no recurring error yet — collecting more data$",
     "nenhum erro recorrente ainda — coletando mais dados"),
    ("target", r"^target = (?P<x>.+)$", "alvo = {x}"),
    ("assigned", r"^assigned (?P<x>.+)$", "intervenção escolhida: {x}"),
    ("practice_done", r"^practice block complete$", "bloco de prática concluído"),
    ("outcome_recorded", r"^outcome recorded$", "resultado registrado"),
    ("reassessment_reused", r"^reassessment of previous cycle used as new measurement$",
     "a reavaliação do ciclo anterior virou a nova medição"),
]


def _load(v):
    if v is None:
        return None
    return json.loads(v) if isinstance(v, (str, bytes)) else v


def _translate_log(entries: list, to_pt: bool) -> tuple[list, bool]:
    changed = False
    out = []
    for e in entries or []:
        e = dict(e)
        msg = e.get("msg", "")
        if to_pt:
            for code, pat, pt in LOOP_MESSAGES:
                m = re.match(pat, msg)
                if m:
                    e["code"], e["msg"] = code, pt.format(**m.groupdict())
                    changed = True
                    break
        else:
            for code, pat, pt in LOOP_MESSAGES:
                if e.get("code") == code:
                    en = pat.strip("^$").replace("(?P<x>.+)", "{x}")
                    x = re.match("^" + re.escape(pt).replace(r"\{x\}", "(?P<x>.+)") + "$", msg)
                    e["msg"] = en.format(**(x.groupdict() if x else {"x": ""}))
                    e.pop("code", None)
                    changed = True
                    break
        out.append(e)
    return out, changed


def _migrate(to_pt: bool) -> None:
    bind = op.get_bind()
    titles = PLAN_TITLES if to_pt else {v: k for k, v in PLAN_TITLES.items()}
    for old, new in titles.items():
        bind.execute(sa.text("UPDATE plan_blocks SET title = :new WHERE title = :old"), {"new": new, "old": old})
    row = bind.execute(sa.text("SELECT value FROM kv WHERE key = 'plan_config'")).first()
    if row is not None:
        cfg = _load(row[0]) or {}
        blocks = [{**b, "title": titles.get(b.get("title"), b.get("title"))} for b in cfg.get("blocks", [])]
        bind.execute(sa.text("UPDATE kv SET value = :v WHERE key = 'plan_config'"),
                     {"v": json.dumps({**cfg, "blocks": blocks})})
    for cid, log in bind.execute(sa.text("SELECT id, log FROM loop_cycles")).all():
        entries, changed = _translate_log(_load(log) or [], to_pt)
        if changed:
            bind.execute(sa.text("UPDATE loop_cycles SET log = :v WHERE id = :id"),
                         {"v": json.dumps(entries), "id": cid})


def upgrade() -> None:
    _migrate(to_pt=True)


def downgrade() -> None:
    _migrate(to_pt=False)
