from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["Student", "Instructor"]


# ── Auth ──────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: Role = "Student"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: Role
    university: str | None = None
    study_plan: str | None = None
    major: str | None = None
    github_connected: bool = False
    github_username: str | None = None
    onboarding_completed: bool = False
    picture: str | None = None
    provider: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    role: Role | None = None
    university: str | None = None
    study_plan: str | None = None
    major: str | None = None
    onboarding_completed: bool | None = None
    picture: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── Quizzes ───────────────────────────────────────────────────────────────
class QuizQuestion(BaseModel):
    id: str
    text: str
    type: Literal["mcq", "truefalse"]
    options: list[str] = []
    correctAnswer: int = 0
    points: int = 1


class QuizIn(BaseModel):
    id: str
    title: str
    description: str | None = None
    published: bool = False
    time_limit: int | None = None
    questions: list[QuizQuestion] = []


class QuizOut(BaseModel):
    id: str
    title: str
    description: str | None
    created_by: str
    created_at: datetime
    published: bool
    time_limit: int | None
    questions: list[QuizQuestion]


class SubmitRequest(BaseModel):
    answers: list[int | None] = []
    time_spent_seconds: int = 0
    question_times: list[int] = []


class SubmissionOut(BaseModel):
    id: str
    quiz_id: str
    student_id: str
    student_name: str | None = None
    student_email: str | None = None
    answers: list[int | None]
    submitted_at: datetime
    score: int
    total_points: int
    time_spent_seconds: int
    ai_detection_score: float


# ── Progress / dashboard ──────────────────────────────────────────────────
class ProgressIn(BaseModel):
    status: Literal["Not Started", "In Progress", "Completed"] = "In Progress"
    answered_task_ids: list[str] = []
    earned_points: int = 0
    completed_at: datetime | None = None


class ProgressOut(BaseModel):
    lab_id: str
    status: str
    answered_task_ids: list[str]
    earned_points: int
    completed_at: datetime | None


class DashboardStats(BaseModel):
    labs_completed: int
    labs_in_progress: int
    total_points: int
    quizzes_taken: int
    average_quiz_score: float


# ── Mentor ────────────────────────────────────────────────────────────────
class MentorRequest(BaseModel):
    question: str
    hintsUsed: int = 0


# ── Instructor analytics ──────────────────────────────────────────────────
class InstructorOverview(BaseModel):
    total_students: int
    active_now: int
    avg_ai_detection: float
    integrity_flags: int


class StudentSummary(BaseModel):
    id: int
    name: str
    email: str
    github_connected: bool
    github_username: str | None
    labs_completed: int
    quizzes_taken: int
    avg_quiz_score: float
    avg_ai_detection: float
    flagged: bool
    last_active: datetime | None
