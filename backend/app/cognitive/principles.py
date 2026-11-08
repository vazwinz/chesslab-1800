"""SCIENTIFIC VALIDATION registry. Every Cognitive Engine feature declares which learning
principle it relies on and whether that principle is well supported by research (in general
learning science — chess-specific evidence is thinner) or is a ChessLab experiment."""
from __future__ import annotations

PRINCIPLES = {
    "active_retrieval": {
        "name": "Active retrieval (testing effect)",
        "status": "validated",
        "summary": "Producing an answer from memory strengthens retention more than re-reading/re-watching.",
        "references": ["Roediger & Karpicke (2006), Psychological Science 17(3)",
                       "Dunlosky et al. (2013), Psychological Science in the Public Interest 14(1)"],
        "used_by": ["every puzzle is solved before the answer is shown", "blind calculation mode",
                    "retention probes"],
    },
    "spaced_repetition": {
        "name": "Spaced repetition / distributed practice",
        "status": "validated",
        "summary": "Reviews spread over increasing intervals beat massed practice for long-term retention.",
        "references": ["Cepeda et al. (2006), Psychological Bulletin 132(3)", "Dunlosky et al. (2013)"],
        "used_by": ["retention engine (SM-2-style intervals per concept)", "intervention blocks mix in due reviews"],
    },
    "interleaving": {
        "name": "Interleaving",
        "status": "validated",
        "summary": "Mixing problem types forces choosing the method, improving discrimination and transfer.",
        "references": ["Rohrer & Taylor (2007), Instructional Science 35", "Brunmair & Richter (2019), "
                       "Psychological Bulletin 145(11) — benefit varies by material"],
        "used_by": ["every 4th intervention exercise is a different concept", "reassessment uses mixed sets"],
    },
    "feedback": {
        "name": "Immediate, specific feedback",
        "status": "validated",
        "summary": "Feedback about the task and the process (not the person) improves learning.",
        "references": ["Hattie & Timperley (2007), Review of Educational Research 77(1)"],
        "used_by": ["solution + engine line after every attempt", "Error DNA label with the evidence used"],
    },
    "deliberate_practice": {
        "name": "Deliberate practice",
        "status": "validated",
        "summary": "Targeted practice on specific weaknesses with feedback; in chess, serious study predicts "
                   "skill but explains only part of the variance.",
        "references": ["Ericsson, Krampe & Tesch-Römer (1993), Psychological Review 100(3)",
                       "Charness et al. (2005), Applied Cognitive Psychology 19",
                       "Macnamara, Hambrick & Oswald (2014), Psychological Science 25(8)"],
        "used_by": ["interventions target measured recurring error categories"],
    },
    "progressive_challenge": {
        "name": "Progressive challenge (desirable difficulty)",
        "status": "validated",
        "summary": "Practice should be hard enough to require effort but still mostly successful.",
        "references": ["Bjork (1994), in Metacognition: Knowing about Knowing", "Bjork & Bjork (2011)"],
        "used_by": ["adaptive bands", "intervention difficulty targets ~70–85% success", "pressure levels"],
    },
}

EXPERIMENTAL = {
    "error_dna": "Rule-based error categories from engine evals, board features and timing. Heuristic labels; "
                 "a mistake can have several causes and the label cannot see the player's thoughts.",
    "intervention_effectiveness": "Per-user Beta/Thompson-sampling estimate of which intervention reduced an error "
                                  "category. Small samples, no control group, regression to the mean and general "
                                  "improvement all confound it — treat as a hint, not proof.",
    "fatigue_detection": "Within-session decline in difficulty-adjusted accuracy plus slower decisions. A training "
                         "signal, not a medical or psychological assessment.",
    "pressure_complexity": "Complexity score (forcing moves, line length, defence, rating deviation) is a ChessLab "
                           "design, not a validated scale.",
    "performance_prediction": "Linear trend with 95% prediction intervals on your own data. Learning curves are not "
                              "linear; the forecast is short-range and not an Elo prediction.",
    "retention_transfer_probe": "Treating success on NEW positions of a concept as 'genuine retention' is a "
                                "reasonable operationalisation, not an established psychometric measure.",
}


def report() -> dict:
    return {"validated_principles": PRINCIPLES, "experimental_features": EXPERIMENTAL,
            "note": "‘Validated’ refers to the general learning-science literature. Direct evidence that each "
                    "principle transfers to chess playing strength is limited; ChessLab measures that for you "
                    "through game metrics rather than assuming it."}
