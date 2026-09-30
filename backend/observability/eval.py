"""A cheap, no-LLM groundedness check.

Question it answers: "how much of the answer is actually backed by the retrieved
chunks?" It's the share of meaningful answer words that also appear in the
context. Crude on purpose — every caller only depends on this function's
signature, so it can be swapped for an LLM-as-judge later without touching
rag.py.
"""
import re

_WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = set(
    "a an and are as at be by for from has have in is it its of on or that the this to "
    "was were will with based documents document you your can not no yes do does".split()
)


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 2}


def groundedness(answer: str, contexts: list[str]) -> float:
    answer_words = _content_words(answer)
    if not answer_words:
        return 0.0
    context_words = _content_words(" ".join(contexts))
    return round(len(answer_words & context_words) / len(answer_words), 3)
