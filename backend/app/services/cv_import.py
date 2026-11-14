"""Best-effort CV import.

CVs are wildly inconsistent, so this parser is deliberately conservative: it
extracts the details it can identify, leaves uncertain fields empty, and lets
the student correct the form before rebuilding. It never invents a job, date or
qualification.
"""

from __future__ import annotations

import re
from typing import Any

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}")
_DATE_HINT = re.compile(
    r"(?i)(?:\b(?:19|20)\d{2}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b|\bpresent\b|\bcurrent\b)"
)
_DATE_RANGE = re.compile(
    r"(?i)\(?\s*(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?"
    r"(?:19|20)\d{2}\s*(?:[-–—]|to)\s*"
    r"(?:present|current|now|(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?(?:19|20)\d{2})\s*\)?"
)
_BULLET = re.compile(r"^\s*(?:[-*•·▪◦]|\d+[.)])\s*")
_YEARS = re.compile(r"(?i)\b(\d{1,2})\+?\s+years?(?:\s+of)?\s+experience\b")
_INLINE_SECTION = re.compile(
    r"^(?P<name>professional summary|career summary|summary|profile|about me|"
    r"work experience|professional experience|employment history|employment|experience|"
    r"education and training|education|qualifications|academic background|"
    r"core skills|technical skills|key skills|skills|competencies|"
    r"certifications and licenses|certifications|certificates|licenses|"
    r"key achievements|achievements|awards|projects|selected projects)\s*:\s*(?P<body>.+)$",
    re.I,
)

_ALIASES = {
    "professional summary": "summary",
    "career summary": "summary",
    "summary": "summary",
    "profile": "summary",
    "about me": "summary",
    "work experience": "experience",
    "professional experience": "experience",
    "employment history": "experience",
    "employment": "experience",
    "experience": "experience",
    "work history": "experience",
    "relevant experience": "experience",
    "volunteer experience": "experience",
    "volunteering": "experience",
    "education and training": "education",
    "education": "education",
    "qualifications": "education",
    "academic background": "education",
    "core skills": "skills",
    "technical skills": "skills",
    "key skills": "skills",
    "skills": "skills",
    "competencies": "skills",
    "areas of expertise": "skills",
    "certifications and licenses": "certifications",
    "certifications": "certifications",
    "certificates": "certifications",
    "licenses": "certifications",
    "key achievements": "achievements",
    "achievements": "achievements",
    "awards": "achievements",
    "honors": "achievements",
    "projects": "achievements",
    "selected projects": "achievements",
}


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _section_key(line: str) -> str | None:
    candidate = re.sub(r"^[#\s]+", "", line).strip().rstrip(":").lower()
    candidate = re.sub(r"[^a-z ]", "", candidate).strip()
    return _ALIASES.get(candidate)


def _clean_item(line: str) -> str:
    return _BULLET.sub("", line).strip(" -–—|·").strip()


def _looks_like_date(line: str) -> bool:
    text = line.strip()
    return bool(text) and len(text) <= 80 and bool(_DATE_HINT.search(text))


def _split_period(line: str) -> tuple[str, str]:
    """Return ``(period, rest)`` after removing a leading/trailing date range."""
    match = _DATE_RANGE.search(line)
    if not match:
        return "", line
    period = match.group(0).strip(" ()")
    rest = (line[: match.start()] + " " + line[match.end() :]).strip(" ,|·-–—")
    return period, rest


def _looks_like_name(line: str) -> bool:
    text = line.strip()
    if not text or len(text) > 80 or _EMAIL.search(text) or "http" in text.lower():
        return False
    if any(char.isdigit() for char in text):
        return False
    if text.lower().strip(" .:") in {"curriculum vitae", "cv", "resume", "résumé"}:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'.-]*", text)
    if not 1 <= len(words) <= 5:
        return False
    capitalised = sum(1 for word in words if word[:1].isupper())
    return capitalised >= max(1, len(words) - 1)


def _looks_like_location(line: str) -> bool:
    text = line.strip()
    if not text or len(text) > 80 or _EMAIL.search(text) or "http" in text.lower():
        return False
    if any(char.isdigit() for char in text):
        return False
    if "|" in text or "·" in text:
        return False
    parts = [part.strip() for part in text.split(",")]
    return 2 <= len(parts) <= 3 and all(parts)


def _split_role(line: str) -> tuple[str, str]:
    text = _clean_item(line)
    at_match = re.split(r"\s+(?:at|@)\s+", text, maxsplit=1, flags=re.I)
    if len(at_match) == 2:
        return at_match[0].strip(), at_match[1].strip()

    dash_match = re.split(r"\s+[–—]\s+|\s+-\s+", text, maxsplit=1)
    if len(dash_match) == 2 and not _looks_like_date(text):
        return dash_match[0].strip(), dash_match[1].strip()

    comma_match = [part.strip() for part in text.split(",") if part.strip()]
    if len(comma_match) == 2:
        return comma_match[0], comma_match[1]
    return text, ""


