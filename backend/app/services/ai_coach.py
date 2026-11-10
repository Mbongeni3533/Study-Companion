"""The study coach.

Two engines behind one interface:

* ``ai``    - the optional Anthropic provider, grounded in retrieved excerpts.
* ``rules`` - a deterministic Socratic engine that needs no API key and is what
  makes the product usable out of the box.

The coach is deliberately *hint-first*: it nudges, quizzes and points back into
the student's own material instead of handing over answers.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Sequence

from ..utils.text import (
    STOPWORDS,
    first_sentences,
    split_sentences,
    title_case,
    top_keywords,
    truncate,
)
from .ai_provider import AIProvider, LLMMessage, build_provider

TASK_TYPES = ("read", "practice", "quiz", "review", "write")


@dataclass
class TopicBrief:
    title: str
    summary: str | None = None
    keywords: list[str] = field(default_factory=list)
    difficulty: int = 3
    order_index: int = 0


@dataclass
class Excerpt:
    text: str
    heading: str | None = None
    document_name: str | None = None

    @property
    def label(self) -> str:
        if self.heading:
            return self.heading
        if self.document_name:
            return self.document_name
        return "your material"


@dataclass
class CoachAnswer:
    text: str
    source: str  # "ai" | "rules"
    citations: list[str] = field(default_factory=list)


@dataclass
class PlanItem:
    title: str
    description: str
    task_type: str
    difficulty: int
    estimated_minutes: int
    day_offset: int
    topic_index: int | None
    hint: str


@dataclass
class TaskPlan:
    items: list[PlanItem]
    source: str
    note: str


@lru_cache
def get_coach() -> "AIStudyCoach":
    """Process-wide coach so the provider client is created once."""
    return AIStudyCoach()


class AIStudyCoach:
    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider if provider is not None else build_provider()

    @property
    def provider_name(self) -> str:
        return self.provider.name if self.provider else "rules"

    @property
    def ai_available(self) -> bool:
        return self.provider is not None

    # ================================================================== chat
    async def reply(
        self,
        *,
        course_title: str,
        course_code: str | None,
        topics: Sequence[TopicBrief],
        excerpts: Sequence[Excerpt],
        history: Sequence[dict],
        message: str,
        hint_level: int = 1,
    ) -> CoachAnswer:
        if self.provider is not None:
            answer = await self._ai_reply(
                course_title=course_title,
                course_code=course_code,
                topics=topics,
                excerpts=excerpts,
                history=history,
                message=message,
                hint_level=hint_level,
            )
            if answer is not None:
                return answer

        return self._rule_reply(
            course_title=course_title,
            topics=topics,
            excerpts=excerpts,
            message=message,
            hint_level=hint_level,
        )

    async def _ai_reply(
        self,
        *,
        course_title: str,
        course_code: str | None,
        topics: Sequence[TopicBrief],
        excerpts: Sequence[Excerpt],
        history: Sequence[dict],
        message: str,
        hint_level: int,
    ) -> CoachAnswer | None:
        topic_lines = "\n".join(f"- {t.title}" for t in topics[:12]) or "- (no topic map yet)"
        excerpt_lines = "\n\n".join(
            f"[{i}] {e.label} ({e.document_name or 'upload'})\n{truncate(e.text, 700)}"
            for i, e in enumerate(excerpts[:5], start=1)
        )
        system = f"""You are Study Companion, a Socratic study coach for university students.
Course: {course_title}{f" ({course_code})" if course_code else ""}.
Hint level for this turn: {hint_level} of 3.
Rules:
- Level 1: give a nudge, a reframing or one guiding question. Do not answer for the student.
- Level 2: give a targeted clue and point to the relevant part of their material.
- Level 3: explain step by step, then ask them to restate it in their own words.
- Ground every factual claim in the numbered excerpts. If they do not cover the question, say so and name what to upload.
- Be warm and concise: under 220 words, short paragraphs, bullets where useful.
- Never hand over an essay. Never invent sources.
Topic map:
{topic_lines}

