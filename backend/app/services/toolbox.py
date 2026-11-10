"""Toolbox agents: CVs, application letters, humanising and integrity checks.

Same philosophy as the study coach: the deterministic engine is the product and
works with no key, while the optional Anthropic provider upgrades the writing
when one is configured.

The integrity check is deliberately bounded. It compares a submission with the
student's *own* uploaded library and with itself, and the report says so. It is
not a web-wide plagiarism database and never pretends to be one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..utils.text import STOPWORDS, split_sentences, title_case, words
from .ai_provider import AIProvider, LLMMessage, build_provider

CONTENT_PATH = Path(__file__).resolve().parent.parent / "content" / "toolbox.json"

TONES = ("professional", "warm", "direct", "academic")

#: Phrases that make writing sound like it was generated rather than said.
#: Used both to rewrite (with the replacements below) and to report.
AI_TELLS = (
    "delve",
    "tapestry",
    "leverage",
    "pivotal",
    "seamless",
    "robust",
    "foster",
    "elevate",
    "unlock",
    "underscore",
    "testament",
    "myriad",
    "plethora",
    "holistic",
    "synergy",
    "paradigm",
    "cutting-edge",
    "ever-evolving",
    "meticulous",
    "game-changer",
)

#: (pattern, replacement, why). Replacement may be "" to delete the phrase.
REWRITES: tuple[tuple[str, str, str], ...] = (
    (r"\bit is important to note that\s+(\w)", "", "Deleted a filler opener"),
    (r"\bit is worth noting that\s+(\w)", "", "Deleted a filler opener"),
    (r"\bplease note that\s+(\w)", "", "Deleted a filler opener"),
    (r"\bin today's fast-paced world,?\s*(\w)?", "", "Deleted an opening cliché"),
    (r"\bin the ever-evolving (landscape|world) of\s+", "", "Deleted an opening cliché"),
    (r"\bnavigate the complexities of\b", "work through", "Plain wording"),
    (r"\bdelve into\b", "look at", "Plain wording"),
    (r"\bdelves into\b", "looks at", "Plain wording"),
    (r"\bleverage\b", "use", "Plain wording"),
    (r"\bleverages\b", "uses", "Plain wording"),
    (r"\butilize\b", "use", "Plain wording"),
    (r"\butilizes\b", "uses", "Plain wording"),
    (r"\butilise\b", "use", "Plain wording"),
    (r"\bfacilitate\b", "support", "Plain wording"),
    (r"\bfacilitates\b", "supports", "Plain wording"),
    (r"\bcommence\b", "start", "Plain wording"),
    (r"\bterminate\b", "end", "Plain wording"),
    (r"\bprior to\b", "before", "Plain wording"),
    (r"\bsubsequently\b", "then", "Plain wording"),
    (r"\bin order to\b", "to", "Plainer and shorter"),
    (r"\bdue to the fact that\b", "because", "Plainer and shorter"),
    (r"\bin the event that\b", "if", "Plainer and shorter"),
    (r"\bat this point in time\b", "now", "Plainer and shorter"),
    (r"\bhas the ability to\b", "can", "Plainer and shorter"),
    (r"\bmake a decision\b", "decide", "Plainer and shorter"),
    (r"\ba myriad of\b", "many", "Plain wording"),
    (r"\ba plethora of\b", "many", "Plain wording"),
    (r"\brobust\b", "solid", "Plain wording"),
    (r"\belevate\b", "improve", "Plain wording"),
    (r"\b fosters?\b", "supports", "Plain wording"),
    (r"\bpivotal\b", "key", "Plain wording"),
    (r"\bseamless(ly)?\b", "smooth", "Plain wording"),
    (r"\bholistic\b", "complete", "Plain wording"),
    (r"\bmeticulous(ly)?\b", "careful", "Plain wording"),
    (r"\bunlock\b", "open up", "Plain wording"),
    (r"\bunderscores?\b", "shows", "Plain wording"),
    (r"\ba testament to\b", "proof of", "Plain wording"),
    (r"\bcutting-edge\b", "new", "Plain wording"),
    (r"\bgame-changer\b", "big change", "Plain wording"),
    (r"\bsynergy\b", "teamwork", "Plain wording"),
    (r"\bparadigm shift\b", "change in approach", "Plain wording"),
    (r"\bascertain\b", "find out", "Plain wording"),
    (r"\bendeavour to\b", "try to", "Plain wording"),
    (r"\bendeavor to\b", "try to", "Plain wording"),
    (r"\baforementioned\b", "this", "Plain wording"),
    (r"\bwhilst\b", "while", "Plain wording"),
    (r"\bamongst\b", "among", "Plain wording"),
    (r"\bfurthermore,?\s+", "Also, ", "Simpler connective"),
    (r"\bmoreover,?\s+", "Also, ", "Simpler connective"),
    (r"\bnevertheless,?\s+", "Even so, ", "Simpler connective"),
    (r"\bthus,?\s+", "So ", "Simpler connective"),
    (r"\bhence,?\s+", "So ", "Simpler connective"),
    (r"\btherefore,?\s+", "So ", "Simpler connective"),
    (r"\bin conclusion,?\s+", "To sum up, ", "Plain wording"),
)

CONTRACTIONS: tuple[tuple[str, str], ...] = (
    (r"\bdo not\b", "don't"),
    (r"\bdoes not\b", "doesn't"),
    (r"\bdid not\b", "didn't"),
    (r"\bis not\b", "isn't"),
    (r"\bare not\b", "aren't"),
    (r"\bwas not\b", "wasn't"),
    (r"\bwill not\b", "won't"),
    (r"\bcannot\b", "can't"),
    (r"\bit is\b", "it's"),
    (r"\bthat is\b", "that's"),
    (r"\bI am\b", "I'm"),
    (r"\byou are\b", "you're"),
    (r"\bwe are\b", "we're"),
    (r"\bthey are\b", "they're"),
)

CITATION_HINT = re.compile(
    r"\((?:\d{4}|[A-Z][a-z]+,\s*\d{4}|[A-Z][a-z]+\s+et\s+al)" r"|according to|as cited in|https?://|doi\.org",
    re.IGNORECASE,
)
QUOTED = re.compile(r"[\"“]([^\"”]{25,400})[\"”]")

_VOWELS = "aeiouy"


@lru_cache(maxsize=1)
def toolbox_content() -> dict[str, Any]:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def professions() -> list[dict[str, str]]:
    data = toolbox_content()["professions"]
    return sorted(
        ({"key": key, "label": entry["label"]} for key, entry in data.items()),
        key=lambda item: item["label"],
    )


def resolve_profession(value: str) -> tuple[str, dict[str, Any]]:
    """Match a profession key *or* label; unknown values get a generic profile."""
    data = toolbox_content()["professions"]
    raw = (value or "").strip()
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if slug in data:
        return slug, data[slug]
    for key, entry in data.items():
        if entry["label"].lower() == raw.lower():
            return key, entry
    label = title_case(raw) or "Professional"
    return slug or "general", {
        "label": label,
        "summary": f"{label.lower()} who delivers careful, well-documented work",
        "skills": ["Communication", "Problem solving", "Planning", "Teamwork", "Time management"],
        "certifications": [],
        "highlights": [
            "Describe one result you are proud of, with a number in it.",
            "Describe a problem you solved and what changed because of it.",
        ],
        "keywords": [],
    }


# ------------------------------------------------------------------ wording
def _match_case(source: str, replacement: str) -> str:
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _apply_rules(text: str, rules: Iterable[tuple[str, str, str]], changes: list[dict], limit: int = 12) -> str:
    total = 0
    for pattern, replacement, reason in rules:
        def repl(match: re.Match, replacement=replacement, reason=reason) -> str:
            nonlocal total
            total += 1
            original = match.group(0).strip()
            if not original:
                return match.group(0)
            tail = match.group(match.lastindex) if match.lastindex else ""
            if replacement == "":
                # Deleting a filler opener keeps the word that followed it.
                if tail:
                    original = match.group(0)[: -len(tail)].strip()
                fixed = tail.upper() if tail else ""
            elif match.lastindex:
                fixed = _match_case(match.group(0), replacement) + tail
            else:
                fixed = _match_case(match.group(0), replacement)
            if len(changes) < limit:
                changes.append({"before": original, "after": fixed or "(removed)", "reason": reason})
            return fixed

        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


def _syllables(word: str) -> int:
    cleaned = re.sub(r"[^a-z]", "", word.lower())
    if not cleaned:
        return 0
    count, previous_vowel = 0, False
    for char in cleaned:
        is_vowel = char in _VOWELS
        if is_vowel and not previous_vowel:
            count += 1
        previous_vowel = is_vowel
    if cleaned.endswith("e") and count > 1 and not cleaned.endswith(("le", "ee")):
        count -= 1
    return max(1, count)


def text_metrics(text: str) -> dict[str, Any]:
    body = (text or "").strip()
    sentences = split_sentences(body)
    tokens = words(body)
    syllables = sum(_syllables(token) for token in tokens)
    total_words = len(tokens)
    total_sentences = max(1, len(sentences))
    long_sentences = [s for s in sentences if len(s.split()) > 30]
    ease = 206.835 - 1.015 * (total_words / total_sentences) - 84.6 * (syllables / max(1, total_words))
    lowered = body.lower()
    return {
        "words": total_words,
        "sentences": len(sentences),
        "average_sentence_words": round(total_words / total_sentences, 1) if tokens else 0.0,
        "long_sentences": len(long_sentences),
        "reading_ease": round(max(0.0, min(100.0, ease)), 1),
        "cliches": sum(len(re.findall(rf"\b{re.escape(tell)}\b", lowered)) for tell in AI_TELLS),
        "contractions": len(re.findall(r"\b\w+(?:n't|'re|'ll|'ve|'d|'m|'s)\b", lowered)),
    }


def humanize(text: str, tone: str = "professional") -> dict[str, Any]:
    """Deterministic rewrite. Changes are reported so none has to be accepted."""
    tone = tone if tone in TONES else "professional"
    changes: list[dict] = []
    before = text_metrics(text)

    rules = list(REWRITES)
    if tone != "academic":
        rules.extend((pattern, replacement, "Spoken contraction") for pattern, replacement in CONTRACTIONS)
    if tone == "direct":
        rules.extend(
            [
                (r"\bI would like to\b", "I want to", "Direct wording"),
                (r"\bI am writing to\b", "I'm writing to", "Direct wording"),
                (r"\bplease do not hesitate to\b", "feel free to", "Direct wording"),
            ]
        )
    if tone == "warm":
        rules.extend(
            [
                (r"\bregards\b", "best wishes", "Warmer sign-off"),
                (r"\bI would like to\b", "I'd love to", "Warmer wording"),
            ]
        )

    rewritten = _apply_rules(text, rules, changes)
    rewritten = re.sub(r"[ \t]{2,}", " ", rewritten)
    rewritten = re.sub(r" +([,.;:!?])", r"\1", rewritten)
    rewritten = re.sub(r"\n{3,}", "\n\n", rewritten).strip()
    after = text_metrics(rewritten)

    notes: list[str] = []
    if not changes:
        notes.append("No clichés or filler phrases were found - this already reads as your own writing.")
    notes.append("Rule-based rewrite: every change is listed, so reject any that changes your meaning.")
    if tone == "academic":
        notes.append("Academic tone keeps contractions out on purpose.")
    long_after = [s for s in split_sentences(rewritten) if len(s.split()) > 30]
    if long_after:
        notes.append(
            f"{len(long_after)} sentence(s) are still over 30 words. Splitting them automatically could cut meaning, so rewrite those yourself."
        )
    remaining = sorted({tell for tell in AI_TELLS if re.search(rf"\b{re.escape(tell)}\b", rewritten.lower())})
    if remaining:
        notes.append("Still worth replacing: " + ", ".join(remaining[:6]) + ".")
    if after["reading_ease"] > before["reading_ease"]:
        notes.append(f"Reading ease improved from {before['reading_ease']} to {after['reading_ease']}.")

    return {
        "text": rewritten,
        "changes": changes,
        "before": before,
        "after": after,
        "source": "rules",
        "notes": notes,
    }


# ----------------------------------------------------------------------- CV
def _join_contact(values: Sequence[str | None]) -> str:
    return " · ".join(value.strip() for value in values if value and value.strip())


def _keyword_hits(skills: Sequence[str], blob: str, keywords: Sequence[str]) -> list[str]:
    haystack = " ".join(skills + [blob]).lower()
    return [word for word in keywords if word.lower() in haystack]


def build_cv_rules(data: dict[str, Any], profile: dict[str, Any], key: str) -> dict[str, Any]:
    name = (data.get("full_name") or "").strip() or "Your Name"
    target = (data.get("target_role") or "").strip()
    years = data.get("years_experience")
    # Nothing the student has not told us may appear as a claim. Template skills
    # are used only to fill an empty section, and that is disclosed below.
    given_skills = list(dict.fromkeys(data.get("skills") or []))
    skills = given_skills or list(profile.get("skills") or [])
    used_template_skills = not given_skills and bool(skills)
    experience = [item for item in data.get("experience") or [] if (item.get("role") or item.get("organisation"))]
    education = list(data.get("education") or [])
    certifications = list(data.get("certifications") or [])
    achievements = list(data.get("achievements") or [])

    lines: list[str] = [f"# {name}", ""]
    contact = _join_contact([data.get("location"), data.get("email"), data.get("phone")])
    if contact:
        lines += [contact, ""]

    summary = profile["summary"].strip()
    summary = summary[:1].upper() + summary[1:]
    if years:
        summary += f" with {years} year{'s' if years != 1 else ''} of experience"
    profile_line = summary + "." + (f" Targeting {target}." if target else "")
    lines += ["## Profile", "", profile_line, ""]

    if skills:
        lines += ["## Core skills", ""]
        for skill in skills[:16]:
            lines.append(f"- {skill}")
        lines.append("")

    lines += ["## Experience", ""]
    if experience:
        for item in experience:
            heading = " - ".join(part for part in [(item.get("role") or "").strip(), (item.get("organisation") or "").strip()] if part)
            lines.append(f"### {heading or 'Role'}")
            if (item.get("period") or "").strip():
                lines.append(f"_{item['period'].strip()}_")
            highlights = item.get("highlights") or []
            for highlight in highlights:
                lines.append(f"- {highlight.rstrip('.')}.")
            lines.append("")
    else:
        lines += ["_(No roles added yet. Add placements, internships or part-time work - see the suggestions.)_", ""]

    selected_education = education or []
    if selected_education:
        lines += ["## Education", ""] + [f"- {line}" for line in selected_education] + [""]

    if certifications:
        lines += ["## Certifications", ""] + [f"- {line}" for line in certifications] + [""]

    if achievements:
        lines += ["## Achievements", ""] + [f"- {line}" for line in achievements] + [""]

    document = "\n".join(lines).strip() + "\n"

    blob = " ".join(
        [target, data.get("job_description") or "", " ".join(achievements)]
        + [" ".join(item.get("highlights") or []) for item in experience]
    )
    matched = _keyword_hits(skills, blob, profile.get("keywords") or [])
    missing = [word for word in (profile.get("keywords") or []) if word not in matched]

    suggestions: list[str] = []
    if not data.get("email") or not data.get("phone"):
        suggestions.append("Add both an email and a phone number - recruiters skip CVs they cannot contact.")
    if not target:
        suggestions.append("Name the role you are aiming at; a CV without a target reads as generic.")
    if not experience:
        suggestions.append("Add at least one role, placement or project. A CV with no experience section gets filtered out.")
    if not education:
        suggestions.append("Add your qualification, institution and year.")
    if used_template_skills:
        suggestions.append(
            f"The skills section came from the {profile['label']} template - delete anything you have not actually used, or type your own list."
        )
    elif len(skills) < 6:
        suggestions.append("List six to ten skills, using the same words the advert uses.")
    if missing:
        suggestions.append("Keywords the advert likely screens for: " + ", ".join(missing[:6]) + ".")
    if not achievements:
        suggestions.append("Add one or two achievements with a number in them (time saved, % improved, people served).")
    if not certifications:
        template_certs = profile.get("certifications") or []
        if template_certs:
            suggestions.append("Add any certification you hold - for this field employers often look for: " + ", ".join(template_certs[:2]) + ".")
    if years:
        suggestions.append("Keep the CV to one page for under ten years of experience; two pages at most.")
    else:
        suggestions.append("Add your years of experience (even '1 year' or 'graduate') so the summary can be specific.")

    return {
        "document": document,
        "source": "rules",
        "profession": key,
        "profession_label": profile["label"],
        "suggestions": suggestions,
        "matched_keywords": matched,
        "missing_keywords": missing,
    }


# ------------------------------------------------------------------- letters
GREETINGS = {
    "professional": "Dear {recipient},",
    "warm": "Hello {recipient},",
    "direct": "Dear {recipient},",
    "academic": "Dear {recipient},",
}

OPENERS = {
    "professional": "I am applying for the {role} role{at_company}. I am a {summary}.",
    "warm": "I was glad to see the {role} opening{at_company}. I am a {summary}, and this role is the kind of work I want to keep doing.",
    "direct": "I want to apply for the {role} role{at_company}. I am a {summary}.",
    "academic": "I write to apply for the {role} position{at_company}. My work is that of a {summary}.",
}

CLOSERS = {
    "professional": "I would welcome the chance to discuss how I can contribute. Thank you for your time.",
    "warm": "I'd love to talk through how I could help the team. Thanks for reading.",
    "direct": "I can start at short notice. Happy to talk whenever suits you.",
    "academic": "I would be glad to provide further detail or references, and I thank you for considering this application.",
}

SIGNOFFS = {
    "professional": "Kind regards,",
    "warm": "Best wishes,",
    "direct": "Regards,",
    "academic": "Yours sincerely,",
}


def build_letter_rules(data: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    tone = data.get("tone") if data.get("tone") in TONES else "professional"
    kind = data.get("kind") or "cover_letter"
    role = (data.get("role") or "").strip() or profile["label"]
    company = (data.get("company") or "").strip()
    recipient = (data.get("recipient") or "").strip() or "Hiring Manager"
    at_company = f" at {company}" if company else ""
    highlights = [line.strip(" -•") for line in (data.get("highlights") or []) if line.strip()]
    if not highlights:
        highlights = list(profile.get("highlights") or [])[:2]

    opening = OPENERS[tone].format(role=role, at_company=at_company, summary=profile["summary"])
    paragraphs = [opening]
    if company:
        paragraphs.append(
            f"What draws me to {company} is the chance to do that work with a team that takes it seriously. "
            "I would bring the same care to your clients and colleagues that I bring to my own."
            if tone != "direct"
            else f"{company} is the kind of place where that work matters. I would bring the same standard to your team."
        )
    if highlights:
        lead = "A few things I have done that are relevant:" if tone != "direct" else "Relevant work:"
        paragraphs.append(lead + "\n" + "\n".join(f"- {line.rstrip('.')}." for line in highlights[:4]))
    paragraphs.append(CLOSERS[tone])

    body = "\n\n".join([GREETINGS[tone].format(recipient=recipient)] + paragraphs + [SIGNOFFS[tone] + f"\n{(data.get('your_name') or data.get('full_name') or 'Your Name')}"])

    subject = None
    if kind == "email":
        subject = f"Application: {role}" + (f" - {company}" if company else "")
        # An email should be shorter than a letter: drop the second paragraph.
        short = [opening, paragraphs[-1]]
        body = "\n\n".join([f"Hi {recipient.split()[0] if recipient != 'Hiring Manager' else 'there'},", *short, SIGNOFFS[tone] + f"\n{(data.get('your_name') or 'Your Name')}"])

    tips = [
        "Name the role and the company in the first two lines - that is what the reader is checking for.",
        "One page maximum. If a paragraph does not add a fact, cut it.",
        "Swap generic praise for something specific you know about the employer.",
    ]
    if not highlights:
        tips.append("Add one or two concrete results: the letter is much stronger with numbers in it.")
    if not company and kind == "cover_letter":
        tips.append("Add the company name; unnamed letters read like a mass application.")
    if not data.get("job_description"):
        tips.append("Paste the advert and mirror its wording where it is honest to do so - many employers screen for those terms.")

    return {"subject": subject, "body": body, "source": "rules", "tips": tips}


# ----------------------------------------------------------------- integrity
def _shingles(text: str, size: int = 5) -> set[tuple[str, ...]]:
    tokens = words(text)
    if len(tokens) < size:
        return set()
    return {tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


def _shared_span(sentence: str, passage: str, size: int = 5) -> int:
    """How much of ``sentence`` (0-100) appears verbatim in ``passage``."""
    sentence_shingles = _shingles(sentence, size)
    if not sentence_shingles:
        return 0
    passage_shingles = _shingles(passage, size)
    return round(100 * len(sentence_shingles & passage_shingles) / len(sentence_shingles))


def check_integrity(text: str, sources: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """Compare ``text`` with ``sources`` (label, passage) and with itself."""
    sentences = [s for s in split_sentences(text) if len(words(s)) >= 6]
    matches: list[dict[str, Any]] = []
    matched_words = 0
    total_words = max(1, len(words(text)))

    for sentence in sentences:
        best_label, best_score = None, 0
        for label, passage in sources:
            score = _shared_span(sentence, passage)
            if score > best_score:
                best_label, best_score = label, score
        if best_score >= 45 and best_label:
            matches.append({"sentence": sentence.strip(), "source": best_label, "similarity": best_score})
            matched_words += len(words(sentence))

    matches.sort(key=lambda item: item["similarity"], reverse=True)
    similarity = min(100, round(100 * matched_words / total_words))
    if matches and similarity < 15:
        # A short copied sentence in a long submission still matters.
        similarity = max(15, round(sum(m["similarity"] for m in matches) / len(matches) / 4))

    flags: list[dict[str, str]] = []
    for quoted in QUOTED.findall(text):
        window_start = max(0, text.find(quoted) - 120)
        context = text[window_start : text.find(quoted) + len(quoted) + 120]
        if not CITATION_HINT.search(context):
            flags.append(
                {
                    "kind": "uncited-quote",
                    "label": "Quotation without a citation",
                    "detail": f"“{quoted[:80]}…” is quoted but no author, year or link appears nearby.",
                }
            )
            break

    seen: set[str] = set()
    duplicates: set[str] = set()
    for sentence in split_sentences(text):
        key = re.sub(r"[^a-z0-9 ]", "", sentence.lower()).strip()
        if len(words(sentence)) < 8:
            continue
        if key in seen:
            duplicates.add(sentence.strip())
        seen.add(key)
    if duplicates:
        flags.append(
            {
                "kind": "duplicate-sentence",
                "label": "Repeated sentence",
                "detail": f"This sentence appears more than once: “{sorted(duplicates)[0][:90]}”",
            }
        )

    tells = sorted({tell for tell in AI_TELLS if re.search(rf"\b{re.escape(tell)}\b", text.lower())})
    if len(tells) >= 3:
        flags.append(
            {
                "kind": "ai-phrasing",
                "label": "Phrasing that reads as AI-generated",
                "detail": "Overused words: " + ", ".join(tells[:8]) + ". Ask the humanizer to replace them.",
            }
        )

    if not sources:
        flags.append(
            {
                "kind": "no-sources",
                "label": "No library to compare against",
                "detail": "Upload course material to compare against your own sources. This check cannot see the web.",
            }
        )

    level = "high" if similarity >= 40 else "medium" if similarity >= 15 else "low"
    verdict = {
        "high": "High overlap - most of this text also appears in your sources. Check every match before submitting.",
        "medium": "Some overlap - review the highlighted sentences and quote or cite them properly.",
        "low": "No significant overlap found in the sources this check can see.",
    }[level]
    scope = (
        f"Compared with {len(sources)} passage(s) in your library. "
        "Text-matching only: it cannot see sources you have not uploaded, and it will not reliably catch paraphrasing. "
        "Treat a low score as 'nothing found', not as proof of originality."
    )

    return {
        "similarity_score": similarity,
        "originality_score": 100 - similarity,
        "verdict": verdict,
        "level": level,
        "matches": matches[:8],
        "flags": flags,
        "sources_checked": len({label.split(" · ")[0] for label, _ in sources}),
        "passages_checked": len(sources),
        "scope": scope,
    }


# ------------------------------------------------------------------ agents
@dataclass
class ToolboxAgents:
    """The five toolbox agents, with a rules fallback for the writing ones."""

    provider: AIProvider | None = None
    _notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.provider is None:
            self.provider = build_provider()

    @property
    def ai_available(self) -> bool:
        return self.provider is not None

    async def _complete(self, system: str, prompt: str, max_tokens: int = 1200) -> str | None:
        if self.provider is None:
            return None
        return await self.provider.complete(
            system=system, messages=[LLMMessage(role="user", content=prompt)], max_tokens=max_tokens
        )

    async def cv(self, data: dict[str, Any]) -> dict[str, Any]:
        key, profile = resolve_profession(data.get("profession") or "")
        result = build_cv_rules(data, profile, key)
        if self.provider is not None:
            prompt = (
                "Write an ATS-friendly CV in Markdown for this candidate. Use only the facts given; "
                "never invent employers, dates, qualifications or numbers. Keep it to one page.\n\n"
                f"Facts (JSON): {json.dumps({k: v for k, v in data.items() if v}, ensure_ascii=False)}"
            )
            text = await self._complete(
                "You are a careful CV editor. Output only the CV in Markdown, no commentary.", prompt
            )
            if text:
                result["document"] = text.strip() + "\n"
                result["source"] = "ai"
        return result

    async def letter(self, data: dict[str, Any]) -> dict[str, Any]:
        key, profile = resolve_profession(data.get("profession") or "")
        result = build_letter_rules(data, profile)
        if self.provider is not None:
            prompt = (
                f"Write a {data.get('kind', 'cover_letter').replace('_', ' ')} for this candidate. "
                f"Tone: {data.get('tone', 'professional')}. Use only the facts given and keep it under 300 words.\n\n"
                f"Facts (JSON): {json.dumps({k: v for k, v in data.items() if v}, ensure_ascii=False)}"
            )
            text = await self._complete(
                "You write short, specific application letters that sound like the applicant, "
                "not like a template. Output only the letter body, no commentary.",
                prompt,
            )
            if text:
                result["body"] = text.strip()
                result["source"] = "ai"
        return result

    async def humanize(self, text: str, tone: str = "professional") -> dict[str, Any]:
        result = humanize(text, tone)
        if self.provider is not None:
            prompt = (
                f"Rewrite this text so it reads like a person wrote it. Tone: {tone}. "
                "Keep every fact, figure and name. Do not add new claims. Return only the rewritten text.\n\n"
                f"{text}"
            )
            rewritten = await self._complete(
                "You are a plain-English editor. Remove clichés and filler, keep the author's meaning, "
                "and never insert facts.",
                prompt,
                max_tokens=2000,
            )
            if rewritten:
                result["text"] = rewritten.strip()
                result["source"] = "ai"
                result["changes"] = []
                result["notes"] = [
                    "AI rewrite: compare the two versions before you use it - the model can smooth away a detail.",
                    *result["notes"][1:],
                ]
                result["after"] = text_metrics(rewritten)
        return result


@lru_cache(maxsize=1)
def get_agents() -> ToolboxAgents:
    return ToolboxAgents()


# --------------------------------------------------------------- counselling
def next_slots(
    counsellors: Sequence[dict[str, Any]],
    booked: set[tuple[str, str, str]],
    *,
    start_date,
    limit: int = 6,
    days: int = 10,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """The next free slots per counsellor, skipping taken and past times."""
    from datetime import timedelta, timezone

    if now is None:
        now = datetime.now(timezone.utc)
    slots: list[dict[str, Any]] = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        if day.weekday() >= 5:  # no weekend sessions
            continue
        for counsellor in counsellors:
            for time in counsellor.get("slot_times", []):
                key = (counsellor["id"], day.isoformat(), time)
                if key in booked:
                    continue
                hour, minute = (int(part) for part in time.split(":"))
                if day == now.date() and (hour, minute) <= (now.hour, now.minute):
                    continue  # already passed today
                slots.append(
                    {
                        "date": day,
                        "time": time,
                        "label": f"{day.strftime('%a %d %b')} · {time}",
                        "counsellor_id": counsellor["id"],
                    }
                )
        if len(slots) >= limit * max(1, len(counsellors)):
            break
    return slots
