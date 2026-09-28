"""Plain-Slovak explanations of rules, validation errors and legislation.

Retrieval-augmented: a small curated knowledge base (``knowledge/*.md``) is
searched with a diacritics-insensitive keyword scorer. Without an LLM the best
articles are returned as-is; with Claude enabled, the model answers the user's
question grounded only in the retrieved articles.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"


@dataclass(frozen=True)
class Article:
    id: str
    title: str
    tags: tuple[str, ...]
    rules: tuple[str, ...]
    body: str


def fold(text: str) -> str:
    """Lowercase and strip diacritics so 'danovej' matches 'daňovej'."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", fold(text)) if len(t) > 2]


@lru_cache
def load_articles() -> tuple[Article, ...]:
    articles = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        _, header, body = raw.split("---", 2)
        meta = dict(line.split(":", 1) for line in header.strip().splitlines())
        articles.append(Article(
            id=path.stem, title=meta["title"].strip(),
            tags=tuple(t.strip() for t in meta.get("tags", "").split(",") if t.strip()),
            rules=tuple(r.strip() for r in meta.get("rules", "").split(",") if r.strip()),
            body=body.strip(),
        ))
    return tuple(articles)


def search(query: str, rule_id: str | None = None, limit: int = 3) -> list[Article]:
    q = set(_tokens(query))
    scored = []
    for art in load_articles():
        score = 0.0
        if rule_id and rule_id in art.rules:
            score += 100
        tag_tokens = set(_tokens(" ".join(art.tags)))
        title_tokens = set(_tokens(art.title))
        body_tokens = _tokens(art.body)
        score += 5 * len(q & tag_tokens) + 3 * len(q & title_tokens)
        score += sum(1 for t in body_tokens if t in q) / (1 + len(body_tokens) / 200)
        # Prefix matches catch Slovak inflection (faktúra/faktúry/faktúru).
        score += sum(1 for t in q for tag in tag_tokens if len(t) > 4 and tag.startswith(t[:5]) and t != tag)
        if score > 0:
            scored.append((score, art))
    scored.sort(key=lambda s: -s[0])
    return [a for _, a in scored[:limit]]


_SYSTEM = (
    "Si asistent aplikácie eFaktúra SK. Vysvetľuješ slovenským živnostníkom a malým firmám pravidlá "
    "e-fakturácie a DPH jednoduchou slovenčinou, bez odborného žargónu, v 3 až 6 vetách. "
    "Odpovedaj iba na základe priložených článkov. Ak odpoveď v článkoch nie je, povedz to a odporuč "
    "daňového poradcu alebo financnasprava.sk. Neuvádzaj čísla paragrafov, ktoré nie sú v článkoch."
)


def explain(question: str, rule_id: str | None = None, context: str | None = None, *,
            use_llm: bool = False, api_key: str | None = None, model: str = "claude-opus-5") -> dict:
    articles = search(" ".join(filter(None, [question, context, rule_id])), rule_id=rule_id)
    sources = [{"id": a.id, "title": a.title} for a in articles]
    if not articles:
        return {"answer": "K tejto otázke zatiaľ nemám článok. Obráťte sa, prosím, na daňového poradcu "
                          "alebo pozrite financnasprava.sk.", "sources": [], "generated": False}
    if not use_llm:
        top = articles[0]
        return {"answer": f"{top.title}\n\n{top.body}", "sources": sources, "generated": False}

    import anthropic

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    docs = "\n\n".join(f"<article id=\"{a.id}\" title=\"{a.title}\">\n{a.body}\n</article>" for a in articles)
    user = f"{docs}\n\nOtázka používateľa: {question}"
    if context:
        user += f"\nKontext (chyba z validácie): {context}"
    try:
        response = client.beta.messages.create(
            model=model, max_tokens=2000, system=_SYSTEM, thinking={"type": "adaptive"},
            output_config={"effort": "low"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIError:
        top = articles[0]
        return {"answer": f"{top.title}\n\n{top.body}", "sources": sources, "generated": False}
    if response.stop_reason == "refusal":
        top = articles[0]
        return {"answer": f"{top.title}\n\n{top.body}", "sources": sources, "generated": False}
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return {"answer": text, "sources": sources, "generated": True}
