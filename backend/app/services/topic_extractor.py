"""Rule-based topic mapping.

Turns the chunks extracted from a course's documents into a topic map. It uses
the document's own structure (headings) when available and otherwise falls back
to keyword clustering, so the feature works with no AI key configured.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from ..utils.text import (
    STOPWORDS,
    clean_text,
    first_sentences,
    split_sentences,
    title_case,
    top_keywords,
    unique_preserving_order,
    words,
)

MAX_TOPICS = 12
MIN_TOPICS = 3


@dataclass
class ChunkView:
    """The subset of a Chunk the extractor needs (works with ORM objects too)."""

    id: int
    text: str
    heading: str | None


def _difficulty(text: str) -> int:
    """Estimate 1-5 difficulty from sentence length and rare-word density."""
    tokens = words(text)
    if not tokens:
        return 2
    sentences = split_sentences(text) or [text]
    avg_sentence = len(tokens) / max(1, len(sentences))
    long_words = sum(1 for t in tokens if len(t) >= 8)
    density = long_words / len(tokens)
    score = 1.0
    score += min(1.5, avg_sentence / 20.0)
    score += min(1.5, density * 6.0)
    return max(1, min(5, round(score)))


class TopicExtractor:
    """Builds a topic map from a course's chunks."""

    @classmethod
    def build_topics(cls, chunks: list[ChunkView]) -> list[dict]:
        chunks = [c for c in chunks if c.text and c.text.strip()]
        if not chunks:
            return []

        if cls._heading_coverage(chunks) >= 0.5:
            groups = cls._group_by_heading(chunks)
        else:
            groups = cls._group_by_keywords(chunks)

        if len(groups) < MIN_TOPICS and len(chunks) >= MIN_TOPICS:
            groups = cls._group_by_keywords(chunks, desired=max(MIN_TOPICS, len(groups)))
        if not groups:
            groups = [(cls._fallback_title(chunks), chunks)]

        topics: list[dict] = []
        total_chunks = len(chunks)
        for order, (title, members) in enumerate(groups[:MAX_TOPICS]):
            if not members:
                continue
            body = "\n".join(m.text for m in members)
            keywords = top_keywords(body, limit=6)
            topics.append(
                {
                    "title": title_case(title)[:300] or cls._fallback_title(members),
                    "summary": first_sentences(members[0].text, count=2),
                    "keywords": keywords,
                    "difficulty": _difficulty(body),
                    "weight": round(len(members) / total_chunks, 3),
                    "order_index": order,
                    "chunk_ids": [m.id for m in members],
                }
            )

        if not topics:
            return []
        # normalise weights to sum to 1
        weight_sum = sum(t["weight"] for t in topics) or 1.0
        for topic in topics:
            topic["weight"] = round(topic["weight"] / weight_sum, 3)
        return topics

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _heading_coverage(chunks: list[ChunkView]) -> float:
        headings = {c.heading.strip().lower() for c in chunks if c.heading and c.heading.strip()}
        return len(headings) / max(1, len(chunks))

    @classmethod
    def _group_by_heading(cls, chunks: list[ChunkView]) -> list[tuple[str, list[ChunkView]]]:
        ordered: dict[str, list[ChunkView]] = {}
        for chunk in chunks:
            key = (chunk.heading or "").strip() or "Overview"
            key = re.sub(r"^[\d.\s):-]+", "", key).strip() or "Overview"
            ordered.setdefault(key, []).append(chunk)
        # Only fold micro-sections (stray headings) when there are many of them -
        # a course with three short sections should still get three topics.
        fold_micro = len(ordered) > 6
        merged: list[tuple[str, list[ChunkView]]] = []
        for title, members in ordered.items():
            words_in_group = sum(len(m.text.split()) for m in members)
            if fold_micro and merged and words_in_group < 20:
                prev_title, prev_members = merged[-1]
                merged[-1] = (prev_title, prev_members + members)
            else:
                merged.append((title, list(members)))
        return merged

    @staticmethod
    def _chunk_terms(text: str) -> set[str]:
        return {w for w in words(text) if w not in STOPWORDS and len(w) > 3}

    @classmethod
    def _group_by_keywords(cls, chunks: list[ChunkView], desired: int = 6) -> list[tuple[str, list[ChunkView]]]:
        """Cluster chunks around their strongest shared keywords."""
        doc_freq: Counter[str] = Counter()
        per_chunk: list[set[str]] = []
        for chunk in chunks:
            terms = cls._chunk_terms(chunk.text)
            per_chunk.append(terms)
            doc_freq.update(terms)

        n_docs = len(chunks)
        candidates: list[tuple[float, str]] = []
        for term, freq in doc_freq.items():
            if freq < 2:
                continue
            # prefer terms that appear in a reasonable share of chunks
            coverage = freq / n_docs
            if coverage > 0.7:
                continue
            score = freq * math.log(1 + n_docs / freq) * (1 + min(len(term), 14) / 14)
            candidates.append((score, term))

        candidates.sort(reverse=True)
        picked: list[str] = []
        for _, term in candidates:
            if any(term in other or other in term for other in picked):
                continue
            picked.append(term)
            if len(picked) >= desired:
                break

        if not picked:
            # no shared vocabulary at all - split sequentially
            size = max(1, math.ceil(len(chunks) / max(MIN_TOPICS, 1)))
            return [
                (cls._fallback_title(chunks[i : i + size]), chunks[i : i + size])
                for i in range(0, len(chunks), size)
            ]

        assigned: dict[str, list[ChunkView]] = defaultdict(list)
        unassigned: list[ChunkView] = []
        for chunk, terms in zip(chunks, per_chunk):
            best_term, best_hits = None, 0
            for term in picked:
                hits = sum(1 for t in terms if t == term or term in t)
                if hits > best_hits:
                    best_term, best_hits = term, hits
            if best_term:
                assigned[best_term].append(chunk)
            else:
                unassigned.append(chunk)

        # distribute leftovers proportionally into the smallest groups
        for chunk in unassigned:
            target = min(assigned, key=lambda key: len(assigned[key] or [])) if assigned else None
            if target is None:
                assigned[cls._fallback_title([chunk])] = [chunk]
            else:
                assigned[target].append(chunk)

        groups = [(term, members) for term, members in assigned.items() if members]
        groups.sort(key=lambda pair: (-len(pair[1]), pair[0]))
        return groups

    @staticmethod
    def _fallback_title(chunks: list[ChunkView]) -> str:
        for chunk in chunks:
            if chunk.heading and chunk.heading.strip():
                return chunk.heading.strip()[:120]
        keywords = top_keywords("\n".join(c.text for c in chunks), limit=3)
        if keywords:
            return " & ".join(title_case(k) for k in keywords)
        return "Study material"


def summarise_course(chunks: list[ChunkView], limit: int = 4) -> str:
    """A short study overview used by the coach and the UI."""
    if not chunks:
        return ""
    joined = "\n".join(c.text for c in chunks)
    sentences = split_sentences(joined)
    scored: list[tuple[float, str]] = []
    keywords = set(top_keywords(joined, limit=12))
    for sentence in sentences:
        if len(sentence.split()) < 6:
            continue
        overlap = len({w for w in words(sentence) if w in keywords})
        position_bonus = 1.0 / (1 + sentences.index(sentence) * 0.05)
        scored.append((overlap + position_bonus, clean_text(sentence)))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    picked = unique_preserving_order([s for _, s in scored])[:limit]
    return " ".join(picked)
