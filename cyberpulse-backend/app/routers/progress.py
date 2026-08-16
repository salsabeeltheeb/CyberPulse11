from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LabProgress, Submission, User, utcnow
from ..schemas import DashboardStats, ProgressIn, ProgressOut
from ..security import get_current_user

router = APIRouter(tags=["progress"])


def _out(row: LabProgress) -> ProgressOut:
    return ProgressOut(
        lab_id=row.lab_id,
        status=row.status,
        answered_task_ids=row.answered_task_ids or [],
        earned_points=row.earned_points,
        completed_at=row.completed_at,
    )


@router.get("/api/progress", response_model=list[ProgressOut])
def list_progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(LabProgress).filter(LabProgress.user_id == user.id).all()
    return [_out(r) for r in rows]


@router.put("/api/progress/{lab_id}", response_model=ProgressOut)
def upsert_progress(
    lab_id: str,
    payload: ProgressIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(LabProgress)
        .filter(LabProgress.user_id == user.id, LabProgress.lab_id == lab_id)
        .first()
    )
    if row is None:
        row = LabProgress(user_id=user.id, lab_id=lab_id)
        db.add(row)

    row.status = payload.status
    row.answered_task_ids = payload.answered_task_ids
    row.earned_points = payload.earned_points
    row.completed_at = payload.completed_at or (utcnow() if payload.status == "Completed" else None)

    db.commit()
    db.refresh(row)
    return _out(row)


@router.get("/api/dashboard", response_model=DashboardStats)
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(LabProgress).filter(LabProgress.user_id == user.id).all()
    subs = db.query(Submission).filter(Submission.student_id == str(user.id)).all()

    percentages = [
        (s.score / s.total_points) * 100 for s in subs if s.total_points > 0
    ]

    return DashboardStats(
        labs_completed=sum(1 for r in rows if r.status == "Completed"),
        labs_in_progress=sum(1 for r in rows if r.status == "In Progress"),
        total_points=sum(r.earned_points for r in rows) + sum(s.score for s in subs),
        quizzes_taken=len(subs),
        average_quiz_score=round(sum(percentages) / len(percentages), 1) if percentages else 0.0,
    )