Excerpts from the student's own material:
{excerpt_lines or "(no material uploaded yet)"}"""

        messages: list[LLMMessage] = []
        for turn in list(history)[-8:]:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                messages.append(LLMMessage(role=role, content=truncate(content, 1500)))
        messages.append(LLMMessage(role="user", content=message))

        text = await self.provider.complete(system=system, messages=messages, max_tokens=900)
        if not text:
            return None
        citations = [e.label for e in excerpts[:3] if e.text and e.text[:40].lower() in text.lower()]
        if not citations:
            citations = [e.label for e in excerpts[:2]]
        return CoachAnswer(text=text, source="ai", citations=citations[:3])

    # ------------------------------------------------------- rule engine: chat
    def _rule_reply(
        self,
        *,
        course_title: str,
        topics: Sequence[TopicBrief],
        excerpts: Sequence[Excerpt],
        message: str,
        hint_level: int,
    ) -> CoachAnswer:
        intent = self._detect_intent(message)
        topic = self._match_topic(message, topics) or (topics[0] if topics else None)
        citations = [e.label for e in excerpts[:2]]

        if not excerpts and not topics:
            return CoachAnswer(
                text=(
                    f"I don't have any of your **{course_title}** material yet, so I'd only be guessing.\n\n"
                    "Upload a lecture PDF, slide deck or your notes and I'll build a topic map, "
                    "a study plan and quiz you from it.\n\n"
                    "In the meantime: what's the one topic you're most worried about?"
                ),
                source="rules",
            )

        if intent == "quiz":
            return CoachAnswer(self._quiz_reply(topic, excerpts, hint_level), "rules", citations)
        if intent == "flashcards":
            return CoachAnswer(self._flashcard_reply(excerpts), "rules", citations)
        if intent == "summary":
            return CoachAnswer(self._summary_reply(course_title, topics, excerpts), "rules", citations)
        if intent == "plan":
            return CoachAnswer(self._plan_reply(course_title, topics), "rules", [])
        if intent in {"explain", "hint"}:
            return CoachAnswer(
                self._explain_reply(topic, excerpts, hint_level), "rules", citations
            )
        return CoachAnswer(self._coach_reply(topic, topics, excerpts), "rules", citations)

    @staticmethod
    def _detect_intent(message: str) -> str:
        text = message.lower()
        patterns = [
            ("quiz", r"\b(quiz|test me|practice question|past question|exam question|questions?)\b"),
            ("flashcards", r"\b(flash ?cards?|anki|memory cards)\b"),
            ("summary", r"\b(summari[sz]e|summary|overview|recap|tl;?dr|key points)\b"),
            ("plan", r"\b(plan|schedule|what should i (study|do)|where do i start|today|timetable)\b"),
            ("hint", r"\b(hint|clue|stuck|help me|nudge|not sure|confused)\b"),
            ("explain", r"\b(explain|what is|what are|why|how does|how do|define|describe|difference between|meaning)\b"),
        ]
        for intent, pattern in patterns:
            if re.search(pattern, text):
                return intent
        return "coach"

    @staticmethod
    def _match_topic(message: str, topics: Sequence[TopicBrief]) -> TopicBrief | None:
        if not topics:
            return None
        message_words = {
            w for w in re.findall(r"[a-z]{3,}", message.lower()) if w not in STOPWORDS
        }
        best: TopicBrief | None = None
        best_score = 0.0
        for topic in topics:
            terms = set(re.findall(r"[a-z]{3,}", topic.title.lower())) | {
                k.lower() for k in (topic.keywords or [])
            }
            terms -= STOPWORDS
            if not terms:
                continue
            overlap = len(message_words & terms) / len(terms)
            if topic.title.lower() in message.lower():
                overlap += 0.6
            if overlap > best_score:
                best, best_score = topic, overlap
        return best if best_score > 0 else None

    def _explain_reply(
        self,
        topic: TopicBrief | None,
        excerpts: Sequence[Excerpt],
        hint_level: int,
    ) -> str:
        heading = topic.title if topic else "this part of your material"
        excerpt = excerpts[0] if excerpts else None
        keywords = ", ".join((topic.keywords if topic else [])[:4]) or "the key terms"
        source_note = f" _(from {excerpt.label})_" if excerpt else ""

        if hint_level <= 1:
            lines = [f"Let's work it out rather than read it off. **{heading}**{source_note}", ""]
            lines.append("Start here:")
            lines.append(f"1. In one sentence, what does *{heading}* let you explain or predict?")
            lines.append(f"2. Which of these do you recognise - {keywords}? Say what each means to you.")
            lines.append("3. Where does it break down or stop applying?")
            lines.append("")
            lines.append("Answer any one of those and I'll push you further.")
            return "\n".join(lines)

        if hint_level == 2:
            lines = [f"Here's the clue, not the answer. **{heading}**{source_note}", ""]
            if excerpt:
                lines.append(f"> {first_sentences(excerpt.text, count=2, max_words=55)}")
                lines.append("")
            lines.append(f"Notice the role of {keywords}. Ask yourself: what changes if one of those is missing?")
            lines.append("")
            lines.append("Write your attempt in a sentence or two and I'll check the reasoning.")
            return "\n".join(lines)

        lines = [f"Full walkthrough - then you restate it. **{heading}**{source_note}", ""]
        if excerpt:
            lines.append(f"> {first_sentences(excerpt.text, count=3, max_words=90)}")
            lines.append("")
        lines.append("How to hold onto it:")
        lines.append(f"- **Core idea:** {topic.summary if topic and topic.summary else heading}.")
        if topic and topic.keywords:
            lines.append("- **Key terms:** " + ", ".join(topic.keywords[:5]))
        lines.append("- **How it's examined:** definitions first, then a short applied example, then a limitation.")
        lines.append("")
        lines.append("Now close this chat, write the idea from memory in 3 sentences, and paste it back for a check.")
        return "\n".join(lines)

    def _quiz_reply(
        self,
        topic: TopicBrief | None,
        excerpts: Sequence[Excerpt],
        hint_level: int,
    ) -> str:
        questions = self._build_quiz(excerpts, topic, count=3)
        if not questions:
            return (
                "I need a bit more text before I can quiz you reliably. "
                "Upload the lecture or paste a paragraph and I'll turn it into questions."
            )
        label = topic.title if topic else "your material"
        lines = [f"Three questions on **{label}**. No notes - answer from memory first.", ""]
        for number, (question, _answer) in enumerate(questions, start=1):
            lines.append(f"{number}. {question}")
        lines.append("")
        if hint_level >= 3:
            lines.append("**Answer key (check only after you've written yours):**")
            for number, (_question, answer) in enumerate(questions, start=1):
                lines.append(f"- {number}. {answer}")
        else:
            lines.append("Send your answers and I'll mark each one and tell you what to fix.")
        return "\n".join(lines)

    def _build_quiz(
        self,
        excerpts: Sequence[Excerpt],
        topic: TopicBrief | None,
        count: int = 3,
    ) -> list[tuple[str, str]]:
        keywords = [k for k in (topic.keywords if topic else []) if len(k) > 3][:10]
        corpus = "\n".join(e.text for e in excerpts)
        sentences = [s for s in split_sentences(corpus) if 8 <= len(s.split()) <= 50]
        questions: list[tuple[str, str]] = []
        used: set[str] = set()

        for sentence in sentences:
            if len(questions) >= count:
                break
            sentence_lower = sentence.lower()
            candidate = None
            for keyword in keywords:
                if keyword.lower() in sentence_lower:
                    candidate = keyword
                    break
            if candidate is None:
                # fall back to the longest content word in the sentence
                tokens = [
                    t
                    for t in re.findall(r"[A-Za-z][A-Za-z\-]{5,}", sentence)
                    if t.lower() not in STOPWORDS
                ]
                if not tokens:
                    continue
                candidate = max(tokens, key=len)

            if candidate.lower() in used:
                continue
            pattern = re.compile(re.escape(candidate), re.IGNORECASE)
            if not pattern.search(sentence):
                continue
            blanked = pattern.sub("________", sentence, count=1)
            questions.append((f"Fill in the blank: \"{truncate(blanked, 260)}\"", candidate))
            used.add(candidate.lower())

        return questions

    def _flashcard_reply(self, excerpts: Sequence[Excerpt]) -> str:
        cards: list[tuple[str, str]] = []
        for excerpt in excerpts[:4]:
            for sentence in split_sentences(excerpt.text):
                match = re.match(
                    r"^(?P<term>[A-Z][A-Za-z0-9\- ]{2,48}?)\s+(?:is|are|refers to|means|describes|is defined as)\s+(?P<body>.{15,220})$",
                    sentence.strip(),
                )
                if not match:
                    continue
                term = match.group("term").strip()
                if term.lower() in STOPWORDS or len(term.split()) > 6:
                    continue
                cards.append((term, truncate(match.group("body").strip(), 200)))
                if len(cards) >= 8:
                    break
            if len(cards) >= 8:
                break

        if not cards:
            keywords = top_keywords("\n".join(e.text for e in excerpts), limit=6)
            if not keywords:
                return "I couldn't find clean definitions in your material yet. Try a lecture PDF or your notes."
            lines = ["No formal definitions found, so here are concept cards from your key terms:", ""]
            for keyword in keywords:
                lines.append(f"- **{title_case(keyword)}** - explain it in your own words, then check the lecture.")
            return "\n".join(lines)

        lines = ["Flashcards from your material. Cover the answer, then say it out loud:", ""]
        for term, body in cards:
            lines.append(f"- **{term}** - {truncate(body, 140)}")
        lines.append("")
        lines.append("Tap 'quiz me' and I'll test the same terms in different wording.")
        return "\n".join(lines)

    def _summary_reply(
        self,
        course_title: str,
        topics: Sequence[TopicBrief],
        excerpts: Sequence[Excerpt],
    ) -> str:
        if not topics:
            return (
                f"No topic map for **{course_title}** yet. Upload something and I'll summarise it into topics."
            )
        lines = [f"Here's **{course_title}** at a glance ({len(topics)} topics):", ""]
        for index, topic in enumerate(topics[:10], start=1):
            summary = topic.summary or " - ".join(topic.keywords[:3]) or "no summary yet"
            lines.append(f"{index}. **{topic.title}** - {truncate(summary, 160)}")
        lines.append("")
        first = topics[0]
        lines.append(
            f"Start with **{first.title}** (difficulty {first.difficulty}/5) - it carries the most material. "
            "Then quiz yourself before moving on."
        )
        return "\n".join(lines)

    def _plan_reply(self, course_title: str, topics: Sequence[TopicBrief]) -> str:
        if not topics:
            return "Upload material first and I'll build a plan you can actually finish."
        ordered = sorted(topics, key=lambda t: (t.difficulty, -len(t.keywords)))
        first, second = ordered[0], ordered[min(1, len(ordered) - 1)]
        lines = [
            f"A 60-minute block for **{course_title}**:",
            "",
            f"- **0-10 min** - recall: shut the notes and write everything you remember about *{first.title}*.",
            f"- **10-30 min** - study *{first.title}* (difficulty {first.difficulty}/5). One worked example.",
            "- **30-40 min** - break. Actually take it.",
            f"- **40-55 min** - quiz yourself on *{second.title}*, then re-read only what you got wrong.",
            "- **55-60 min** - write 3 questions you still can't answer. Those are tomorrow's start.",
            "",
            "Generate a multi-day plan from the **Plan** tab and I'll spread these across your week.",
        ]
        return "\n".join(lines)

    def _coach_reply(
        self,
        topic: TopicBrief | None,
        topics: Sequence[TopicBrief],
        excerpts: Sequence[Excerpt],
    ) -> str:
        heading = topic.title if topic else (topics[0].title if topics else "your next step")
        lines = [f"Good - let's make this concrete. **{heading}**.", ""]
        if excerpts:
            lines.append(f"> {first_sentences(excerpts[0].text, count=1, max_words=40)}")
            lines.append("")
        lines.append("Pick one:")
        lines.append(f"- **Explain it** - \"explain {heading.lower()}\"")
        lines.append(f"- **Test it** - \"quiz me on {heading.lower()}\"")
        lines.append("- **Plan it** - \"what should I study today?\"")
        lines.append("")
        lines.append("What's your goal for this session?")
        return "\n".join(lines)

    # ============================================================== planning
    async def build_task_plan(
        self,
        *,
        course_title: str,
        topics: Sequence[TopicBrief],
        excerpts: Sequence[Excerpt],
        count: int = 5,
        focus: str | None = None,
        minutes_per_day: int = 60,
        difficulty: int | None = None,
    ) -> TaskPlan:
        if self.provider is not None:
            plan = await self._ai_plan(
                course_title=course_title,
                topics=topics,
                excerpts=excerpts,
                count=count,
                focus=focus,
                minutes_per_day=minutes_per_day,
                difficulty=difficulty,
            )
            if plan is not None:
                return plan
        return self._rule_plan(
            course_title=course_title,
            topics=topics,
            count=count,
            focus=focus,
            minutes_per_day=minutes_per_day,
            difficulty=difficulty,
        )

    async def _ai_plan(
        self,
        *,
        course_title: str,
        topics: Sequence[TopicBrief],
        excerpts: Sequence[Excerpt],
        count: int,
        focus: str | None,
        minutes_per_day: int,
        difficulty: int | None,
    ) -> TaskPlan | None:
        topic_lines = "\n".join(
            f"{i}. {t.title} (difficulty {t.difficulty}/5; keywords: {', '.join(t.keywords[:4])})"
            for i, t in enumerate(topics[:12])
        ) or "0. Course material (no topic map)"
        excerpt_note = truncate("\n".join(e.text for e in excerpts[:3]), 1500)
        system = f"""You design realistic, specific study plans for university students.
