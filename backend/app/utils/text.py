"""Text normalisation and retrieval helpers shared by the services."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, Sequence

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_WHITESPACE = re.compile(r"[ \t\u00a0]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")

STOPWORDS: frozenset[str] = frozenset(
    """
    a about above after again against all am an and any are aren't as at be because been before being
    below between both but by can cannot could couldn't did didn't do does doesn't doing don't down during
    each few for from further had hadn't has hasn't have haven't having he he'd he'll he's her here here's
    hers herself him himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself let's
    me more most mustn't my myself no nor not of off on once only or other ought our ours ourselves out over
    own same shan't she she'd she'll she's should shouldn't so some such than that that's the their theirs
    them themselves then there there's these they they'd they'll they're they've this those through to too
    under until up very was wasn't we we'd we'll we're we've were weren't what what's when when's where
    where's which while who who's whom why why's with won't would wouldn't you you'd you'll you're you've
    your yours yourself yourselves also may might must shall will can just however therefore thus hence
    e.g i.e etc et al figure fig table chapter section page pages lecture slide slides week topic using use
    used uses within upon many much one two three four five six seven eight nine ten first second third
    """.split()
)


def clean_text(raw: str) -> str:
    """Normalise whitespace and rebuild paragraph breaks."""
    if not raw:
        return ""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
    text = _WHITESPACE.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def words(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text or "")]


def split_sentences(text: str) -> list[str]:
    text = clean_text(text).replace("\n", " ")
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p.strip()]
    return parts or [text]


def content_words(text: str) -> list[str]:
    return [w for w in words(text) if w not in STOPWORDS and len(w) > 2]


def top_keywords(text: str, limit: int = 8) -> list[str]:
    counts = Counter(content_words(text))
    return [word for word, _ in counts.most_common(limit)]


def _terms(text: str) -> list[str]:
    """Unigrams plus bigrams, used for relevance scoring."""
    toks = words(text)
    terms = [t for t in toks if len(t) > 2]
    terms.extend(f"{a} {b}" for a, b in zip(toks, toks[1:]))
    return terms


def rank_chunks(
    query: str,
    chunks: Sequence,
    top_k: int = 4,
    text_getter=lambda c: getattr(c, "text", ""),
) -> list[tuple[object, float]]:
    """Rank chunks against a query with TF-IDF-ish scoring (no external service).

    Returns ``(chunk, score)`` pairs sorted by descending relevance.
    """
    if not chunks:
        return []

    corpus = [_terms(text_getter(c)) for c in chunks]
    doc_count = len(corpus)
    doc_freq: Counter[str] = Counter()
    for terms in corpus:
        doc_freq.update(set(terms))

    query_terms = [t for t in _terms(query) if t not in STOPWORDS]
    if not query_terms:
        return [(c, 0.0) for c in chunks[:top_k]]

    scored: list[tuple[object, float]] = []
    for chunk, terms in zip(chunks, corpus):
        if not terms:
            scored.append((chunk, 0.0))
            continue
        counts = Counter(terms)
        length_norm = 1.0 + math.log(1 + len(terms))
        score = 0.0
        for term in query_terms:
            tf = counts.get(term)
            if not tf:
                continue
            idf = math.log(1 + doc_count / (1 + doc_freq[term]))
            weight = 1.6 if " " in term else 1.0
            score += (1 + math.log(tf)) * idf * weight
        scored.append((chunk, score / length_norm))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    positive = [pair for pair in scored if pair[1] > 0]
    return (positive or scored)[:top_k]


def first_sentences(text: str, count: int = 2, max_words: int = 60) -> str:
    sentences = split_sentences(text)
    picked: list[str] = []
    total = 0
    for sentence in sentences:
        n = len(sentence.split())
        if picked and total + n > max_words:
            break
        picked.append(sentence)
        total += n
        if len(picked) >= count:
            break
    return " ".join(picked)


def truncate(text: str, limit: int = 320) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "..."


def title_case(value: str) -> str:
    small = {"and", "or", "of", "the", "in", "to", "for", "with", "a", "an", "on", "at", "by"}
    parts = [p for p in re.split(r"\s+", value.strip()) if p]
    out: list[str] = []
    for i, part in enumerate(parts):
        if i and part.lower() in small:
            out.append(part.lower())
        elif part.isupper() and len(part) <= 5:
            out.append(part)  # keep acronyms like DNA, ATP
        else:
            out.append(part[:1].upper() + part[1:])
    return " ".join(out)


def unique_preserving_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
