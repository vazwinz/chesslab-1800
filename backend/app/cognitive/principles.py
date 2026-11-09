"""SCIENTIFIC VALIDATION registry. Every Cognitive Engine feature declares which learning
principle it relies on and whether that principle is well supported by research (in general
learning science — chess-specific evidence is thinner) or is a ChessLab experiment."""
from __future__ import annotations

PRINCIPLES = {
    "active_retrieval": {
        "name": "Recuperação ativa (efeito de teste)",
        "status": "validated",
        "summary": "Tirar a resposta da memória fixa mais do que reler ou rever a solução.",
        "references": ["Roediger & Karpicke (2006), Psychological Science 17(3)",
                       "Dunlosky et al. (2013), Psychological Science in the Public Interest 14(1)"],
        "used_by": ["todo puzzle é resolvido antes de a resposta aparecer", "modo de cálculo às cegas",
                    "testes de retenção"],
    },
    "spaced_repetition": {
        "name": "Repetição espaçada / prática distribuída",
        "status": "validated",
        "summary": "Revisões com intervalos cada vez maiores fixam mais a longo prazo do que treinar tudo de uma vez.",
        "references": ["Cepeda et al. (2006), Psychological Bulletin 132(3)", "Dunlosky et al. (2013)"],
        "used_by": ["motor de retenção (intervalos no estilo SM-2 por tema)", "os blocos de intervenção misturam revisões vencidas"],
    },
    "interleaving": {
        "name": "Intercalação",
        "status": "validated",
        "summary": "Misturar tipos de problema obriga a escolher o método, o que melhora a distinção e a transferência.",
        "references": ["Rohrer & Taylor (2007), Instructional Science 35", "Brunmair & Richter (2019), "
                       "Psychological Bulletin 145(11) — o benefício varia com o material"],
        "used_by": ["a cada 4 exercícios de intervenção, 1 é de outro tema", "a reavaliação usa conjuntos misturados"],
    },
    "feedback": {
        "name": "Feedback imediato e específico",
        "status": "validated",
        "summary": "Feedback sobre a tarefa e o processo (não sobre a pessoa) melhora o aprendizado.",
        "references": ["Hattie & Timperley (2007), Review of Educational Research 77(1)"],
        "used_by": ["solução + linha do Stockfish depois de cada exercício", "rótulo do Error DNA com a evidência usada", "botão Explicar"],
    },
    "deliberate_practice": {
        "name": "Prática deliberada",
        "status": "validated",
        "summary": "Treino focado em fraquezas específicas, com feedback. No xadrez, estudo sério prevê força, "
                   "mas explica só parte da diferença entre jogadores.",
        "references": ["Ericsson, Krampe & Tesch-Römer (1993), Psychological Review 100(3)",
                       "Charness et al. (2005), Applied Cognitive Psychology 19",
                       "Macnamara, Hambrick & Oswald (2014), Psychological Science 25(8)"],
        "used_by": ["as intervenções miram as categorias de erro recorrentes que foram medidas"],
    },
    "progressive_challenge": {
        "name": "Desafio progressivo (dificuldade desejável)",
        "status": "validated",
        "summary": "O treino deve exigir esforço, mas você ainda deve acertar a maior parte.",
        "references": ["Bjork (1994), in Metacognition: Knowing about Knowing", "Bjork & Bjork (2011)"],
        "used_by": ["faixas adaptativas", "a dificuldade das intervenções mira ~70–85% de acerto", "níveis de pressão"],
    },
}

EXPERIMENTAL = {
    "error_dna": "Categorias de erro por regras, a partir das avaliações do Stockfish, do tabuleiro e do tempo. São "
                 "rótulos heurísticos: um erro pode ter várias causas e o rótulo não enxerga o que você pensou.",
    "intervention_effectiveness": "Estimativa (Beta/Thompson sampling, só com os seus dados) de qual intervenção "
                                  "reduziu cada categoria de erro. Amostras pequenas, sem grupo de controle, regressão à "
                                  "média e a melhora geral atrapalham — é uma pista, não uma prova.",
    "fatigue_detection": "Queda, dentro da sessão, do acerto ajustado pela dificuldade, junto com decisões mais "
                         "lentas. Sinal de treino, não avaliação médica ou psicológica.",
    "pressure_complexity": "A nota de complexidade (lances forçantes, tamanho da linha, defesa, incerteza do rating) "
                           "foi desenhada pelo AURA, não é uma escala validada.",
    "performance_prediction": "Tendência linear com intervalos de previsão de 95% nos seus dados. A curva de "
                              "aprendizado não é linear; a projeção é de curto prazo e não é uma previsão de Elo.",
    "retention_transfer_probe": "Considerar 'retenção de verdade' o acerto em posições NOVAS de um tema é uma "
                                "definição razoável, não uma medida psicométrica estabelecida.",
}


def report() -> dict:
    return {"validated_principles": PRINCIPLES, "experimental_features": EXPERIMENTAL,
            "note": "'Validado' se refere à literatura geral de ciência do aprendizado. A evidência direta de que cada "
                    "princípio vira força no tabuleiro é limitada; por isso o AURA mede isso nas suas partidas em vez "
                    "de supor."}
