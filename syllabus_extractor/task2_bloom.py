import re
from typing import Optional, Tuple

BLOOM_LEVELS = ["remember", "understand", "apply", "analyse", "evaluate", "create"]

# Mapping of common explicit/printed indicators to standard Bloom levels (lowercase)
PRINTED_BLOOM_MAP = {
    "remember": "remember",
    "remembering": "remember",
    "k1": "remember",
    "l1": "remember",
    "b1": "remember",
    "bl1": "remember",
    
    "understand": "understand",
    "understanding": "understand",
    "comprehend": "understand",
    "comprehension": "understand",
    "k2": "understand",
    "l2": "understand",
    "b2": "understand",
    "bl2": "understand",
    
    "apply": "apply",
    "application": "apply",
    "applying": "apply",
    "k3": "apply",
    "l3": "apply",
    "b3": "apply",
    "bl3": "apply",
    
    "analyze": "analyse",
    "analyse": "analyse",
    "analysis": "analyse",
    "analyzing": "analyse",
    "analysing": "analyse",
    "k4": "analyse",
    "l4": "analyse",
    "b4": "analyse",
    "bl4": "analyse",
    
    "evaluate": "evaluate",
    "evaluation": "evaluate",
    "evaluating": "evaluate",
    "k5": "evaluate",
    "l5": "evaluate",
    "b5": "evaluate",
    "bl5": "evaluate",
    
    "create": "create",
    "creation": "create",
    "creating": "create",
    "synthesis": "create",
    "synthesize": "create",
    "design": "create",
    "k6": "create",
    "l6": "create",
    "b6": "create",
    "bl6": "create",
}

# Action verbs mapped to standard Bloom levels for zero-shot inference
ACTION_VERB_MAP = {
    # Level 1: Remember
    "define": "remember",
    "describe": "remember",
    "identify": "remember",
    "label": "remember",
    "list": "remember",
    "match": "remember",
    "name": "remember",
    "recall": "remember",
    "recognize": "remember",
    "reproduce": "remember",
    "select": "remember",
    "state": "remember",
    "outline": "remember",
    "repeat": "remember",
    "memorize": "remember",
    "record": "remember",
    "cite": "remember",
    "quote": "remember",
    
    # Level 2: Understand
    "comprehend": "understand",
    "convert": "understand",
    "defend": "understand",
    "distinguish": "understand",
    "estimate": "understand",
    "explain": "understand",
    "extend": "understand",
    "generalize": "understand",
    "infer": "understand",
    "paraphrase": "understand",
    "predict": "understand",
    "rewrite": "understand",
    "summarize": "understand",
    "understand": "understand",
    "discuss": "understand",
    "express": "understand",
    "locate": "understand",
    "report": "understand",
    "review": "understand",
    "translate": "understand",
    "interpret": "understand",
    "clarify": "understand",
    "elucidate": "understand",
    "exemplify": "understand",
    "classify": "understand",
    
    # Level 3: Apply
    "apply": "apply",
    "change": "apply",
    "choose": "apply",
    "compute": "apply",
    "demonstrate": "apply",
    "discover": "apply",
    "dramatize": "apply",
    "employ": "apply",
    "illustrate": "apply",
    "manipulate": "apply",
    "modify": "apply",
    "operate": "apply",
    "practice": "apply",
    "prepare": "apply",
    "produce": "apply",
    "relate": "apply",
    "schedule": "apply",
    "show": "apply",
    "sketch": "apply",
    "solve": "apply",
    "use": "apply",
    "calculate": "apply",
    "execute": "apply",
    "implement": "apply",
    "simulate": "apply",
    "perform": "apply",
    "utilize": "apply",
    "construct": "apply",
    "develop": "apply",
    
    # Level 4: Analyse
    "analyze": "analyse",
    "analyse": "analyse",
    "appraise": "analyse",
    "breakdown": "analyse",
    "categorize": "analyse",
    "compare": "analyse",
    "contrast": "analyse",
    "criticize": "analyse",
    "diagram": "analyse",
    "differentiate": "analyse",
    "discriminate": "analyse",
    "examine": "analyse",
    "experiment": "analyse",
    "question": "analyse",
    "separate": "analyse",
    "subdivide": "analyse",
    "test": "analyse",
    "inspect": "analyse",
    "investigate": "analyse",
    "deduce": "analyse",
    "diagnose": "analyse",
    "correlate": "analyse",
    "dissect": "analyse",
    "model": "analyse",
    
    # Level 5: Evaluate
    "assess": "evaluate",
    "argue": "evaluate",
    "attach": "evaluate",
    "conclude": "evaluate",
    "judge": "evaluate",
    "justify": "evaluate",
    "rate": "evaluate",
    "score": "evaluate",
    "support": "evaluate",
    "value": "evaluate",
    "critique": "evaluate",
    "validate": "evaluate",
    "verify": "evaluate",
    "measure": "evaluate",
    "recommend": "evaluate",
    "prioritize": "evaluate",
    
    # Level 6: Create
    "combine": "create",
    "compile": "create",
    "compose": "create",
    "create": "create",
    "devise": "create",
    "design": "create",
    "generate": "create",
    "organize": "create",
    "plan": "create",
    "rearrange": "create",
    "reconstruct": "create",
    "reorganize": "create",
    "revise": "create",
    "synthesize": "create",
    "formulate": "create",
    "integrate": "create",
    "invent": "create",
    "originate": "create",
    "propose": "create",
    "build": "create",
}


def normalize_printed_bloom(raw: str) -> Optional[str]:
    """
    Normalizes printed Bloom taxonomy strings (e.g., 'Understand', 'Analysing', 'K3', 'L2') into standard form.
    """
    if not raw:
        return None
    clean = re.sub(r"[^a-zA-Z0-9]", "", raw.lower())
    if clean in PRINTED_BLOOM_MAP:
        return PRINTED_BLOOM_MAP[clean]
    # Prefix check e.g. "analy" -> "analyse"
    for k, v in PRINTED_BLOOM_MAP.items():
        if clean.startswith(k) or k.startswith(clean):
            return v
    return None


def infer_bloom_from_text(text: str) -> Tuple[str, str]:
    """
    Infers Bloom taxonomy level from the action verbs within the statement or topic.
    Returns (bloom, 'inferred'). Defaults to 'understand' if no strong verb found.
    """
    words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
    
    # Check leading verb or prominent words in text
    for word in words:
        if word in ["to", "the", "a", "an", "and", "or", "of", "in", "for", "with", "on", "by", "after", "successful", "completion", "student", "will", "be", "able"]:
            continue
        
        # Lemmatize common suffixes (-ing, -ed, -s, -es, -tion)
        base_candidates = [word]
        if word.endswith("ing"):
            base_candidates.append(word[:-3])
            base_candidates.append(word[:-3] + "e")
        elif word.endswith("ed"):
            base_candidates.append(word[:-2])
            base_candidates.append(word[:-1])
        elif word.endswith("es"):
            base_candidates.append(word[:-2])
        elif word.endswith("s"):
            base_candidates.append(word[:-1])

        for cand in base_candidates:
            if cand in ACTION_VERB_MAP:
                return ACTION_VERB_MAP[cand], "inferred"

    return "understand", "inferred"
