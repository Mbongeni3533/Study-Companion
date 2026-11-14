"""Pydantic request/response schemas (the public API contract)."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

TaskType = Literal["read", "practice", "quiz", "review", "write"]
TaskStatus = Literal["todo", "in_progress", "done"]
DocumentStatus = Literal["pending", "processing", "ready", "failed"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth/users
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="Student", max_length=120)
    university: str | None = Field(default=None, max_length=200)
    daily_study_minutes: int | None = Field(default=None, ge=15, le=480)
    invite_code: str | None = Field(default=None, max_length=120)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AnonymousSessionCreate(BaseModel):
    name: str = Field(default="Guest student", max_length=120)
    university: str | None = Field(default=None, max_length=200)
    daily_study_minutes: int | None = Field(default=None, ge=15, le=480)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    university: str | None = Field(default=None, max_length=200)
    profession: str | None = Field(default=None, max_length=120)
    daily_study_minutes: int | None = Field(default=None, ge=15, le=480)


class UserResponse(ORMModel):
    id: str
    email: str | None
    name: str
    university: str | None
    profession: str | None = None
    thinking_level: str | None = None
    thinking_scores: dict[str, Any] | None = None
    assessment_completed_at: datetime | None = None
    is_anonymous: bool

    @field_validator("thinking_scores", mode="before")
    @classmethod
    def _parse_scores(cls, value: Any) -> Any:
        if value is None or isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value) if value.strip() else None
            except json.JSONDecodeError:
                return None
        return value
    subscription_tier: str
    daily_study_minutes: int
    created_at: datetime


class AssessmentQuestion(BaseModel):
    id: str
    kind: str
    dimension: str
    prompt: str
    options: list[dict]


class AssessmentOverview(BaseModel):
    intro: dict
    questions: list[AssessmentQuestion]
    profile: dict | None = None


class AssessmentSubmit(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


class AssessmentResult(BaseModel):
    profile: dict
    user: UserResponse


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class AccessPolicy(BaseModel):
    beta_invite_only: bool
    allow_anonymous_sessions: bool
    registration_doc_url: str | None = None


class InviteCodeCreate(BaseModel):
    code: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    max_uses: int = Field(default=1, ge=1, le=1000)
    expires_at: datetime | None = None
    send_email: bool = False


class InviteCodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    email_sent: bool | None = None
    email: str | None = None
    max_uses: int
    uses: int
    revoked: bool
    expires_at: datetime | None = None
    created_at: datetime


# ------------------------------------------------------------------- courses
class FeedbackCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    rating: int | None = Field(default=None, ge=1, le=5)
    category: str = Field(default="general", max_length=60)
    course_id: str | None = None
    page: str | None = Field(default=None, max_length=200)


class FeedbackResponse(ORMModel):
    id: int
    user_id: str | None = None
    user_email: str | None = None
    user_name: str | None = None
    course_id: str | None = None
    rating: int | None = None
    category: str
    message: str
    page: str | None = None
    created_at: datetime


class CourseCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    code: str | None = Field(default=None, max_length=60)
    subject: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    exam_date: date | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("title must be at least 2 characters")
        return cleaned


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    code: str | None = Field(default=None, max_length=60)
    subject: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    exam_date: date | None = None


class CourseResponse(ORMModel):
    id: str
    title: str
    code: str | None
    subject: str | None
    description: str | None
    exam_date: date | None
    created_at: datetime

    document_count: int = 0
    topic_count: int = 0
    task_count: int = 0
    completed_task_count: int = 0
    minutes_studied: int = 0
    days_until_exam: int | None = None
    readiness_score: int = 0


# ----------------------------------------------------------------- documents
class DocumentResponse(ORMModel):
    id: str
    course_id: str
    filename: str
    content_type: str | None
    size_bytes: int
    status: str
    error_message: str | None
    word_count: int
    page_count: int
    extraction_warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    processed_at: datetime | None
    progress_stage: str | None = None
    progress_current: int = 0
    progress_total: int = 0

    @field_validator("extraction_warnings", mode="before")
    @classmethod
    def _default_warnings(cls, value):
        return value or []


class DocumentUploadResult(BaseModel):
    document: DocumentResponse
    topics_created: int = 0
    chunks_created: int = 0
    message: str


class TextPasteCreate(BaseModel):
    """Ingest typed notes without a file upload."""

    text: str = Field(min_length=40, max_length=400_000)
    filename: str = Field(default="Pasted notes.txt", max_length=200)


class ChunkResponse(ORMModel):
    id: int
    document_id: str
    position: int
    text: str
    word_count: int
    heading: str | None
    topic_id: str | None


# -------------------------------------------------------------------- topics
class TopicResponse(ORMModel):
    id: str
    course_id: str
    title: str
    summary: str | None
    keywords: list[str] = Field(default_factory=list)
    difficulty: int
    weight: float
    order_index: int
    chunk_count: int = 0
    confidence: int = 0
    task_count: int = 0
    completed_task_count: int = 0

    @field_validator("keywords", mode="before")
    @classmethod
    def _default_keywords(cls, value):
        return value or []


# --------------------------------------------------------------------- tasks
class TaskResponse(ORMModel):
    id: str
    course_id: str
    topic_id: str | None
    title: str
    description: str | None
    task_type: str
    difficulty: int
    estimated_minutes: int
    due_date: date | None
    status: str
    hint: str | None
    created_at: datetime
    completed_at: datetime | None
    topic_title: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    status: TaskStatus | None = None
    due_date: date | None = None
    estimated_minutes: int | None = Field(default=None, ge=5, le=240)
    difficulty: int | None = Field(default=None, ge=1, le=5)


class TaskGenerateRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=20)
    focus: str | None = Field(default=None, max_length=300)
    minutes_per_day: int | None = Field(default=None, ge=10, le=480)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    replace_existing: bool = False


class TaskGenerateResult(BaseModel):
    tasks: list[TaskResponse]
    source: Literal["ai", "rules"]
    plan_note: str


# ---------------------------------------------------------------------- chat
class ChatSessionCreate(BaseModel):
    topic_id: str | None = None
    title: str | None = Field(default=None, max_length=200)


class MessageResponse(ORMModel):
    id: int
    role: str
    content: str
    hint_level: int
    created_at: datetime


class ChatSessionResponse(ORMModel):
    id: str
    course_id: str
    topic_id: str | None
    title: str
    created_at: datetime
    message_count: int = 0
    preview: str | None = None


class ChatSessionDetail(ChatSessionResponse):
    messages: list[MessageResponse] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    hint_level: int = Field(default=1, ge=1, le=3)


class ChatReply(BaseModel):
    reply: MessageResponse
    user_message: MessageResponse
    source: Literal["ai", "rules"]
    hint_level: int
    citations: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------ progress
class StudyLogCreate(BaseModel):
    course_id: str | None = None
    task_id: str | None = None
    minutes: int = Field(ge=1, le=600)
    focus: str = Field(default="study", max_length=60)
    note: str | None = Field(default=None, max_length=500)


class StudyLogResponse(ORMModel):
    id: int
    course_id: str | None
    task_id: str | None
    minutes: int
    focus: str
    note: str | None
    created_at: datetime


class CourseProgress(BaseModel):
    course_id: str
    course_title: str
    total_tasks: int
    completed_tasks: int
    minutes_studied: int
    streak_days: int
    readiness_score: int
    topics: list[TopicResponse] = Field(default_factory=list)


class ProgressSummary(BaseModel):
    minutes_today: int
    minutes_this_week: int
    minutes_total: int
    tasks_completed: int
    tasks_open: int
    streak_days: int
    daily_goal_minutes: int
    courses: list[CourseProgress] = Field(default_factory=list)
    recent_logs: list[StudyLogResponse] = Field(default_factory=list)


class SearchHit(BaseModel):
    chunk_id: int
    document_id: str
    document_name: str
    heading: str | None
    text: str
    score: float


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    ai_provider: str
    database: str


# ------------------------------------------------------------------- admin agents
class ExecutiveReportResponse(BaseModel):
    generated_at: datetime
    report: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    ai_used: bool = False


class DiagnosticFinding(BaseModel):
    severity: Literal["info", "warning", "error"]
    area: str
    message: str
    suggested_action: str | None = None


class DiagnosticsResponse(BaseModel):
    generated_at: datetime
    findings: list[DiagnosticFinding] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    ai_used: bool = False


class RemediationAction(BaseModel):
    action: str
    affected: int = 0
    detail: str | None = None


class RemediationResponse(BaseModel):
    generated_at: datetime
    actions: list[RemediationAction] = Field(default_factory=list)
    remaining_issues: list[str] = Field(default_factory=list)


class ComplianceResponse(BaseModel):
    generated_at: datetime
    jurisdiction: str
    report: str
    checklist: list[str] = Field(default_factory=list)
    ai_used: bool = False


class AIResearchResponse(BaseModel):
    generated_at: datetime
    focus: str
    briefing: str
    key_developments: list[str] = Field(default_factory=list)
    ai_used: bool = False


# ------------------------------------------------------------------- toolbox
class ExperienceItem(BaseModel):
    role: str = Field(default="", max_length=160)
    organisation: str = Field(default="", max_length=160)
    period: str = Field(default="", max_length=80)
    highlights: list[str] = Field(default_factory=list)

    @field_validator("highlights", mode="before")
    @classmethod
    def _clean_highlights(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = value.splitlines()
        return [str(line).strip(" -•\t") for line in value if str(line).strip(" -•\t")][:8]


class CVRequest(BaseModel):
    """Everything the CV agent needs. Only ``profession`` is required."""

    profession: str = Field(min_length=2, max_length=120)
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=60)
    location: str | None = Field(default=None, max_length=120)
    target_role: str | None = Field(default=None, max_length=160)
    years_experience: int | None = Field(default=None, ge=0, le=60)
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    job_description: str | None = Field(default=None, max_length=8000)

    @field_validator("skills", mode="before")
    @classmethod
    def _clean_skills(cls, value):
        if not value:
            return []
        if isinstance(value, str):
            value = value.split(",")
        return [str(item).strip() for item in value if str(item).strip()][:24]

    @field_validator("education", "certifications", "achievements", mode="before")
    @classmethod
    def _clean_lines(cls, value):
        if not value:
            return []
        if isinstance(value, str):
            value = value.splitlines()
        return [str(line).strip(" -•\t") for line in value if str(line).strip(" -•\t")][:10]


class CVResult(BaseModel):
    document: str
    source: Literal["ai", "rules"]
    profession: str
    profession_label: str
    suggestions: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)


class CVPDFRequest(BaseModel):
    """The Markdown already shown to the student, so the PDF matches it exactly."""

    document: str = Field(min_length=10, max_length=60000)
    full_name: str | None = Field(default=None, max_length=120)


class CVImportFields(BaseModel):
    """Fields found in an uploaded CV. Anything uncertain is left empty."""

    profession: str | None = Field(default=None, max_length=120)
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=60)
    location: str | None = Field(default=None, max_length=120)
    target_role: str | None = Field(default=None, max_length=160)
    years_experience: int | None = Field(default=None, ge=0, le=60)
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)

    @field_validator("skills", mode="before")
    @classmethod
    def _clean_skills(cls, value):
        if not value:
            return []
        if isinstance(value, str):
            value = value.split(",")
        return [str(item).strip() for item in value if str(item).strip()][:24]

    @field_validator("education", "certifications", "achievements", mode="before")
    @classmethod
    def _clean_lines(cls, value):
        if not value:
            return []
        if isinstance(value, str):
            value = value.splitlines()
        return [str(line).strip(" -•\t") for line in value if str(line).strip(" -•\t")][:10]


class CVImportResult(BaseModel):
    filename: str
    text: str
    fields: CVImportFields
    warnings: list[str] = Field(default_factory=list)


class LetterRequest(BaseModel):
    kind: Literal["cover_letter", "email"] = "cover_letter"
    profession: str = Field(min_length=2, max_length=120)
    role: str = Field(min_length=2, max_length=160)
    company: str = Field(default="", max_length=160)
    recipient: str | None = Field(default=None, max_length=160)
    tone: Literal["professional", "warm", "direct", "academic"] = "professional"
    highlights: list[str] = Field(default_factory=list)
    job_description: str | None = Field(default=None, max_length=8000)
    your_name: str | None = Field(default=None, max_length=120)

    @field_validator("highlights", mode="before")
    @classmethod
    def _clean_highlights(cls, value):
        if not value:
            return []
        if isinstance(value, str):
            value = value.splitlines()
        return [str(line).strip(" -•\t") for line in value if str(line).strip(" -•\t")][:8]


class LetterResult(BaseModel):
    subject: str | None
    body: str
    source: Literal["ai", "rules"]
    tips: list[str] = Field(default_factory=list)


class HumanizeRequest(BaseModel):
    text: str = Field(min_length=20, max_length=20000)
    tone: Literal["professional", "warm", "direct", "academic"] = "professional"


class TextChange(BaseModel):
    before: str
    after: str
    reason: str


class TextMetrics(BaseModel):
    words: int
    sentences: int
    average_sentence_words: float
    long_sentences: int
    reading_ease: float
    cliches: int
    contractions: int


class HumanizeResult(BaseModel):
    text: str
    changes: list[TextChange] = Field(default_factory=list)
    before: TextMetrics
    after: TextMetrics
    source: Literal["ai", "rules"]
    notes: list[str] = Field(default_factory=list)


class IntegrityRequest(BaseModel):
    text: str = Field(min_length=40, max_length=40000)
    course_id: str | None = None


class IntegrityMatch(BaseModel):
    sentence: str
    source: str
    similarity: int


class IntegrityFlag(BaseModel):
    kind: str
    label: str
    detail: str


class IntegrityResult(BaseModel):
    similarity_score: int
    originality_score: int
    verdict: str
    level: Literal["low", "medium", "high"]
    matches: list[IntegrityMatch] = Field(default_factory=list)
    flags: list[IntegrityFlag] = Field(default_factory=list)
    sources_checked: int
    passages_checked: int
    scope: str


class CounsellorResponse(BaseModel):
    id: str
    name: str
    title: str
    specialties: list[str]
    languages: list[str]
    bio: str
    next_slot: str | None = None


class CounsellingSlot(BaseModel):
    date: date
    time: str
    label: str
    counsellor_id: str


class CounsellingSessionResponse(ORMModel):
    id: str
    counsellor_id: str
    counsellor_name: str = ""
    focus: str
    scheduled_for: datetime
    duration_minutes: int
    notes: str | None
    status: str
    created_at: datetime


class CounsellingBookingRequest(BaseModel):
    counsellor_id: str = Field(min_length=2, max_length=64)
    focus: str = Field(min_length=2, max_length=120)
    date: date
    time: str = Field(min_length=4, max_length=8)
    notes: str | None = Field(default=None, max_length=1000)


class CounsellingOverview(BaseModel):
    counsellors: list[CounsellorResponse] = Field(default_factory=list)
    sessions: list[CounsellingSessionResponse] = Field(default_factory=list)
    slots: list[CounsellingSlot] = Field(default_factory=list)
    focus_options: list[str] = Field(default_factory=list)


class DictionaryDefinition(BaseModel):
    part_of_speech: str | None = None
    definition: str
    example: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    antonyms: list[str] = Field(default_factory=list)


class DictionaryResponse(BaseModel):
    word: str
    phonetic: str | None = None
    entries: list[DictionaryDefinition] = Field(default_factory=list)
    source: str = "dictionaryapi.dev"


class ToolboxMeta(BaseModel):
    agents: list[dict]
    tones: list[dict]
    professions: list[dict]
    counselling_focus: list[str]
    counsellors: list[CounsellorResponse]
    ai_available: bool
