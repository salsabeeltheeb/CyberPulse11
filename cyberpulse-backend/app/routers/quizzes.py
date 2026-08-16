import uuid
from statistics import median

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..ai_detection import compute_ai_detection_score
from ..database import get_db
from ..models import Quiz, Submission, User, utcnow
from ..schemas import QuizIn, QuizOut, SubmissionOut, SubmitRequest
from ..security import get_current_user

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


def _quiz_out(quiz: Quiz) -> QuizOut:
    return QuizOut(
        id=quiz.id,
        title=quiz.title,
        description=quiz.description,
        created_by=quiz.created_by,
        created_at=quiz.created_at,
        published=quiz.published,
        time_limit=quiz.time_limit,
        questions=quiz.questions or [],
    )


def _submission_out(sub: Submission, student: User | None = None) -> SubmissionOut:
    student = student or sub.student
    return SubmissionOut(
        id=sub.id,
        quiz_id=sub.quiz_id,
        student_id=sub.student_id,
        student_name=student.name if student else None,
        student_email=student.email if student else None,
        answers=sub.answers or [],
        submitted_at=sub.submitted_at,
        score=sub.score,
        total_points=sub.total_points,
        time_spent_seconds=sub.time_spent_seconds,
        ai_detection_score=sub.ai_detection_score,
    )


@router.get("", response_model=list[QuizOut])
def list_quizzes(
    published_only: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Quiz)
    # Students only ever see published quizzes, whatever the flag says.
    if published_only or user.role != "Instructor":
        query = query.filter(Quiz.published.is_(True))
    quizzes = query.order_by(Quiz.created_at.desc()).all()
    return [_quiz_out(q) for q in quizzes]


@router.get("/{quiz_id}", response_model=QuizOut)
def get_quiz(quiz_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None or (not quiz.published and user.role != "Instructor"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    return _quiz_out(quiz)


@router.post("", response_model=QuizOut, status_code=status.HTTP_200_OK)
def save_quiz(payload: QuizIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create or update a quiz (upsert by id). Instructors only."""
    if user.role != "Instructor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only instructors can manage quizzes")

    quiz = db.get(Quiz, payload.id)
    if quiz is None:
        quiz = Quiz(id=payload.id, created_by=str(user.id), author_id=user.id, created_at=utcnow())
        db.add(quiz)
    elif quiz.author_id not in (None, user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only edit your own quizzes")

    quiz.title = payload.title
    quiz.description = payload.description
    quiz.published = payload.published
    quiz.time_limit = payload.time_limit
    quiz.questions = [q.model_dump() for q in payload.questions]

    db.commit()
    db.refresh(quiz)
    return _quiz_out(quiz)


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quiz(quiz_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "Instructor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only instructors can delete quizzes")
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    if quiz.author_id not in (None, user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own quizzes")
    db.delete(quiz)
    db.commit()


@router.post("/{quiz_id}/submit", response_model=SubmissionOut)
def submit_quiz(
    quiz_id: str,
    payload: SubmitRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None or not quiz.published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")

    existing = (
        db.query(Submission)
        .filter(Submission.quiz_id == quiz_id, Submission.student_id == str(user.id))
        .first()
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already submitted this quiz")

    questions = quiz.questions or []
    total_points = sum(int(q.get("points", 1)) for q in questions)
    score = 0
    for index, question in enumerate(questions):
        answer = payload.answers[index] if index < len(payload.answers) else None
        if answer is not None and answer == question.get("correctAnswer"):
            score += int(question.get("points", 1))

    peer_times = [
        s.time_spent_seconds
        for s in db.query(Submission).filter(Submission.quiz_id == quiz_id).all()
        if s.time_spent_seconds > 0
    ]
    cohort_median = median(peer_times) if peer_times else None

    ai_score = compute_ai_detection_score(
        total_questions=len(questions),
        time_spent_seconds=payload.time_spent_seconds,
        question_times=payload.question_times,
        score=score,
        total_points=total_points,
        cohort_median_time=cohort_median,
    )

    submission = Submission(
        id=str(uuid.uuid4()),
        quiz_id=quiz_id,
        student_id=str(user.id),
        student_db_id=user.id,
        answers=payload.answers,
        submitted_at=utcnow(),
        score=score,
        total_points=total_points,
        time_spent_seconds=payload.time_spent_seconds,
        ai_detection_score=ai_score,
        question_times=payload.question_times,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return _submission_out(submission, user)


@router.get("/{quiz_id}/submissions", response_model=list[SubmissionOut])
def submissions_for_quiz(
    quiz_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "Instructor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Instructor role required")
    subs = (
        db.query(Submission)
        .filter(Submission.quiz_id == quiz_id)
        .order_by(Submission.submitted_at.desc())
        .all()
    )
    return [_submission_out(s) for s in subs]


@router.get("/{quiz_id}/my-submission", response_model=SubmissionOut | None)
def my_submission(quiz_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = (
        db.query(Submission)
        .filter(Submission.quiz_id == quiz_id, Submission.student_id == str(user.id))
        .first()
    )
    return _submission_out(sub, user) if sub else None
