"""Portuguese names and plain-language explanations of the Lichess puzzle themes. Used after
each attempt and by the coach. No evaluation is ever written here: numbers come only from
Stockfish."""
from __future__ import annotations

THEMES: dict[str, tuple[str, str]] = {
    "fork": ("Garfo", "Uma peça ataca duas (ou mais) peças ao mesmo tempo e o adversário não consegue salvar as duas."),
    "pin": ("Cravada", "Uma peça não pode (ou não deve) sair do lugar porque deixaria exposta uma peça mais valiosa "
                       "atrás dela. Cravada no rei = absoluta: a peça nem pode se mexer."),
    "skewer": ("Espeto", "Você ataca uma peça valiosa; quando ela sai, a peça que estava atrás fica exposta e cai. "
                         "É a cravada ao contrário."),
    "discoveredAttack": ("Ataque descoberto", "Você move uma peça e, ao sair do caminho, ela libera o ataque de outra "
                                              "peça sua (bispo, torre ou dama)."),
    "doubleCheck": ("Xeque duplo", "Duas peças dão xeque ao mesmo tempo. Só um lance de rei resolve."),
    "deflection": ("Desvio", "Você força uma peça defensora a sair da casa ou da linha que ela precisava proteger."),
    "attraction": ("Atração", "Você força uma peça (muitas vezes o rei) a ir para uma casa onde ela leva uma tática."),
    "capturingDefender": ("Eliminação do defensor", "Você captura a peça que protegia o alvo de verdade, que fica sem "
                                                     "defesa."),
    "intermezzo": ("Lance intermediário", "Em vez da recaptura esperada, um lance no meio (quase sempre um xeque ou "
                                          "uma ameaça) que melhora a sua situação. Também chamado de zwischenzug."),
    "backRankMate": ("Mate de corredor", "O rei está preso na última fileira pelos próprios peões e leva mate de "
                                         "torre ou dama."),
    "mateIn1": ("Mate em 1", "Há um lance que dá xeque-mate."),
    "mateIn2": ("Mate em 2", "Uma sequência forçada de dois lances seus termina em xeque-mate."),
    "mateIn3": ("Mate em 3", "Uma sequência forçada mais longa: calcule todos os xeques e capturas."),
    "mateIn4": ("Mate em 4", "Sequência forçada de quatro lances até o mate."),
    "mateIn5": ("Mate em 5 ou mais", "Sequência de mate longa: só lances forçados funcionam."),
    "mate": ("Xeque-mate", "Padrão de xeque-mate."),
    "smotheredMate": ("Mate sufocado", "Um cavalo dá mate num rei cercado pelas próprias peças."),
    "arabianMate": ("Mate árabe", "Torre e cavalo dão mate no rei encurralado no canto."),
    "anastasiaMate": ("Mate de Anastácia", "Cavalo e torre (ou dama) prendem o rei na lateral do tabuleiro."),
    "bodenMate": ("Mate de Boden", "Dois bispos em diagonais cruzadas dão mate num rei bloqueado pelas próprias peças."),
    "doubleBishopMate": ("Mate dos dois bispos", "Dois bispos em diagonais vizinhas dão mate."),
    "dovetailMate": ("Mate cauda de andorinha", "A dama dá mate colada ao rei, que tem as duas casas de fuga "
                                                "bloqueadas pelas próprias peças."),
    "hookMate": ("Mate do gancho", "Torre, cavalo e peão trabalham juntos para dar mate."),
    "sacrifice": ("Sacrifício", "Você entrega material de propósito para ganhar algo maior: mate, mais material ou "
                                "um ataque decisivo."),
    "defensiveMove": ("Lance defensivo", "O único lance que segura a ameaça do adversário."),
    "equality": ("Salvar a posição", "De uma posição pior, ache o lance que mantém o equilíbrio."),
    "hangingPiece": ("Peça solta", "Uma peça sem defesa pode simplesmente ser capturada."),
    "trappedPiece": ("Peça presa", "Uma peça sem casas seguras pode ser ganha."),
    "xRayAttack": ("Raio X", "Uma peça ataca ou defende através de outra peça que está na mesma linha."),
    "quietMove": ("Lance quieto", "Um lance sem xeque e sem captura que cria uma ameaça impossível de parar."),
    "clearance": ("Liberação", "Você tira uma peça de uma casa ou linha para outra peça poder usá-la."),
    "interference": ("Interferência", "Você coloca uma peça entre um defensor e a casa ou peça que ele defende."),
    "kingsideAttack": ("Ataque na ala do rei", "Ataque contra o rei que rocou do lado curto."),
    "queensideAttack": ("Ataque na ala da dama", "Ataque contra o rei que rocou do lado longo."),
    "exposedKing": ("Rei exposto", "O rei sem proteção de peões permite um ataque decisivo."),
    "attackingF2F7": ("Ataque em f2/f7", "Ataque na casa mais fraca do início da partida, defendida só pelo rei."),
    "promotion": ("Promoção", "Um peão chega à última fileira e vira dama (ou outra peça)."),
    "underPromotion": ("Subpromoção", "Promover a cavalo, torre ou bispo é melhor do que a dama aqui."),
    "advancedPawn": ("Peão avançado", "Um peão muito adiantado cria ameaças decisivas."),
    "castling": ("Roque", "O roque faz parte da solução."),
    "enPassant": ("En passant", "A captura en passant faz parte da solução."),
    "pawnEndgame": ("Final de peões", "Atividade do rei, oposição e corridas de peões decidem."),
    "rookEndgame": ("Final de torres", "Atividade da torre, xeques por trás e cortar o rei adversário são o mais "
                                       "importante."),
    "queenEndgame": ("Final de damas", "Final com damas: cuidado com xeques perpétuos."),
    "bishopEndgame": ("Final de bispos", "Final com bispos."),
    "knightEndgame": ("Final de cavalos", "Final com cavalos."),
    "queenRookEndgame": ("Final de dama e torre", "Final com damas e torres."),
    "endgame": ("Final", "Técnica de final."),
    "middlegame": ("Meio-jogo", "Posição de meio-jogo."),
    "opening": ("Abertura", "Tática que acontece ainda na abertura."),
    "zugzwang": ("Zugzwang", "Quem joga piora a própria posição: qualquer lance do adversário estraga a dele."),
    "crushing": ("Vantagem esmagadora", "A solução ganha de forma decisiva."),
    "advantage": ("Vantagem", "A solução dá uma vantagem clara."),
    "oneMove": ("Um lance", "A solução tem um lance só."),
    "short": ("Curto", "Solução de dois lances."),
    "long": ("Longo", "Solução de três lances."),
    "veryLong": ("Muito longo", "Solução de quatro lances ou mais."),
    "master": ("Partida de mestre", "Vem de uma partida de jogador titulado."),
    "masterVsMaster": ("Mestre contra mestre", "Vem de uma partida entre dois jogadores titulados."),
    "superGM": ("Super GM", "Vem de uma partida de um dos melhores jogadores do mundo."),
}
# themes that only describe length, phase or evaluation (not shown as "the idea")
NOT_AN_IDEA = {"oneMove", "short", "long", "veryLong", "middlegame", "opening", "endgame", "crushing", "advantage",
               "master", "masterVsMaster", "superGM", "mate"}

CATEGORY_NAMES = {
    "forks": "Garfos", "pins": "Cravadas", "skewers": "Espetos", "discovered_attacks": "Ataques descobertos",
    "double_attacks": "Ataques duplos", "deflection": "Desvio", "decoy": "Atração",
    "removing_the_defender": "Eliminação do defensor", "zwischenzug": "Lance intermediário",
    "back_rank": "Mate de corredor", "checkmate_patterns": "Padrões de mate", "sacrifices": "Sacrifícios",
    "defensive": "Defesa",
}


def theme_name(key: str) -> str:
    return THEMES.get(key, (key, ""))[0]


def explain(themes: str) -> list[str]:
    """One sentence per theme of the puzzle that is a real idea (not just its length or phase)."""
    out = []
    for t in themes.split():
        if t in THEMES and t not in NOT_AN_IDEA:
            name, text = THEMES[t]
            out.append(f"{name}: {text}")
    return out


def themes_payload() -> dict:
    return {k: {"name": n, "text": t} for k, (n, t) in THEMES.items()}
