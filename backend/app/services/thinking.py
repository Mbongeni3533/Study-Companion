"""The thinking check: a short, friendly pre-assessment and what it changes.

Eight questions, about three minutes: six have a right answer and measure
reasoning, reading comprehension and planning; two are about how the student
likes to learn. Nothing here is a diagnosis or a grade. The result is a plain
level ("Small steps", "Steady pace", "Ready for a challenge") plus a learning
style, and the coach uses it to choose how much to explain and how hard to push.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CONTENT_PATH = Path(__file__).resolve().parent.parent / "content" / "assessment.json"

#: Order used to break ties between learning-style signals.
STYLE_PRIORITY = ("explain", "examples", "explore", "support")


@lru_cache(maxsize=1)
def content() -> dict[str, Any]:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def public_questions() -> list[dict[str, Any]]:
    """Questions with answers and style tags removed."""
    questions: list[dict[str, Any]] = []
    for item in content()["questions"]:
        questions.append(
            {
                "id": item["id"],
                "kind": item["kind"],
                "dimension": item["dimension"],
                "prompt": item["prompt"],
                "options": [{"id": option["id"], "label": option["label"]} for option in item["options"]],
            }
        )
    return questions


def _level_for(correct: int, total: int) -> str:
    if total <= 0:
        return "steady"
    ratio = correct / total
    if ratio <= 0.4:
        return "foundation"
    if ratio < 0.85:
        return "steady"
    return "stretch"


def assess(answers: dict[str, str]) -> dict[str, Any]:
    """Score answers and return the profile stored on the user.

    Unknown question or option ids are ignored rather than rejected: the form is
    fixed, and a stale tab should not fail with a validation wall.
    """
    data = content()
    totals: dict[str, int] = {}
    correct_by: dict[str, int] = {}
    correct_total = 0
    knowledge_total = 0
    style_votes: dict[str, int] = {}

    for question in data["questions"]:
        chosen = (answers.get(question["id"]) or "").strip()
        if not chosen:
            continue
        option = next((item for item in question["options"] if item["id"] == chosen), None)
        if option is None:
            continue

        if question["kind"] == "habit":
            style = option.get("style")
            if style:
                style_votes[style] = style_votes.get(style, 0) + 1
            continue

        dimension = question["dimension"]
        totals[dimension] = totals.get(dimension, 0) + 1
        knowledge_total += 1
        if option["id"] == question.get("answer"):
            correct_by[dimension] = correct_by.get(dimension, 0) + 1
            correct_total += 1

    scores = {
        dimension: round(100 * correct_by.get(dimension, 0) / total)
        for dimension, total in totals.items()
        if total
    }
    level = _level_for(correct_total, knowledge_total)
    level_info = data["levels"][level]

    style = "examples"
    if style_votes:
        style = max(STYLE_PRIORITY, key=lambda key: (style_votes.get(key, 0), -STYLE_PRIORITY.index(key)))
        if style_votes.get(style, 0) == 0:
            style = "examples"
    style_info = data["styles"][style]

    summary = [
        f"You answered {correct_total} of {knowledge_total} questions correctly.",
        level_info["summary"],
        style_info["line"],
    ]

    return {
        "level": level,
        "level_label": level_info["label"],
        "style": style,
        "style_label": style_info["label"],
        "style_line": style_info["line"],
        "correct": correct_total,
        "total": knowledge_total,
        "scores": scores,
        "summary": summary,
        "coach_actions": list(level_info["actions"]),
        "coach_note": level_info["coach_note"],
    }


def guide(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Compact instructions for the coach. Falls back to balanced behaviour."""
    if not profile or not profile.get("level"):
        return {
            "level": "steady",
            "label": "Steady pace",
            "coach_note": "",
            "actions": [],
            "style": "",
            "assessed": False,
        }
    level = profile.get("level", "steady")
    info = content()["levels"].get(level, content()["levels"]["steady"])
    return {
        "level": level,
        "label": profile.get("level_label") or info["label"],
        "coach_note": profile.get("coach_note") or info["coach_note"],
        "actions": profile.get("coach_actions") or list(info["actions"]),
        "style": profile.get("style", ""),
        "assessed": True,
    }