Course: {course_title}. The student can study about {minutes_per_day} minutes per day.
{f"Student focus: {focus}." if focus else ""}
{f"Requested difficulty ceiling: {difficulty}/5." if difficulty else ""}
Topic map:
{topic_lines}

Relevant material:
{excerpt_note or "(none)"}

Return ONLY a JSON array (no prose, no markdown fence) of at most {count} objects:
{{"title": str, "description": str, "task_type": "read"|"practice"|"quiz"|"review"|"write",
  "difficulty": 1-5, "estimated_minutes": 10-90, "day_offset": 0-6,
  "topic_index": int or null, "hint": str}}
Rules: titles must name the actual topic, not "study topic 1". Interleave types so the plan
includes retrieval practice, not only reading. Keep each day's total <= {minutes_per_day} minutes."""
        text = await self.provider.complete(
            system=system,
            messages=[LLMMessage(role="user", content=f"Build the plan for {course_title}.")],
            max_tokens=1400,
        )
        if not text:
            return None
        items = self._parse_plan_json(text, topic_count=len(topics), minutes_per_day=minutes_per_day)
        if not items:
            return None
        return TaskPlan(items=items, source="ai", note=f"Built by {self.provider.name} from your material.")

    @staticmethod
    def _parse_plan_json(text: str, *, topic_count: int, minutes_per_day: int) -> list[PlanItem]:
        raw = text.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []

        items: list[PlanItem] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title", "")).strip()
            if not title:
                continue
            task_type = str(entry.get("task_type", "read")).lower().strip()
            if task_type not in TASK_TYPES:
                task_type = "read"
            try:
                difficulty = int(entry.get("difficulty", 3))
            except (TypeError, ValueError):
                difficulty = 3
            try:
                minutes = int(entry.get("estimated_minutes", 25))
            except (TypeError, ValueError):
                minutes = 25
            try:
                day_offset = int(entry.get("day_offset", 0))
            except (TypeError, ValueError):
                day_offset = 0
            topic_index = entry.get("topic_index")
            if not isinstance(topic_index, int) or isinstance(topic_index, bool):
                topic_index = None
            elif not 0 <= topic_index < topic_count:
                topic_index = None
            items.append(
                PlanItem(
                    title=title[:300],
                    description=str(entry.get("description", "")).strip()[:2000],
                    task_type=task_type,
                    difficulty=max(1, min(5, difficulty)),
                    estimated_minutes=max(5, min(180, minutes)),
                    day_offset=max(0, min(13, day_offset)),
                    topic_index=topic_index,
                    hint=str(entry.get("hint", "")).strip()[:500],
                )
            )
        return items

    def _rule_plan(
        self,
        *,
        course_title: str,
        topics: Sequence[TopicBrief],
        count: int,
        focus: str | None,
        minutes_per_day: int,
        difficulty: int | None,
    ) -> TaskPlan:
        briefs = list(topics)
        if not briefs:
            briefs = [TopicBrief(title=f"{course_title} material", difficulty=3, order_index=0)]

        ordered = sorted(briefs, key=lambda t: t.order_index)
        if focus:
            focus_terms = {w for w in re.findall(r"[a-z]{3,}", focus.lower())} - STOPWORDS
            ordered.sort(
                key=lambda t: -len(
                    focus_terms & ({w for w in re.findall(r"[a-z]{3,}", t.title.lower())} | {k.lower() for k in t.keywords})
                )
            )

        # Interleave task types so every topic gets retrieval practice, not just reading.
        sequence: list[tuple[TopicBrief, str]] = []
        for task_type in ("read", "practice", "quiz", "review"):
            for topic in ordered:
                sequence.append((topic, task_type))

        # Repeat the cycle when more tasks are requested than topics * 4 allow.
        wanted = max(1, count)
        if len(sequence) < wanted:
            base = list(sequence)
            while len(sequence) < wanted:
                sequence.extend(base)

        budget = max(15, minutes_per_day)
        day_offsets: dict[int, int] = {}
        items: list[PlanItem] = []
        for topic, task_type in sequence[:wanted]:
            level = difficulty or topic.difficulty
            minutes = {
                "read": 15 + level * 6,
                "practice": 15 + level * 5,
                "quiz": 10 + level * 3,
                "review": 10 + level * 2,
            }[task_type]
            minutes = max(10, min(120, minutes))

            day = 0
            while day_offsets.get(day, 0) + minutes > budget and day < 13:
                day += 1
            day_offsets[day] = day_offsets.get(day, 0) + minutes

            keywords = ", ".join(topic.keywords[:4])
            items.append(
                PlanItem(
                    title=self._task_title(task_type, topic.title),
                    description=self._task_description(task_type, topic, keywords),
                    task_type=task_type,
                    difficulty=max(1, min(5, level)),
                    estimated_minutes=minutes,
                    day_offset=day,
                    topic_index=briefs.index(topic),
                    hint=self._task_hint(task_type, topic.title, keywords),
                )
            )

        total = sum(i.estimated_minutes for i in items)
        note = (
            f"Rule-based plan across {len({b.title for b in briefs})} topic(s), "
            f"{total} minutes total, ~{minutes_per_day} min/day."
        )
        return TaskPlan(items=items, source="rules", note=note)

    @staticmethod
    def _task_title(task_type: str, topic: str) -> str:
        topic = topic[:120]
        return {
            "read": f"Read and annotate: {topic}",
            "practice": f"Worked examples: {topic}",
            "quiz": f"Self-test: {topic}",
            "review": f"Spaced review: {topic}",
            "write": f"Write it up: {topic}",
        }[task_type]

    @staticmethod
    def _task_description(task_type: str, topic: TopicBrief, keywords: str) -> str:
        base = topic.summary or f"Key terms: {keywords or topic.title}."
        tail = {
            "read": "Read with a pen: one sentence summary per section, no highlighting.",
            "practice": "Do 3 problems without notes, then check and fix only what you missed.",
            "quiz": "Close the notes. Answer from memory, then mark yourself honestly.",
            "review": "Come back to this in 2 days and recall it before re-reading.",
            "write": "Explain it in 5 sentences as if teaching a classmate.",
        }[task_type]
        return f"{truncate(base, 220)}\n\n{tail}"

    @staticmethod
    def _task_hint(task_type: str, topic: str, keywords: str) -> str:
        if keywords:
            return f"Track these terms: {keywords}. If you can't define one from memory, that's your gap."
        if task_type == "quiz":
            return "Write the questions you expect before you answer them."
        return f"What would you tell a classmate about {topic} in 30 seconds?"
