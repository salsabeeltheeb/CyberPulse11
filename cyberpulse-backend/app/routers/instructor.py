from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..ai_detection import is_flagged
from ..database import get_db
from ..models import LabProgress, Submission, User, utcnow
from ..schemas import InstructorOverview, StudentSummary
from ..security import require_instructor

router = APIRouter(prefix="/api/instructor", tags=["instructor"])

ACTIVE_WINDOW = timedelta(minutes=15)


def _student_rows(db: Session) -> list[User]:
    return db.query(User).filter(User.role == "Student").order_by(User.name).all()


@router.get("/overview", response_model=InstructorOverview)
def overview(_: User = Depends(require_instructor), db: Session = Depends(get_db)):
    students = _student_rows(db)
    subs = db.query(Submission).all()

    cutoff = utcnow().replace(tzinfo=None) - ACTIVE_WINDOW
    active_now = sum(1 for s in students if s.last_active and s.last_active >= cutoff)
    ai_scores = [s.ai_detection_score for s in subs]

    return InstructorOverview(
        total_students=len(students),
        active_now=active_now,
        avg_ai_detection=round(sum(ai_scores) / len(ai_scores), 1) if ai_scores else 0.0,
        integrity_flags=sum(1 for s in ai_scores if is_flagged(s)),
    )


@router.get("/students", response_model=list[StudentSummary])
def students(_: User = Depends(require_instructor), db: Session = Depends(get_db)):
    result: list[StudentSummary] = []

    for student in _student_rows(db):
        subs = db.query(Submission).filter(Submission.student_id == str(student.id)).all()
        labs_completed = (
            db.query(LabProgress)
            .filter(LabProgress.user_id == student.id, LabProgress.status == "Completed")
            .count()
        )

        percentages = [(s.score / s.total_points) * 100 for s in subs if s.total_points > 0]
        ai_scores = [s.ai_detection_score for s in subs]
        avg_ai = round(sum(ai_scores) / len(ai_scores), 1) if ai_scores else 0.0

        result.append(
            StudentSummary(
                id=student.id,
                name=student.name,
                email=student.email,
                github_connected=student.github_connected,
                github_username=student.github_username,
                labs_completed=labs_completed,
                quizzes_taken=len(subs),
                avg_quiz_score=round(sum(percentages) / len(percentages), 1) if percentages else 0.0,
                avg_ai_detection=avg_ai,
                flagged=any(is_flagged(s) for s in ai_scores),
                last_active=student.last_active,
            )
        )

    return result