def _parse_experience(lines: list[str]) -> list[dict[str, Any]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)

    entries: list[dict[str, Any]] = []
    for block in blocks:
        bullets = [_clean_item(line) for line in block if _BULLET.match(line)]
        plain = [line for line in block if not _BULLET.match(line)]
        if not plain and not bullets:
            continue

        first = plain[0] if plain else ""
        period = ""
        role = ""
        organisation = ""

        if first:
            period, first = _split_period(first)
            parts = [part.strip() for part in re.split(r"\s*[|·]\s*", first) if part.strip()]
            if len(parts) >= 2 and _looks_like_date(parts[-1]):
                period = period or parts.pop()
            if len(parts) >= 2:
                role = parts[0]
                organisation = " ".join(parts[1:])
            else:
                role, organisation = _split_role(first)

        rest = plain[1:] if first else []
        if not organisation and rest and not _looks_like_date(rest[0]):
            organisation = _clean_item(rest[0])
            rest = rest[1:]
        if not period:
            period = next((line for line in rest if _looks_like_date(line)), "")

        highlights = bullets or [_clean_item(line) for line in rest if line != period]
        role = role[:160].strip()
        organisation = organisation[:160].strip()
        period = period[:80].strip()
        highlights = [item[:500] for item in highlights if item][:8]

        if not role and not organisation:
            continue
        entries.append(
            {
                "role": role,
                "organisation": organisation,
                "period": period,
                "highlights": highlights,
            }
        )
    return entries[:8]


def _section_items(lines: list[str], limit: int = 10) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for line in lines:
        cleaned = _clean_item(line)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(cleaned[:500])
        if len(items) >= limit:
            break
    return items


def _skill_items(lines: list[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for line in lines:
        cleaned = _clean_item(line)
        if not cleaned:
            continue
        for part in re.split(r"[,;|/•·]|\s{2,}", cleaned):
            skill = part.strip(" .-–—")
            if not skill or len(skill) > 80:
                continue
            key = skill.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(skill)
            if len(items) >= 24:
                return items
    return items


def parse_cv_text(text: str) -> dict[str, Any]:
    """Return fields compatible with ``CVImportFields``.

    Only clearly identified values are returned. Everything else is left empty
    so the student can fill it in.
    """
    lines = [_clean_line(line) for line in text.replace("\r\n", "\n").split("\n")]
    email_match = _EMAIL.search(text)
    email = email_match.group(0)[:200] if email_match else None

    # Header lines are everything before the first recognised CV section.
    first_section = next((index for index, line in enumerate(lines) if _section_key(line)), len(lines))
    header_lines = [line for line in lines[:first_section] if line]

    name = next((line for line in header_lines if _looks_like_name(line)), None)
    location = next(
        (
            line
            for line in header_lines
            if line != name and _looks_like_location(line)
        ),
        None,
    )

    phone = None
    for line in header_lines + lines[:12]:
        if "http" in line.lower() or re.search(r"(19|20)\d{2}", line):
            continue
        match = _PHONE.search(line)
        if not match:
            continue
        candidate = match.group(0).strip(" .-()")
        digits = re.sub(r"\D", "", candidate)
        if 7 <= len(digits) <= 15:
            phone = candidate[:60]
            break

    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        if not line:
            if current:
                sections.setdefault(current, []).append("")
            continue
        key = _section_key(line)
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        inline = _INLINE_SECTION.match(line)
        if inline:
            key = _ALIASES.get(inline.group("name").lower().strip())
            if key:
                current = key
                sections.setdefault(current, []).append(inline.group("body").strip())
                continue
        if current:
            sections.setdefault(current, []).append(line)

    experience = _parse_experience(sections.get("experience", []))
    skills = _skill_items(sections.get("skills", []))
    education = _section_items(sections.get("education", []))
    certifications = _section_items(sections.get("certifications", []))
    achievements = _section_items(sections.get("achievements", []))

    summary = " ".join(_clean_item(line) for line in sections.get("summary", []) if line)
    years_match = _YEARS.search(summary or text)
    years = min(60, int(years_match.group(1))) if years_match else None

    first_role = next((entry["role"] for entry in experience if entry.get("role")), "")
    profession = first_role[:120] or None

    return {
        "profession": profession,
        "full_name": name,
        "email": email,
        "phone": phone,
        "location": location,
        "target_role": None,
        "years_experience": years,
        "skills": skills,
        "experience": experience,
        "education": education,
        "certifications": certifications,
        "achievements": achievements,
    }
