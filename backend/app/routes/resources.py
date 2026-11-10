"""Student Resources Centre: scholarships, research routes, careers, jobs,
career paths and the document library.

The content is static JSON and markdown shipped with the app, so nothing here
needs a database or a network call. Endpoints are public: the resources are the
same for every student and carry no personal data.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/resources", tags=["resources"])

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content" / "resources"
SECTIONS = ("overview", "scholarships", "research", "career", "employment", "library")


@lru_cache(maxsize=None)
def _load(name: str) -> dict[str, Any]:
    path = CONTENT_DIR / f"{name}.json"
    if not path.exists():  # pragma: no cover - packaging mistake, not user input
        raise FileNotFoundError(f"resources content missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _document(slug: str) -> tuple[dict[str, Any], str]:
    for document in _load("library")["documents"]:
        if document["slug"] == slug:
            path = CONTENT_DIR / "library" / document["file"]
            if not path.exists():  # pragma: no cover
                break
            return document, path.read_text(encoding="utf-8")
    raise HTTPException(status_code=404, detail="Unknown document")


def _join_locations(labels: list[str]) -> str:
    if len(labels) <= 1:
        return labels[0] if labels else ""
    return f"{', '.join(labels[:-1])} and {labels[-1]}"


# The literal routes come first: FastAPI matches in declaration order, so a
# "/{section}" catch-all above them would swallow /career-path and /library.
@router.get("/career-path")
def career_path(
    field: str | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    performance: str | None = Query(default=None),
) -> dict[str, Any]:
    """Opportunities and advice for a field, one or more locations and a band.

    Unknown values are rejected rather than silently defaulted: a typo in the
    caller should be visible, not turned into plausible-looking advice.
    """
    data = _load("career-path")
    field_labels = {item["key"]: item["label"] for item in data["fields"]}
    region_labels = {item["key"]: item["label"] for item in data["regions"]}
    bands = {item["key"]: item for item in data["performance_bands"]}

    if field is not None and field not in field_labels:
        raise HTTPException(status_code=400, detail="Unknown field")
    for key in region or []:
        if key not in region_labels:
            raise HTTPException(status_code=400, detail="Unknown region")
    if performance is not None and performance not in bands:
        raise HTTPException(status_code=400, detail="Unknown performance band")

    field_key = field or data["default_field"]
    entry = data["by_field"][field_key]

    requested = [key for key in (region or []) if key in region_labels]
    # Preserve the caller's order while dropping duplicates.
    regions = list(dict.fromkeys(requested)) or [data["default_region"]]
    band_key = performance or data["default_performance"]

    allowed = set(regions) | {"africa"}
    local = [item for item in entry["local"] if item["region"] in allowed]

    board_names: set[str] = set()
    for key in regions:
        board_names.update(entry["board_regions"].get(key, []))
    boards = [board for board in entry["boards"] if board["name"] in board_names]

    gaps = [entry["gaps"][key] for key in regions if entry["gaps"].get(key)]

    return {
        "fields": data["fields"],
        "regions": data["regions"],
        "region_groups": data["region_groups"],
        "selected": {
            "field": field_key,
            "field_label": field_labels[field_key],
            "region": regions[0],
            "region_label": region_labels[regions[0]],
            "regions": [{"key": key, "label": region_labels[key]} for key in regions],
            "locations_label": _join_locations([region_labels[key] for key in regions]),
        },
        "profile": entry["profile"],
        "local": local,
        "abroad": entry["abroad"],
        "funding": entry["funding"],
        "boards": boards,
        "gaps": gaps,
        "performance_bands": data["performance_bands"],
        "advisor": entry["advisor"][band_key],
        "counts": {
            "local": len(local),
            "abroad": len(entry["abroad"]),
            "funding": len(entry["funding"]),
        },
        "coverage": data["coverage"],
    }


@router.get("/library/{slug}")
def library_document(slug: str) -> dict[str, Any]:
    document, content = _document(slug)
    return {"document": document, "content": content}


@router.get("/library/{slug}/download", response_class=PlainTextResponse)
def library_download(slug: str) -> PlainTextResponse:
    document, content = _document(slug)
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{document["slug"]}.md"'},
    )


@router.get("/{section}")
def resources_section(section: str) -> dict[str, Any]:
    """One section of the centre. The overview carries the headline stats."""
    if section not in SECTIONS:
        raise HTTPException(status_code=404, detail="Unknown section")
    return _load(section)
