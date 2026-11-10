"""Persisting the topic map for a course."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Chunk, Course, Task, Topic
from ..utils.auth import generate_topic_id
from .topic_extractor import ChunkView, TopicExtractor


def rebuild_course_topics(db: Session, course: Course) -> list[Topic]:
    """Recompute the topic map from every chunk in the course.

    Existing topics are replaced; tasks keep their text but lose the link to the
    old topic so the plan is never silently deleted.
    """
    chunks = list(
        db.scalars(
            select(Chunk)
            .where(Chunk.course_id == course.id)
            .order_by(Chunk.document_id, Chunk.position)
        ).all()
    )

    for chunk in chunks:
        chunk.topic_id = None
    for task in db.scalars(select(Task).where(Task.course_id == course.id)).all():
        task.topic_id = None
    for topic in list(course.topics):
        db.delete(topic)
    db.flush()

    if not chunks:
        db.commit()
        return []

    views = [ChunkView(id=chunk.id, text=chunk.text, heading=chunk.heading) for chunk in chunks]
    specs = TopicExtractor.build_topics(views)

    chunk_map = {chunk.id: chunk for chunk in chunks}
    created: list[tuple[Topic, list[int]]] = []
    for spec in specs:
        document_ids = sorted(
            {
                chunk_map[cid].document_id
                for cid in spec.get("chunk_ids", [])
                if cid in chunk_map
            }
        )
        topic = Topic(
            id=generate_topic_id(),
            course_id=course.id,
            title=spec["title"][:300],
            summary=spec.get("summary"),
            keywords=spec.get("keywords", []),
            difficulty=spec.get("difficulty", 3),
            weight=spec.get("weight", 1.0),
            order_index=spec.get("order_index", 0),
            source_document_ids=document_ids,
        )
        db.add(topic)
        created.append((topic, spec.get("chunk_ids", [])))

    db.flush()

    for topic, chunk_ids in created:
        for chunk_id in chunk_ids:
            chunk = chunk_map.get(chunk_id)
            if chunk is not None:
                chunk.topic_id = topic.id

    db.commit()
    for topic, _ in created:
        db.refresh(topic)
    return [topic for topic, _ in created]
